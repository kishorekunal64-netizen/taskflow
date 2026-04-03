"""
scheduler_monitor.py — Reads scheduler queue/status for RAGAI Editor V3.

Reads from:
  topics_queue.json   — pending topics
  tmp/scheduler_status.json — last run result
  tmp/ragai_quota.json — quota usage

Never modifies any file — read-only monitor.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_QUEUE_FILE   = Path("topics_queue.json")
_STATUS_FILE  = Path("tmp/scheduler_status.json")
_QUOTA_FILE   = Path("tmp/ragai_quota.json")


@dataclass
class SchedulerStatus:
    running: bool = False
    queue_size: int = 0
    current_topic: str = ""
    last_result: str = ""
    next_job: str = ""
    pending_topics: List[str] = field(default_factory=list)
    groq_used: int = 0
    groq_limit: int = 500_000
    leo_used: int = 0
    leo_limit: int = 150


def read_status() -> SchedulerStatus:
    st = SchedulerStatus()

    # Queue
    if _QUEUE_FILE.exists():
        try:
            data = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                st.pending_topics = [str(t) for t in data]
            elif isinstance(data, dict):
                st.pending_topics = [str(t) for t in data.get("topics", [])]
            st.queue_size = len(st.pending_topics)
            if st.pending_topics:
                st.next_job = st.pending_topics[0]
        except Exception as exc:
            logger.debug("Could not read topics_queue.json: %s", exc)

    # Scheduler status
    if _STATUS_FILE.exists():
        try:
            data = json.loads(_STATUS_FILE.read_text(encoding="utf-8"))
            st.running = bool(data.get("running", False))
            st.current_topic = str(data.get("current_topic", ""))
            st.last_result = str(data.get("last_result", ""))
        except Exception as exc:
            logger.debug("Could not read scheduler_status.json: %s", exc)

    # Quota
    if _QUOTA_FILE.exists():
        try:
            data = json.loads(_QUOTA_FILE.read_text(encoding="utf-8"))
            st.groq_used = int(data.get("groq_used", 0))
            st.leo_used  = int(data.get("leonardo_used", 0))
        except Exception as exc:
            logger.debug("Could not read ragai_quota.json: %s", exc)

    return st
