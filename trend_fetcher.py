"""
trend_fetcher.py — Fetch real-time trending topics from free APIs for RAGAI Trend Booster.

Sources:
  1. Google Trends (pytrends) — trending searches in India
  2. Nitter RSS — Twitter/X trending (no API key)
  3. YouTube trending RSS — most popular in India (Hindi)

Results are cached for 30 minutes to avoid repeated API calls.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

# Cache: (timestamp, results)
_cache: dict[str, tuple[float, List[str]]] = {}
_CACHE_TTL = 1800  # 30 minutes

# Nitter instances to try (public, no auth)
_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

# YouTube trending RSS for India (Hindi)
_YT_RSS_URL = "https://www.youtube.com/feeds/videos.xml?chart=mostpopular&regionCode=IN&hl=hi"


def _is_cached(key: str) -> bool:
    if key not in _cache:
        return False
    ts, _ = _cache[key]
    return (time.time() - ts) < _CACHE_TTL


def _get_cached(key: str) -> List[str]:
    return _cache[key][1]


def _set_cache(key: str, results: List[str]) -> None:
    _cache[key] = (time.time(), results)


# ---------------------------------------------------------------------------
# Individual source fetchers
# ---------------------------------------------------------------------------

def _fetch_google_trends(topic: str) -> List[str]:
    """Fetch trending searches from Google Trends India via pytrends."""
    try:
        from pytrends.request import TrendReq  # type: ignore
        pt = TrendReq(hl="hi-IN", tz=330, timeout=(5, 15))

        # today_searches is more reliable than trending_searches
        try:
            trending_df = pt.today_searches(pn="IN")
            trends = trending_df.tolist()[:20]
        except Exception:
            # fallback: related queries for the topic itself
            pt.build_payload([topic[:100]], geo="IN", timeframe="now 1-d")
            related = pt.related_queries()
            trends = []
            for val in related.values():
                if val and val.get("top") is not None:
                    trends += val["top"]["query"].tolist()[:10]

        if not trends:
            return []

        # Filter by keyword relevance to topic
        topic_words = set(topic.lower().split())
        relevant = [t for t in trends if any(w in t.lower() for w in topic_words)]
        return relevant[:5] if relevant else trends[:5]
    except ImportError:
        logger.warning("pytrends not installed — skipping Google Trends")
        return []
    except Exception as exc:
        logger.warning("Google Trends fetch failed: %s", exc)
        return []


def _fetch_nitter_trends() -> List[str]:
    """Fetch trending topics from Nitter RSS (Twitter/X mirror)."""
    try:
        import feedparser  # type: ignore
        import requests

        for instance in _NITTER_INSTANCES:
            try:
                url = f"{instance}/search/rss?q=%23trending+india&f=tweets"
                resp = requests.get(url, timeout=8, headers={"User-Agent": "RAGAI/1.0"})
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    titles = [e.title for e in feed.entries[:10] if hasattr(e, "title")]
                    if titles:
                        return titles[:5]
            except Exception:
                continue
        return []
    except ImportError:
        logger.warning("feedparser not installed — skipping Nitter trends")
        return []
    except Exception as exc:
        logger.warning("Nitter fetch failed: %s", exc)
        return []


def _fetch_youtube_trends() -> List[str]:
    """Fetch YouTube trending video titles from RSS feed."""
    try:
        import feedparser  # type: ignore
        import requests

        resp = requests.get(_YT_RSS_URL, timeout=10, headers={"User-Agent": "RAGAI/1.0"})
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
        titles = [e.title for e in feed.entries[:15] if hasattr(e, "title")]
        return titles[:5]
    except ImportError:
        logger.warning("feedparser not installed — skipping YouTube trends")
        return []
    except Exception as exc:
        logger.warning("YouTube trends fetch failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Relevance filtering
# ---------------------------------------------------------------------------

def _filter_by_relevance(items: List[str], topic: str) -> List[str]:
    """Score items by keyword overlap with topic and return sorted list."""
    topic_words = set(topic.lower().split())
    if not topic_words:
        return items

    def score(item: str) -> int:
        item_words = set(item.lower().split())
        return len(topic_words & item_words)

    scored = sorted(items, key=score, reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_trends(topic: str) -> List[str]:
    """Fetch top 5 trending angles relevant to *topic*.

    Returns cached results if available (30-min TTL).
    Falls back gracefully if internet is unavailable.
    """
    cache_key = topic.lower().strip()
    if _is_cached(cache_key):
        logger.info("Trend Booster: returning cached results for '%s'", topic)
        return _get_cached(cache_key)

    logger.info("Trend Booster: fetching trends for topic '%s'", topic)
    all_trends: List[str] = []

    # Collect from all sources
    google = _fetch_google_trends(topic)
    nitter = _fetch_nitter_trends()
    youtube = _fetch_youtube_trends()

    all_trends = google + nitter + youtube

    if not all_trends:
        logger.warning("Trend Booster: all sources returned empty — using fallback angles")
        all_trends = _fallback_angles(topic)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: List[str] = []
    for t in all_trends:
        key = t.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)

    # Filter by relevance and cap at 5
    results = _filter_by_relevance(unique, topic)[:5]
    _set_cache(cache_key, results)
    return results


def _fallback_angles(topic: str) -> List[str]:
    """Generate generic viral angles when all APIs fail."""
    return [
        f"{topic} — shocking truth revealed",
        f"Why everyone is talking about {topic}",
        f"{topic} — what they don't want you to know",
        f"The real story behind {topic}",
        f"{topic} — viral moment of 2025",
    ]


def generate_hashtags(topic: str, trends: List[str]) -> List[str]:
    """Generate top 10 hashtags from topic + trending terms."""
    words = topic.split() + [w for t in trends for w in t.split()]
    # Deduplicate, clean, and format
    seen: set[str] = set()
    tags: List[str] = []
    for w in words:
        clean = w.strip("#@.,!?").replace(" ", "")
        if len(clean) >= 3 and clean.lower() not in seen:
            seen.add(clean.lower())
            tags.append(f"#{clean}")
        if len(tags) >= 10:
            break
    return tags
