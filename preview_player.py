"""
preview_player.py — Preview Player for RAGAI Editor V3.

Renders a fast 720p preview of the current timeline using FFmpeg,
then plays it via ffplay (or subprocess). Non-blocking.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, List, Optional

from timeline import TimelineEntry

logger = logging.getLogger(__name__)

PREVIEW_CRF    = 28
PREVIEW_PRESET = "ultrafast"
PREVIEW_SCALE  = "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def _ffplay() -> Optional[str]:
    p = shutil.which("ffplay")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffplay.exe"
    return str(local) if local.exists() else None


class PreviewPlayer:
    """
    Builds a fast 720p preview of the timeline and plays it.
    All work is done in a background thread.
    """

    def __init__(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_done: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        crf: int = PREVIEW_CRF,
        preset: str = PREVIEW_PRESET,
    ):
        self._on_status = on_status or (lambda m: None)
        self._on_done   = on_done   or (lambda p: None)
        self._on_error  = on_error  or (lambda m: None)
        self._crf    = crf
        self._preset = preset
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def play(self, entries: List[TimelineEntry], output_dir: Path = Path("tmp")) -> None:
        """Start preview render + playback in background."""
        if self._thread and self._thread.is_alive():
            self._on_status("Preview already running…")
            return
        self._thread = threading.Thread(
            target=self._run, args=(list(entries), Path(output_dir)), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    # ── internal ──────────────────────────────────────────────────────────────

    def _run(self, entries: List[TimelineEntry], output_dir: Path) -> None:
        ffmpeg = _ffmpeg()
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "preview_720p.mp4"

        self._on_status("Building preview…")

        if not entries:
            self._on_error("No clips in timeline")
            return

        # Build concat list
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                         delete=False, encoding="utf-8") as f:
            concat_path = Path(f.name)
            for e in entries:
                clip = e.clip
                p = Path(clip.filepath)
                if p.exists():
                    f.write(f"file '{p.as_posix()}'\n")
                    # trim
                    ti = clip.trim_in  if clip.trim_in  >= 0 else 0.0
                    to = clip.trim_out if clip.trim_out >= 0 else clip.duration
                    if ti > 0:
                        f.write(f"inpoint {ti:.3f}\n")
                    if to < clip.duration:
                        f.write(f"outpoint {to:.3f}\n")

        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-vf", PREVIEW_SCALE,
            "-c:v", "libx264", "-crf", str(self._crf),
            "-preset", self._preset,
            "-c:a", "aac", "-b:a", "128k",
            str(out),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            concat_path.unlink(missing_ok=True)
            if result.returncode != 0:
                self._on_error(f"Preview render failed: {result.stderr[-200:]}")
                return
        except Exception as exc:
            self._on_error(f"Preview error: {exc}")
            return

        self._on_status("Preview ready — launching player…")
        self._on_done(out)

        # Play
        player = _ffplay()
        if player:
            try:
                self._proc = subprocess.Popen(
                    [player, "-autoexit", "-window_title", "RAGAI Preview", str(out)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._proc.wait()
            except Exception as exc:
                logger.debug("ffplay error: %s", exc)
        else:
            # Fallback: open with default OS player
            import os
            try:
                os.startfile(str(out))
            except Exception:
                self._on_status(f"Preview saved: {out}")
