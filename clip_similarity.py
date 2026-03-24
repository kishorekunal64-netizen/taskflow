"""
clip_similarity.py - Clip similarity detection for RAGAI Editor V2.

Compares clips by topic keywords and hashtags using Jaccard similarity.
Clips with similarity > threshold are skipped during compilation to ensure diversity.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Set, Tuple

from clip_manager import Clip

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.6


def _tokenize(text: str) -> Set[str]:
    text = re.sub(r"[#@]", " ", text.lower())
    return set(re.findall(r"[a-z0-9\u0900-\u097f]+", text))


def _clip_tokens(clip: Clip) -> Set[str]:
    return _tokenize(" ".join([clip.topic or "", clip.filename or ""] + clip.tags))


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


class ClipSimilarityDetector:
    """
    Filters out clips that are too similar to already-selected ones.

    Usage:
        detector = ClipSimilarityDetector(threshold=0.6)
        diverse_clips = detector.filter_diverse(clips)
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold

    def similarity(self, a: Clip, b: Clip) -> float:
        return jaccard(_clip_tokens(a), _clip_tokens(b))

    def filter_diverse(self, clips: List[Clip]) -> List[Clip]:
        """Return subset where no two clips exceed similarity threshold."""
        accepted: List[Clip] = []
        accepted_tokens: List[Set[str]] = []

        for clip in clips:
            tokens = _clip_tokens(clip)
            too_similar = any(
                jaccard(tokens, prev) >= self.threshold
                for prev in accepted_tokens
            )
            if too_similar:
                logger.info("Skipping similar clip: %s", clip.filename)
            else:
                accepted.append(clip)
                accepted_tokens.append(tokens)

        logger.info(
            "ClipSimilarity: %d/%d clips kept (threshold=%.2f)",
            len(accepted), len(clips), self.threshold,
        )
        return accepted

    def similarity_matrix(self, clips: List[Clip]) -> Dict[Tuple[str, str], float]:
        tokens = [_clip_tokens(c) for c in clips]
        return {
            (clips[i].clip_id, clips[j].clip_id): round(jaccard(tokens[i], tokens[j]), 3)
            for i in range(len(clips))
            for j in range(i + 1, len(clips))
        }
