"""
voice_synthesizer_v2.py — Multi-speaker dialogue voice synthesis for RAGAI v9.0.

Drop-in replacement for voice_synthesizer.py with character-aware voice assignment:
  - Parses "CharacterName: dialogue" patterns in scene narration
  - Assigns unique Edge-TTS voices per character (gender-aware)
  - Narrator lines use the default language voice
  - Voice assignments persisted to characters.json for consistency
  - Falls back to gTTS if Edge-TTS is unavailable
  - Single audio file output per scene (FFmpeg concat)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models import Language, Scene, VoiceSynthesisError
from voice_synthesizer import VoiceSynthesizer, VOICE_MAP, GTTS_LANG_MAP, _probe_edge_tts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gender-aware voice pools (Edge-TTS)
# ---------------------------------------------------------------------------

_MALE_VOICES = [
    "hi-IN-MadhurNeural",
    "en-IN-PrabhatNeural",
    "en-US-GuyNeural",
    "hi-IN-MadhurNeural",
    "te-IN-MohanNeural",
    "ta-IN-ValluvarNeural",
    "bn-IN-BashkarNeural",
    "mr-IN-ManoharNeural",
    "kn-IN-GaganNeural",
    "ml-IN-MidhunNeural",
]

_FEMALE_VOICES = [
    "hi-IN-SwaraNeural",
    "en-IN-NeerjaNeural",
    "en-US-JennyNeural",
    "ta-IN-PallaviNeural",
    "te-IN-ShrutiNeural",
    "bn-IN-TanishaaNeural",
    "gu-IN-DhwaniNeural",
    "mr-IN-AarohiNeural",
    "kn-IN-SapnaNeural",
    "ml-IN-SobhanaNeural",
]

# Indian names gender heuristics (common suffixes/names)
_FEMALE_SUFFIXES = ("a", "i", "ee", "ita", "ika", "ini", "iya", "devi", "bai",
                    "kumari", "lata", "priya", "maya", "radha", "sita", "gita",
                    "anita", "sunita", "kavita", "geeta", "neeta", "reeta",
                    "pooja", "puja", "asha", "usha", "rekha", "seema", "meena",
                    "leela", "sheela", "kamla", "vimla", "nirmala", "shanta",
                    "gauri", "durga", "lakshmi", "saraswati", "parvati")

_MALE_SUFFIXES = ("raj", "ram", "kumar", "singh", "dev", "esh", "ish", "ant",
                  "endra", "inder", "deep", "jeet", "veer", "bir", "nath",
                  "arjun", "rajan", "mohan", "sohan", "rohan", "vikas",
                  "suresh", "mahesh", "ramesh", "dinesh", "ganesh", "naresh",
                  "rakesh", "mukesh", "lokesh", "yogesh", "umesh", "hitesh",
                  "ritesh", "nitesh", "jitesh", "mitesh", "satish", "manish",
                  "ashish", "rajesh", "suresh", "naresh", "ramesh", "dinesh")

_NARRATOR_KEYWORDS = {"narrator", "narration", "voice", "आवाज़", "वर्णनकर्ता"}


def _detect_gender(name: str) -> str:
    """Return 'male' or 'female' based on name heuristics."""
    lower = name.lower().strip()
    for suffix in _FEMALE_SUFFIXES:
        if lower.endswith(suffix) or lower == suffix:
            return "female"
    for suffix in _MALE_SUFFIXES:
        if lower.endswith(suffix) or lower == suffix:
            return "male"
    # Default: alternate based on hash for consistency
    return "female" if sum(ord(c) for c in lower) % 2 == 0 else "male"


# ---------------------------------------------------------------------------
# Voice registry
# ---------------------------------------------------------------------------

_CHARACTERS_JSON = Path("characters.json")


def _load_voice_registry() -> Dict[str, str]:
    """Load existing character→voice assignments from characters.json."""
    if _CHARACTERS_JSON.exists():
        try:
            data = json.loads(_CHARACTERS_JSON.read_text(encoding="utf-8"))
            if isinstance(data, list):
                # Convert list format to dict
                return {item["id"]: item.get("voice", "") for item in data if "id" in item and "voice" in item}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_voice_registry(registry: Dict[str, str]) -> None:
    """Merge voice assignments back into characters.json."""
    existing = []
    if _CHARACTERS_JSON.exists():
        try:
            existing = json.loads(_CHARACTERS_JSON.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    # Update or append voice field
    ids_in_file = {item.get("id") for item in existing if isinstance(item, dict)}
    for char_id, voice in registry.items():
        found = False
        for item in existing:
            if isinstance(item, dict) and item.get("id") == char_id:
                item["voice"] = voice
                found = True
                break
        if not found:
            existing.append({"id": char_id, "voice": voice})

    _CHARACTERS_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


class MultiSpeakerVoiceSynthesizer:
    """Multi-speaker voice synthesizer with character-aware voice assignment."""

    # Pattern: "CharacterName: dialogue text"
    _DIALOGUE_RE = re.compile(
        r'^([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F ]{0,30})\s*:\s*(.+)',
        re.MULTILINE,
    )

    def __init__(self, use_edge_tts: bool, work_dir: Path,
                 known_characters: Optional[List[str]] = None) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.known_characters = [c.lower() for c in (known_characters or [])]

        if use_edge_tts and not _probe_edge_tts():
            logger.warning("Edge-TTS unreachable — using gTTS fallback")
            self.use_edge_tts = False
        else:
            self.use_edge_tts = use_edge_tts

        # Load existing voice assignments
        self._registry: Dict[str, str] = _load_voice_registry()
        self._male_idx = 0
        self._female_idx = 0

    def _assign_voice(self, character: str, language: Language) -> str:
        """Return Edge-TTS voice for a character, assigning one if not yet known."""
        key = character.lower().strip()

        # Narrator always uses default language voice
        if key in _NARRATOR_KEYWORDS:
            return VOICE_MAP.get(language, "hi-IN-SwaraNeural")

        if key in self._registry:
            return self._registry[key]

        # Assign new voice based on gender
        gender = _detect_gender(character)
        if gender == "male":
            voice = _MALE_VOICES[self._male_idx % len(_MALE_VOICES)]
            self._male_idx += 1
        else:
            voice = _FEMALE_VOICES[self._female_idx % len(_FEMALE_VOICES)]
            self._female_idx += 1

        self._registry[key] = voice
        logger.info("Voice assigned: %s → %s (%s)", character, voice, gender)
        return voice

    def _parse_segments(self, text: str, language: Language) -> List[Tuple[str, str]]:
        """Parse text into (voice, segment_text) tuples.

        Lines matching "Name: text" get character voice.
        All other lines get narrator voice.
        """
        narrator_voice = VOICE_MAP.get(language, "hi-IN-SwaraNeural")
        segments: List[Tuple[str, str]] = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = self._DIALOGUE_RE.match(line)
            if m:
                char_name = m.group(1).strip()
                dialogue = m.group(2).strip()
                voice = self._assign_voice(char_name, language)
                segments.append((voice, dialogue))
            else:
                segments.append((narrator_voice, line))

        if not segments:
            segments = [(narrator_voice, text.strip())]

        return segments

    async def _synthesize_segment_edge(self, voice: str, text: str, out_path: Path) -> None:
        """Synthesize one segment with Edge-TTS."""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

    def _synthesize_segment_gtts(self, lang_code: str, text: str, out_path: Path) -> None:
        """Synthesize one segment with gTTS."""
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang_code, slow=False)
        tts.save(str(out_path))

    def _concat_segments(self, segment_paths: List[Path], output_path: Path) -> None:
        """Concatenate audio segments into a single file via FFmpeg."""
        if len(segment_paths) == 1:
            shutil.copy2(str(segment_paths[0]), str(output_path))
            return

        # Write concat list
        list_file = output_path.parent / f"{output_path.stem}_concat.txt"
        list_file.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in segment_paths),
            encoding="utf-8",
        )
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(output_path)],
            capture_output=True, text=True,
        )
        list_file.unlink(missing_ok=True)
        if result.returncode != 0:
            raise VoiceSynthesisError(f"FFmpeg concat failed: {result.stderr[-300:]}")

    def synthesize_one(self, scene: Scene, language: Language) -> Path:
        """Synthesize multi-speaker audio for one scene. Returns audio path."""
        output_path = self.work_dir / f"scene_{scene.number:03d}.mp3"
        segments = self._parse_segments(scene.narration, language)
        segment_paths: List[Path] = []

        for idx, (voice, text) in enumerate(segments):
            seg_path = self.work_dir / f"scene_{scene.number:03d}_seg{idx:02d}.mp3"
            try:
                if self.use_edge_tts:
                    asyncio.run(self._synthesize_segment_edge(voice, text, seg_path))
                else:
                    lang_code = GTTS_LANG_MAP.get(language, "hi")
                    self._synthesize_segment_gtts(lang_code, text, seg_path)
                segment_paths.append(seg_path)
            except Exception as exc:
                logger.warning("Segment %d synthesis failed (%s): %s — skipping", idx, voice, exc)

        if not segment_paths:
            raise VoiceSynthesisError(f"All segments failed for scene {scene.number}")

        self._concat_segments(segment_paths, output_path)

        # Clean up segment files
        for p in segment_paths:
            p.unlink(missing_ok=True)

        # Persist voice assignments
        _save_voice_registry(self._registry)

        logger.info("Multi-speaker audio: scene %d, %d segments → %s",
                    scene.number, len(segments), output_path)
        return output_path


# ---------------------------------------------------------------------------
# Drop-in function signature (matches pipeline.py call)
# ---------------------------------------------------------------------------

def synthesize_voice(
    scene_text: str,
    language: Language,
    output_path: Path,
    known_characters: Optional[List[str]] = None,
    use_edge_tts: bool = True,
    tmp_dir: Optional[Path] = None,
) -> Path:
    """Drop-in replacement for voice_synthesizer.synthesize_voice."""
    work_dir = tmp_dir or Path("tmp") / "voice_v2"
    synth = MultiSpeakerVoiceSynthesizer(
        use_edge_tts=use_edge_tts,
        work_dir=work_dir,
        known_characters=known_characters,
    )
    # Create a minimal Scene-like object
    from models import Scene as SceneModel
    scene = SceneModel(number=1, narration=scene_text, image_prompt="", duration_seconds=6.0)
    result = synth.synthesize_one(scene, language)
    shutil.copy2(str(result), str(output_path))
    return output_path
