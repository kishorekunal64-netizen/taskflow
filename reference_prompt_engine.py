"""
reference_prompt_engine.py — Reference-based character prompt injection for RAGAI.

Injects "same character from reference image" language into scene prompts
when character references exist. This is the strongest available signal
for text-to-image models to maintain character consistency.

When enable_reference_conditioning is True and a reference image exists,
the reference path is also stored on the Scene for API-level conditioning
(Leonardo AI supports init_image / character reference via their API).

Controlled via: enable_character_reference_system, enable_reference_conditioning
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from character_anchor_engine import _CHARACTER_TRIGGERS

logger = logging.getLogger(__name__)

# Phrase injected when a character reference exists
_REFERENCE_PHRASE = "the same {role} as shown in the reference image"

# Phrase used when no reference image exists (fallback to description)
_DESCRIPTION_PHRASE = "{description}"


class ReferencePromptEngine:
    """Inject character reference language into scene prompts."""

    def __init__(
        self,
        references: Optional[Dict[str, Path]] = None,
        profiles: Optional[List[Dict]] = None,
        enable_conditioning: bool = True,
    ) -> None:
        """
        Args:
            references:           Dict of char_id → reference image Path.
            profiles:             List of character profile dicts.
            enable_conditioning:  If True, store reference path on scene for API use.
        """
        self._references: Dict[str, Path] = references or {}
        self._enable_conditioning = enable_conditioning

        # Build role → profile lookup
        self._role_to_profile: Dict[str, Dict] = {}
        for p in (profiles or []):
            self._role_to_profile[p["role"]] = p

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_references(self, references: Dict[str, Path]) -> None:
        """Update the reference image map (called after portrait generation)."""
        self._references.update(references)

    def inject(self, prompt: str, scene_number: int = 1) -> str:
        """Inject reference-based character language into a scene prompt.

        For each character detected in the prompt:
          - If a reference image exists: inject "same X as in reference image"
          - If no reference: fall back to description anchor (existing behaviour)

        Args:
            prompt:       The current image prompt string.
            scene_number: Used for logging only.

        Returns:
            Enhanced prompt string.
        """
        prompt_lower = prompt.lower()
        injections: List[str] = []

        for role, triggers in _CHARACTER_TRIGGERS.items():
            for trigger in triggers:
                if trigger.lower() in prompt_lower:
                    profile = self._role_to_profile.get(role)
                    if not profile:
                        break

                    char_id = profile["id"]
                    ref_path = self._references.get(char_id)

                    if ref_path and ref_path.exists():
                        phrase = _REFERENCE_PHRASE.format(role=role)
                        injections.append(phrase)
                        logger.debug("ReferencePrompt scene %d: reference injection for %r",
                                     scene_number, role)
                    else:
                        # Fallback to description
                        desc = profile.get("description", "")
                        if desc:
                            injections.append(desc)
                    break

        if not injections:
            return prompt

        injection_str = ", ".join(injections)
        result = f"{injection_str}, {prompt}"
        logger.debug("ReferencePrompt scene %d → %s", scene_number, result[:140])
        return result

    def get_reference_path(self, role: str) -> Optional[Path]:
        """Return the reference image path for a role, or None."""
        profile = self._role_to_profile.get(role)
        if not profile:
            return None
        return self._references.get(profile["id"])

    def has_any_references(self) -> bool:
        return bool(self._references)
