"""
story_knowledge_graph.py — Semantic story memory for RAGAI.

Stores structured story metadata in SQLite (story_graph.db) and provides
similarity search to prevent semantic repetition across generated videos.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = Path("story_graph.db")


class StoryKnowledgeGraph:
    """Persistent graph of generated stories with semantic search."""

    def __init__(self, db_path: Path = _DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self._init_db()
        logger.info("StoryKnowledgeGraph initialised: %s", self.db_path)

    # ------------------------------------------------------------------
    # DB setup
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stories (
                    id          TEXT PRIMARY KEY,
                    topic       TEXT NOT NULL,
                    characters  TEXT DEFAULT '[]',
                    locations   TEXT DEFAULT '[]',
                    themes      TEXT DEFAULT '[]',
                    emotion_arc TEXT DEFAULT '[]',
                    language    TEXT DEFAULT 'hi',
                    style       TEXT DEFAULT '',
                    video_id    TEXT DEFAULT '',
                    created_at  TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON stories(topic)")

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def add_story(
        self,
        topic: str,
        characters: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        themes: Optional[List[str]] = None,
        emotion_arc: Optional[List[str]] = None,
        language: str = "hi",
        style: str = "",
        video_id: str = "",
    ) -> str:
        """Add a story to the graph. Returns the generated story ID."""
        import hashlib
        sid = hashlib.md5(f"{topic}{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO stories
                   (id, topic, characters, locations, themes, emotion_arc,
                    language, style, video_id, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    sid, topic,
                    json.dumps(characters or [], ensure_ascii=False),
                    json.dumps(locations or [], ensure_ascii=False),
                    json.dumps(themes or [], ensure_ascii=False),
                    json.dumps(emotion_arc or [], ensure_ascii=False),
                    language, style, video_id, now,
                ),
            )
        logger.info("StoryGraph: added story id=%s topic=%r", sid, topic[:60])
        return sid

    def search_similar_story(self, topic: str, threshold: float = 0.35) -> Optional[Dict]:
        """Return the most similar stored story, or None if below threshold."""
        topic_words = set(topic.lower().split())
        best_score = 0.0
        best_row = None

        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM stories").fetchall()

        for row in rows:
            stored_words = set(row["topic"].lower().split())
            union = topic_words | stored_words
            if not union:
                continue
            jaccard = len(topic_words & stored_words) / len(union)
            if jaccard > best_score:
                best_score = jaccard
                best_row = row

        if best_row and best_score >= threshold:
            result = dict(best_row)
            result["similarity"] = round(best_score, 3)
            result["characters"] = json.loads(result["characters"])
            result["locations"] = json.loads(result["locations"])
            result["themes"] = json.loads(result["themes"])
            result["emotion_arc"] = json.loads(result["emotion_arc"])
            logger.info("StoryGraph: similar story found (jaccard=%.2f) for %r", best_score, topic[:60])
            return result

        return None

    def suggest_story_variant(self, topic: str) -> str:
        """Suggest a variant topic to avoid repetition."""
        similar = self.search_similar_story(topic)
        if not similar:
            return topic

        # Simple variant: append a differentiating angle
        angles = [
            "with an unexpected twist",
            "from a different perspective",
            "in a modern setting",
            "with a focus on family bonds",
            "highlighting inner strength",
        ]
        import random
        angle = random.choice(angles)
        variant = f"{topic} — {angle}"
        logger.info("StoryGraph: suggested variant: %r", variant)
        return variant

    def stats(self) -> Dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            by_lang = {}
            for row in conn.execute("SELECT language, COUNT(*) as c FROM stories GROUP BY language"):
                by_lang[row["language"]] = row["c"]
        return {"total_stories": total, "by_language": by_lang}
