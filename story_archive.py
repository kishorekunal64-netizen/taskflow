"""
story_archive.py - Content memory / story archive for RAGAI Video Factory.

Maintains a SQLite database of previously generated stories to prevent
duplicate topics and enable similarity-based topic discovery.

Database: story_archive.db
Schema:
    stories(id, topic, summary, language, style, video_id, generated_at, word_count)

Functions:
    save_story()             — persist a generated story
    check_duplicate_topic()  — return True if topic is too similar to an existing one
    retrieve_similar_topics()— return list of similar past topics
    get_recent_topics()      — return N most recent topics (for engagement_predictor novelty)
    stats()                  — summary counts
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path("story_archive.db")
SIMILARITY_THRESHOLD = 0.45   # Jaccard similarity above this = duplicate


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id            TEXT PRIMARY KEY,
            topic         TEXT NOT NULL,
            summary       TEXT,
            language      TEXT DEFAULT 'hi',
            style         TEXT DEFAULT '',
            video_id      TEXT DEFAULT '',
            generated_at  TEXT NOT NULL,
            word_count    INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON stories(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_at ON stories(generated_at)")
    conn.commit()


@contextmanager
def _connect(db_path: Path = DB_PATH):
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
    finally:
        conn.close()


def _story_id(topic: str, generated_at: str) -> str:
    raw = f"{topic}|{generated_at}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> set:
    """Simple whitespace + punctuation tokeniser."""
    import re
    tokens = re.findall(r'\w+', text.lower())
    return set(tokens)


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokenise(a), _tokenise(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class StoryArchive:
    """
    Persistent story memory for the RAGAI pipeline.

    Usage::

        archive = StoryArchive()

        # Before generating:
        if archive.check_duplicate_topic("Village girl becomes IAS officer"):
            topic = archive.suggest_variant("Village girl becomes IAS officer")

        # After generating:
        archive.save_story(
            topic="Village girl becomes IAS officer",
            summary="A poor village girl overcomes hardship to become an IAS officer.",
            language="hi",
            style="cinematic",
            video_id="vid_abc123",
            word_count=850,
        )
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        # Ensure DB is initialised on first use
        with _connect(self.db_path):
            pass
        logger.info("StoryArchive initialised: %s", self.db_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_story(
        self,
        topic: str,
        summary: str = "",
        language: str = "hi",
        style: str = "",
        video_id: str = "",
        word_count: int = 0,
    ) -> str:
        """Persist a generated story. Returns the story ID."""
        now = datetime.now(timezone.utc).isoformat()
        sid = _story_id(topic, now)

        with _connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO stories
                   (id, topic, summary, language, style, video_id, generated_at, word_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sid, topic, summary, language, style, video_id, now, word_count),
            )
            conn.commit()

        logger.info("Story saved: id=%s topic='%s'", sid, topic)
        return sid

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def check_duplicate_topic(
        self,
        topic: str,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> bool:
        """
        Return True if a sufficiently similar topic already exists in the archive.
        Uses Jaccard similarity on tokenised topic strings.
        """
        existing = self._all_topics()
        for existing_topic in existing:
            sim = _jaccard(topic, existing_topic)
            if sim >= threshold:
                logger.info(
                    "Duplicate detected: '%s' ~ '%s' (jaccard=%.2f)",
                    topic, existing_topic, sim,
                )
                return True
        return False

    def similarity_score(self, topic: str) -> Tuple[float, str]:
        """Return (max_similarity, most_similar_topic) against the archive."""
        existing = self._all_topics()
        if not existing:
            return 0.0, ""
        best_sim, best_topic = 0.0, ""
        for et in existing:
            sim = _jaccard(topic, et)
            if sim > best_sim:
                best_sim, best_topic = sim, et
        return round(best_sim, 3), best_topic

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve_similar_topics(
        self,
        topic: str,
        top_n: int = 5,
        min_similarity: float = 0.2,
    ) -> List[Dict]:
        """
        Return up to top_n past topics similar to the given topic.
        Each result: {topic, similarity, generated_at, video_id}
        """
        existing = self._all_rows()
        scored = []
        for row in existing:
            sim = _jaccard(topic, row["topic"])
            if sim >= min_similarity:
                scored.append({
                    "topic":        row["topic"],
                    "similarity":   round(sim, 3),
                    "generated_at": row["generated_at"],
                    "video_id":     row["video_id"],
                })
        scored.sort(key=lambda r: r["similarity"], reverse=True)
        return scored[:top_n]

    def get_recent_topics(self, n: int = 20) -> List[str]:
        """Return the N most recently generated topic strings."""
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT topic FROM stories ORDER BY generated_at DESC LIMIT ?", (n,)
            ).fetchall()
        return [r["topic"] for r in rows]

    def suggest_variant(self, topic: str) -> str:
        """
        Suggest a variant of a duplicate topic by appending a differentiator.
        Simple heuristic — caller can use this as a seed for LLM regeneration.
        """
        similar = self.retrieve_similar_topics(topic, top_n=3)
        used_angles = {r["topic"] for r in similar}
        angles = [
            "from a different perspective",
            "with an unexpected twist",
            "set in modern times",
            "told through a child's eyes",
            "with a female protagonist",
        ]
        for angle in angles:
            candidate = f"{topic} — {angle}"
            if not any(_jaccard(candidate, u) > 0.6 for u in used_angles):
                logger.info("Suggested variant: '%s'", candidate)
                return candidate
        return f"{topic} — new angle"

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict:
        """Return summary statistics about the archive."""
        with _connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            by_lang = conn.execute(
                "SELECT language, COUNT(*) as cnt FROM stories GROUP BY language"
            ).fetchall()
            by_style = conn.execute(
                "SELECT style, COUNT(*) as cnt FROM stories GROUP BY style"
            ).fetchall()
            latest = conn.execute(
                "SELECT generated_at FROM stories ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()

        return {
            "total_stories":  total,
            "by_language":    {r["language"]: r["cnt"] for r in by_lang},
            "by_style":       {r["style"]: r["cnt"] for r in by_style},
            "latest_entry":   latest["generated_at"] if latest else None,
        }

    def all_topics(self) -> List[str]:
        """Public accessor for all stored topics."""
        return self._all_topics()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _all_topics(self) -> List[str]:
        with _connect(self.db_path) as conn:
            rows = conn.execute("SELECT topic FROM stories").fetchall()
        return [r["topic"] for r in rows]

    def _all_rows(self) -> List[sqlite3.Row]:
        with _connect(self.db_path) as conn:
            return conn.execute(
                "SELECT topic, generated_at, video_id FROM stories"
            ).fetchall()
