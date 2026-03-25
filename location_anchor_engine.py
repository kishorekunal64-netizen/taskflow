"""
location_anchor_engine.py — Location consistency across scenes for RAGAI.

Maintains consistent environment descriptions within a story so the same
location looks the same in every scene that references it.

Controlled via ragai_advanced_config.json: enable_location_anchor
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default location profiles
# ---------------------------------------------------------------------------

DEFAULT_LOCATIONS: Dict[str, str] = {
    "village":  "small rural Indian village surrounded by wheat fields, mud houses, narrow dirt roads, banyan trees",
    "temple":   "ancient stone temple in a quiet village surrounded by trees and oil lamps",
    "farm":     "golden wheat field stretching across the countryside under open sky",
    "school":   "simple village school building with a courtyard, children playing outside",
    "city":     "busy Indian city street with traffic, shops, and tall buildings",
    "forest":   "dense green forest with tall trees, dappled sunlight filtering through leaves",
    "river":    "peaceful river bank with green grass, trees, and flowing water",
    "home":     "modest Indian rural home with a small courtyard, clay walls, and a tulsi plant",
    "office":   "government office interior with wooden desks, files, and Indian decor",
    "hospital": "clean hospital corridor with white walls, nurses, and medical equipment",
    "mountain": "rugged mountain landscape with rocky terrain and misty peaks",
    "market":   "vibrant Indian village market with colorful stalls and busy crowds",
}

# Keywords that trigger location anchor injection
_LOCATION_TRIGGERS: Dict[str, List[str]] = {
    "village":  ["village", "गाँव", "gaon"],
    "temple":   ["temple", "mandir", "मंदिर"],
    "farm":     ["farm", "field", "wheat", "खेत", "फसल"],
    "school":   ["school", "classroom", "स्कूल", "विद्यालय"],
    "city":     ["city", "town", "शहर"],
    "forest":   ["forest", "jungle", "जंगल"],
    "river":    ["river", "nadi", "नदी"],
    "home":     ["home", "house", "घर"],
    "office":   ["office", "government", "दफ्तर"],
    "hospital": ["hospital", "clinic", "अस्पताल"],
    "mountain": ["mountain", "hill", "पहाड़"],
    "market":   ["market", "bazaar", "बाजार"],
}


class LocationAnchorEngine:
    """Maintain consistent location descriptions within a story session."""

    def __init__(self) -> None:
        self._locations: Dict[str, str] = dict(DEFAULT_LOCATIONS)
        self._used: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_location(self, location_key: str, description: str) -> None:
        """Override a location description for this session."""
        self._locations[location_key] = description
        logger.info("LocationAnchor: location set for %r", location_key)

    def get_location(self, location_key: str) -> Optional[str]:
        return self._locations.get(location_key)

    def inject(self, prompt: str, scene_number: int = 1) -> str:
        """Detect locations referenced in prompt and inject anchor descriptions.

        Args:
            prompt:       The current image prompt string.
            scene_number: Used for logging only.

        Returns:
            Prompt with location anchor appended, or original if no match.
        """
        prompt_lower = prompt.lower()
        matched: List[str] = []

        for loc_key, triggers in _LOCATION_TRIGGERS.items():
            for trigger in triggers:
                if trigger.lower() in prompt_lower:
                    anchor = self._locations.get(loc_key)
                    if anchor and anchor not in matched:
                        matched.append(anchor)
                        self._used[loc_key] = self._used.get(loc_key, 0) + 1
                    break

        if not matched:
            return prompt

        # Append location context after the main prompt
        loc_str = ", ".join(matched)
        result = f"{prompt}, {loc_str}"
        logger.debug("LocationAnchor scene %d: injected %d location(s)", scene_number, len(matched))
        return result

    def reset_session(self) -> None:
        self._used.clear()

    def session_stats(self) -> Dict[str, int]:
        return dict(self._used)
