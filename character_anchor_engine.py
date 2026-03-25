"""
character_anchor_engine.py — Character consistency across scenes for RAGAI.

Maintains a per-story character profile registry so the same character
description is reused in every scene that references that character.

Controlled via ragai_advanced_config.json: enable_character_anchor
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default character profile templates
# ---------------------------------------------------------------------------

DEFAULT_CHARACTER_PROFILES: Dict[str, str] = {
    "farmer":   "young Indian farmer, mid-30s, brown skin, short black hair, thin mustache, wearing a white kurta and brown dhoti",
    "girl":     "young village girl, 14 years old, long black hair, brown skin, wearing a simple blue school uniform",
    "teacher":  "elderly village teacher, grey hair, glasses, white beard, wearing a traditional white kurta",
    "mother":   "Indian village woman, 50s, grey-streaked hair tied in a bun, wearing a simple cotton saree",
    "officer":  "IAS officer, formal attire, confident posture, mid-30s, Indian features",
    "doctor":   "young Indian doctor, white coat, stethoscope, confident expression",
    "soldier":  "Indian soldier, military uniform, strong build, determined expression",
    "child":    "young Indian child, 8-10 years old, bright eyes, simple school clothes",
    "elder":    "elderly Indian man, 70s, white dhoti, walking stick, wise expression",
    "woman":    "Indian woman, 30s, traditional saree, graceful posture",
}

# Keywords that trigger character anchor injection
_CHARACTER_TRIGGERS: Dict[str, List[str]] = {
    "farmer":  ["farmer", "kisan", "खेत", "किसान"],
    "girl":    ["girl", "daughter", "student", "लड़की", "बेटी"],
    "teacher": ["teacher", "guru", "शिक्षक", "गुरु"],
    "mother":  ["mother", "mom", "माँ", "माता"],
    "officer": ["officer", "ias", "collector", "अधिकारी"],
    "doctor":  ["doctor", "डॉक्टर"],
    "soldier": ["soldier", "army", "सैनिक"],
    "child":   ["child", "boy", "बच्चा"],
    "elder":   ["elder", "old man", "बुजुर्ग"],
    "woman":   ["woman", "महिला"],
}


class CharacterAnchorEngine:
    """Maintain consistent character descriptions within a story session."""

    def __init__(self) -> None:
        # Session profiles — can be overridden per story
        self._profiles: Dict[str, str] = dict(DEFAULT_CHARACTER_PROFILES)
        # Track which characters have appeared (for logging)
        self._used: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_profile(self, character_key: str, description: str) -> None:
        """Override a character profile for this session."""
        self._profiles[character_key] = description
        logger.info("CharacterAnchor: profile set for %r", character_key)

    def get_profile(self, character_key: str) -> Optional[str]:
        """Return the profile for a character key, or None."""
        return self._profiles.get(character_key)

    def inject(self, prompt: str, scene_number: int = 1) -> str:
        """Detect characters referenced in prompt and inject anchor descriptions.

        Scans the prompt for character trigger keywords and prepends the
        matching anchor description to ensure visual consistency.

        Args:
            prompt:       The current image prompt string.
            scene_number: Used for logging only.

        Returns:
            Prompt with character anchor injected, or original if no match.
        """
        prompt_lower = prompt.lower()
        matched_anchors: List[str] = []

        for char_key, triggers in _CHARACTER_TRIGGERS.items():
            for trigger in triggers:
                if trigger.lower() in prompt_lower:
                    anchor = self._profiles.get(char_key)
                    if anchor and anchor not in matched_anchors:
                        matched_anchors.append(anchor)
                        self._used[char_key] = self._used.get(char_key, 0) + 1
                    break  # one match per character is enough

        if not matched_anchors:
            return prompt

        # Prepend character anchors to the prompt
        anchor_str = ", ".join(matched_anchors)
        result = f"{anchor_str}, {prompt}"
        logger.debug("CharacterAnchor scene %d: injected %d anchor(s)", scene_number, len(matched_anchors))
        return result

    def reset_session(self) -> None:
        """Reset usage tracking for a new story session."""
        self._used.clear()
        logger.debug("CharacterAnchor: session reset")

    def session_stats(self) -> Dict[str, int]:
        return dict(self._used)
