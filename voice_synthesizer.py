"""
voice_synthesizer.py — Edge-TTS and gTTS voice synthesis for RAGAI Video Factory.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket
from pathlib import Path
from typing import Dict, List, Optional

from models import Language, Scene, VoiceSynthesisError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Edge-TTS connectivity probe
# ---------------------------------------------------------------------------

# Edge-TTS connects to this host for synthesis
_EDGE_TTS_HOST = "speech.platform.bing.com"
_EDGE_TTS_PORT = 443
_PROBE_TIMEOUT = 5.0

_edge_tts_reachable: Optional[bool] = None  # cached after first probe


def _probe_edge_tts() -> bool:
    """Return True if the Edge-TTS endpoint is reachable on this network.

    Some WiFi routers / ISPs block speech.platform.bing.com. This probe
    detects that at startup so RAGAI can auto-switch to gTTS instead of
    failing mid-generation.
    """
    global _edge_tts_reachable
    if _edge_tts_reachable is not None:
        return _edge_tts_reachable
    try:
        with socket.create_connection((_EDGE_TTS_HOST, _EDGE_TTS_PORT), timeout=_PROBE_TIMEOUT):
            _edge_tts_reachable = True
            logger.info("Edge-TTS connectivity: OK (%s:%d reachable)", _EDGE_TTS_HOST, _EDGE_TTS_PORT)
    except OSError:
        _edge_tts_reachable = False
        logger.warning(
            "Edge-TTS connectivity: BLOCKED (%s:%d unreachable) — auto-switching to gTTS. "
            "Use mobile hotspot for natural voice.",
            _EDGE_TTS_HOST, _EDGE_TTS_PORT,
        )
    return _edge_tts_reachable


# ---------------------------------------------------------------------------
# Task 7.1 — VOICE_MAP for all 10 supported languages
# ---------------------------------------------------------------------------

VOICE_MAP: Dict[Language, str] = {
    Language.HI: "hi-IN-SwaraNeural",
    Language.TA: "ta-IN-PallaviNeural",
    Language.TE: "te-IN-ShrutiNeural",
    Language.BN: "bn-IN-TanishaaNeural",
    Language.GU: "gu-IN-DhwaniNeural",
    Language.MR: "mr-IN-AarohiNeural",
    Language.KN: "kn-IN-SapnaNeural",
    Language.ML: "ml-IN-SobhanaNeural",
    Language.PA: "pa-IN-VaaniNeural",
    Language.UR: "ur-PK-UzmaNeural",
}

# gTTS language codes (Language enum value already matches the gtts lang code)
GTTS_LANG_MAP: Dict[Language, str] = {
    Language.HI: "hi",
    Language.TA: "ta",
    Language.TE: "te",
    Language.BN: "bn",
    Language.GU: "gu",
    Language.MR: "mr",
    Language.KN: "kn",
    Language.ML: "ml",
    Language.PA: "pa",
    Language.UR: "ur",
}


# ---------------------------------------------------------------------------
# Task 7.2 + 7.3 — VoiceSynthesizer class
# ---------------------------------------------------------------------------

class VoiceSynthesizer:
    MAX_SEGMENT_CHARS = 500

    def __init__(self, use_edge_tts: bool, work_dir: Path) -> None:
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # If Edge-TTS is requested, probe connectivity first.
        # Auto-switch to gTTS if the endpoint is blocked (common on some WiFi).
        if use_edge_tts and not _probe_edge_tts():
            logger.warning(
                "Edge-TTS requested but endpoint is unreachable — using gTTS fallback. "
                "Switch to mobile hotspot to restore natural voice."
            )
            self.use_edge_tts = False
        else:
            self.use_edge_tts = use_edge_tts

    # ------------------------------------------------------------------
    # Task 7.2 helpers
    # ------------------------------------------------------------------

    def _split_text(self, text: str) -> List[str]:
        """Split text > MAX_SEGMENT_CHARS into segments each <= MAX_SEGMENT_CHARS.

        Splits on sentence boundaries (।.!?). Concatenating all returned
        segments reproduces the original text exactly (round-trip fidelity).
        """
        if len(text) <= self.MAX_SEGMENT_CHARS:
            return [text]

        # Split on sentence-ending punctuation, keeping the delimiter attached
        # to the preceding sentence so round-trip concat works.
        parts = re.split(r'(?<=[।.!?])\s*', text)

        segments: List[str] = []
        current = ""

        for part in parts:
            # If adding this part would exceed the limit, flush current segment
            if current and len(current) + len(part) > self.MAX_SEGMENT_CHARS:
                segments.append(current)
                current = part
            else:
                current += part

        if current:
            segments.append(current)

        # Safety: if any single segment is still too long (no sentence boundary
        # found), hard-split it at MAX_SEGMENT_CHARS.
        final: List[str] = []
        for seg in segments:
            while len(seg) > self.MAX_SEGMENT_CHARS:
                final.append(seg[: self.MAX_SEGMENT_CHARS])
                seg = seg[self.MAX_SEGMENT_CHARS :]
            if seg:
                final.append(seg)

        return final

    def _concat_audio(self, parts: List[Path], dest: Path) -> Path:
        """Concatenate multiple MP3/WAV files into one at dest. Returns dest."""
        if len(parts) == 1:
            import shutil
            shutil.copy2(parts[0], dest)
            return dest

        try:
            from pydub import AudioSegment

            combined = AudioSegment.empty()
            for p in parts:
                combined += AudioSegment.from_file(str(p))
            combined.export(str(dest), format="mp3")
        except ImportError:
            # pydub not available — raw binary concatenation (works for MP3)
            with open(dest, "wb") as out_f:
                for p in parts:
                    out_f.write(p.read_bytes())

        return dest

    def _edge_tts(self, text: str, voice: str, dest: Path) -> Path:
        """Synthesize text using Edge-TTS and save to dest as MP3. Returns dest."""
        import edge_tts  # type: ignore

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(dest))

        try:
            asyncio.run(_run())
        except RuntimeError:
            # Already inside a running event loop (e.g. Jupyter / some GUIs)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(_run())

        return dest

    def _gtts_fallback(self, text: str, lang_code: str, dest: Path) -> Path:
        """Synthesize text using gTTS and save to dest. Returns dest."""
        from gtts import gTTS  # type: ignore

        tts = gTTS(text=text, lang=lang_code)
        tts.save(str(dest))
        return dest

    # ------------------------------------------------------------------
    # Task 7.3 — synthesize_one and synthesize_all
    # ------------------------------------------------------------------

    def synthesize_one(self, scene: Scene, language: Language) -> Path:
        """Synthesize audio for a single scene. Returns path to the MP3 file."""
        text = scene.narration
        dest = self.work_dir / f"scene_{scene.number:03d}_audio.mp3"

        if len(text) > self.MAX_SEGMENT_CHARS:
            segments = self._split_text(text)
            part_paths: List[Path] = []
            for idx, segment in enumerate(segments):
                part_dest = self.work_dir / f"scene_{scene.number:03d}_part{idx:03d}.mp3"
                part_paths.append(self._synthesize_segment(segment, language, part_dest))
            return self._concat_audio(part_paths, dest)

        return self._synthesize_segment(text, language, dest)

    def _synthesize_segment(self, text: str, language: Language, dest: Path) -> Path:
        """Synthesize a single text segment, applying Edge-TTS → gTTS fallback."""
        lang_code = GTTS_LANG_MAP[language]

        if self.use_edge_tts:
            voice = VOICE_MAP[language]
            try:
                return self._edge_tts(text, voice, dest)
            except Exception as exc:
                logger.warning(
                    "Edge-TTS failed for language=%s voice=%s — falling back to gTTS. Error: %s",
                    language.value,
                    voice,
                    exc,
                )
                return self._gtts_fallback(text, lang_code, dest)
        else:
            return self._gtts_fallback(text, lang_code, dest)

    def synthesize_all(self, scenes: List[Scene], language: Language) -> List[Scene]:
        """Synthesize audio for all scenes. Mutates scene.audio_path. Returns scenes."""
        for scene in scenes:
            try:
                scene.audio_path = self.synthesize_one(scene, language)
                logger.info("Synthesized audio for scene %d: %s", scene.number, scene.audio_path)
            except Exception as exc:
                raise VoiceSynthesisError(
                    f"Voice synthesis failed for scene {scene.number}: {exc}"
                ) from exc
        return scenes
