"""
viral_scorer.py — Score topics for viral potential for RAGAI Trend Booster.

Scoring factors:
  1. Trend velocity (how many sources picked it up)
  2. Emotional triggers (love, fear, surprise, inspiration, anger)
  3. Hindi content performance patterns (devotional, family, drama)

Returns a score 1-10 with suggested title format, thumbnail style, and hook line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


# ---------------------------------------------------------------------------
# Emotional trigger word banks
# ---------------------------------------------------------------------------

_TRIGGERS: dict[str, list[str]] = {
    "love":        ["love", "romance", "pyaar", "mohabbat", "dil", "heart", "couple", "wedding", "shaadi"],
    "fear":        ["fear", "danger", "scary", "horror", "dark", "death", "maut", "bhoot", "ghost", "accident"],
    "surprise":    ["shocking", "unbelievable", "viral", "secret", "hidden", "revealed", "exposed", "truth", "sach"],
    "inspiration": ["inspire", "success", "motivat", "achieve", "dream", "sapna", "hero", "champion", "winner"],
    "anger":       ["injustice", "unfair", "corrupt", "scam", "fraud", "cheating", "betrayal", "dhoka"],
    "curiosity":   ["why", "how", "what", "mystery", "rahasya", "unknown", "strange", "ajeeb", "weird"],
    "pride":       ["india", "bharat", "desh", "national", "culture", "tradition", "heritage", "proud"],
    "empowerment": ["women", "girl", "mahila", "nari", "shakti", "power", "freedom", "azaadi", "rights"],
}

# Hindi content performance multipliers
_HINDI_BOOST: dict[str, float] = {
    "devotional": 1.3,   # devotional content performs very well
    "family":     1.2,
    "drama":      1.2,
    "comedy":     1.1,
    "news":       1.15,
    "education":  1.0,
}

# Title format templates by dominant emotion
_TITLE_FORMATS: dict[str, str] = {
    "love":        "💕 {topic} — Dil Ko Chhu Lene Wali Kahani",
    "fear":        "😱 {topic} — Sach Jankar Aap Hairan Ho Jayenge!",
    "surprise":    "🔥 {topic} — Yeh Sach Kisi Ne Nahi Bataya!",
    "inspiration": "⚡ {topic} — Ek Aisi Kahani Jo Zindagi Badal De",
    "anger":       "😤 {topic} — Yeh Sach Sunna Zaroori Hai",
    "curiosity":   "🤔 {topic} — Aakhir Kyun? Poori Kahani Jaaniye",
    "pride":       "🇮🇳 {topic} — Bharat Ki Shaan",
    "empowerment": "💪 {topic} — Naari Shakti Ki Kahani",
    "default":     "🎬 {topic} — Ek Alag Andaaz Ki Kahani",
}

_THUMBNAIL_STYLES: dict[str, str] = {
    "love":        "Warm golden tones, couple silhouette, soft bokeh background",
    "fear":        "Dark dramatic lighting, high contrast, mysterious shadows",
    "surprise":    "Bold red/yellow text overlay, shocked expression, bright background",
    "inspiration": "Sunrise/mountain backdrop, silhouette pose, motivational text",
    "anger":       "High contrast, red accents, serious face close-up",
    "curiosity":   "Question mark graphic, intriguing blurred background, bold text",
    "pride":       "Tricolor accents, heritage imagery, proud expression",
    "empowerment": "Strong confident pose, vibrant colors, empowering text",
    "default":     "Cinematic wide shot, bold title text, high contrast",
}

_HOOK_LINES: dict[str, str] = {
    "love":        "Yeh kahani aapka dil pighla degi — ek baar zaroor dekhiye...",
    "fear":        "Yeh sach jaankar aapki raat ki neend ud jayegi...",
    "surprise":    "Kya aap jaante hain? Yeh baat aaj tak kisi ne nahi batai...",
    "inspiration": "Ek insaan ki himmat ne poori duniya ko badal diya...",
    "anger":       "Yeh sach sunna aapka haq hai — aur aaj hum batayenge...",
    "curiosity":   "Ek aisa rahasya jo sadiyon se chhupa tha — aaj khulega...",
    "pride":       "Bharat ki is kahani par aapko garv hoga...",
    "empowerment": "Yeh ladki ne woh kar dikhaya jo sab impossible samajhte the...",
    "default":     "Ek aisi kahani jo aapne pehle kabhi nahi suni...",
}


# ---------------------------------------------------------------------------
# Public data class
# ---------------------------------------------------------------------------

@dataclass
class ViralScore:
    score: int                  # 1–10
    dominant_emotion: str
    title_format: str
    thumbnail_style: str
    hook_line: str
    score_color: str            # "red" | "yellow" | "green"
    breakdown: dict[str, float] # emotion → weight


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def score_topic(topic: str, trends: list[str] | None = None) -> ViralScore:
    """Score *topic* for viral potential and return suggestions.

    Args:
        topic: The user's topic string.
        trends: Optional list of trending angles (boosts score if non-empty).
    """
    text = (topic + " " + " ".join(trends or [])).lower()

    # --- Emotion detection ---
    emotion_scores: dict[str, float] = {}
    for emotion, keywords in _TRIGGERS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            emotion_scores[emotion] = hits

    dominant = max(emotion_scores, key=emotion_scores.get) if emotion_scores else "default"

    # --- Base score from emotion breadth ---
    base = min(len(emotion_scores) * 1.5 + 2.0, 7.0)

    # --- Trend velocity boost ---
    trend_boost = min(len(trends or []) * 0.5, 2.0)

    # --- Hindi content pattern boost ---
    hindi_boost = 1.0
    for pattern, multiplier in _HINDI_BOOST.items():
        if pattern in text:
            hindi_boost = max(hindi_boost, multiplier)

    raw_score = (base + trend_boost) * hindi_boost
    score = max(1, min(10, round(raw_score)))

    # --- Color coding ---
    if score <= 3:
        color = "red"
    elif score <= 6:
        color = "yellow"
    else:
        color = "green"

    return ViralScore(
        score=score,
        dominant_emotion=dominant,
        title_format=_TITLE_FORMATS.get(dominant, _TITLE_FORMATS["default"]).format(topic=topic),
        thumbnail_style=_THUMBNAIL_STYLES.get(dominant, _THUMBNAIL_STYLES["default"]),
        hook_line=_HOOK_LINES.get(dominant, _HOOK_LINES["default"]),
        score_color=color,
        breakdown=emotion_scores,
    )
