"""
topic_quality_engine.py - Score topics before video generation.

Evaluates each topic on four dimensions:
  - emotional_intensity : how emotionally charged the topic is
  - curiosity_factor    : how much it triggers curiosity / click desire
  - relatability        : how relatable it is to a general Indian audience
  - keyword_popularity  : presence of high-performing keywords

Returns a score dict and a composite score (0-10).
The Scheduler uses this to prioritise higher-scoring topics.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword banks  (additive scoring)
# ---------------------------------------------------------------------------

_EMOTION_KEYWORDS: List[str] = [
    "emotional", "crying", "tears", "sacrifice", "love", "heartbreak",
    "mother", "father", "family", "death", "struggle", "pain", "hope",
    "reunion", "betrayal", "forgiveness", "orphan", "widow", "poor",
    "village", "farmer", "soldier", "brave", "hero", "inspire",
    "माँ", "पिता", "परिवार", "गाँव", "किसान", "बलिदान", "प्रेम",
]

_CURIOSITY_KEYWORDS: List[str] = [
    "secret", "hidden", "mystery", "shocking", "truth", "revealed",
    "unknown", "untold", "real story", "never seen", "rare", "surprising",
    "twist", "unexpected", "what happened", "why", "how",
    "रहस्य", "सच", "अनजान", "असली", "हैरान",
]

_RELATABILITY_KEYWORDS: List[str] = [
    "girl", "boy", "student", "teacher", "doctor", "ias", "officer",
    "poor", "rich", "village", "city", "india", "hindi", "desi",
    "marriage", "wedding", "exam", "job", "success", "failure",
    "लड़की", "लड़का", "गरीब", "अमीर", "शादी", "परीक्षा", "नौकरी",
]

_POPULARITY_KEYWORDS: List[str] = [
    "ias", "upsc", "viral", "trending", "real", "true story", "based on",
    "inspirational", "motivational", "emotional story", "hindi kahani",
    "short film", "devotional", "bhakti", "shiva", "krishna", "ram",
    "आईएएस", "वायरल", "सच्ची कहानी", "प्रेरणादायक", "भक्ति",
]

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _keyword_score(text: str, keywords: List[str], max_score: float = 10.0) -> float:
    """Count keyword hits and normalise to 0-max_score."""
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    # Diminishing returns: each hit worth less after the first few
    raw = min(hits * 1.5, max_score)
    return round(raw, 2)


def _length_bonus(text: str) -> float:
    """Longer, more descriptive topics tend to be more specific (small bonus)."""
    words = len(text.split())
    if words >= 8:
        return 0.5
    if words >= 5:
        return 0.25
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TopicQualityEngine:
    """
    Scores topics on four dimensions and returns a composite score.

    Usage::

        engine = TopicQualityEngine()
        result = engine.score("Village girl becomes IAS officer")
        # {'topic': '...', 'emotion': 8.5, 'curiosity': 7.2,
        #  'relatability': 9.1, 'keyword_popularity': 6.0, 'score': 7.7}
    """

    # Weights for composite score (must sum to 1.0)
    _WEIGHTS = {
        "emotion":           0.35,
        "curiosity":         0.25,
        "relatability":      0.25,
        "keyword_popularity": 0.15,
    }

    def score(self, topic: str) -> Dict[str, float]:
        """Return a score dict for a single topic string."""
        if not topic or not topic.strip():
            logger.warning("Empty topic passed to TopicQualityEngine.score()")
            return self._empty_result(topic)

        emotion      = _keyword_score(topic, _EMOTION_KEYWORDS)
        curiosity    = _keyword_score(topic, _CURIOSITY_KEYWORDS)
        relatability = _keyword_score(topic, _RELATABILITY_KEYWORDS)
        popularity   = _keyword_score(topic, _POPULARITY_KEYWORDS)

        # Apply length bonus to relatability (specific topics are more relatable)
        relatability = min(10.0, relatability + _length_bonus(topic))

        composite = (
            emotion      * self._WEIGHTS["emotion"] +
            curiosity    * self._WEIGHTS["curiosity"] +
            relatability * self._WEIGHTS["relatability"] +
            popularity   * self._WEIGHTS["keyword_popularity"]
        )
        composite = round(min(composite, 10.0), 2)

        result = {
            "topic":             topic,
            "emotion":           emotion,
            "curiosity":         curiosity,
            "relatability":      relatability,
            "keyword_popularity": popularity,
            "score":             composite,
        }
        logger.info(
            "Topic scored: '%s' → emotion=%.1f curiosity=%.1f "
            "relatability=%.1f popularity=%.1f composite=%.2f",
            topic, emotion, curiosity, relatability, popularity, composite,
        )
        return result

    def score_batch(self, topics: List[str]) -> List[Dict[str, float]]:
        """Score a list of topics and return sorted by composite score (desc)."""
        results = [self.score(t) for t in topics]
        results.sort(key=lambda r: r["score"], reverse=True)
        logger.info("Batch scored %d topics", len(results))
        return results

    def filter_by_threshold(
        self,
        topics: List[str],
        threshold: float = 4.0,
    ) -> List[str]:
        """Return only topics whose composite score meets the threshold."""
        scored = self.score_batch(topics)
        passed = [r["topic"] for r in scored if r["score"] >= threshold]
        skipped = len(topics) - len(passed)
        if skipped:
            logger.info(
                "TopicQualityEngine filtered out %d/%d topics below threshold %.1f",
                skipped, len(topics), threshold,
            )
        return passed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(topic: str) -> Dict[str, float]:
        return {
            "topic":             topic,
            "emotion":           0.0,
            "curiosity":         0.0,
            "relatability":      0.0,
            "keyword_popularity": 0.0,
            "score":             0.0,
        }
