"""
music_selector.py — Smart BGM selection for RAGAI Video Factory.

Scores all available music tracks against the story topic and visual style
using a keyword-mood matrix, then returns the best-matching track path.

Priority order:
  1. User-supplied custom_music_path (if set and file exists)
  2. Topic keyword scoring across all available tracks
  3. Style-based fallback (STYLE_MUSIC_MAP)
  4. neutral.mp3 as last resort
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from models import VisualStyle
from style_detector import STYLE_MUSIC_MAP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mood keyword matrix
# Each track filename maps to a list of topic keywords that match its mood.
# Scores are additive — more keyword hits = higher score.
# ---------------------------------------------------------------------------

_TRACK_KEYWORDS: Dict[str, List[str]] = {
    "epic.mp3": [
        "war", "battle", "warrior", "kingdom", "empire", "mythology", "legend",
        "hero", "king", "queen", "throne", "sword", "army", "victory", "conquest",
        "ancient", "history", "mahabharata", "ramayana", "shivaji", "akbar",
        "fight", "power", "glory", "triumph", "epic",
    ],
    "mystery.mp3": [
        "mystery", "thriller", "detective", "crime", "murder", "ghost", "horror",
        "dark", "shadow", "secret", "spy", "investigation", "suspense", "noir",
        "haunted", "curse", "unknown", "hidden", "conspiracy", "danger",
    ],
    "devotional.mp3": [
        "god", "goddess", "temple", "prayer", "bhajan", "devotional", "spiritual",
        "divine", "sacred", "mandir", "puja", "krishna", "rama", "shiva", "durga",
        "ganesh", "hanuman", "religious", "faith", "blessing", "holy", "worship",
        "radha", "gauri", "devi", "bhakti", "aarti",
    ],
    "nature.mp3": [
        "nature", "forest", "river", "mountain", "village", "peaceful", "calm",
        "serene", "garden", "flower", "tree", "rain", "sunrise", "sunset",
        "children", "innocent", "pure", "countryside", "meadow", "waterfall",
        "birds", "animals", "wildlife", "environment",
    ],
    "romantic.mp3": [
        "love", "romance", "wedding", "couple", "heart", "relationship", "drama",
        "emotional", "family", "marriage", "girlfriend", "boyfriend", "husband",
        "wife", "passion", "longing", "separation", "reunion", "bollywood",
        "song", "dance", "celebration", "festival",
    ],
    "adventure.mp3": [
        "adventure", "journey", "quest", "travel", "explore", "discovery",
        "magic", "fantasy", "dragon", "treasure", "pirate", "space", "sci-fi",
        "future", "robot", "alien", "mission", "escape", "survival", "challenge",
        "sport", "race", "competition", "action",
    ],
    "neutral.mp3": [
        "story", "life", "people", "world", "time", "day", "work", "school",
        "city", "town", "news", "documentary", "education", "learning",
    ],
}

# Style → preferred track (used as a tiebreaker / bonus score)
_STYLE_BONUS: Dict[VisualStyle, str] = {
    VisualStyle.DYNAMIC_EPIC:         "epic.mp3",
    VisualStyle.MYSTERY_DARK:         "mystery.mp3",
    VisualStyle.SPIRITUAL_DEVOTIONAL: "devotional.mp3",
    VisualStyle.PEACEFUL_NATURE:      "nature.mp3",
    VisualStyle.ROMANTIC_DRAMA:       "romantic.mp3",
    VisualStyle.ADVENTURE_ACTION:     "adventure.mp3",
}


class MusicSelector:
    """Selects the best-matching BGM track for a given topic and style."""

    def __init__(self, music_dir: Path) -> None:
        self.music_dir = Path(music_dir)

    def select(
        self,
        topic: str,
        style: VisualStyle,
        custom_path: Optional[str] = None,
    ) -> Tuple[Optional[Path], str]:
        """Return (music_path, reason_string).

        Args:
            topic: The video topic / story description.
            style: The resolved VisualStyle (not AUTO).
            custom_path: User-supplied override path (optional).

        Returns:
            Tuple of (Path or None, human-readable reason).
        """
        # 1. User override
        if custom_path:
            p = Path(custom_path)
            if p.exists() and p.is_file():
                logger.info("BGM: using custom file %s", p)
                return p, f"Custom: {p.name}"
            else:
                logger.warning("BGM: custom path not found: %s — falling back to auto", custom_path)

        # 2. Score all available tracks against topic keywords
        scores = self._score_tracks(topic, style)
        logger.info("BGM scores: %s", scores)

        # Pick highest-scoring track that actually exists on disk
        for track_name, score in sorted(scores.items(), key=lambda x: -x[1]):
            p = self.music_dir / track_name
            if p.exists():
                reason = f"Auto-matched: {track_name} (score {score})"
                logger.info("BGM selected: %s", reason)
                return p, reason

        # 3. Style fallback
        fallback_name = STYLE_MUSIC_MAP.get(style, "neutral.mp3")
        p = self.music_dir / fallback_name
        if p.exists():
            return p, f"Style fallback: {fallback_name}"

        # 4. neutral.mp3
        p = self.music_dir / "neutral.mp3"
        if p.exists():
            return p, "Default: neutral.mp3"

        return None, "No music found"

    def _score_tracks(self, topic: str, style: VisualStyle) -> Dict[str, float]:
        """Score each track by keyword hits in topic + style bonus."""
        lower = topic.lower()
        scores: Dict[str, float] = {}

        for track, keywords in _TRACK_KEYWORDS.items():
            score = sum(1.0 for kw in keywords if kw in lower)
            # Style bonus: +2 for the preferred track of this style
            if _STYLE_BONUS.get(style) == track:
                score += 2.0
            scores[track] = score

        return scores

    def available_tracks(self) -> List[str]:
        """Return list of track filenames present in music_dir."""
        return [p.name for p in sorted(self.music_dir.glob("*.mp3"))]
