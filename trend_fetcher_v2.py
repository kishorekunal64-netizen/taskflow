"""
trend_fetcher_v2.py — All-source trend fetcher for RAGAI v9.0.

Sources (all free, no mandatory API key):
  1. Google Trends India    — pytrends
  2. YouTube Trending India — YouTube Data API v3 (optional key)
  3. RSS News India         — 4 major feeds
  4. Wikipedia Trending     — public API

Outputs scored, deduped topics to topics_queue.json.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

_TOPICS_QUEUE = Path("topics_queue.json")
_TOPICS_MANUAL = Path("topics_manual.txt")

# ---------------------------------------------------------------------------
# Emotion/curiosity/relatability keyword scorer (reuses topic_quality_engine logic)
# ---------------------------------------------------------------------------

_EMOTION_KW = {"love", "death", "sacrifice", "betrayal", "hope", "fear", "anger",
               "joy", "grief", "revenge", "courage", "struggle", "victory", "loss",
               "प्यार", "मृत्यु", "बलिदान", "संघर्ष", "जीत", "डर", "खुशी"}

_CURIOSITY_KW = {"secret", "mystery", "hidden", "truth", "revealed", "shocking",
                 "unknown", "discovered", "रहस्य", "सच", "खुलासा", "अनजान"}

_RELATABLE_KW = {"village", "family", "mother", "father", "farmer", "student",
                 "poor", "rich", "marriage", "child", "गाँव", "परिवार", "माँ",
                 "बाप", "किसान", "गरीब", "अमीर", "शादी", "बच्चा"}

_STORY_TRANSFORMS = [
    (r"(\w+) wins? (.+)", r"How \1 won \2 — an inspiring story"),
    (r"(\w+) dies?", r"The last days of \1 — a true story"),
    (r"(\w+) arrested", r"Why \1 was arrested — the full story"),
    (r"(\w+) launches? (.+)", r"The story behind \1's \2"),
    (r"(.+) crisis", r"A family surviving the \1 crisis"),
    (r"(.+) flood", r"A village saved from the \1 flood"),
    (r"(.+) election", r"A common man's fight during the \1 election"),
]


def _score_topic(topic: str) -> float:
    lower = topic.lower()
    score = 0.0
    score += sum(2.0 for kw in _EMOTION_KW if kw in lower)
    score += sum(1.5 for kw in _CURIOSITY_KW if kw in lower)
    score += sum(2.0 for kw in _RELATABLE_KW if kw in lower)
    # Length bonus — longer topics tend to be more specific
    words = len(topic.split())
    if 5 <= words <= 15:
        score += 1.0
    return round(score, 2)


def _to_story_topic(headline: str) -> str:
    """Transform a news headline into a RAGAI story topic."""
    for pattern, replacement in _STORY_TRANSFORMS:
        result = re.sub(pattern, replacement, headline, flags=re.IGNORECASE)
        if result != headline:
            return result.strip()
    # Generic transform
    return f"A story inspired by: {headline.strip()}"


def _jaccard(a: str, b: str) -> float:
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _dedup(topics: List[str], existing: List[str], threshold: float = 0.5) -> List[str]:
    """Remove topics too similar to existing ones."""
    all_existing = list(existing)
    result = []
    for t in topics:
        if all(_jaccard(t, e) < threshold for e in all_existing):
            result.append(t)
            all_existing.append(t)
    return result


# ---------------------------------------------------------------------------
# Source 1 — Google Trends India
# ---------------------------------------------------------------------------

def _fetch_google_trends(limit: int = 20) -> List[str]:
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="hi-IN", tz=330, timeout=(10, 25))
        df = pt.trending_searches(pn="india")
        topics = df[0].tolist()[:limit]
        logger.info("Google Trends: %d topics fetched", len(topics))
        return [_to_story_topic(t) for t in topics]
    except Exception as exc:
        logger.warning("Google Trends failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Source 2 — YouTube Trending India (optional API key)
# ---------------------------------------------------------------------------

def _fetch_youtube_trending(api_key: Optional[str] = None, limit: int = 10) -> List[str]:
    if not api_key:
        api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        logger.info("YouTube trending: no API key — skipping")
        return []
    try:
        url = (
            f"https://www.googleapis.com/youtube/v3/videos"
            f"?part=snippet&chart=mostPopular&regionCode=IN"
            f"&videoCategoryId=0&maxResults={limit}&key={api_key}"
        )
        req = Request(url, headers={"User-Agent": "RAGAI/9.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        titles = [item["snippet"]["title"] for item in data.get("items", [])]
        logger.info("YouTube trending: %d titles fetched", len(titles))
        return [_to_story_topic(t) for t in titles]
    except Exception as exc:
        logger.warning("YouTube trending failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Source 3 — RSS News India
# ---------------------------------------------------------------------------

_RSS_FEEDS = [
    "https://feeds.feedburner.com/ndtvnews-india-news",
    "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
]


def _fetch_rss(limit: int = 15) -> List[str]:
    topics = []
    for feed_url in _RSS_FEEDS:
        try:
            req = Request(feed_url, headers={"User-Agent": "RAGAI/9.0"})
            with urlopen(req, timeout=10) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            items = root.findall(".//item/title")
            for item in items[:5]:
                if item.text:
                    topics.append(_to_story_topic(item.text.strip()))
        except Exception as exc:
            logger.debug("RSS feed %s failed: %s", feed_url, exc)
    logger.info("RSS feeds: %d topics fetched", len(topics))
    return topics[:limit]


# ---------------------------------------------------------------------------
# Source 4 — Wikipedia Trending India
# ---------------------------------------------------------------------------

def _fetch_wikipedia_trending(limit: int = 10) -> List[str]:
    try:
        today = datetime.now(timezone.utc)
        url = (
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
            f"en.wikipedia/all-access/{today.year}/{today.month:02d}/{today.day:02d}"
        )
        req = Request(url, headers={"User-Agent": "RAGAI/9.0"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        articles = data["items"][0]["articles"][:limit]
        titles = [a["article"].replace("_", " ") for a in articles
                  if a["article"] not in ("Main_Page", "Special:Search")]
        logger.info("Wikipedia trending: %d articles fetched", len(titles))
        return [_to_story_topic(t) for t in titles[:limit]]
    except Exception as exc:
        logger.warning("Wikipedia trending failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Manual topics (highest priority)
# ---------------------------------------------------------------------------

def _load_manual_topics() -> List[str]:
    if not _TOPICS_MANUAL.exists():
        return []
    lines = [l.strip() for l in _TOPICS_MANUAL.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    logger.info("Manual topics: %d loaded", len(lines))
    return lines


# ---------------------------------------------------------------------------
# Main fetch + score + write
# ---------------------------------------------------------------------------

def fetch_and_queue(
    youtube_api_key: Optional[str] = None,
    min_score: float = 1.0,
    max_new: int = 30,
) -> List[str]:
    """Fetch from all sources, score, dedup, write to topics_queue.json.

    Returns list of newly added topics.
    """
    # Load existing queue
    existing: List[str] = []
    if _TOPICS_QUEUE.exists():
        try:
            existing = json.loads(_TOPICS_QUEUE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    # Collect from all sources
    manual = _load_manual_topics()
    google = _fetch_google_trends()
    youtube = _fetch_youtube_trending(youtube_api_key)
    rss = _fetch_rss()
    wiki = _fetch_wikipedia_trending()

    # Priority order: manual first, then scored sources
    all_candidates = manual + google + youtube + rss + wiki

    # Score and filter
    scored = [(t, _score_topic(t)) for t in all_candidates]
    scored = [(t, s) for t, s in scored if s >= min_score]
    scored.sort(key=lambda x: -x[1])

    # Dedup against existing queue
    new_topics = _dedup([t for t, _ in scored], existing)[:max_new]

    if new_topics:
        updated = new_topics + existing  # new topics go to front
        _TOPICS_QUEUE.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Added %d new topics to queue (total: %d)", len(new_topics), len(updated))
    else:
        logger.info("No new topics to add (all deduped or below score threshold)")

    return new_topics


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    new = fetch_and_queue()
    print(f"\nAdded {len(new)} new topics:")
    for t in new[:10]:
        print(f"  • {t}")
