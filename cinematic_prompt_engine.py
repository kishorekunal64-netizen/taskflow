"""
cinematic_prompt_engine.py — Cinematic prompt transformation for RAGAI.

Transforms simple scene descriptions into rich cinematic prompts with
shot type rotation and lighting style variation.

Zero additional API calls — only the prompt text changes.
Controlled via ragai_advanced_config.json: enable_cinematic_prompt_engine
"""

from __future__ import annotations

import logging
import random
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shot type library
# ---------------------------------------------------------------------------

SHOT_TYPES: List[str] = [
    "cinematic wide shot",
    "dramatic close-up",
    "low-angle cinematic shot",
    "over-the-shoulder shot",
    "cinematic aerial view",
    "tracking shot perspective",
]

# ---------------------------------------------------------------------------
# Lighting style library
# ---------------------------------------------------------------------------

LIGHTING_STYLES: List[str] = [
    "golden hour lighting",
    "soft morning light",
    "dramatic sunset lighting",
    "warm cinematic lighting",
    "diffused cloudy daylight",
    "moody night lighting",
]

# Cinematic quality suffix appended to every prompt
_QUALITY_SUFFIX = (
    "cinematic storytelling, ultra realistic, film still, "
    "shallow depth of field, 4k"
)


class CinematicPromptEngine:
    """Transform scene descriptions into cinematic image prompts."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

    def enhance(self, base_prompt: str, scene_number: int = 1) -> str:
        """Wrap a base prompt with cinematic shot type and lighting.

        Args:
            base_prompt:   The original scene.image_prompt string.
            scene_number:  Used to deterministically vary shot types across scenes.

        Returns:
            Enhanced cinematic prompt string.
        """
        shot = self._pick_shot(scene_number)
        lighting = self._pick_lighting(scene_number)

        enhanced = f"{shot} of {base_prompt}, {lighting}, {_QUALITY_SUFFIX}"
        logger.debug("CinematicPrompt scene %d: %s", scene_number, enhanced[:120])
        return enhanced

    def _pick_shot(self, scene_number: int) -> str:
        """Rotate through shot types based on scene number for variety."""
        idx = (scene_number - 1) % len(SHOT_TYPES)
        # Add slight randomness — shift by a random offset seeded per scene
        offset = self._rng.randint(0, len(SHOT_TYPES) - 1)
        return SHOT_TYPES[(idx + offset) % len(SHOT_TYPES)]

    def _pick_lighting(self, scene_number: int) -> str:
        """Pick a lighting style, varying across scenes."""
        idx = self._rng.randint(0, len(LIGHTING_STYLES) - 1)
        return LIGHTING_STYLES[idx]
