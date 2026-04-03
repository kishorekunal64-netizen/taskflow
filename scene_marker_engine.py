"""
scene_marker_engine.py — Narrative arc detection for RAGAI Editor V3.

Assigns story-arc markers to a list of clips based on emotion scores,
topic keywords, and position in the sequence.

Markers: Hook · Rising · Conflict · Climax · Resolution · Outro
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

MARKERS = ["Hook", "Rising", "Conflict", "Climax", "Resolution", "Outro"]

_CONFLICT_WORDS = {"fight", "war", "battle", "crisis", "problem", "danger", "struggle",
                   "conflict", "enemy", "villain", "dark", "fear", "death"}
_RESOLUTION_WORDS = {"save", "win", "victory", "peace", "happy", "success", "love",
                     "hope", "light", "joy", "celebrate", "triumph", "resolve"}
_HOOK_WORDS = {"begin", "start", "once", "story", "hero", "journey", "dream",
               "young", "child", "village", "poor", "farmer"}


@dataclass
class SceneMarker:
    clip_id: str
    marker: str          # one of MARKERS
    confidence: float    # 0.0–1.0


def _score_topic(topic: str) -> dict:
    words = set(re.split(r"\W+", (topic or "").lower()))
    return {
        "hook":       len(words & _HOOK_WORDS) / max(1, len(_HOOK_WORDS)),
        "conflict":   len(words & _CONFLICT_WORDS) / max(1, len(_CONFLICT_WORDS)),
        "resolution": len(words & _RESOLUTION_WORDS) / max(1, len(_RESOLUTION_WORDS)),
    }


def assign_markers(clips) -> List[SceneMarker]:
    """
    Assign arc markers to clips.
    clips: list of Clip objects (must have .clip_id, .topic, .tags, .duration)
    """
    n = len(clips)
    if n == 0:
        return []

    markers: List[SceneMarker] = []

    for i, clip in enumerate(clips):
        pos = i / max(1, n - 1)   # 0.0 = first, 1.0 = last
        scores = _score_topic(clip.topic)

        # Position-based arc assignment
        if i == 0:
            marker = "Hook"
            conf = 0.9
        elif i == n - 1:
            marker = "Outro"
            conf = 0.9
        elif pos < 0.25:
            if scores["conflict"] > 0.05:
                marker = "Conflict"
                conf = 0.7
            else:
                marker = "Rising"
                conf = 0.75
        elif pos < 0.6:
            if scores["conflict"] > 0.05:
                marker = "Climax"
                conf = 0.8
            else:
                marker = "Conflict"
                conf = 0.65
        else:
            if scores["resolution"] > 0.05:
                marker = "Resolution"
                conf = 0.8
            else:
                marker = "Resolution"
                conf = 0.6

        markers.append(SceneMarker(clip_id=clip.clip_id, marker=marker, confidence=conf))

    return markers
