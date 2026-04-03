"""
style_detector.py — Visual style detection and style configuration maps for RAGAI Video Factory.
"""

from __future__ import annotations

from typing import Dict, Optional

from models import VisualStyle


# ---------------------------------------------------------------------------
# Style configuration dictionaries
# ---------------------------------------------------------------------------

STYLE_PROMPT_MODIFIERS: Dict[VisualStyle, str] = {
    VisualStyle.DYNAMIC_EPIC: (
        "epic cinematic composition, dramatic lighting, golden hour, sweeping wide angle, "
        "heroic atmosphere, rich warm tones, volumetric god rays, ultra-detailed, 8k"
    ),
    VisualStyle.MYSTERY_DARK: (
        "dark moody atmosphere, noir lighting, deep shadows, cool desaturated palette, "
        "cinematic tension, fog and mist, chiaroscuro, dramatic contrast, 8k"
    ),
    VisualStyle.SPIRITUAL_DEVOTIONAL: (
        "divine radiant light, sacred atmosphere, soft golden glow, ethereal bokeh, "
        "devotional warmth, celestial ambiance, intricate temple architecture, 8k"
    ),
    VisualStyle.PEACEFUL_NATURE: (
        "serene natural landscape, soft diffused light, lush greenery, gentle pastel tones, "
        "tranquil atmosphere, shallow depth of field, morning mist, 8k"
    ),
    VisualStyle.ROMANTIC_DRAMA: (
        "warm romantic lighting, soft bokeh, golden hour glow, emotional depth, "
        "intimate framing, rich warm palette, cinematic drama, 8k"
    ),
    VisualStyle.ADVENTURE_ACTION: (
        "dynamic action composition, vibrant saturated colors, dramatic perspective, "
        "motion blur, high energy atmosphere, bold lighting, cinematic wide angle, 8k"
    ),
}

STYLE_COLOR_GRADE: Dict[VisualStyle, str] = {
    # DYNAMIC EPIC — warm golden tones, crushed blacks, lifted highlights, high contrast
    # Inspired by Hollywood blockbuster LUT: orange-teal split, lifted shadows
    VisualStyle.DYNAMIC_EPIC: (
        "curves=r='0/0 0.1/0.05 0.5/0.58 0.9/1.0 1/1':"
        "g='0/0 0.1/0.08 0.5/0.52 0.9/0.96 1/1':"
        "b='0/0 0.1/0.12 0.5/0.44 0.9/0.88 1/0.95',"
        "eq=contrast=1.25:saturation=1.45:brightness=-0.04,"
        "vibrance=intensity=0.3,"
        "unsharp=5:5:0.6:3:3:0.0"
    ),
    # MYSTERY DARK — deep teal shadows, desaturated mids, crushed blacks, cool highlights
    # Noir / thriller look: blue-green shadows, near-monochrome mids
    VisualStyle.MYSTERY_DARK: (
        "curves=r='0/0 0.15/0.08 0.5/0.44 0.85/0.82 1/0.92':"
        "g='0/0 0.15/0.10 0.5/0.46 0.85/0.84 1/0.94':"
        "b='0/0.04 0.15/0.16 0.5/0.54 0.85/0.88 1/1',"
        "eq=contrast=1.45:saturation=0.55:brightness=-0.12,"
        "colorbalance=rs=-0.08:gs=-0.06:bs=0.06:rm=-0.04:gm=-0.02:bm=0.04"
    ),
    # SPIRITUAL DEVOTIONAL — warm saffron-gold lift, soft glow, gentle bloom
    # Sacred / divine look: lifted shadows, warm highlights, soft contrast
    VisualStyle.SPIRITUAL_DEVOTIONAL: (
        "curves=r='0/0.06 0.3/0.38 0.6/0.68 0.85/0.92 1/1':"
        "g='0/0.04 0.3/0.34 0.6/0.62 0.85/0.88 1/0.96':"
        "b='0/0.02 0.3/0.28 0.6/0.52 0.85/0.78 1/0.86',"
        "eq=contrast=1.08:saturation=1.35:brightness=0.06,"
        "gblur=sigma=0.6"
    ),
    # PEACEFUL NATURE — clean greens, lifted shadows, airy feel, slight cool mids
    # Nature documentary look: accurate greens, open shadows, clean whites
    VisualStyle.PEACEFUL_NATURE: (
        "curves=r='0/0.02 0.4/0.40 0.7/0.72 1/1':"
        "g='0/0.03 0.4/0.44 0.7/0.76 1/1':"
        "b='0/0.03 0.4/0.42 0.7/0.72 1/0.98',"
        "eq=contrast=1.05:saturation=1.25:brightness=0.04,"
        "hue=s=1.1"
    ),
    # ROMANTIC DRAMA — warm rose-gold tones, lifted blacks, soft contrast, skin glow
    # K-drama / Bollywood romance: warm shadows, pink-peach mids, creamy highlights
    VisualStyle.ROMANTIC_DRAMA: (
        "curves=r='0/0.05 0.3/0.36 0.6/0.66 0.9/0.94 1/1':"
        "g='0/0.03 0.3/0.32 0.6/0.60 0.9/0.88 1/0.96':"
        "b='0/0.04 0.3/0.30 0.6/0.54 0.9/0.82 1/0.90',"
        "eq=contrast=1.12:saturation=1.30:brightness=0.03,"
        "colorbalance=rs=0.06:gs=0.04:bs=0.02:rm=0.04:gm=0.02:bm=0.01"
    ),
    # ADVENTURE ACTION — punchy contrast, vivid saturated, teal-orange grade
    # Marvel / action blockbuster: deep blacks, vivid primaries, orange skin, teal BG
    VisualStyle.ADVENTURE_ACTION: (
        "curves=r='0/0 0.1/0.06 0.5/0.56 0.9/1.0 1/1':"
        "g='0/0 0.1/0.08 0.5/0.50 0.9/0.94 1/1':"
        "b='0/0 0.1/0.10 0.5/0.46 0.9/0.90 1/0.96',"
        "eq=contrast=1.35:saturation=1.55:brightness=-0.05,"
        "unsharp=5:5:0.8:3:3:0.0,"
        "vibrance=intensity=0.4"
    ),
}

STYLE_MUSIC_MAP: Dict[VisualStyle, str] = {
    VisualStyle.DYNAMIC_EPIC:         "epic.mp3",
    VisualStyle.MYSTERY_DARK:         "mystery.mp3",
    VisualStyle.SPIRITUAL_DEVOTIONAL: "devotional.mp3",
    VisualStyle.PEACEFUL_NATURE:      "nature.mp3",
    VisualStyle.ROMANTIC_DRAMA:       "romantic.mp3",
    VisualStyle.ADVENTURE_ACTION:     "adventure.mp3",
}

# ---------------------------------------------------------------------------
# Keyword mapping for AUTO style detection
# ---------------------------------------------------------------------------

_KEYWORD_MAP: Dict[VisualStyle, list[str]] = {
    VisualStyle.DYNAMIC_EPIC: [
        "mythology", "history", "war", "battle", "kingdom",
        "warrior", "ancient", "empire",
    ],
    VisualStyle.MYSTERY_DARK: [
        "thriller", "detective", "horror", "mystery", "crime",
        "dark", "ghost", "murder",
    ],
    VisualStyle.SPIRITUAL_DEVOTIONAL: [
        "religious", "bhajan", "devotional", "temple", "god",
        "goddess", "prayer", "spiritual", "mandir",
    ],
    VisualStyle.PEACEFUL_NATURE: [
        "children", "nature", "calm", "village", "forest",
        "river", "peaceful", "innocent",
    ],
    VisualStyle.ROMANTIC_DRAMA: [
        "love", "romance", "family", "drama", "emotional",
        "wedding", "heart", "relationship",
    ],
    VisualStyle.ADVENTURE_ACTION: [
        "action", "adventure", "fantasy", "journey", "quest",
        "hero", "magic", "travel",
    ],
}


# ---------------------------------------------------------------------------
# StyleDetector
# ---------------------------------------------------------------------------

class StyleDetector:
    """Detects the best-matching VisualStyle for a given topic string."""

    def detect(self, topic: str) -> VisualStyle:
        """Analyse topic text and return the best matching VisualStyle.

        If the style cannot be determined from keywords, falls back to
        DYNAMIC_EPIC as a sensible cinematic default.
        """
        matched = self._keyword_match(topic)
        if matched is not None:
            return matched
        return VisualStyle.DYNAMIC_EPIC

    def _keyword_match(self, topic: str) -> Optional[VisualStyle]:
        """Return the VisualStyle whose keywords best match the topic, or None.

        Scoring is based on the count of keyword hits; the style with the
        highest score wins. Ties are broken by dict insertion order.
        """
        lower = topic.lower()
        best_style: Optional[VisualStyle] = None
        best_score = 0

        for style, keywords in _KEYWORD_MAP.items():
            score = sum(1 for kw in keywords if kw in lower)
            if score > best_score:
                best_score = score
                best_style = style

        return best_style if best_score > 0 else None
