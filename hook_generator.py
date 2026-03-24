"""
hook_generator.py — AI-generated hook intro clip for RAGAI Editor V2.

Generates a short Hindi narration via Groq LLM, synthesises voice via Edge-TTS,
then renders an 8-10 second intro video (black background, gold text, slow zoom,
background music) using FFmpeg.
"""

from __future__ import annotations

import asyncio
import logging
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"

# Hook style variants for variation
_HOOK_STYLES = [
    "dramatic and emotional",
    "curious and mysterious",
    "inspiring and uplifting",
    "warm and storytelling",
]

# Gold text colour for FFmpeg drawtext
_GOLD = "0xFFD700"
_SHADOW = "0x000000@0.8"


def _ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def _check_qsv() -> bool:
    try:
        r = subprocess.run([_ffmpeg_path(), "-encoders"], capture_output=True, text=True, timeout=10)
        return "h264_qsv" in r.stdout
    except Exception:
        return False


class HookGenerator:
    """Generates an 8-10 second hook intro video."""

    def __init__(self, groq_api_key: str, music_dir: Path = Path("music")):
        self._api_key = groq_api_key
        self._music_dir = Path(music_dir)
        self._ffmpeg = _ffmpeg_path()
        self._qsv = _check_qsv()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(
        self,
        compilation_title: str,
        clip_count: int,
        output_path: Path,
        hook_style: Optional[str] = None,
    ) -> Path:
        """
        Full pipeline: LLM narration → TTS audio → FFmpeg video.
        Returns path to hook_clip.mp4.
        """
        style = hook_style or random.choice(_HOOK_STYLES)
        logger.info("Generating hook for '%s' (style: %s)", compilation_title, style)

        narration = self._generate_narration(compilation_title, clip_count, style)
        logger.info("Hook narration: %s", narration)

        with tempfile.TemporaryDirectory(prefix="ragai_hook_") as tmp:
            tmp_path = Path(tmp)
            audio_path = tmp_path / "hook_voice.mp3"
            self._synthesise_voice(narration, audio_path)
            self._render_video(narration, audio_path, output_path)

        logger.info("Hook clip ready: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_narration(self, title: str, count: int, style: str) -> str:
        """Call Groq LLM to generate a short Hindi hook narration."""
        prompt = (
            f"Write a short Hindi hook narration (2-3 sentences, max 40 words) "
            f"for a YouTube compilation video titled '{title}' containing {count} stories. "
            f"Style: {style}. "
            f"The narration should make viewers excited to watch. "
            f"Output ONLY the Hindi narration text, nothing else."
        )
        try:
            resp = requests.post(
                _GROQ_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={"model": _GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 150},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Groq hook generation failed: %s — using fallback", exc)
            return (
                f"आज की इस वीडियो में हम आपको सुनाएंगे {count} ऐसी कहानियाँ "
                f"जो आपकी जिंदगी बदल सकती हैं।"
            )

    def _synthesise_voice(self, text: str, output: Path) -> None:
        """Synthesise Hindi voice using Edge-TTS (async)."""
        try:
            import edge_tts
            async def _run():
                communicate = edge_tts.Communicate(text, voice="hi-IN-SwaraNeural")
                await communicate.save(str(output))
            asyncio.run(_run())
            logger.debug("Hook voice synthesised: %s", output)
        except Exception as exc:
            logger.warning("Edge-TTS failed: %s — using gTTS fallback", exc)
            try:
                from gtts import gTTS
                gTTS(text=text, lang="hi").save(str(output))
            except Exception as exc2:
                logger.error("gTTS also failed: %s — hook will have no audio", exc2)
                # Create silent audio via FFmpeg
                subprocess.run(
                    [self._ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                     "-t", "8", str(output)],
                    capture_output=True,
                )

    def _render_video(self, narration: str, audio_path: Path, output: Path) -> None:
        """Render hook video: black bg + gold text + slow zoom + music."""
        output.parent.mkdir(parents=True, exist_ok=True)

        # Pick background music
        music_path = self._pick_music()

        # Escape text for FFmpeg drawtext
        safe_text = narration.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")
        # Wrap long text — split at ~20 chars
        words = narration.split()
        lines, line = [], []
        for w in words:
            line.append(w)
            if len(" ".join(line)) > 22:
                lines.append(" ".join(line))
                line = []
        if line:
            lines.append(" ".join(line))
        wrapped = "\n".join(lines)
        safe_wrapped = wrapped.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")

        # Duration from audio (fallback 9s)
        duration = self._probe_duration(audio_path) if audio_path.exists() else 9.0
        duration = max(8.0, min(duration + 1.0, 12.0))

        # Video filter: black bg + gold text with shadow + slow zoom via scale
        vf = (
            f"color=black:s=1920x1080:d={duration:.1f}[bg];"
            f"[bg]zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(duration * 25)}:s=1920x1080:fps=25,"
            f"drawtext=text='{safe_wrapped}'"
            f":fontcolor={_GOLD}:fontsize=52:font='Arial'"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":shadowcolor={_SHADOW}:shadowx=3:shadowy=3"
            f":line_spacing=12[vout]"
        )

        encoder_args = (
            ["-c:v", "h264_qsv", "-global_quality", "20"]
            if self._qsv
            else ["-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p"]
        )

        if music_path and music_path.exists() and audio_path.exists():
            cmd = [
                self._ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=black:s=1920x1080:d={duration:.1f}",
                "-i", str(audio_path),
                "-i", str(music_path),
                "-filter_complex",
                    f"[0:v]zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":d={int(duration * 25)}:s=1920x1080:fps=25,"
                    f"drawtext=text='{safe_wrapped}':fontcolor={_GOLD}:fontsize=52:font='Arial'"
                    f":x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor={_SHADOW}:shadowx=3:shadowy=3"
                    f":line_spacing=12[vout];"
                    f"[2:a]volume=0.2,afade=t=in:d=1,afade=t=out:st={duration-2:.1f}:d=2[mus];"
                    f"[1:a][mus]amix=inputs=2:duration=first[aout]",
                "-map", "[vout]", "-map", "[aout]",
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                str(output),
            ]
        elif audio_path.exists():
            cmd = [
                self._ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=black:s=1920x1080:d={duration:.1f}",
                "-i", str(audio_path),
                "-filter_complex",
                    f"[0:v]zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":d={int(duration * 25)}:s=1920x1080:fps=25,"
                    f"drawtext=text='{safe_wrapped}':fontcolor={_GOLD}:fontsize=52:font='Arial'"
                    f":x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor={_SHADOW}:shadowx=3:shadowy=3"
                    f":line_spacing=12[vout]",
                "-map", "[vout]", "-map", "1:a",
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                str(output),
            ]
        else:
            cmd = [
                self._ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=black:s=1920x1080:d={duration:.1f}",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex",
                    f"[0:v]zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":d={int(duration * 25)}:s=1920x1080:fps=25,"
                    f"drawtext=text='{safe_wrapped}':fontcolor={_GOLD}:fontsize=52:font='Arial'"
                    f":x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor={_SHADOW}:shadowx=3:shadowy=3"
                    f":line_spacing=12[vout]",
                "-map", "[vout]", "-map", "1:a",
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                str(output),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Hook FFmpeg failed:\n%s", result.stderr[-800:])
            raise RuntimeError(f"Hook render failed (exit {result.returncode})")

    def _pick_music(self) -> Optional[Path]:
        """Pick a suitable background music track."""
        for name in ["devotional.mp3", "epic.mp3", "neutral.mp3"]:
            p = self._music_dir / name
            if p.exists():
                return p
        tracks = list(self._music_dir.glob("*.mp3"))
        return tracks[0] if tracks else None

    def _probe_duration(self, path: Path) -> float:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            return float(r.stdout.strip())
        except Exception:
            return 9.0
