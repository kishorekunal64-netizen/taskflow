import json
import logging
from datetime import datetime

from finplatform.db import get_conn
from finplatform.result_cache import ResultCache

logger = logging.getLogger(__name__)


def prewarm_cache(cache: ResultCache) -> None:
    """On startup: read latest rows from durable tables and populate the cache."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT market_sentiment, sector_strength, ai_signal "
                    "FROM analysis_results ORDER BY date DESC LIMIT 1"
                )
                row = cur.fetchone()
        if row:
            cache.set("market_sentiment", row[0])
            cache.set("sector_strength", row[1])
            cache.set("ai_signals", row[2])
    except Exception as e:
        logger.error(f"prewarm analysis_results failed: {e}")

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT date, fii_buy, fii_sell, dii_buy, dii_sell, net_flow "
                    "FROM institutional_flow ORDER BY date DESC LIMIT 1"
                )
                row = cur.fetchone()
        if row:
            cache.set("institutional_flows", {
                "date": row[0],
                "fii_buy": row[1],
                "fii_sell": row[2],
                "dii_buy": row[3],
                "dii_sell": row[4],
                "net_flow": row[5],
            })
    except Exception as e:
        logger.error(f"prewarm institutional_flow failed: {e}")


def upsert_analysis_results(
    date: datetime,
    sentiment_dict: dict | None,
    sector_strength_list: list | None,
    ai_signal_dict: dict | None,
) -> None:
    """Upsert latest analysis results. Called only from engine_bridge.py."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analysis_results (date, market_sentiment, sector_strength, ai_signal)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    market_sentiment = EXCLUDED.market_sentiment,
                    sector_strength  = EXCLUDED.sector_strength,
                    ai_signal        = EXCLUDED.ai_signal
                """,
                (
                    date,
                    json.dumps(sentiment_dict),
                    json.dumps(sector_strength_list),
                    json.dumps(ai_signal_dict),
                ),
            )
        conn.commit()


def upsert_sector_performance(date: datetime, sector_metrics_list: list[dict]) -> None:
    """Upsert sector performance rows. Called only from engine_bridge.py."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in sector_metrics_list:
                cur.execute(
                    """
                    INSERT INTO sector_performance (date, sector, momentum_score, relative_strength, ranking)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (date, sector) DO UPDATE SET
                        momentum_score    = EXCLUDED.momentum_score,
                        relative_strength = EXCLUDED.relative_strength,
                        ranking           = EXCLUDED.ranking
                    """,
                    (
                        date,
                        item.get("sector"),
                        item.get("momentum_score"),
                        item.get("relative_strength"),
                        item.get("ranking"),
                    ),
                )
        conn.commit()


def upsert_institutional_flow(date: datetime, flow_dict: dict) -> None:
    """Upsert institutional flow row. Called only from engine_bridge.py."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO institutional_flow (date, fii_buy, fii_sell, dii_buy, dii_sell, net_flow)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    fii_buy  = EXCLUDED.fii_buy,
                    fii_sell = EXCLUDED.fii_sell,
                    dii_buy  = EXCLUDED.dii_buy,
                    dii_sell = EXCLUDED.dii_sell,
                    net_flow = EXCLUDED.net_flow
                """,
                (
                    date,
                    flow_dict.get("fii_buy"),
                    flow_dict.get("fii_sell"),
                    flow_dict.get("dii_buy"),
                    flow_dict.get("dii_sell"),
                    flow_dict.get("net_flow"),
                ),
            )
        conn.commit()
