"""
scene_composer.py — Cinematic scene composition for RAGAI.

Combines visual layers (background, character overlay, foreground, lighting,
motion effect) into a single composed PNG before video assembly.

Used optionally before video_assembler._write_scene_clip().
If disabled via ragai_advanced_config.json, the pipeline uses raw images as-is.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lighting presets
# ---------------------------------------------------------------------------

_LIGHTING_PRESETS = {
    "golden_hour":  {"brightness": 1.15, "contrast": 1.1,  "color": (255, 200, 100, 30)},
    "blue_hour":    {"brightness": 0.90, "contrast": 1.05, "color": (80,  120, 200, 25)},
    "dramatic":     {"brightness": 0.85, "contrast": 1.25, "color": (0,   0,   0,   40)},
    "soft_natural": {"brightness": 1.05, "contrast": 1.0,  "color": (255, 255, 240, 15)},
    "night":        {"brightness": 0.70, "contrast": 1.15, "color": (20,  30,  80,  50)},
}

_MOTION_EFFECTS = ["none", "vignette", "film_grain", "soft_blur_edges"]


class SceneComposer:
    """Compose cinematic scenes by layering visual elements."""

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compose(
        self,
        scene_number: int,
        background_path: Path,
        output_size: Tuple[int, int],
        lighting: Optional[str] = None,
        motion_effect: Optional[str] = None,
        overlay_paths: Optional[List[Path]] = None,
        foreground_path: Optional[Path] = None,
    ) -> Path:
        """Compose a scene and return path to the composed PNG.

        Args:
            scene_number:   Scene index (used for output filename).
            background_path: Base image from image_generator.
            output_size:    (width, height) target resolution.
            lighting:       Lighting preset name or None for auto.
            motion_effect:  Effect name or None for auto.
            overlay_paths:  Optional character/object overlay images (RGBA).
            foreground_path: Optional foreground layer (RGBA).

        Returns:
            Path to composed_scene_NNN.png in work_dir.
        """
        out_path = self.work_dir / f"composed_scene_{scene_number:03d}.png"

        # 1. Load and resize background
        bg = Image.open(background_path).convert("RGBA")
        bg = bg.resize(output_size, Image.LANCZOS)

        # 2. Apply lighting overlay
        preset_name = lighting or random.choice(list(_LIGHTING_PRESETS.keys()))
        bg = self._apply_lighting(bg, preset_name)

        # 3. Composite overlays (character layers)
        if overlay_paths:
            for ov_path in overlay_paths:
                try:
                    ov = Image.open(ov_path).convert("RGBA")
                    ov = ov.resize(output_size, Image.LANCZOS)
                    bg = Image.alpha_composite(bg, ov)
                except Exception as exc:
                    logger.warning("SceneComposer: overlay %s failed: %s", ov_path, exc)

        # 4. Foreground layer
        if foreground_path and foreground_path.exists():
            try:
                fg = Image.open(foreground_path).convert("RGBA")
                fg = fg.resize(output_size, Image.LANCZOS)
                bg = Image.alpha_composite(bg, fg)
            except Exception as exc:
                logger.warning("SceneComposer: foreground %s failed: %s", foreground_path, exc)

        # 5. Motion / cinematic effect
        effect = motion_effect or random.choice(_MOTION_EFFECTS)
        bg = self._apply_motion_effect(bg, effect)

        # 6. Save as RGB PNG
        result = bg.convert("RGB")
        result.save(str(out_path), "PNG")
        logger.info("SceneComposer: composed scene %d → %s", scene_number, out_path)
        return out_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_lighting(self, img: Image.Image, preset_name: str) -> Image.Image:
        preset = _LIGHTING_PRESETS.get(preset_name, _LIGHTING_PRESETS["soft_natural"])

        # Brightness + contrast
        img = ImageEnhance.Brightness(img).enhance(preset["brightness"])
        img = ImageEnhance.Contrast(img).enhance(preset["contrast"])

        # Color tint overlay
        r, g, b, a = preset["color"]
        tint = Image.new("RGBA", img.size, (r, g, b, a))
        img = Image.alpha_composite(img.convert("RGBA"), tint)
        return img

    def _apply_motion_effect(self, img: Image.Image, effect: str) -> Image.Image:
        if effect == "vignette":
            return self._vignette(img)
        if effect == "film_grain":
            return self._film_grain(img)
        if effect == "soft_blur_edges":
            return self._blur_edges(img)
        return img  # "none"

    def _vignette(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        mask = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(mask)
        # Radial gradient approximation via concentric ellipses
        steps = 40
        for i in range(steps):
            ratio = i / steps
            alpha = int(255 * ratio * 0.6)
            x0 = int(w * ratio * 0.5)
            y0 = int(h * ratio * 0.5)
            x1 = w - x0
            y1 = h - y0
            draw.ellipse([x0, y0, x1, y1], fill=255 - alpha)
        vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        vignette.putalpha(ImageFilter.GaussianBlur(radius=w // 8).filter(
            Image.new("L", (w, h), 0)
        ))
        # Simple darkening at edges
        dark = Image.new("RGBA", (w, h), (0, 0, 0, 80))
        edge_mask = Image.new("L", (w, h), 0)
        em_draw = ImageDraw.Draw(edge_mask)
        em_draw.ellipse([w // 6, h // 6, 5 * w // 6, 5 * h // 6], fill=255)
        edge_mask = edge_mask.filter(ImageFilter.GaussianBlur(radius=min(w, h) // 5))
        inverted = Image.eval(edge_mask, lambda x: 255 - x)
        img.paste(dark, mask=inverted)
        return img

    def _film_grain(self, img: Image.Image) -> Image.Image:
        import numpy as np
        arr = np.array(img.convert("RGBA"), dtype=np.int16)
        grain = np.random.randint(-8, 9, size=arr.shape[:2], dtype=np.int16)
        arr[:, :, :3] = np.clip(arr[:, :, :3] + grain[:, :, None], 0, 255)
        return Image.fromarray(arr.astype(np.uint8), "RGBA")

    def _blur_edges(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        blurred = img.filter(ImageFilter.GaussianBlur(radius=6))
        mask = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(mask)
        margin = min(w, h) // 8
        draw.rectangle([margin, margin, w - margin, h - margin], fill=0)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=margin // 2))
        result = Image.composite(blurred, img, mask)
        return result.convert("RGBA")
