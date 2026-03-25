"""
manual_topic_loader.py — Manual topic input for RAGAI.

Loads topics from topics_manual.txt or topics_queue.json and injects
them into the pipeline with priority over auto-discovered topics.

Priority order:
  1. topics_manual.txt  (highest — user-typed topics)
  2. topics_queue.json  (scheduled queue)
  3. Automated topic discovery (lowest)

When enable_manual_topic_mode is False in ragai_advanced_config.json,
this module is a no-op and the pipeline behaves exactly as before.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_MANUAL_TXT  = Path("topics_manual.txt")
_QUEUE_JSON  = Path("topics_queue.json")


class ManualTopicLoader:
    """Load and prioritize manually provided topics."""

    def __init__(
        self,
        manual_txt: Path = _MANUAL_TXT,
        queue_json: Path = _QUEUE_JSON,
    ) -> None:
        self.manual_txt = Path(manual_txt)
        self.queue_json = Path(queue_json)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_manual_topics(self) -> List[str]:
        """Return topics from topics_manual.txt (one per line, # = comment)."""
        if not self.manual_txt.exists():
            return []
        topics = []
        for line in self.manual_txt.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                topics.append(line)
        logger.info("ManualTopicLoader: loaded %d topics from %s", len(topics), self.manual_txt)
        return topics

    def load_queue_topics(self) -> List[str]:
        """Return topics from topics_queue.json."""
        if not self.queue_json.exists():
            return []
        try:
            data = json.loads(self.queue_json.read_text(encoding="utf-8"))
            if isinstance(data, list):
                topics = [str(t) for t in data if t]
            elif isinstance(data, dict):
                topics = [str(t) for t in data.get("topics", []) if t]
            else:
                topics = []
            logger.info("ManualTopicLoader: loaded %d topics from %s", len(topics), self.queue_json)
            return topics
        except Exception as exc:
            logger.warning("ManualTopicLoader: failed to load %s — %s", self.queue_json, exc)
            return []

    def next_topic(self, auto_topics: Optional[List[str]] = None) -> Optional[str]:
        """Return the highest-priority available topic.

        Priority: manual_txt > queue_json > auto_topics.
        Returns None if no topics are available anywhere.
        """
        # 1. Manual text file
        manual = self.load_manual_topics()
        if manual:
            topic = manual[0]
            self._consume_manual_topic(topic)
            logger.info("ManualTopicLoader: using manual topic: %r", topic)
            return topic

        # 2. Queue JSON
        queue = self.load_queue_topics()
        if queue:
            topic = queue[0]
            self._consume_queue_topic(topic)
            logger.info("ManualTopicLoader: using queue topic: %r", topic)
            return topic

        # 3. Auto-discovered
        if auto_topics:
            topic = auto_topics[0]
            logger.info("ManualTopicLoader: using auto topic: %r", topic)
            return topic

        logger.info("ManualTopicLoader: no topics available")
        return None

    def all_prioritized(self, auto_topics: Optional[List[str]] = None) -> List[str]:
        """Return all topics in priority order (manual → queue → auto)."""
        result = self.load_manual_topics() + self.load_queue_topics()
        if auto_topics:
            # Deduplicate while preserving order
            seen = set(result)
            for t in auto_topics:
                if t not in seen:
                    result.append(t)
                    seen.add(t)
        return result

    def add_manual_topic(self, topic: str) -> None:
        """Append a topic to topics_manual.txt (GUI integration point)."""
        with open(self.manual_txt, "a", encoding="utf-8") as f:
            f.write(f"{topic}\n")
        logger.info("ManualTopicLoader: added topic to %s: %r", self.manual_txt, topic)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _consume_manual_topic(self, topic: str) -> None:
        """Remove the first occurrence of topic from topics_manual.txt."""
        if not self.manual_txt.exists():
            return
        lines = self.manual_txt.read_text(encoding="utf-8").splitlines()
        remaining = []
        consumed = False
        for line in lines:
            if not consumed and line.strip() == topic:
                consumed = True
                continue
            remaining.append(line)
        self.manual_txt.write_text("\n".join(remaining) + ("\n" if remaining else ""),
                                   encoding="utf-8")

    def _consume_queue_topic(self, topic: str) -> None:
        """Remove the first occurrence of topic from topics_queue.json."""
        if not self.queue_json.exists():
            return
        try:
            data = json.loads(self.queue_json.read_text(encoding="utf-8"))
            if isinstance(data, list):
                if topic in data:
                    data.remove(topic)
                self.queue_json.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            elif isinstance(data, dict) and "topics" in data:
                if topic in data["topics"]:
                    data["topics"].remove(topic)
                self.queue_json.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except Exception as exc:
            logger.warning("ManualTopicLoader: failed to consume queue topic — %s", exc)
