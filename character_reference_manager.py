"""
character_reference_manager.py — Reference portrait generation and management for RAGAI.

Generates one portrait image per character using the existing image generation
API and caches it in characters/. Reference images are generated only once
per story — reused across all scenes.

Scene image count is NOT increased — portraits are pre-generated before
the main scene generation loop.

Controlled via: enable_character_reference_system in ragai_advanced_config.json
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_CHARACTERS_DIR = Path("characters")

# Portrait prompt template — neutral background for clean reference
_PORTRAIT_TEMPLATE = (
    "portrait photo of {description}, "
    "studio lighting, ultra realistic, neutral background, "
    "sharp focus, professional headshot, 4k"
)


class CharacterReferenceManager:
    """Generate and cache reference portrait images for story characters."""

    def __init__(
        self,
        characters_dir: Path = _CHARACTERS_DIR,
        image_generator=None,
    ) -> None:
        self.characters_dir = Path(characters_dir)
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self._image_generator = image_generator  # ImageGenerator instance
        # In-memory cache: char_id → Path
        self._cache: Dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image_generator(self, image_generator) -> None:
        """Inject the ImageGenerator instance (set after pipeline init)."""
        self._image_generator = image_generator

    def generate_references(self, profiles: List[Dict]) -> Dict[str, Path]:
        """Generate portrait images for all profiles that don't have one yet.

        Args:
            profiles: List of character profile dicts from CharacterProfileGenerator.

        Returns:
            Dict mapping char_id → reference image Path.
        """
        from models import Scene, VideoFormat, VisualStyle

        for profile in profiles:
            char_id = profile["id"]
            description = profile.get("description", "")

            # Check existing reference
            existing = self._find_existing(char_id)
            if existing:
                self._cache[char_id] = existing
                logger.info("CharacterRef: reusing existing reference for %r: %s",
                            char_id, existing.name)
                continue

            if not self._image_generator:
                logger.warning("CharacterRef: no image generator — skipping portrait for %r", char_id)
                continue

            # Build portrait prompt
            prompt = _PORTRAIT_TEMPLATE.format(description=description)
            dest = self.characters_dir / f"{char_id}_reference.png"

            # Create a minimal Scene object to reuse image_generator.generate_one()
            portrait_scene = Scene(
                number=0,
                narration="",
                image_prompt=prompt,
                duration_seconds=0.0,
            )

            try:
                # Temporarily override work_dir destination
                orig_work_dir = self._image_generator.work_dir
                self._image_generator.work_dir = self.characters_dir

                result = self._image_generator.generate_one(
                    portrait_scene, VisualStyle.AUTO, VideoFormat.LANDSCAPE
                )
                # Rename to canonical reference filename
                if result.exists() and result != dest:
                    result.rename(dest)
                    result = dest

                self._image_generator.work_dir = orig_work_dir
                self._cache[char_id] = result
                logger.info("CharacterRef: generated reference for %r → %s", char_id, result.name)

            except Exception as exc:
                self._image_generator.work_dir = orig_work_dir
                logger.warning("CharacterRef: portrait generation failed for %r — %s", char_id, exc)

        return dict(self._cache)

    def get_reference(self, char_id: str) -> Optional[Path]:
        """Return the reference image path for a character, or None."""
        if char_id in self._cache:
            return self._cache[char_id]
        existing = self._find_existing(char_id)
        if existing:
            self._cache[char_id] = existing
        return existing

    def get_all_references(self) -> Dict[str, Path]:
        """Return all cached character references."""
        return dict(self._cache)

    def has_reference(self, char_id: str) -> bool:
        return self.get_reference(char_id) is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_existing(self, char_id: str) -> Optional[Path]:
        """Check if a reference image already exists on disk."""
        for ext in (".png", ".jpg", ".jpeg"):
            p = self.characters_dir / f"{char_id}_reference{ext}"
            if p.exists():
                return p
        return None
