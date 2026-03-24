"""
engagement_predictor.py - Predict engagement before video generation.

Estimates expected CTR and watch-time for a topic+title combination.
Topics scoring below the configured threshold are skipped or flagged
for regeneration before the scheduler runs RAGAI.

Factors:
  - title_strength      : length, power words, question/number hooks
  - topic_emotion       : from TopicQualityEngine composite score
  - story_novelty       : penalises recently used narrative structures
  - keyword_popularity  : high-performing keyword density
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Power-word banks
# ---------------------------------------------------------------------------

_POWER_WORDS: List[str] = [
    "shocking", "secret", "truth", "revealed", "never", "real", "untold",
    "viral", "emotional", "heartbreaking", "inspiring", "unbelievable",
    "rare", "hidden", "amazing", "incredible", "true story",
    "असली", "सच", "रहस्य", "हैरान", "वायरल", "सच्ची", "अविश्वसनीय",
]

_QUESTION_PATTERNS = [
    r"\?",
    r"\bwhy\b", r"\bhow\b", r"\bwhat\b", r"\bwho\b",
    r"\bक्यों\b", r"\bकैसे\b", r"\bक्या\b", r"\bकौन\b",
]

_NUMBER_PATTERN = re.compile(r"\b\d+\b")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _title_strength(title: str) -> float:
    """
    Score a title 0-10 based on:
      - length (optimal 6-12 words)
      - power word count
      - presence of a question
      - presence of a number
    """
    if not title:
        return 0.0

    words = title.split()
    word_count = len(words)

    # Length score (0-3)
    if 6 <= word_count <= 12:
        length_score = 3.0
    elif 4 <= word_count <= 14:
        length_score = 2.0
    else:
        length_score = 1.0

    # Power words (0-4)
    title_lower = title.lower()
    power_hits = sum(1 for pw in _POWER_WORDS if pw.lower() in title_lower)
    power_score = min(power_hits * 1.5, 4.0)

    # Question hook (0-1.5)
    has_question = any(re.search(p, title_lower) for p in _QUESTION_PATTERNS)
    question_score = 1.5 if has_question else 0.0

    # Number hook (0-1.5)
    has_number = bool(_NUMBER_PATTERN.search(title))
    number_score = 1.5 if has_number else 0.0

    total = length_score + power_score + question_score + number_score
    return round(min(total, 10.0), 2)


def _novelty_score(
    topic: str,
    recent_topics: Optional[List[str]] = None,
    max_recent: int = 10,
) -> float:
    """
    Penalise topics that are too similar to recently generated ones.
    Returns 0-10 (10 = completely novel).
    """
    if not recent_topics:
        return 10.0

    topic_words = set(topic.lower().split())
    max_overlap = 0.0
    for recent in recent_topics[-max_recent:]:
        recent_words = set(recent.lower().split())
        if not topic_words or not recent_words:
            continue
        overlap = len(topic_words & recent_words) / len(topic_words | recent_words)
        max_overlap = max(max_overlap, overlap)

    novelty = round((1.0 - max_overlap) * 10.0, 2)
    return novelty


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class EngagementPredictor:
    """
    Predicts CTR and watch-time for a topic before generation.

    Usage::

        predictor = EngagementPredictor(ctr_threshold=5.0, watch_threshold=3.5)
        result = predictor.predict(
            topic="Village girl becomes IAS officer",
            title="गाँव की लड़की बनी IAS अफसर | सच्ची कहानी",
            topic_score=8.3,
        )
        # {'topic': ..., 'predicted_ctr': 7.2, 'predicted_watch_minutes': 5.1,
        #  'title_strength': 8.0, 'novelty': 9.5, 'should_generate': True}
    """

    # Regression coefficients (empirically tuned for Indian YouTube content)
    _CTR_WEIGHTS = {
        "title_strength": 0.50,
        "topic_emotion":  0.30,
        "novelty":        0.20,
    }
    _WATCH_WEIGHTS = {
        "topic_emotion":  0.40,
        "novelty":        0.35,
        "title_strength": 0.25,
    }

    # CTR scale: model output 0-10 → mapped to realistic CTR % (2-12%)
    _CTR_SCALE_MIN  = 2.0
    _CTR_SCALE_MAX  = 12.0

    # Watch time scale: model output 0-10 → mapped to minutes (1-8 min)
    _WATCH_SCALE_MIN = 1.0
    _WATCH_SCALE_MAX = 8.0

    def __init__(
        self,
        ctr_threshold: float = 4.5,
        watch_threshold: float = 3.0,
    ):
        self.ctr_threshold   = ctr_threshold
        self.watch_threshold = watch_threshold

    def predict(
        self,
        topic: str,
        title: str = "",
        topic_score: float = 5.0,
        recent_topics: Optional[List[str]] = None,
    ) -> Dict:
        """
        Predict engagement for a topic/title pair.

        Args:
            topic        : raw topic string
            title        : generated or candidate title (optional)
            topic_score  : composite score from TopicQualityEngine (0-10)
            recent_topics: list of recently generated topics for novelty check

        Returns:
            dict with predicted_ctr, predicted_watch_minutes, should_generate
        """
        ts      = _title_strength(title or topic)
        novelty = _novelty_score(topic, recent_topics)
        emotion = min(topic_score, 10.0)

        # Weighted composite scores (0-10)
        ctr_raw = (
            ts      * self._CTR_WEIGHTS["title_strength"] +
            emotion * self._CTR_WEIGHTS["topic_emotion"] +
            novelty * self._CTR_WEIGHTS["novelty"]
        )
        watch_raw = (
            emotion * self._WATCH_WEIGHTS["topic_emotion"] +
            novelty * self._WATCH_WEIGHTS["novelty"] +
            ts      * self._WATCH_WEIGHTS["title_strength"]
        )

        # Scale to realistic ranges
        predicted_ctr   = self._scale(ctr_raw,   self._CTR_SCALE_MIN,   self._CTR_SCALE_MAX)
        predicted_watch = self._scale(watch_raw, self._WATCH_SCALE_MIN, self._WATCH_SCALE_MAX)

        should_generate = (
            predicted_ctr   >= self.ctr_threshold and
            predicted_watch >= self.watch_threshold
        )

        result = {
            "topic":                   topic,
            "title":                   title,
            "title_strength":          ts,
            "novelty":                 novelty,
            "topic_score":             round(emotion, 2),
            "predicted_ctr":           round(predicted_ctr, 2),
            "predicted_watch_minutes": round(predicted_watch, 2),
            "should_generate":         should_generate,
            "skip_reason": (
                None if should_generate else
                self._skip_reason(predicted_ctr, predicted_watch)
            ),
        }

        logger.info(
            "Engagement prediction: '%s' → CTR=%.1f%% watch=%.1fmin generate=%s",
            topic, predicted_ctr, predicted_watch, should_generate,
        )
        return result

    def filter_topics(
        self,
        topics: List[str],
        topic_scores: Optional[Dict[str, float]] = None,
        recent_topics: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Filter a list of topics, returning only those predicted to engage.
        topic_scores: {topic_string: composite_score} from TopicQualityEngine
        """
        passed, skipped = [], []
        for topic in topics:
            score = (topic_scores or {}).get(topic, 5.0)
            result = self.predict(topic, topic_score=score, recent_topics=recent_topics)
            if result["should_generate"]:
                passed.append(topic)
            else:
                skipped.append((topic, result["skip_reason"]))

        for t, reason in skipped:
            logger.info("Skipped topic '%s': %s", t, reason)

        logger.info(
            "EngagementPredictor: %d/%d topics passed filter",
            len(passed), len(topics),
        )
        return passed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _scale(value: float, min_val: float, max_val: float) -> float:
        """Linearly scale a 0-10 value to [min_val, max_val]."""
        return round(min_val + (value / 10.0) * (max_val - min_val), 2)

    def _skip_reason(self, ctr: float, watch: float) -> str:
        reasons = []
        if ctr < self.ctr_threshold:
            reasons.append(f"CTR {ctr:.1f}% < threshold {self.ctr_threshold}%")
        if watch < self.watch_threshold:
            reasons.append(f"watch {watch:.1f}min < threshold {self.watch_threshold}min")
        return "; ".join(reasons)
