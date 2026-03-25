"""
emotion_detector.py — Script emotion analysis for RAGAI.

Analyzes generated scene narrations and assigns emotional scores.
Output is used by story_flow_optimizer.py to improve scene ordering.

Operates fully offline using keyword heuristics — no external API required.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List

from models import Scene

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emotion keyword banks (multilingual — Hindi + English)
# ---------------------------------------------------------------------------

_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "joy": [
        "खुशी", "आनंद", "हर्ष", "उत्सव", "प्रसन्न", "मुस्कान",
        "happy", "joy", "celebrate", "smile", "laugh", "delight", "cheer",
    ],
    "sadness": [
        "दुख", "रोना", "आंसू", "विदाई", "मृत्यु", "अकेला", "दर्द",
        "sad", "cry", "tears", "grief", "loss", "alone", "pain", "sorrow",
    ],
    "tension": [
        "संघर्ष", "खतरा", "डर", "चुनौती", "संकट", "युद्ध", "लड़ाई",
        "conflict", "danger", "fear", "threat", "crisis", "fight", "struggle",
    ],
    "hope": [
        "उम्मीद", "विश्वास", "सपना", "भविष्य", "प्रयास", "आशा",
        "hope", "dream", "believe", "future", "try", "aspire", "faith",
    ],
    "inspiration": [
        "प्रेरणा", "साहस", "जीत", "सफलता", "उपलब्धि", "शक्ति",
        "inspire", "courage", "victory", "success", "achieve", "strength", "triumph",
    ],
    "calm": [
        "शांति", "सुकून", "प्रकृति", "मौन", "ध्यान",
        "peace", "calm", "quiet", "nature", "serene", "gentle",
    ],
    "conflict": [
        "विरोध", "झगड़ा", "टकराव", "बाधा",
        "oppose", "argue", "obstacle", "clash", "resist",
    ],
    "resolution": [
        "समाधान", "माफी", "मेल", "अंत", "निष्कर्ष",
        "resolve", "forgive", "reconcile", "conclusion", "end", "finally",
    ],
}

# Narrative arc labels mapped to dominant emotions
_ARC_LABELS = {
    "joy":         "joyful",
    "sadness":     "emotional_peak",
    "tension":     "conflict",
    "hope":        "rising_hope",
    "inspiration": "climax",
    "calm":        "calm",
    "conflict":    "conflict",
    "resolution":  "resolution",
}


class EmotionDetector:
    """Detect dominant emotion per scene using keyword scoring."""

    def analyze_scene(self, narration: str) -> str:
        """Return the dominant emotion label for a single narration text."""
        text = narration.lower()
        scores: Dict[str, int] = {emotion: 0 for emotion in _EMOTION_KEYWORDS}

        for emotion, keywords in _EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    scores[emotion] += 1

        dominant = max(scores, key=lambda e: scores[e])
        if scores[dominant] == 0:
            dominant = "calm"  # neutral default

        label = _ARC_LABELS.get(dominant, dominant)
        return label

    def analyze_scenes(self, scenes: List[Scene]) -> Dict[str, str]:
        """Analyze all scenes and return a dict of scene_N → emotion label.

        Example output:
            {"scene_1": "calm", "scene_2": "conflict", "scene_3": "emotional_peak"}
        """
        result: Dict[str, str] = {}
        for scene in scenes:
            label = self.analyze_scene(scene.narration)
            key = f"scene_{scene.number}"
            result[key] = label
            logger.debug("EmotionDetector: %s → %s", key, label)

        logger.info("EmotionDetector: analyzed %d scenes — arc: %s",
                    len(scenes), list(result.values()))
        return result

    def emotion_arc_summary(self, emotion_map: Dict[str, str]) -> str:
        """Return a human-readable arc summary string."""
        arc = " → ".join(emotion_map.values())
        return arc

    def dominant_emotion(self, emotion_map: Dict[str, str]) -> str:
        """Return the most frequent emotion across all scenes."""
        from collections import Counter
        if not emotion_map:
            return "calm"
        counts = Counter(emotion_map.values())
        return counts.most_common(1)[0][0]
