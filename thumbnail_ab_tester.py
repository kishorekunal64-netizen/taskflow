"""
thumbnail_ab_tester.py - A/B test thumbnail layouts to maximise CTR.

Workflow:
  1. generate_variants()  — produce 3 thumbnail variants (layouts A, B, C)
  2. record_impression()  — call when a thumbnail is shown / uploaded
  3. record_click()       — call when a click/CTR data arrives (from analytics_engine)
  4. pick_winner()        — return the layout with highest CTR after min_impressions
  5. update_from_analytics() — bulk-update from analytics_data.json records

State is persisted in ab_test_results.json so data survives restarts.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

AB_RESULTS_FILE = Path("ab_test_results.json")
MIN_IMPRESSIONS  = 50   # minimum impressions before declaring a winner
CONFIDENCE_Z     = 1.65  # ~90% one-tailed confidence


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _ctr(impressions: int, clicks: int) -> float:
    return (clicks / impressions * 100.0) if impressions > 0 else 0.0


def _wilson_lower(impressions: int, clicks: int, z: float = CONFIDENCE_Z) -> float:
    """Wilson score lower bound — conservative CTR estimate for small samples."""
    if impressions == 0:
        return 0.0
    p = clicks / impressions
    denom = 1 + z * z / impressions
    centre = p + z * z / (2 * impressions)
    spread = z * math.sqrt(p * (1 - p) / impressions + z * z / (4 * impressions * impressions))
    return (centre - spread) / denom * 100.0


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class ThumbnailABTester:
    """
    Manages A/B testing of thumbnail layouts across videos.

    Each video_id gets a record tracking impressions + clicks per layout.
    The winner is the layout with the highest Wilson lower-bound CTR.

    Usage::

        tester = ThumbnailABTester()

        # After generating variants and uploading:
        tester.record_impression("vid_abc123", "A")
        tester.record_impression("vid_abc123", "B")
        tester.record_impression("vid_abc123", "C")

        # After analytics data arrives:
        tester.record_click("vid_abc123", "A", clicks=120)
        tester.record_click("vid_abc123", "B", clicks=95)

        winner = tester.pick_winner("vid_abc123")
        # → "A"

        # Global layout performance:
        best = tester.best_global_layout()
        # → "A"
    """

    LAYOUTS = ["A", "B", "C"]

    def __init__(self, results_file: Path = AB_RESULTS_FILE):
        self._file = results_file
        self._data: dict = _load(self._file)

    # ------------------------------------------------------------------
    # Per-video tracking
    # ------------------------------------------------------------------

    def record_impression(self, video_id: str, layout: str, count: int = 1) -> None:
        """Record that a thumbnail variant was shown count times."""
        rec = self._get_record(video_id, layout)
        rec["impressions"] += count
        self._persist()
        logger.debug("Impression recorded: video=%s layout=%s total=%d",
                     video_id, layout, rec["impressions"])

    def record_click(self, video_id: str, layout: str, clicks: int) -> None:
        """Set absolute click count for a variant (from analytics API)."""
        rec = self._get_record(video_id, layout)
        rec["clicks"] = clicks
        self._persist()
        logger.info("Clicks updated: video=%s layout=%s clicks=%d ctr=%.2f%%",
                    video_id, layout, clicks,
                    _ctr(rec["impressions"], clicks))

    def pick_winner(self, video_id: str) -> Optional[str]:
        """
        Return the winning layout for a video, or None if not enough data.
        Uses Wilson lower bound so low-impression variants aren't over-promoted.
        """
        entry = self._data.get(video_id, {})
        if not entry:
            return None

        best_layout, best_score = None, -1.0
        for layout, stats in entry.items():
            imp = stats.get("impressions", 0)
            clk = stats.get("clicks", 0)
            if imp < MIN_IMPRESSIONS:
                continue
            score = _wilson_lower(imp, clk)
            if score > best_score:
                best_score = score
                best_layout = layout

        if best_layout:
            logger.info("Winner for %s: layout %s (wilson=%.2f%%)", video_id, best_layout, best_score)
        return best_layout

    def get_stats(self, video_id: str) -> Dict[str, dict]:
        """Return per-layout stats dict for a video."""
        entry = self._data.get(video_id, {})
        result = {}
        for layout, stats in entry.items():
            imp = stats.get("impressions", 0)
            clk = stats.get("clicks", 0)
            result[layout] = {
                "impressions": imp,
                "clicks":      clk,
                "ctr_pct":     round(_ctr(imp, clk), 2),
                "wilson_lb":   round(_wilson_lower(imp, clk), 2),
            }
        return result

    # ------------------------------------------------------------------
    # Global layout performance
    # ------------------------------------------------------------------

    def best_global_layout(self) -> str:
        """
        Aggregate all video data and return the layout with the best
        overall Wilson lower-bound CTR. Falls back to "A" if no data.
        """
        totals: Dict[str, Dict[str, int]] = {l: {"impressions": 0, "clicks": 0}
                                              for l in self.LAYOUTS}
        for entry in self._data.values():
            for layout, stats in entry.items():
                if layout in totals:
                    totals[layout]["impressions"] += stats.get("impressions", 0)
                    totals[layout]["clicks"]      += stats.get("clicks", 0)

        best_layout, best_score = "A", -1.0
        for layout, agg in totals.items():
            score = _wilson_lower(agg["impressions"], agg["clicks"])
            if score > best_score:
                best_score = score
                best_layout = layout

        logger.info("Best global layout: %s (wilson=%.2f%%)", best_layout, best_score)
        return best_layout

    def global_summary(self) -> List[dict]:
        """Return sorted list of layout performance dicts."""
        totals: Dict[str, Dict[str, int]] = {l: {"impressions": 0, "clicks": 0}
                                              for l in self.LAYOUTS}
        for entry in self._data.values():
            for layout, stats in entry.items():
                if layout in totals:
                    totals[layout]["impressions"] += stats.get("impressions", 0)
                    totals[layout]["clicks"]      += stats.get("clicks", 0)

        rows = []
        for layout, agg in totals.items():
            imp, clk = agg["impressions"], agg["clicks"]
            rows.append({
                "layout":      layout,
                "impressions": imp,
                "clicks":      clk,
                "ctr_pct":     round(_ctr(imp, clk), 2),
                "wilson_lb":   round(_wilson_lower(imp, clk), 2),
            })
        rows.sort(key=lambda r: r["wilson_lb"], reverse=True)
        return rows

    # ------------------------------------------------------------------
    # Bulk update from analytics_data.json
    # ------------------------------------------------------------------

    def update_from_analytics(self, analytics_path: Path = Path("analytics_data.json")) -> int:
        """
        Read analytics_data.json and update click counts for any video
        that has a 'thumbnail_layout' field recorded.

        Returns number of records updated.
        """
        if not analytics_path.exists():
            logger.warning("analytics_data.json not found — skipping A/B update")
            return 0

        try:
            records = json.loads(analytics_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to read analytics_data.json: %s", exc)
            return 0

        if not isinstance(records, list):
            records = [records]

        updated = 0
        for rec in records:
            vid = rec.get("video_id")
            layout = rec.get("thumbnail_layout")
            ctr = rec.get("ctr")          # e.g. 7.8 (percent)
            views = rec.get("views", 0)

            if not vid or not layout or ctr is None:
                continue

            # Estimate clicks from CTR + views
            estimated_clicks = int(views * ctr / 100.0)
            self.record_impression(vid, layout, count=max(views, 1))
            self.record_click(vid, layout, clicks=estimated_clicks)
            updated += 1

        logger.info("A/B tester updated %d records from analytics", updated)
        return updated

    # ------------------------------------------------------------------
    # Variant generation helper
    # ------------------------------------------------------------------

    def generate_variants(
        self,
        video_path: Path,
        title: str,
        output_dir: Path,
        video_id: str,
    ) -> Dict[str, Path]:
        """
        Generate all 3 thumbnail variants for a video.
        Returns {layout: path} dict.
        Records one impression per variant.
        """
        from thumbnail_generator import ThumbnailGenerator

        gen = ThumbnailGenerator()
        output_dir.mkdir(parents=True, exist_ok=True)
        variants: Dict[str, Path] = {}

        for layout in self.LAYOUTS:
            out_path = output_dir / f"thumbnail_{layout}.jpg"
            result = gen.generate(
                video_path=video_path,
                title=title,
                output_path=out_path,
                layout=layout,
            )
            if result:
                variants[layout] = result
                self.record_impression(video_id, layout)
                logger.info("Variant %s generated: %s", layout, result)
            else:
                logger.warning("Variant %s generation failed", layout)

        self._persist()
        return variants

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_record(self, video_id: str, layout: str) -> dict:
        if video_id not in self._data:
            self._data[video_id] = {}
        if layout not in self._data[video_id]:
            self._data[video_id][layout] = {"impressions": 0, "clicks": 0}
        return self._data[video_id][layout]

    def _persist(self) -> None:
        try:
            _save(self._file, self._data)
        except Exception as exc:
            logger.error("Failed to persist A/B results: %s", exc)
