"""
waveform_generator.py — Audio waveform renderer for RAGAI Editor V3.

Extracts audio from a video clip and renders a waveform as a list of
normalised amplitude values (0.0–1.0) suitable for drawing on a canvas.

Uses pydub if available; falls back to FFmpeg raw PCM extraction.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    _PYDUB_OK = True
except ImportError:
    _PYDUB_OK = False


def _ffmpeg_path() -> str:
    import shutil
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def extract_waveform(video_path: Path, samples: int = 200) -> List[float]:
    """
    Return a list of `samples` normalised amplitude values (0.0–1.0).
    Returns empty list on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return []

    if _PYDUB_OK:
        return _extract_pydub(video_path, samples)
    return _extract_ffmpeg(video_path, samples)


def _extract_pydub(path: Path, samples: int) -> List[float]:
    try:
        audio = AudioSegment.from_file(str(path))
        # Downsample to mono
        audio = audio.set_channels(1)
        raw = audio.get_array_of_samples()
        if not raw:
            return []
        # Chunk into `samples` buckets
        chunk = max(1, len(raw) // samples)
        result = []
        peak = max(abs(v) for v in raw) or 1
        for i in range(samples):
            bucket = raw[i * chunk: (i + 1) * chunk]
            if bucket:
                amp = sum(abs(v) for v in bucket) / len(bucket) / peak
            else:
                amp = 0.0
            result.append(float(amp))
        return result
    except Exception as exc:
        logger.debug("pydub waveform failed: %s", exc)
        return []


def _extract_ffmpeg(path: Path, samples: int) -> List[float]:
    """Extract raw PCM via FFmpeg and compute RMS per bucket."""
    ffmpeg = _ffmpeg_path()
    try:
        with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [
            ffmpeg, "-y", "-i", str(path),
            "-ac", "1", "-ar", "8000",
            "-f", "s16le", tmp_path,
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        data = Path(tmp_path).read_bytes()
        Path(tmp_path).unlink(missing_ok=True)
        if not data:
            return []
        import struct
        n = len(data) // 2
        values = [abs(struct.unpack_from("<h", data, i * 2)[0]) for i in range(n)]
        chunk = max(1, n // samples)
        peak = max(values) or 1
        result = []
        for i in range(samples):
            bucket = values[i * chunk: (i + 1) * chunk]
            amp = (sum(bucket) / len(bucket) / peak) if bucket else 0.0
            result.append(float(amp))
        return result
    except Exception as exc:
        logger.debug("FFmpeg waveform failed: %s", exc)
        return []
