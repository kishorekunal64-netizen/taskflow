"""
narrative_variation_engine.py - Prevent repetitive storytelling in RAGAI.

Provides 5 narrative structure templates. The scheduler/story_generator
calls pick_structure() to get a random (non-repeating) template and
injects it into the LLM prompt to vary story shape across generations.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structure definitions
# ---------------------------------------------------------------------------

@dataclass
class NarrativeStructure:
    name: str
    code: str          # short identifier used in prompts
    description: str
    prompt_instruction: str
    acts: List[str]


_STRUCTURES: List[NarrativeStructure] = [
    NarrativeStructure(
        name="Problem to Success",
        code="A",
        description="Classic underdog arc",
        prompt_instruction=(
            "Structure the story as: "
            "1) Introduce a serious problem the character faces. "
            "2) Show the struggle and hardship in detail. "
            "3) End with a triumphant success that feels earned."
        ),
        acts=["Problem", "Struggle", "Success"],
    ),
    NarrativeStructure(
        name="Mystery Reveal",
        code="B",
        description="Curiosity-driven mystery arc",
        prompt_instruction=(
            "Structure the story as: "
            "1) Open with an intriguing mystery or unexplained event. "
            "2) Gradually reveal clues and build suspense. "
            "3) End with a satisfying reveal and a life lesson."
        ),
        acts=["Mystery", "Reveal", "Lesson"],
    ),
    NarrativeStructure(
        name="Conflict Resolution",
        code="C",
        description="Emotional conflict arc",
        prompt_instruction=(
            "Structure the story as: "
            "1) Establish a deep conflict between characters or forces. "
            "2) Build to an emotional peak — the most intense moment. "
            "3) Resolve the conflict in a meaningful, emotional way."
        ),
        acts=["Conflict", "Emotional Peak", "Resolution"],
    ),
    NarrativeStructure(
        name="Character Twist",
        code="D",
        description="Character-driven twist arc",
        prompt_instruction=(
            "Structure the story as: "
            "1) Introduce a compelling character with a clear goal. "
            "2) Introduce an unexpected twist that changes everything. "
            "3) End with a moral or insight the character (and viewer) learns."
        ),
        acts=["Introduction", "Twist", "Moral"],
    ),
    NarrativeStructure(
        name="Investigation",
        code="E",
        description="Event-driven investigation arc",
        prompt_instruction=(
            "Structure the story as: "
            "1) Begin with an unexpected or shocking event. "
            "2) Follow the investigation or journey to understand it. "
            "3) Arrive at a resolution that brings closure."
        ),
        acts=["Unexpected Event", "Investigation", "Resolution"],
    ),
]

_CODE_MAP: Dict[str, NarrativeStructure] = {s.code: s for s in _STRUCTURES}

# Track last used to avoid immediate repetition
_last_code: Optional[str] = None


class NarrativeVariationEngine:
    """
    Selects narrative structures for story generation.
    Avoids repeating the same structure back-to-back.
    """

    def pick_structure(self, exclude_code: Optional[str] = None) -> NarrativeStructure:
        """Return a random structure, avoiding the last used one."""
        global _last_code
        exclude = exclude_code or _last_code
        choices = [s for s in _STRUCTURES if s.code != exclude]
        if not choices:
            choices = _STRUCTURES
        structure = random.choice(choices)
        _last_code = structure.code
        logger.info("Narrative structure selected: %s (%s)", structure.name, structure.code)
        return structure

    def get_structure(self, code: str) -> Optional[NarrativeStructure]:
        """Get a specific structure by code (A-E)."""
        return _CODE_MAP.get(code.upper())

    def all_structures(self) -> List[NarrativeStructure]:
        return list(_STRUCTURES)

    def build_prompt_suffix(self, topic: str, language: str = "hi") -> str:
        """
        Return a full prompt suffix combining topic + narrative structure.
        Inject this into the LLM story generation prompt.
        """
        structure = self.pick_structure()
        lang_note = "Write in Hindi (Devanagari script)." if language == "hi" else f"Write in {language}."
        suffix = (
            f"\n\nTopic: {topic}\n"
            f"Narrative Structure ({structure.code} - {structure.name}):\n"
            f"{structure.prompt_instruction}\n"
            f"Acts: {' → '.join(structure.acts)}\n"
            f"{lang_note}"
        )
        logger.debug("Prompt suffix built for structure %s", structure.code)
        return suffix
