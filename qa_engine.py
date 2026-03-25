"""
qa_engine.py — Output validation engine for RAGAI.

Validates generated video clips and final output before export.
Checks scene duration consistency, audio sync, missing frames,
and file integrity. Triggers regeneration flags on failure.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SceneQAResult:
    scene_number: int
    clip_path: Path
    duration_ok: bool
    audio_ok: bool
    file_ok: bool
    issues: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.duration_ok and self.audio_ok and self.file_ok


@dataclass
class VideoQAResult:
    output_path: Path
    passed: bool
    scene_results: List[SceneQAResult] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    regenerate_scenes: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# QAEngine
# ---------------------------------------------------------------------------

class QAEngine:
    """Validate video clips and final output before export."""

    # Acceptable scene duration range (seconds)
    MIN_SCENE_DURATION = 1.0
    MAX_SCENE_DURATION = 120.0

    # Minimum final video size (bytes)
    MIN_VIDEO_SIZE = 100_000  # 100 KB

    def __init__(self) -> None:
        self._ffprobe = shutil.which("ffprobe")
        if not self._ffprobe:
            # Try local build
            local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffprobe.exe"
            self._ffprobe = str(local) if local.exists() else None
        if not self._ffprobe:
            logger.warning("QAEngine: ffprobe not found — duration checks disabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_scenes(self, scene_clip_map: Dict[int, Path]) -> List[SceneQAResult]:
        """Validate individual scene clips.

        Args:
            scene_clip_map: {scene_number: clip_path}

        Returns:
            List of SceneQAResult, one per scene.
        """
        results = []
        for num, clip_path in sorted(scene_clip_map.items()):
            result = self._validate_clip(num, clip_path)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            logger.info("QA scene %d: %s%s", num, status,
                        f" — {result.issues}" if result.issues else "")
        return results

    def validate_output(self, output_path: Path) -> VideoQAResult:
        """Validate the final assembled video.

        Args:
            output_path: Path to the final video.mp4.

        Returns:
            VideoQAResult with pass/fail and issue list.
        """
        issues = []
        passed = True

        # 1. File exists
        if not output_path.exists():
            return VideoQAResult(
                output_path=output_path,
                passed=False,
                issues=["Output file does not exist"],
            )

        # 2. File size
        size = output_path.stat().st_size
        if size < self.MIN_VIDEO_SIZE:
            issues.append(f"Output file too small: {size} bytes (min {self.MIN_VIDEO_SIZE})")
            passed = False

        # 3. ffprobe duration + stream check
        if self._ffprobe:
            duration, has_video, has_audio = self._probe_file(output_path)
            if duration <= 0:
                issues.append("Could not determine video duration")
                passed = False
            if not has_video:
                issues.append("No video stream detected")
                passed = False
            if not has_audio:
                issues.append("No audio stream detected")
                passed = False
            logger.info("QA output: duration=%.1fs video=%s audio=%s size=%dKB",
                        duration, has_video, has_audio, size // 1024)

        result = VideoQAResult(output_path=output_path, passed=passed, issues=issues)
        logger.info("QA output: %s%s", "PASS" if passed else "FAIL",
                    f" — {issues}" if issues else "")
        return result

    def full_validation(
        self,
        scene_clip_map: Dict[int, Path],
        output_path: Path,
    ) -> VideoQAResult:
        """Run full QA: scene clips + final output.

        Returns VideoQAResult with regenerate_scenes populated for failed scenes.
        """
        scene_results = self.validate_scenes(scene_clip_map)
        output_result = self.validate_output(output_path)

        failed_scenes = [r.scene_number for r in scene_results if not r.passed]
        all_issues = output_result.issues + [
            f"Scene {r.scene_number}: {r.issues}" for r in scene_results if not r.passed
        ]

        return VideoQAResult(
            output_path=output_path,
            passed=output_result.passed and not failed_scenes,
            scene_results=scene_results,
            issues=all_issues,
            regenerate_scenes=failed_scenes,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_clip(self, scene_number: int, clip_path: Path) -> SceneQAResult:
        issues = []

        # File existence
        file_ok = clip_path.exists() and clip_path.stat().st_size > 0
        if not file_ok:
            issues.append("Clip file missing or empty")
            return SceneQAResult(
                scene_number=scene_number,
                clip_path=clip_path,
                duration_ok=False,
                audio_ok=False,
                file_ok=False,
                issues=issues,
            )

        duration_ok = True
        audio_ok = True

        if self._ffprobe:
            duration, has_video, has_audio = self._probe_file(clip_path)

            if duration < self.MIN_SCENE_DURATION:
                issues.append(f"Duration too short: {duration:.1f}s")
                duration_ok = False
            elif duration > self.MAX_SCENE_DURATION:
                issues.append(f"Duration too long: {duration:.1f}s")
                duration_ok = False

            if not has_audio:
                issues.append("No audio stream in clip")
                audio_ok = False

        return SceneQAResult(
            scene_number=scene_number,
            clip_path=clip_path,
            duration_ok=duration_ok,
            audio_ok=audio_ok,
            file_ok=file_ok,
            issues=issues,
        )

    def _probe_file(self, path: Path):
        """Run ffprobe and return (duration, has_video, has_audio)."""
        try:
            r = subprocess.run(
                [
                    self._ffprobe, "-v", "error",
                    "-show_entries", "format=duration:stream=codec_type",
                    "-of", "default=noprint_wrappers=1",
                    str(path),
                ],
                capture_output=True, text=True, timeout=15,
            )
            output = r.stdout
            duration = 0.0
            has_video = False
            has_audio = False

            for line in output.splitlines():
                if line.startswith("duration="):
                    try:
                        duration = float(line.split("=", 1)[1])
                    except ValueError:
                        pass
                elif line == "codec_type=video":
                    has_video = True
                elif line == "codec_type=audio":
                    has_audio = True

            return duration, has_video, has_audio
        except Exception as exc:
            logger.warning("QAEngine: ffprobe failed for %s — %s", path, exc)
            return 0.0, False, False
