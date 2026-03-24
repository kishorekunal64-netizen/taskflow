"""
thumbnail_generator.py — Viral thumbnail generator for RAGAI Editor V2.

Extracts a frame from the first clip, darkens the background,
overlays large Hindi title text with glow/shadow effect,
and saves the result as a JPEG inside the compiled folder.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow not installed — thumbnail generation disabled")


def _ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


class ThumbnailGenerator:
    """Generates a viral-style YouTube thumbnail from a video clip."""

    THUMB_W = 1280
    THUMB_H = 720

    def __init__(self):
        self._ffmpeg = _ffmpeg_path()

    def generate(
        self,
        video_path: Path,
        title: str,
        output_path: Path,
        frame_time: float = 3.0,
    ) -> Optional[Path]:
        """
        Extract frame → darken → overlay title text → save JPEG.
        Returns output_path on success, None on failure.
        """
        if not _PIL_AVAILABLE:
            logger.warning("Pillow unavailable — skipping thumbnail")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="ragai_thumb_") as tmp:
            frame_path = Path(tmp) / "frame.png"
            if not self._extract_frame(video_path, frame_path, frame_time):
                logger.warning("Frame extraction failed for %s", video_path.name)
                return None
            result = self._compose(frame_path, title, output_path)

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_frame(self, video: Path, out: Path, t: float) -> bool:
        """Extract a single frame at time t using FFmpeg."""
        cmd = [
            self._ffmpeg, "-y",
            "-ss", str(t),
            "-i", str(video),
            "-vframes", "1",
            "-vf", f"scale={self.THUMB_W}:{self.THUMB_H}:force_original_aspect_ratio=increase,"
                   f"crop={self.THUMB_W}:{self.THUMB_H}",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        return result.returncode == 0 and out.exists()

    def _compose(self, frame_path: Path, title: str, output_path: Path) -> Optional[Path]:
        """Compose thumbnail: darken frame + text overlay with glow."""
        try:
            img = Image.open(frame_path).convert("RGB")
            img = img.resize((self.THUMB_W, self.THUMB_H), Image.LANCZOS)

            # Darken background (multiply by 0.45)
            dark = Image.new("RGB", img.size, (0, 0, 0))
            img = Image.blend(img, dark, alpha=0.55)

            draw = ImageDraw.Draw(img)

            # Try to load a font; fall back to default
            font_large = self._load_font(60)
            font_small = self._load_font(32)

            # Wrap title text
            lines = self._wrap_text(title, max_chars=20)
            text_block = "\n".join(lines)

            # Glow effect: draw blurred shadow layer
            glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            cx = self.THUMB_W // 2
            cy = self.THUMB_H // 2 - 40

            # Draw glow (orange/gold shadow)
            for offset in range(6, 0, -2):
                glow_draw.text(
                    (cx, cy), text_block,
                    font=font_large, fill=(255, 180, 0, 80),
                    anchor="mm", align="center",
                )
            glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
            img = img.convert("RGBA")
            img = Image.alpha_composite(img, glow_blurred)
            img = img.convert("RGB")

            draw = ImageDraw.Draw(img)

            # Main title text — white with dark shadow
            for dx, dy in [(-2, -2), (2, 2), (-2, 2), (2, -2)]:
                draw.text(
                    (cx + dx, cy + dy), text_block,
                    font=font_large, fill=(0, 0, 0),
                    anchor="mm", align="center",
                )
            draw.text(
                (cx, cy), text_block,
                font=font_large, fill=(255, 255, 255),
                anchor="mm", align="center",
            )

            # Sub-label: "RAGAI Compilation"
            sub_y = self.THUMB_H - 60
            draw.text(
                (cx, sub_y), "▶  RAGAI Compilation",
                font=font_small, fill=(255, 215, 0),
                anchor="mm",
            )

            img.save(str(output_path), "JPEG", quality=92)
            logger.info("Thumbnail saved: %s", output_path)
            return output_path

        except Exception as exc:
            logger.error("Thumbnail compose failed: %s", exc)
            return None

    def _load_font(self, size: int) -> "ImageFont.FreeTypeFont":
        """Try common Windows fonts, fall back to default."""
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _wrap_text(self, text: str, max_chars: int = 20) -> list:
        words = text.split()
        lines, line = [], []
        for w in words:
            line.append(w)
            if len(" ".join(line)) >= max_chars:
                lines.append(" ".join(line))
                line = []
        if line:
            lines.append(" ".join(line))
        return lines[:3]  # max 3 lines
