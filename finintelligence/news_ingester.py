"""
FinIntelligence Market Analysis System — RSS news ingester.
Fetches and parses RSS feeds using feedparser, deduplicates by headline
within a 24-hour rolling window, and stores results via cache_manager.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import pandas as pd

from finintelligence.cache_manager import read_news, write_news
from finintelligence.config import RSS_URLS
from finintelligence.logger import get_logger

logger = get_logger("finintelligence.news_ingester")


def ingest_all_feeds() -> pd.DataFrame:
    """
    Fetch and parse all RSS feeds defined in RSS_URLS.
    Deduplicates entries by headline within a 24-hour rolling window,
    stores new entries via cache_manager.write_news, and returns a
    DataFrame of all newly ingested entries.

    DataFrame columns: headline, published, source, summary

    Returns:
        pd.DataFrame with columns [headline, published, source, summary].
        Empty DataFrame if no new entries were ingested.
    """
    all_entries: list[dict] = []

    for url in RSS_URLS:
        entries = _parse_feed(url)
        all_entries.extend(entries)

    if not all_entries:
        return pd.DataFrame(columns=["headline", "published", "source", "summary"])

    new_entries = _deduplicate(all_entries)

    if not new_entries:
        return pd.DataFrame(columns=["headline", "published", "source", "summary"])

    df = pd.DataFrame(new_entries, columns=["headline", "published", "source", "summary"])
    write_news(df)
    return df


def _parse_feed(url: str) -> list[dict]:
    """
    Fetch and parse a single RSS feed URL using feedparser.
    Extracts headline, published timestamp, source name (domain of URL),
    and summary text from each entry.

    Missing publication timestamp → uses ingestion timestamp (datetime.utcnow()).
    Unreachable or malformed feed → logs URL + error detail, returns empty list.

    Args:
        url: RSS feed URL to fetch and parse.

    Returns:
        List of dicts with keys: headline, published, source, summary.
    """
    ingestion_time = datetime.now(timezone.utc)
    source = _extract_domain(url)

    try:
        feed = feedparser.parse(url)

        # feedparser signals a hard error via bozo + bozo_exception when the
        # feed could not be fetched at all (e.g. connection refused, DNS failure).
        # A bozo feed with entries is still partially parseable — we continue.
        if feed.bozo and not feed.entries:
            exc = getattr(feed, "bozo_exception", None)
            logger.error(
                "news_ingester: unreachable or malformed feed %s — %s",
                url,
                exc,
            )
            return []

    except Exception as exc:  # pragma: no cover — network-level failure
        logger.error("news_ingester: failed to fetch feed %s — %s", url, exc)
        return []

    entries: list[dict] = []
    for entry in feed.entries:
        headline: str = getattr(entry, "title", "") or ""
        summary: str = getattr(entry, "summary", "") or ""

        # Resolve publication timestamp
        published: datetime
        if hasattr(entry, "published_parsed") and entry.published_parsed is not None:
            try:
                import time as _time
                published = datetime(
                    *entry.published_parsed[:6], tzinfo=timezone.utc
                )
            except Exception:
                published = ingestion_time
        else:
            published = ingestion_time

        entries.append(
            {
                "headline": headline,
                "published": published,
                "source": source,
                "summary": summary,
            }
        )

    return entries


def _deduplicate(entries: list[dict]) -> list[dict]:
    """
    Remove entries whose headline already exists in the cached news store
    within the last 24 hours, and also deduplicate within the provided
    entries list itself (keep first occurrence).

    Args:
        entries: List of dicts with keys: headline, published, source, summary.

    Returns:
        Filtered list containing only entries not already cached.
    """
    # Load headlines seen in the last 24 hours from cache
    cached_df = read_news(hours=24)
    cached_headlines: set[str] = set()
    if not cached_df.empty and "headline" in cached_df.columns:
        cached_headlines = set(cached_df["headline"].dropna().tolist())

    seen: set[str] = set(cached_headlines)
    unique: list[dict] = []

    for entry in entries:
        headline = entry.get("headline", "")
        if headline and headline not in seen:
            seen.add(headline)
            unique.append(entry)

    return unique


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Return the netloc (domain) portion of a URL, or the raw URL on failure."""
    try:
        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url
