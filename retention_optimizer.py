"""
retention_optimizer.py - Viewer retention optimizer for RAGAI ecosystem.

Reads analytics_data.json to detect drop points and low watch-time patterns,
then adjusts parameters consumed by hook_generator and story_flow_optimizer
to maximize average watch time in future compilations.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ANALYTICS_DB = Path("analytics_data.json")

# Defaults used when no analytics data is available
_DEFAULT_HOOK_SECONDS = 10
_DEFAULT_STORY_PACE   = "medium"


def _load_analytics() -> List[Dict[str, Any]]:
    if ANALYTICS_DB.exists():
        try:
            return json.loads(ANALYTICS_DB.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load analytics_data.json: %s", exc)
    return []


class RetentionOptimizer:
    """
    Analyses retention data and produces optimized parameters for:
      - hook_generator  (hook_duration_seconds, hook_style)
      - story_flow_optimizer  (ordering strategy)
      - auto_pipeline  (clip pacing)
    """

    def __init__(self):
        self._records = _load_analytics()
        logger.info("RetentionOptimizer: %d analytics records loaded", len(self._records))

    def reload(self) -> None:
        """Reload analytics from disk (call after fetch_video_metrics)."""
        self._records = _load_analytics()

    # ------------------------------------------------------------------
    # Hook parameters
    # ------------------------------------------------------------------

    def recommended_hook_duration(self) -> int:
        """
        Return recommended hook duration in seconds.

        Logic: if avg retention drop < 20s, shorten hook to 6s.
               if avg retention drop > 40s, extend hook to 15s.
               otherwise use 10s default.
        """
        drop = self._avg_drop()
        if drop < 20:
            duration = 6
            reason = f"drop at {drop:.0f}s — shorten hook to grab attention faster"
        elif drop > 40:
            duration = 15
            reason = f"drop at {drop:.0f}s — extend hook to build more suspense"
        else:
            duration = 10
            reason = f"drop at {drop:.0f}s — standard hook length"
        logger.info("Hook duration: %ds (%s)", duration, reason)
        return duration

    def recommended_hook_style(self) -> str:
        """
        Return hook style based on CTR performance.
        High CTR (>6%) -> dramatic. Low CTR -> question style.
        """
        avg_ctr = self._avg_ctr()
        if avg_ctr >= 6.0:
            style = "dramatic"
        elif avg_ctr >= 3.0:
            style = "emotional"
        else:
            style = "question"
        logger.info("Hook style: %s (avg CTR=%.1f%%)", style, avg_ctr)
        return style

    # ------------------------------------------------------------------
    # Story ordering
    # ------------------------------------------------------------------

    def recommended_story_order(self) -> str:
        """
        Return story ordering strategy.
        'strong_first' (default) or 'build_up' if watch time is high.
        """
        avg_watch = self._avg_watch_seconds()
        if avg_watch > 300:  # >5 min avg watch
            order = "build_up"
            logger.info("Story order: build_up (avg watch %.0fs)", avg_watch)
        else:
            order = "strong_first"
            logger.info("Story order: strong_first (avg watch %.0fs)", avg_watch)
        return order

    # ------------------------------------------------------------------
    # Clip pacing
    # ------------------------------------------------------------------

    def recommended_clip_count(self, target_minutes: float = 12.0) -> int:
        """
        Suggest number of clips based on avg watch time.
        If viewers drop early, use fewer longer clips.
        If watch time is high, pack more clips.
        """
        avg_watch = self._avg_watch_seconds()
        target_s = target_minutes * 60

        if avg_watch < 120:
            count = 3
        elif avg_watch < 300:
            count = 5
        else:
            count = 8

        logger.info("Recommended clip count: %d (avg watch %.0fs)", count, avg_watch)
        return count

    def get_optimization_report(self) -> Dict[str, Any]:
        """Return a full optimization report dict."""
        report = {
            "records_analysed": len(self._records),
            "avg_retention_drop_seconds": round(self._avg_drop(), 1),
            "avg_watch_seconds": round(self._avg_watch_seconds(), 1),
            "avg_ctr_percent": round(self._avg_ctr(), 2),
            "recommended_hook_duration": self.recommended_hook_duration(),
            "recommended_hook_style": self.recommended_hook_style(),
            "recommended_story_order": self.recommended_story_order(),
            "recommended_clip_count": self.recommended_clip_count(),
        }
        logger.info("Optimization report: %s", report)
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _avg_drop(self) -> float:
        drops = [float(r["retention_drop_seconds"])
                 for r in self._records if r.get("retention_drop_seconds") is not None]
        return sum(drops) / len(drops) if drops else 25.0

    def _avg_watch_seconds(self) -> float:
        watches = [float(r["avg_watch_seconds"])
                   for r in self._records if r.get("avg_watch_seconds") is not None]
        return sum(watches) / len(watches) if watches else 180.0

    def _avg_ctr(self) -> float:
        ctrs = [float(r["ctr"]) for r in self._records if r.get("ctr")]
        return sum(ctrs) / len(ctrs) if ctrs else 4.0
