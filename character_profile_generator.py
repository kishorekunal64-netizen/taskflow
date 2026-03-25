"""
character_profile_generator.py — Detect and generate structured character profiles for RAGAI.

Scans story scenes to identify main characters and builds structured
profiles stored in characters.json. Profiles feed into the character
reference manager for portrait generation.

Controlled via: enable_character_reference_system in ragai_advanced_config.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from models import Scene
from character_anchor_engine import DEFAULT_CHARACTER_PROFILES, _CHARACTER_TRIGGERS

logger = logging.getLogger(__name__)

_CHARACTERS_JSON = Path("characters.json")


# ---------------------------------------------------------------------------
# Character profile dataclass (plain dict for JSON serialisability)
# ---------------------------------------------------------------------------

def _make_profile(char_id: str, role: str, description: str) -> Dict:
    return {
        "id":          char_id,
        "role":        role,
        "description": description,
        "reference_image": None,   # filled by CharacterReferenceManager
    }


class CharacterProfileGenerator:
    """Detect main characters from story scenes and build structured profiles."""

    def __init__(self, output_path: Path = _CHARACTERS_JSON) -> None:
        self.output_path = Path(output_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_from_scenes(self, scenes: List[Scene], story_id: str = "") -> List[Dict]:
        """Scan scenes, detect characters, return profile list.

        Args:
            scenes:   List of Scene objects from story_generator.
            story_id: Optional story identifier for namespacing character IDs.

        Returns:
            List of character profile dicts.
        """
        detected: Dict[str, Dict] = {}

        for scene in scenes:
            text = (scene.narration + " " + scene.image_prompt).lower()
            for role, triggers in _CHARACTER_TRIGGERS.items():
                if role in detected:
                    continue
                for trigger in triggers:
                    if trigger.lower() in text:
                        char_id = f"{role}_{story_id}" if story_id else role
                        description = DEFAULT_CHARACTER_PROFILES.get(role, f"Indian {role}")
                        detected[role] = _make_profile(char_id, role, description)
                        logger.info("CharacterProfileGenerator: detected %r in scene %d",
                                    role, scene.number)
                        break

        profiles = list(detected.values())
        self._save(profiles)
        logger.info("CharacterProfileGenerator: %d profiles saved to %s",
                    len(profiles), self.output_path)
        return profiles

    def load(self) -> List[Dict]:
        """Load existing profiles from characters.json."""
        if not self.output_path.exists():
            return []
        try:
            return json.loads(self.output_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("CharacterProfileGenerator: failed to load %s — %s",
                           self.output_path, exc)
            return []

    def update_reference(self, char_id: str, reference_path: str) -> None:
        """Update the reference_image field for a character profile."""
        profiles = self.load()
        for p in profiles:
            if p["id"] == char_id:
                p["reference_image"] = reference_path
                break
        self._save(profiles)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save(self, profiles: List[Dict]) -> None:
        self.output_path.write_text(
            json.dumps(profiles, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
