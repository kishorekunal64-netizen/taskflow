"""
render_optimizer.py — FFmpeg rendering performance optimizer for RAGAI.

Detects available GPU acceleration (NVENC, QSV, VAAPI) and selects
optimal encoding parameters. Provides dynamic bitrate selection based
on content complexity.

Integrates with video_assembler.py as an optional advisor — the assembler
calls get_encode_args() instead of hardcoding codec params.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPU encoder detection order (preference: NVENC > QSV > VAAPI > CPU)
# ---------------------------------------------------------------------------

_ENCODER_PROBES: List[Tuple[str, str]] = [
    ("h264_nvenc", "NVIDIA NVENC"),
    ("h264_qsv",   "Intel QSV"),
    ("h264_vaapi", "VAAPI (Linux)"),
]

_detected_encoder: Optional[str] = None  # cached


def detect_gpu_encoder() -> Optional[str]:
    """Return the best available hardware encoder name, or None for CPU."""
    global _detected_encoder
    if _detected_encoder is not None:
        return _detected_encoder if _detected_encoder != "cpu" else None

    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        available = result.stdout
    except Exception as exc:
        logger.warning("RenderOptimizer: ffmpeg probe failed — %s", exc)
        _detected_encoder = "cpu"
        return None

    for encoder, label in _ENCODER_PROBES:
        if encoder in available:
            _detected_encoder = encoder
            logger.info("RenderOptimizer: GPU encoder detected — %s (%s)", encoder, label)
            return encoder

    _detected_encoder = "cpu"
    logger.info("RenderOptimizer: no GPU encoder found — using libx264 (CPU)")
    return None


# ---------------------------------------------------------------------------
# Bitrate profiles
# ---------------------------------------------------------------------------

_BITRATE_PROFILES: Dict[str, Dict[str, str]] = {
    "draft":    {"landscape": "4000k",  "shorts": "3000k"},
    "standard": {"landscape": "8000k",  "shorts": "6000k"},
    "high":     {"landscape": "12000k", "shorts": "9000k"},
    "cinema":   {"landscape": "20000k", "shorts": "15000k"},
}


class RenderOptimizer:
    """Select optimal FFmpeg encoding parameters for the current hardware."""

    def __init__(self) -> None:
        self.gpu_encoder = detect_gpu_encoder()

    def get_encode_args(
        self,
        preset: str = "medium",
        crf: int = 20,
        quality_label: str = "standard",
        fmt: str = "landscape",
        use_bitrate: bool = False,
    ) -> List[str]:
        """Return FFmpeg video codec argument list.

        Args:
            preset:        libx264 preset (fast/medium/slow).
            crf:           CRF value for quality control.
            quality_label: One of draft/standard/high/cinema.
            fmt:           'landscape' or 'shorts'.
            use_bitrate:   If True, use -b:v instead of -crf (required for some GPU encoders).

        Returns:
            List of FFmpeg argument strings.
        """
        enc = self.gpu_encoder

        if enc == "h264_nvenc":
            # NVENC: use CQ (constant quality) mode
            cq = max(18, min(int(crf * 1.1), 51))
            args = [
                "-c:v", "h264_nvenc",
                "-preset", "p4",          # balanced NVENC preset
                "-rc", "vbr",
                "-cq", str(cq),
                "-b:v", "0",
            ]
            logger.debug("RenderOptimizer: NVENC args selected (cq=%d)", cq)
            return args

        if enc == "h264_qsv":
            icq = max(18, min(int(crf * 1.1), 51))
            args = [
                "-c:v", "h264_qsv",
                "-preset", "medium",
                "-global_quality", str(icq),
                "-look_ahead", "1",
            ]
            logger.debug("RenderOptimizer: QSV args selected (icq=%d)", icq)
            return args

        if enc == "h264_vaapi":
            args = [
                "-c:v", "h264_vaapi",
                "-qp", str(crf),
            ]
            logger.debug("RenderOptimizer: VAAPI args selected (qp=%d)", crf)
            return args

        # CPU fallback — libx264
        args = [
            "-c:v", "libx264",
            "-profile:v", "high", "-level", "5.1",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
        ]
        logger.debug("RenderOptimizer: libx264 CPU args selected (crf=%d)", crf)
        return args

    def recommended_bitrate(self, quality_label: str, fmt: str = "landscape") -> str:
        """Return recommended bitrate string for the given quality and format."""
        profile = _BITRATE_PROFILES.get(quality_label, _BITRATE_PROFILES["standard"])
        return profile.get(fmt, "8000k")

    def parallel_workers(self) -> int:
        """Return recommended number of parallel scene encoding workers."""
        import os
        cpu_count = os.cpu_count() or 2
        if self.gpu_encoder:
            # GPU can handle more parallel jobs
            return min(cpu_count, 6)
        return min(cpu_count, 4)

    def summary(self) -> str:
        enc = self.gpu_encoder or "libx264 (CPU)"
        return f"RenderOptimizer: encoder={enc} workers={self.parallel_workers()}"
