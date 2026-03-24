"""
smart_compiler.py - Duration-based smart compilation engine for RAGAI Editor V2.

Selects clips until target duration is reached instead of using a fixed clip count.
Config keys: target_video_minutes, min_clips, max_clips (from ragai_config.json).
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from clip_manager import Clip
from topic_engine import TopicEngine
from editor_config import load_editor_config

logger = logging.getLogger(__name__)


class SmartCompiler:
    """Selects clips to fill a target duration window."""

    def __init__(self):
        cfg = load_editor_config()
        self.target_seconds: float = float(cfg.get("target_video_minutes", 12)) * 60
        self.min_clips: int = int(cfg.get("min_clips", 3))
        self.max_clips: int = int(cfg.get("max_clips", 10))
        self._topic_engine = TopicEngine()
        logger.info(
            "SmartCompiler: target=%.0fs  min=%d  max=%d",
            self.target_seconds, self.min_clips, self.max_clips,
        )

    def select_clips(self, available: List[Clip]) -> Tuple[List[Clip], str]:
        """Pick clips that fill target_seconds. Returns (clips, group_title)."""
        if not available:
            return [], "RAGAI Compilation"

        group = self._topic_engine.best_group(available)
        if group:
            pool, title = group.clips, group.title
            logger.info("SmartCompiler: group '%s' (%d clips)", title, len(pool))
        else:
            pool, title = list(available), "RAGAI Compilation"

        selected = self._fill_duration(pool)
        if len(selected) < self.min_clips:
            logger.warning("SmartCompiler: only %d clips, using all available", len(selected))
            selected = pool[: self.max_clips]

        total = sum(c.duration for c in selected)
        logger.info(
            "SmartCompiler: %d clips selected, %.0fs (target %.0fs)",
            len(selected), total, self.target_seconds,
        )
        return selected, title

    def estimate_duration(self, clips: List[Clip]) -> float:
        """Total duration in seconds."""
        return sum(c.duration for c in clips)

    def estimate_filesize_mb(self, clips: List[Clip], quality: str = "Standard 1080p") -> float:
        """Rough file-size estimate based on bitrate x duration."""
        bitrate_map = {
            "Standard 1080p": 8_000_000,
            "High 1440p":     12_000_000,
            "Cinema 4K":      20_000_000,
        }
        bps = bitrate_map.get(quality, 8_000_000)
        return round((bps * self.estimate_duration(clips)) / 8 / 1_048_576, 1)

    def _fill_duration(self, pool: List[Clip]) -> List[Clip]:
        selected: List[Clip] = []
        total = 0.0
        for clip in pool:
            if len(selected) >= self.max_clips:
                break
            selected.append(clip)
            total += clip.duration
            if total >= self.target_seconds:
                break
        return selected
