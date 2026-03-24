"""
variation_engine.py — Content variation for RAGAI Editor V2.

Randomises narrator voices, background music, story order, hook styles,
and transitions to avoid repetitive compilations.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional

from clip_manager import Clip

# ---------------------------------------------------------------------------
# Voice variants (Edge-TTS Hindi voices)
# ---------------------------------------------------------------------------

HINDI_VOICES = [
    "hi-IN-SwaraNeural",    # female, natural
    "hi-IN-MadhurNeural",   # male, warm
]

# ---------------------------------------------------------------------------
# Hook style variants
# ---------------------------------------------------------------------------

HOOK_STYLES = [
    "dramatic and emotional",
    "curious and mysterious",
    "inspiring and uplifting",
    "warm and storytelling",
    "energetic and exciting",
]

# ---------------------------------------------------------------------------
# Transition variants
# ---------------------------------------------------------------------------

TRANSITIONS = [
    "Cut",
    "Dissolve 0.5s",
    "Dissolve 1s",
    "Dissolve 2s",
    "Fade Black 1s",
]

# Weighted so Cut and Dissolve 1s are most common
_TRANSITION_WEIGHTS = [3, 2, 3, 1, 1]


class VariationEngine:
    """Provides randomised variation choices for each compilation run."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def pick_voice(self) -> str:
        """Return a random Hindi narrator voice."""
        return self._rng.choice(HINDI_VOICES)

    def pick_music(self, music_dir: Path) -> Optional[Path]:
        """Return a random .mp3 from music_dir."""
        tracks = list(music_dir.glob("*.mp3"))
        if not tracks:
            return None
        return self._rng.choice(tracks)

    def shuffle_clips(self, clips: List[Clip]) -> List[Clip]:
        """Return a shuffled copy of the clip list."""
        shuffled = list(clips)
        self._rng.shuffle(shuffled)
        return shuffled

    def pick_hook_style(self) -> str:
        """Return a random hook style string."""
        return self._rng.choice(HOOK_STYLES)

    def pick_transition(self) -> str:
        """Return a weighted-random transition name."""
        return self._rng.choices(TRANSITIONS, weights=_TRANSITION_WEIGHTS, k=1)[0]

    def assign_transitions(self, clip_count: int) -> List[str]:
        """
        Return a list of transition names, one per clip.
        First clip is always 'Cut' (no transition before it).
        """
        result = ["Cut"]
        for _ in range(clip_count - 1):
            result.append(self.pick_transition())
        return result

    def pick_outro_variant(self) -> int:
        """Return an index for OutroGenerator text variants."""
        return self._rng.randint(0, 2)
