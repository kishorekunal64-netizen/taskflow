"""
outro_generator.py — Subscribe outro clip generator for RAGAI Editor V2.

Generates a 6-8 second outro video with Hindi subscribe narration,
Edge-TTS voice, and FFmpeg rendering (dark bg, white/gold text, fade).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_OUTRO_TEXTS = [
    "अगर आपको यह कहानी पसंद आई हो तो चैनल को जरूर सब्सक्राइब करें।",
    "ऐसी और कहानियों के लिए हमारे चैनल को सब्सक्राइब करें और बेल आइकन दबाएं।",
    "वीडियो अच्छी लगी हो तो लाइक करें और चैनल सब्सक्राइब करना न भूलें।",
]

_GOLD   = "0xFFD700"
_WHITE  = "0xFFFFFF"
_SHADOW = "0x000000@0.9"


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


class OutroGenerator:
    """Generates a 6-8 second subscribe outro clip."""

    def __init__(self, music_dir: Path = Path("music")):
        self._music_dir = Path(music_dir)
        self._ffmpeg = _ffmpeg_path()
        self._qsv = _check_qsv()

    def generate(self, output_path: Path, text_index: int = 0) -> Path:
        """
        Render outro_clip.mp4 at output_path.
        text_index cycles through _OUTRO_TEXTS for variation.
        """
        text = _OUTRO_TEXTS[text_index % len(_OUTRO_TEXTS)]
        logger.info("Generating outro clip: %s", output_path)

        with tempfile.TemporaryDirectory(prefix="ragai_outro_") as tmp:
            tmp_path = Path(tmp)
            audio_path = tmp_path / "outro_voice.mp3"
            self._synthesise_voice(text, audio_path)
            self._render_video(text, audio_path, output_path)

        logger.info("Outro clip ready: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _synthesise_voice(self, text: str, output: Path) -> None:
        try:
            import edge_tts
            async def _run():
                communicate = edge_tts.Communicate(text, voice="hi-IN-SwaraNeural")
                await communicate.save(str(output))
            asyncio.run(_run())
        except Exception as exc:
            logger.warning("Edge-TTS outro failed: %s — gTTS fallback", exc)
            try:
                from gtts import gTTS
                gTTS(text=text, lang="hi").save(str(output))
            except Exception as exc2:
                logger.error("gTTS outro failed: %s — silent audio", exc2)
                subprocess.run(
                    [self._ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                     "-t", "7", str(output)],
                    capture_output=True,
                )

    def _render_video(self, text: str, audio_path: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        duration = self._probe_duration(audio_path) if audio_path.exists() else 7.0
        duration = max(6.0, min(duration + 1.0, 9.0))

        safe_text = text.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")
        # Wrap text
        words = text.split()
        lines, line = [], []
        for w in words:
            line.append(w)
            if len(" ".join(line)) > 24:
                lines.append(" ".join(line))
                line = []
        if line:
            lines.append(" ".join(line))
        safe_wrapped = "\n".join(lines).replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")

        # Subscribe icon line
        subscribe_line = "▶  Subscribe  🔔"

        encoder_args = (
            ["-c:v", "h264_qsv", "-global_quality", "20"]
            if self._qsv
            else ["-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p"]
        )

        music_path = self._pick_music()

        vf_text = (
            f"[0:v]"
            f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration-1:.1f}:d=1,"
            f"drawtext=text='{safe_wrapped}':fontcolor={_WHITE}:fontsize=46:font='Arial'"
            f":x=(w-text_w)/2:y=(h-text_h)/2-40"
            f":shadowcolor={_SHADOW}:shadowx=2:shadowy=2:line_spacing=10,"
            f"drawtext=text='{subscribe_line}':fontcolor={_GOLD}:fontsize=38:font='Arial'"
            f":x=(w-text_w)/2:y=(h-text_h)/2+80"
            f":shadowcolor={_SHADOW}:shadowx=2:shadowy=2"
            f"[vout]"
        )

        if music_path and music_path.exists() and audio_path.exists():
            cmd = [
                self._ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=c=0x0a0a1a:s=1920x1080:d={duration:.1f}",
                "-i", str(audio_path),
                "-i", str(music_path),
                "-filter_complex",
                    vf_text + ";"
                    f"[2:a]volume=0.15,afade=t=in:d=0.5,afade=t=out:st={duration-1.5:.1f}:d=1.5[mus];"
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
                "-f", "lavfi", "-i", f"color=c=0x0a0a1a:s=1920x1080:d={duration:.1f}",
                "-i", str(audio_path),
                "-filter_complex", vf_text,
                "-map", "[vout]", "-map", "1:a",
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                str(output),
            ]
        else:
            cmd = [
                self._ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=c=0x0a0a1a:s=1920x1080:d={duration:.1f}",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", vf_text,
                "-map", "[vout]", "-map", "1:a",
                *encoder_args,
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                str(output),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Outro FFmpeg failed:\n%s", result.stderr[-800:])
            raise RuntimeError(f"Outro render failed (exit {result.returncode})")

    def _pick_music(self) -> Optional[Path]:
        for name in ["neutral.mp3", "devotional.mp3", "epic.mp3"]:
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
            return 7.0
