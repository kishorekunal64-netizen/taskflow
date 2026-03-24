"""
story_flow_optimizer.py - Arrange clips in optimal storytelling order for RAGAI Editor V2.

Scores each clip on emotion intensity, conflict level, and novelty,
then orders them Strong -> Medium -> Light for maximum viewer retention.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List

from clip_manager import Clip

logger = logging.getLogger(__name__)

_EMOTION: Dict[str, float] = {
    "death": 3.0, "sacrifice": 3.0, "tragedy": 3.0, "heartbreak": 2.8,
    "struggle": 2.5, "pain": 2.5, "cry": 2.5, "rona": 2.5, "dard": 2.5,
    "emotional": 2.5, "touching": 2.3, "inspiring": 2.2, "motivational": 2.0,
    "love": 1.8, "pyar": 1.8, "family": 1.6, "mother": 1.7, "father": 1.6,
    "success": 1.5, "victory": 1.5, "hope": 1.4, "dream": 1.4,
    "village": 1.0, "nature": 0.8, "comedy": 0.7, "funny": 0.6,
}

_CONFLICT: Dict[str, float] = {
    "fight": 2.5, "war": 2.5, "battle": 2.5, "conflict": 2.0,
    "struggle": 2.0, "challenge": 1.8, "problem": 1.5, "obstacle": 1.5,
    "poor": 1.3, "garib": 1.3, "injustice": 2.0, "corruption": 2.0,
}

_NOVELTY: Dict[str, float] = {
    "ias": 2.5, "officer": 2.0, "doctor": 1.8, "engineer": 1.8,
    "village": 1.5, "tribal": 2.0, "ancient": 1.8, "historical": 1.8,
    "mystery": 2.2, "secret": 2.0, "hidden": 1.8, "unknown": 1.8,
}


@dataclass
class ScoredClip:
    clip: Clip
    emotion_score: float
    conflict_score: float
    novelty_score: float
    total_score: float


class StoryFlowOptimizer:
    """Scores and reorders clips for optimal storytelling flow."""

    W_EMOTION  = 0.50
    W_CONFLICT = 0.30
    W_NOVELTY  = 0.20

    def optimize(self, clips: List[Clip]) -> List[Clip]:
        """Return clips sorted Strong -> Medium -> Light."""
        if not clips:
            return clips
        scored = sorted(
            [self._score(c) for c in clips],
            key=lambda x: -x.total_score,
        )
        for sc in scored:
            logger.info(
                "Score %.2f | %s (e=%.1f c=%.1f n=%.1f)",
                sc.total_score, sc.clip.filename,
                sc.emotion_score, sc.conflict_score, sc.novelty_score,
            )
        return [sc.clip for sc in scored]

    def score_clips(self, clips: List[Clip]) -> List[ScoredClip]:
        return sorted([self._score(c) for c in clips], key=lambda x: -x.total_score)

    def _score(self, clip: Clip) -> ScoredClip:
        text = " ".join([clip.topic or "", clip.filename or ""] + clip.tags).lower()
        e = self._kw_score(text, _EMOTION)
        c = self._kw_score(text, _CONFLICT)
        n = self._kw_score(text, _NOVELTY)
        total = self.W_EMOTION * e + self.W_CONFLICT * c + self.W_NOVELTY * n
        return ScoredClip(clip=clip, emotion_score=round(e, 2),
                          conflict_score=round(c, 2), novelty_score=round(n, 2),
                          total_score=round(total, 2))

    @staticmethod
    def _kw_score(text: str, table: Dict[str, float]) -> float:
        score = 0.0
        for kw, w in table.items():
            if kw in text:
                score += w
        return min(score, 10.0)
