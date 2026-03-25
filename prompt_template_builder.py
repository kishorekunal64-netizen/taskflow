"""
prompt_template_builder.py — Cinematic prompt assembly for RAGAI.

Assembles the final image prompt from all cinematic components:
  shot_type + character_anchor/reference + scene_action + location_anchor + lighting_style

This is the single entry point used by image_generator._build_prompt()
when the cinematic prompt engine is enabled.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from models import Scene, VisualStyle
from cinematic_prompt_engine import CinematicPromptEngine
from character_anchor_engine import CharacterAnchorEngine
from location_anchor_engine import LocationAnchorEngine

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("ragai_advanced_config.json")


def _load_flags() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


class PromptTemplateBuilder:
    """Assemble cinematic prompts from modular components."""

    def __init__(self, seed: Optional[int] = None) -> None:
        flags = _load_flags()
        self._enable_cinematic   = flags.get("enable_cinematic_prompt_engine", True)
        self._enable_character   = flags.get("enable_character_anchor", True)
        self._enable_location    = flags.get("enable_location_anchor", True)
        self._enable_ref_system  = flags.get("enable_character_reference_system", True)
        self._enable_ref_cond    = flags.get("enable_reference_conditioning", True)

        self._cinematic  = CinematicPromptEngine(seed=seed)
        self._characters = CharacterAnchorEngine()
        self._locations  = LocationAnchorEngine()

        # Reference prompt engine — activated after portrait generation
        self._ref_engine = None

    # ------------------------------------------------------------------
    # Reference system integration
    # ------------------------------------------------------------------

    def activate_reference_engine(
        self,
        references: Dict,
        profiles: List[Dict],
    ) -> None:
        """Activate reference-based character injection.

        Called by the pipeline after CharacterReferenceManager.generate_references().

        Args:
            references: Dict of char_id → Path from CharacterReferenceManager.
            profiles:   List of profile dicts from CharacterProfileGenerator.
        """
        if not self._enable_ref_system:
            return
        from reference_prompt_engine import ReferencePromptEngine
        self._ref_engine = ReferencePromptEngine(
            references=references,
            profiles=profiles,
            enable_conditioning=self._enable_ref_cond,
        )
        logger.info("PromptTemplateBuilder: reference engine activated (%d refs)",
                    len(references))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, scene: Scene, style_modifier: str = "") -> str:
        """Build the final image prompt for a scene."""
        base = scene.image_prompt.strip()

        # 1. Reference-based character injection (takes priority over anchor)
        if self._enable_ref_system and self._ref_engine and self._ref_engine.has_any_references():
            base = self._ref_engine.inject(base, scene.number)
        elif self._enable_character:
            # Fallback: text-only character anchor
            base = self._characters.inject(base, scene.number)

        # 2. Location anchor injection
        if self._enable_location:
            base = self._locations.inject(base, scene.number)

        # 3. Cinematic shot + lighting wrap
        if self._enable_cinematic:
            base = self._cinematic.enhance(base, scene.number)

        # 4. Append style modifier
        if style_modifier:
            base = f"{base}, {style_modifier}"

        logger.debug("PromptBuilder scene %d → %s", scene.number, base[:140])
        return base

    def reset_session(self) -> None:
        """Reset character and location tracking for a new story."""
        self._characters.reset_session()
        self._locations.reset_session()
        self._ref_engine = None

    def session_stats(self) -> dict:
        return {
            "characters": self._characters.session_stats(),
            "locations":  self._locations.session_stats(),
            "references": len(self._ref_engine._references) if self._ref_engine else 0,
        }
