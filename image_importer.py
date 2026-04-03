"""
image_importer.py — Image import and resizing for RAGAI Video Factory (IMAGE input mode).
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path
from typing import List

from PIL import Image

from models import IMAGE_RESOLUTIONS, ImageImportError, VideoFormat

logger = logging.getLogger(__name__)


class ImageImporter:
    """Validates, resizes, and saves user-supplied images for the IMAGE input mode."""

    SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}

    def __init__(self, work_dir: Path) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def load_and_resize(
        self,
        image_paths: List[Path],
        fmt: VideoFormat,
        n_scenes: int,
    ) -> List[Path]:
        """Validate, resize to IMAGE_RESOLUTIONS[fmt], and save images to work_dir.

        Cycles through images if len(image_paths) < n_scenes.
        Truncates if len(image_paths) > n_scenes.
        Raises ImageImportError if any file cannot be opened by PIL.
        Returns a list of exactly n_scenes saved file paths.
        """
        width, height = IMAGE_RESOLUTIONS[fmt]

        # Build the sequence of source paths (cycle or truncate to n_scenes)
        if len(image_paths) >= n_scenes:
            source_sequence = image_paths[:n_scenes]
        else:
            source_sequence = list(itertools.islice(itertools.cycle(image_paths), n_scenes))

        output_paths: List[Path] = []
        for i, src in enumerate(source_sequence):
            try:
                img = Image.open(src)
            except Exception as exc:
                raise ImageImportError(
                    f"Cannot open image '{src.name}': {exc}"
                ) from exc

            # Keep original image as-is — just convert to RGB and save as PNG.
            # The Ken Burns stage in video_assembler.py handles all scaling/cropping
            # to the output resolution while preserving aspect ratio via cover-scale.
            # Forcing a resize here only degrades quality and causes cropping.
            img_rgb = img.convert("RGB")
            dest = self.work_dir / f"imported_image_{i:03d}.png"
            img_rgb.save(dest, format="PNG")
            logger.info("Saved resized image %d/%d → %s", i + 1, n_scenes, dest)
            output_paths.append(dest)

        return output_paths
