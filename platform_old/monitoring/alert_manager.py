"""
Lightweight monitoring and alerting layer.
Tracks error counts per metric type and logs CRITICAL alerts when
hourly thresholds are exceeded. No external services required.
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("platform.monitoring")

# ── Thresholds (errors per hour) ─────────────────────────────────────────────
THRESHOLDS: dict[str, int] = {
    "api_errors": 20,
    "data_fetch_failures": 5,
    "ai_analysis_failures": 3,
    "scheduler_failures": 5,
}

# ── Internal state ────────────────────────────────────────────────────────────
_lock = threading.Lock()
# metric -> list of UTC datetimes when the error occurred
_events: dict[str, list[datetime]] = defaultdict(list)


def record(metric: str) -> None:
    """Record one occurrence of a metric error and check threshold."""
    if metric not in THRESHOLDS:
        logger.warning("monitoring: unknown metric '%s'", metric)
        return

    now = datetime.now(tz=timezone.utc)
    with _lock:
        _events[metric].append(now)
        # Prune events older than 1 hour
        cutoff = now.timestamp() - 3600
        _events[metric] = [t for t in _events[metric] if t.timestamp() >= cutoff]
        count = len(_events[metric])

    threshold = THRESHOLDS[metric]
    if count >= threshold:
        logger.critical(
            "ALERT | metric=%s | count_last_hour=%d | threshold=%d | "
            "action=investigate_immediately",
            metric, count, threshold,
        )
    else:
        logger.debug("monitoring: metric=%s count_last_hour=%d", metric, count)


def get_counts() -> dict[str, int]:
    """Return current hourly error counts for all tracked metrics."""
    now = datetime.now(tz=timezone.utc)
    cutoff = now.timestamp() - 3600
    with _lock:
        return {
            metric: len([t for t in times if t.timestamp() >= cutoff])
            for metric, times in _events.items()
        }


def reset() -> None:
    """Clear all counters. Intended for testing only."""
    with _lock:
        _events.clear()
