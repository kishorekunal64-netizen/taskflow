"""
audio_sync_engine.py — Narration-to-scene synchronization for RAGAI.

Maps a single narration audio file (or per-scene WAVs) to scene timing.
Uses word count or sentence segmentation to distribute audio across scenes.

Used when mic_narration_recorder provides audio instead of voice_synthesizer.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models import Scene

logger = logging.getLogger(__name__)


def _probe_duration(path: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffprobe.exe"
        ffprobe = str(local) if local.exists() else None
    if not ffprobe:
        logger.warning("AudioSyncEngine: ffprobe not found — duration=0")
        return 0.0
    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(r.stdout.strip())
    except Exception as exc:
        logger.warning("AudioSyncEngine: ffprobe failed — %s", exc)
        return 0.0


def _split_audio(
    src: Path,
    segments: List[Tuple[float, float]],
    out_dir: Path,
    prefix: str = "scene",
) -> List[Path]:
    """Split a WAV/MP3 into segments using FFmpeg.

    Args:
        src:      Source audio file.
        segments: List of (start_sec, end_sec) tuples.
        out_dir:  Output directory.
        prefix:   Filename prefix.

    Returns:
        List of output file paths.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
        ffmpeg = str(local) if local.exists() else None
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found — cannot split audio")

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (start, end) in enumerate(segments, start=1):
        duration = end - start
        out_path = out_dir / f"{prefix}_{i:03d}_audio.wav"
        subprocess.run(
            [ffmpeg, "-y", "-i", str(src),
             "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
             "-c", "copy", str(out_path)],
            capture_output=True, check=True,
        )
        paths.append(out_path)
        logger.debug("AudioSyncEngine: segment %d → %s (%.1f–%.1fs)", i, out_path.name, start, end)
    return paths


class AudioSyncEngine:
    """Synchronize narration audio with scene timing."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign_per_scene_audio(
        self,
        scenes: List[Scene],
        audio_paths: List[Path],
    ) -> List[Scene]:
        """Assign pre-split per-scene audio files directly to scenes.

        Used when mic_narration_recorder recorded each scene separately.
        Pads with silence if fewer audio files than scenes.
        """
        for i, scene in enumerate(scenes):
            if i < len(audio_paths) and audio_paths[i].exists():
                scene.audio_path = audio_paths[i]
                # Update duration from actual audio length
                dur = _probe_duration(audio_paths[i])
                if dur > 0:
                    scene.duration_seconds = dur
                logger.info("AudioSyncEngine: scene %d ← %s (%.1fs)",
                            scene.number, audio_paths[i].name, scene.duration_seconds)
            else:
                logger.warning("AudioSyncEngine: no audio for scene %d — will use TTS fallback",
                               scene.number)
        return scenes

    def split_narration_to_scenes(
        self,
        narration_path: Path,
        scenes: List[Scene],
        method: str = "word_count",
    ) -> List[Scene]:
        """Split a single narration file across scenes and assign audio_path.

        Args:
            narration_path: Path to the full narration WAV/MP3.
            scenes:         Scene list (narration text used for word-count split).
            method:         'word_count' or 'equal' distribution.

        Returns:
            Scenes with audio_path set.
        """
        total_duration = _probe_duration(narration_path)
        if total_duration <= 0:
            logger.error("AudioSyncEngine: cannot probe duration of %s", narration_path)
            return scenes

        segments = self._compute_segments(scenes, total_duration, method)
        audio_paths = _split_audio(
            narration_path, segments, self.work_dir, prefix="scene"
        )
        return self.assign_per_scene_audio(scenes, audio_paths)

    def compute_scene_durations(
        self,
        scenes: List[Scene],
        total_duration: float,
        method: str = "word_count",
    ) -> List[float]:
        """Return per-scene duration list that sums to total_duration."""
        segments = self._compute_segments(scenes, total_duration, method)
        return [end - start for start, end in segments]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_segments(
        self,
        scenes: List[Scene],
        total_duration: float,
        method: str,
    ) -> List[Tuple[float, float]]:
        """Compute (start, end) time segments for each scene."""
        n = len(scenes)
        if n == 0:
            return []

        if method == "word_count":
            weights = self._word_count_weights(scenes)
        else:
            weights = [1.0 / n] * n

        # Normalize weights
        total_w = sum(weights) or 1.0
        weights = [w / total_w for w in weights]

        segments = []
        cursor = 0.0
        for w in weights:
            duration = total_duration * w
            segments.append((cursor, cursor + duration))
            cursor += duration

        return segments

    def _word_count_weights(self, scenes: List[Scene]) -> List[float]:
        """Weight each scene by its narration word count."""
        counts = [max(1, len(s.narration.split())) for s in scenes]
        total = sum(counts)
        return [c / total for c in counts]

    def _sentence_count(self, text: str) -> int:
        return max(1, len(re.findall(r"[।.!?]+", text)) + 1)
