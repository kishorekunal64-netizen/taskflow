"""
music_selector.py — Smart BGM selection for RAGAI Video Factory.

Priority order:
  1. User-supplied custom_music_path (if set and file exists)
  2. Procedural BGM (procedural_bgm_engine.generate_bgm) — copyright-free
  3. Topic keyword scoring across all available tracks in music/
  4. Style-based fallback (STYLE_MUSIC_MAP)
  5. neutral.mp3 as last resort
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
        bgm_mode: str = "auto",
        duration: float = 60.0,
    ) -> Tuple[Optional[Path], str]:
        """Return (music_path, reason_string).

        Args:
            topic: The video topic / story description.
            style: The resolved VisualStyle (not AUTO).
            custom_path: User-supplied override path (optional).
            bgm_mode: "auto" | "procedural" | "custom" | "off"
            duration: Target BGM duration in seconds (for procedural).

        Returns:
            Tuple of (Path or None, human-readable reason).
        """
        # 0. Off
        if bgm_mode == "off":
            return None, "BGM disabled"

        # 1. User override / custom mode
        if custom_path or bgm_mode == "custom":
            if custom_path:
                p = Path(custom_path)
                if p.exists() and p.is_file():
                    logger.info("BGM: using custom file %s", p)
                    return p, f"Custom: {p.name}"
                else:
                    logger.warning("BGM: custom path not found: %s — falling back", custom_path)

        # 2. Procedural BGM (auto or procedural mode)
        if bgm_mode in ("auto", "procedural"):
            try:
                from procedural_bgm_engine import generate_bgm
                bgm_path = generate_bgm(style, duration=duration)
                if bgm_path and bgm_path.exists():
                    return bgm_path, f"Procedural: {bgm_path.name}"
            except Exception as exc:
                logger.warning("Procedural BGM failed: %s — falling back to music/ folder", exc)

        # 3. Score all available tracks against topic keywords
        scores = self._score_tracks(topic, style)
        logger.info("BGM scores: %s", scores)

        for track_name, score in sorted(scores.items(), key=lambda x: -x[1]):
            p = self.music_dir / track_name
            if p.exists():
                reason = f"Auto-matched: {track_name} (score {score})"
                logger.info("BGM selected: %s", reason)
                return p, reason

        # 4. Style fallback
        fallback_name = STYLE_MUSIC_MAP.get(style, "neutral.mp3")
        p = self.music_dir / fallback_name
        if p.exists():
            return p, f"Style fallback: {fallback_name}"

        # 5. neutral.mp3
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
