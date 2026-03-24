"""
analytics_engine.py - YouTube performance analytics for RAGAI ecosystem.

Fetches video metrics via YouTube Analytics API (or mock data when offline),
stores results in analytics_data.json, and exposes helper queries used by
retention_optimizer and channel_manager.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ANALYTICS_DB = Path("analytics_data.json")


def _load_db() -> List[Dict[str, Any]]:
    if ANALYTICS_DB.exists():
        try:
            return json.loads(ANALYTICS_DB.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load analytics_data.json: %s", exc)
    return []


def _save_db(records: List[Dict[str, Any]]) -> None:
    try:
        ANALYTICS_DB.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not save analytics_data.json: %s", exc)


class AnalyticsEngine:
    """
    Fetches and stores YouTube video performance metrics.

    When YouTube Data API credentials are unavailable the engine operates in
    offline mode and returns cached data only.
    """

    def __init__(self, api_key: str = "", channel_id: str = ""):
        self._api_key = api_key
        self._channel_id = channel_id
        self._records: List[Dict[str, Any]] = _load_db()
        logger.info("AnalyticsEngine: loaded %d records", len(self._records))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_video_metrics(self, video_id: str, title: str = "") -> Optional[Dict[str, Any]]:
        """
        Fetch metrics for a single video from YouTube Analytics API.
        Falls back to cached record if API is unavailable.
        """
        record = self._fetch_from_api(video_id, title)
        if record:
            self._upsert(record)
            _save_db(self._records)
            logger.info("Fetched metrics for %s: views=%s ctr=%s",
                        video_id, record.get("views"), record.get("ctr"))
        else:
            record = self._get_cached(video_id)
            if record:
                logger.info("Using cached metrics for %s", video_id)
            else:
                logger.warning("No metrics available for %s", video_id)
        return record

    def update_analytics_database(self, records: List[Dict[str, Any]]) -> None:
        """Bulk-upsert a list of metric records."""
        for r in records:
            self._upsert(r)
        _save_db(self._records)
        logger.info("Analytics DB updated: %d total records", len(self._records))

    def get_top_performing_topics(self, n: int = 5) -> List[str]:
        """Return topic names of the top-n videos by views."""
        sorted_records = sorted(self._records, key=lambda r: r.get("views", 0), reverse=True)
        topics = []
        for r in sorted_records[:n]:
            t = r.get("topic") or r.get("title", "")
            if t:
                topics.append(t)
        logger.info("Top topics: %s", topics)
        return topics

    def get_low_performing_topics(self, n: int = 5) -> List[str]:
        """Return topic names of the bottom-n videos by views."""
        sorted_records = sorted(self._records, key=lambda r: r.get("views", 0))
        topics = []
        for r in sorted_records[:n]:
            t = r.get("topic") or r.get("title", "")
            if t:
                topics.append(t)
        logger.info("Low topics: %s", topics)
        return topics

    def get_avg_retention_drop(self) -> float:
        """Return average retention drop point in seconds across all records."""
        drops = []
        for r in self._records:
            dp = r.get("retention_drop_seconds")
            if dp is not None:
                drops.append(float(dp))
        if not drops:
            return 25.0  # safe default
        avg = sum(drops) / len(drops)
        logger.info("Avg retention drop: %.1fs", avg)
        return avg

    def get_avg_ctr(self) -> float:
        ctrs = [r.get("ctr", 0) for r in self._records if r.get("ctr")]
        return round(sum(ctrs) / len(ctrs), 2) if ctrs else 0.0

    def all_records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    def add_mock_record(self, video_id: str, title: str, views: int,
                        ctr: float, avg_watch_seconds: int,
                        retention_drop_seconds: int, topic: str = "") -> None:
        """Add a mock/manual record for testing without API access."""
        m, s = divmod(avg_watch_seconds, 60)
        record = {
            "video_id": video_id,
            "title": title,
            "topic": topic or title,
            "views": views,
            "ctr": ctr,
            "avg_watch_time": f"{m}:{s:02d}",
            "avg_watch_seconds": avg_watch_seconds,
            "retention_drop_seconds": retention_drop_seconds,
            "retention_drop_point": f"00:{retention_drop_seconds:02d}",
            "likes": 0,
            "comments": 0,
            "fetched_at": datetime.now().isoformat(),
        }
        self._upsert(record)
        _save_db(self._records)
        logger.info("Mock record added: %s", video_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_from_api(self, video_id: str, title: str) -> Optional[Dict[str, Any]]:
        if not self._api_key:
            return None
        try:
            import urllib.request
            url = (
                f"https://www.googleapis.com/youtube/v3/videos"
                f"?part=statistics&id={video_id}&key={self._api_key}"
            )
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            items = data.get("items", [])
            if not items:
                return None
            stats = items[0].get("statistics", {})
            return {
                "video_id": video_id,
                "title": title,
                "topic": title,
                "views": int(stats.get("viewCount", 0)),
                "ctr": 0.0,
                "avg_watch_time": "0:00",
                "avg_watch_seconds": 0,
                "retention_drop_seconds": 25,
                "retention_drop_point": "00:25",
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "fetched_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.warning("YouTube API fetch failed: %s", exc)
            return None

    def _upsert(self, record: Dict[str, Any]) -> None:
        vid = record.get("video_id")
        for i, r in enumerate(self._records):
            if r.get("video_id") == vid:
                self._records[i] = record
                return
        self._records.append(record)

    def _get_cached(self, video_id: str) -> Optional[Dict[str, Any]]:
        for r in self._records:
            if r.get("video_id") == video_id:
                return r
        return None
