"""
thumbnail_generator.py - Viral thumbnail generator for RAGAI Editor V2.

3 rotating layout templates:
  Layout A: large centered Hindi title (dark overlay)
  Layout B: split layout - left image, right dark panel with text
  Layout C: emoji row + title with gradient overlay

Font: Noto Sans Devanagari with system font fallback.
"""
from __future__ import annotations

import logging
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL = True
except ImportError:
    _PIL = False
    logger.warning("Pillow not installed - thumbnail generation disabled")

THUMB_W = 1280
THUMB_H = 720

_FONTS = [
    "C:/Windows/Fonts/NotoSansDevanagari-Bold.ttf",
    "C:/Windows/Fonts/NotoSansDevanagari-Regular.ttf",
    "C:/Windows/Fonts/mangal.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

_LAYOUTS = ["A", "B", "C"]
_last_layout: Optional[str] = None


def _ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def _font(size: int):
    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(text: str, max_chars: int = 20) -> list:
    words, lines, line = text.split(), [], []
    for w in words:
        line.append(w)
        if len(" ".join(line)) >= max_chars:
            lines.append(" ".join(line))
            line = []
    if line:
        lines.append(" ".join(line))
    return lines[:3]


def _pick_layout() -> str:
    global _last_layout
    choices = [l for l in _LAYOUTS if l != _last_layout]
    layout = random.choice(choices)
    _last_layout = layout
    return layout


def _glow_text(img, text: str, font, cx: int, cy: int):
    """Draw gold glow + white text at (cx, cy) center-anchored."""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((cx, cy), text, font=font, fill=(255, 180, 0, 100), anchor="mm", align="center")
    glow = glow.filter(ImageFilter.GaussianBlur(radius=10))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(img)
    for dx, dy in [(-2, -2), (2, 2), (-2, 2), (2, -2)]:
        d.text((cx + dx, cy + dy), text, font=font, fill=(0, 0, 0), anchor="mm", align="center")
    d.text((cx, cy), text, font=font, fill=(255, 255, 255), anchor="mm", align="center")
    return img


def _layout_a(img, title: str):
    """Layout A: large centered title, dark overlay."""
    dark = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, dark, alpha=0.55)
    block = "\n".join(_wrap(title, 18))
    img = _glow_text(img, block, _font(64), THUMB_W // 2, THUMB_H // 2 - 30)
    ImageDraw.Draw(img).text(
        (THUMB_W // 2, THUMB_H - 55), "RAGAI Compilation",
        font=_font(30), fill=(255, 215, 0), anchor="mm"
    )
    return img


def _layout_b(img, title: str):
    """Layout B: left image, right dark panel with text."""
    panel = Image.new("RGBA", (THUMB_W // 2, THUMB_H), (10, 15, 30, 230))
    result = img.convert("RGBA")
    result.paste(panel, (THUMB_W // 2, 0), panel)
    result = result.convert("RGB")
    block = "\n".join(_wrap(title, 16))
    cx = THUMB_W * 3 // 4
    result = _glow_text(result, block, _font(52), cx, THUMB_H // 2 - 20)
    ImageDraw.Draw(result).text(
        (cx, THUMB_H - 50), "Watch Now",
        font=_font(28), fill=(0, 212, 255), anchor="mm"
    )
    return result


def _layout_c(img, title: str):
    """Layout C: emoji row + title with dark gradient."""
    dark = Image.new("RGB", img.size, (5, 5, 20))
    img = Image.blend(img, dark, alpha=0.60)
    d = ImageDraw.Draw(img)
    emojis = random.sample(["*", "!", "?", "+", "#"], 3)
    d.text((THUMB_W // 2, 90), "  ".join(emojis), font=_font(60), fill=(255, 220, 50), anchor="mm")
    block = "\n".join(_wrap(title, 20))
    img = _glow_text(img, block, _font(56), THUMB_W // 2, THUMB_H // 2 + 20)
    ImageDraw.Draw(img).text(
        (THUMB_W // 2, THUMB_H - 50), "RAGAI Hindi Stories",
        font=_font(28), fill=(160, 200, 255), anchor="mm"
    )
    return img


class ThumbnailGenerator:
    """Generates viral-style YouTube thumbnails with 3 rotating layout templates."""

    def __init__(self):
        self._ffmpeg = _ffmpeg_path()

    def generate(
        self,
        video_path: Path,
        title: str,
        output_path: Path,
        frame_time: float = 3.0,
        layout: Optional[str] = None,
    ) -> Optional[Path]:
        if not _PIL:
            logger.warning("Pillow unavailable - skipping thumbnail")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        chosen = layout or _pick_layout()
        logger.info("Thumbnail layout %s for: %s", chosen, title)

        with tempfile.TemporaryDirectory(prefix="ragai_thumb_") as tmp:
            frame = Path(tmp) / "frame.png"
            if not self._extract_frame(video_path, frame, frame_time):
                logger.warning("Frame extraction failed: %s", video_path.name)
                return None
            return self._compose(frame, title, output_path, chosen)

    def _extract_frame(self, video: Path, out: Path, t: float) -> bool:
        cmd = [
            self._ffmpeg, "-y", "-ss", str(t), "-i", str(video),
            "-vframes", "1",
            "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,"
                   f"crop={THUMB_W}:{THUMB_H}",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        return r.returncode == 0 and out.exists()

    def _compose(self, frame: Path, title: str, out: Path, layout: str) -> Optional[Path]:
        try:
            img = Image.open(frame).convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS)
            if layout == "B":
                img = _layout_b(img, title)
            elif layout == "C":
                img = _layout_c(img, title)
            else:
                img = _layout_a(img, title)
            img.save(str(out), "JPEG", quality=92)
            logger.info("Thumbnail saved (%s): %s", layout, out)
            return out
        except Exception as exc:
            logger.error("Thumbnail compose failed: %s", exc)
            return None
