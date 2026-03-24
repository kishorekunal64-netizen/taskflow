"""
shorts_generator.py - Vertical short-form video generator for RAGAI ecosystem.

Detects high-intensity scenes in a compiled video, extracts 15-30 second clips,
crops to 9:16 vertical format (1080x1920), overlays captions, and saves to shorts/.

Dependencies: opencv-python, numpy (already in requirements)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SHORTS_DIR = Path("shorts")

try:
    import cv2
    import numpy as np
    _CV2 = True
except ImportError:
    _CV2 = False
    logger.warning("opencv-python not installed - scene detection disabled, using time-based splits")


def _ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def _probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


class ShortsGenerator:
    """
    Generates vertical short-form clips from a compiled long-form video.

    Scene detection uses frame difference analysis (OpenCV).
    Falls back to equal-interval splitting when OpenCV is unavailable.
    """

    SHORT_MIN = 15   # minimum short duration (seconds)
    SHORT_MAX = 30   # maximum short duration (seconds)
    MAX_SHORTS = 5   # max shorts per video

    def __init__(self, shorts_dir: Path = SHORTS_DIR):
        self._ffmpeg = _ffmpeg_path()
        self._shorts_dir = Path(shorts_dir)
        self._shorts_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, video_path: Path, max_shorts: int = 3) -> List[Path]:
        """
        Generate up to max_shorts vertical clips from video_path.
        Returns list of output paths.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error("Video not found: %s", video_path)
            return []

        duration = _probe_duration(video_path)
        if duration < self.SHORT_MIN:
            logger.warning("Video too short for shorts: %.1fs", duration)
            return []

        logger.info("Generating shorts from %s (%.0fs)", video_path.name, duration)

        if _CV2:
            segments = self._detect_scenes(video_path, duration)
        else:
            segments = self._time_split(duration)

        segments = segments[: min(max_shorts, self.MAX_SHORTS)]
        outputs: List[Path] = []

        stem = video_path.stem
        for i, (start, end) in enumerate(segments, 1):
            out = self._shorts_dir / f"{stem}_short_{i:02d}.mp4"
            result = self._extract_vertical(video_path, start, end - start, out)
            if result:
                outputs.append(result)
                logger.info("Short %d: %s (%.0f-%.0fs)", i, out.name, start, end)

        logger.info("Generated %d shorts from %s", len(outputs), video_path.name)
        return outputs

    # ------------------------------------------------------------------
    # Scene detection
    # ------------------------------------------------------------------

    def _detect_scenes(self, video: Path, duration: float) -> List[Tuple[float, float]]:
        """Use frame difference to find high-intensity moments."""
        try:
            cap = cv2.VideoCapture(str(video))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            scores: List[Tuple[float, float]] = []

            prev_gray = None
            frame_idx = 0
            sample_every = max(1, int(fps))  # sample 1 frame/sec

            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % sample_every == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if prev_gray is not None:
                        diff = cv2.absdiff(gray, prev_gray)
                        score = float(np.mean(diff))
                        t = frame_idx / fps
                        scores.append((t, score))
                    prev_gray = gray
                frame_idx += 1
            cap.release()

            if not scores:
                return self._time_split(duration)

            # Sort by intensity descending, pick top segments
            scores.sort(key=lambda x: -x[1])
            selected: List[Tuple[float, float]] = []
            used_times = set()

            for t, _ in scores:
                # Avoid overlapping segments
                if any(abs(t - u) < self.SHORT_MAX for u in used_times):
                    continue
                start = max(0.0, t - 5.0)
                end = min(duration, start + self.SHORT_MAX)
                if end - start >= self.SHORT_MIN:
                    selected.append((start, end))
                    used_times.add(t)
                if len(selected) >= self.MAX_SHORTS:
                    break

            selected.sort(key=lambda x: x[0])
            return selected if selected else self._time_split(duration)

        except Exception as exc:
            logger.warning("Scene detection failed: %s — using time split", exc)
            return self._time_split(duration)

    def _time_split(self, duration: float) -> List[Tuple[float, float]]:
        """Equal-interval fallback: split video into SHORT_MAX chunks."""
        segments = []
        t = 0.0
        while t + self.SHORT_MIN < duration and len(segments) < self.MAX_SHORTS:
            end = min(t + self.SHORT_MAX, duration)
            segments.append((t, end))
            t += self.SHORT_MAX
        return segments

    # ------------------------------------------------------------------
    # FFmpeg extraction
    # ------------------------------------------------------------------

    def _extract_vertical(self, src: Path, start: float, dur: float, out: Path) -> Optional[Path]:
        """Extract segment, crop to 9:16 vertical, add caption bar."""
        # Crop: take center square then pad to 1080x1920
        vf = (
            "scale=1080:1080:force_original_aspect_ratio=increase,"
            "crop=1080:1080,"
            "pad=1080:1920:0:420:black,"
            "drawtext=text='RAGAI Shorts':fontsize=40:fontcolor=white"
            ":x=(w-text_w)/2:y=h-80:box=1:boxcolor=black@0.5:boxborderw=8"
        )
        cmd = [
            self._ffmpeg, "-y",
            "-ss", f"{start:.2f}",
            "-i", str(src),
            "-t", f"{dur:.2f}",
            "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(out),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode == 0 and out.exists():
                return out
            logger.warning("FFmpeg short extraction failed: %s",
                           result.stderr.decode(errors="ignore")[-200:])
            return None
        except Exception as exc:
            logger.error("Short extraction error: %s", exc)
            return None
