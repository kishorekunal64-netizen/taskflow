"""
FinIntelligence Platform Layer — Engine Bridge.

Wraps the engine's APScheduler jobs so that after each job runs, results are
written to the in-memory Result_Cache and the PostgreSQL Durable_Store.

This module is imported ONLY from app.py lifespan. No router imports it.
The scheduler is started exactly once, here in start_engine().

Requirements: 5.2, 5.3, 5.4, 5.5, 9.3, 9.6, 10.4, 10.5, 10.6
"""

import dataclasses
import logging
import os
from datetime import datetime, timezone

import pandas as pd
import pyarrow.parquet as pq

from finintelligence.scheduler import build_scheduler
from finintelligence import cache_manager as engine_cache
from platform.result_cache import ResultCache
from platform import durable_store
from platform.monitoring import alert_manager

logger = logging.getLogger(__name__)

# Path to the engine's sentiment parquet (mirrors finintelligence/config.py)
_SENTIMENT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "finintelligence", "data", "sentiment", "sentiment.parquet"
)


def _read_latest_sentiment_dict() -> dict | None:
    """
    Read the last row from the engine's sentiment.parquet and return it as a
    plain dict. Returns None on any failure or if the file is empty.
    """
    try:
        df = pq.read_table(_SENTIMENT_PATH).to_pandas()
        if df.empty:
            return None
        row = df.iloc[-1]
        return row.to_dict()
    except Exception as exc:
        logger.debug("_read_latest_sentiment_dict() failed: %s", exc)
        return None


def _wrap_news_sentiment_job(scheduler, cache: ResultCache) -> None:
    """
    Wrap the 'news_ingestion' job.

    After the original job runs:
    - Read the latest sentiment from sentiment.parquet → cache 'market_sentiment'
    - Read the latest AI signal → cache 'ai_signals'
    - Upsert both into analysis_results in the Durable_Store
    """
    original_func = scheduler.get_job("news_ingestion").func

    def wrapped() -> None:
        logger.info("scheduler_event: news_ingestion_run started")
        # 1. Run the original job
        try:
            original_func()
        except Exception as exc:
            logger.error("news_ingestion original job raised: %s", exc)
            alert_manager.record("scheduler_failures")

        # 2. Read latest sentiment from parquet
        sentiment_dict: dict | None = None
        try:
            sentiment_dict = _read_latest_sentiment_dict()
            if sentiment_dict is not None:
                cache.set("market_sentiment", sentiment_dict)
                logger.debug("engine_bridge: updated market_sentiment cache")
        except Exception as exc:
            logger.error("engine_bridge: failed to update market_sentiment: %s", exc)

        # 3. Read latest AI signal
        ai_signal_dict: dict | None = None
        try:
            signal = engine_cache.read_latest_signal()
            if signal is not None:
                ai_signal_dict = dataclasses.asdict(signal)
                cache.set("ai_signals", ai_signal_dict)
                logger.debug("engine_bridge: updated ai_signals cache (from news job)")
        except Exception as exc:
            logger.error("engine_bridge: failed to update ai_signals (news job): %s", exc)

        # 4. Upsert into Durable_Store
        try:
            now = datetime.now(tz=timezone.utc)
            durable_store.upsert_analysis_results(
                date=now,
                sentiment_dict=sentiment_dict,
                sector_strength_list=cache.get("sector_strength"),
                ai_signal_dict=ai_signal_dict,
            )
        except Exception as exc:
            logger.error("engine_bridge: durable_store upsert failed (news job): %s", exc)

    scheduler.modify_job("news_ingestion", func=wrapped)


def _wrap_institutional_flow_job(scheduler, cache: ResultCache) -> None:
    """
    Wrap the 'institutional_flow' job.

    After the original job runs:
    - Read latest institutional flows → cache 'institutional_flows'
    - Read latest sector metrics → cache 'sector_strength'
    - Upsert both into the Durable_Store
    """
    original_func = scheduler.get_job("institutional_flow").func

    def wrapped() -> None:
        logger.info("scheduler_event: institutional_flow_run started")
        # 1. Run the original job
        try:
            original_func()
        except Exception as exc:
            logger.error("institutional_flow original job raised: %s", exc)
            alert_manager.record("scheduler_failures")

        # 2. Read latest institutional flows
        flow_dict: dict | None = None
        try:
            flows_df = engine_cache.read_institutional_flows()
            if not flows_df.empty:
                last_row = flows_df.iloc[-1].to_dict()
                cache.set("institutional_flows", last_row)
                flow_dict = last_row
                logger.debug("engine_bridge: updated institutional_flows cache")
        except Exception as exc:
            logger.error("engine_bridge: failed to update institutional_flows: %s", exc)

        # 3. Read latest sector metrics
        sector_list: list | None = None
        try:
            sector_df = engine_cache.read_sector_metrics()
            if not sector_df.empty:
                sector_list = sector_df.to_dict(orient="records")
                cache.set("sector_strength", sector_list)
                logger.debug("engine_bridge: updated sector_strength cache")
        except Exception as exc:
            logger.error("engine_bridge: failed to update sector_strength: %s", exc)

        # 4. Upsert institutional flow into Durable_Store
        if flow_dict is not None:
            try:
                flow_date = flow_dict.get("date")
                if flow_date is None:
                    flow_date = datetime.now(tz=timezone.utc)
                elif not isinstance(flow_date, datetime):
                    flow_date = pd.Timestamp(flow_date).to_pydatetime()
                durable_store.upsert_institutional_flow(date=flow_date, flow_dict=flow_dict)
            except Exception as exc:
                logger.error(
                    "engine_bridge: durable_store upsert_institutional_flow failed: %s", exc
                )

        # 5. Upsert sector performance into Durable_Store
        if sector_list is not None:
            try:
                sector_date = datetime.now(tz=timezone.utc)
                durable_store.upsert_sector_performance(
                    date=sector_date, sector_metrics_list=sector_list
                )
            except Exception as exc:
                logger.error(
                    "engine_bridge: durable_store upsert_sector_performance failed: %s", exc
                )

    scheduler.modify_job("institutional_flow", func=wrapped)


def _wrap_market_refresh_job(scheduler, cache: ResultCache) -> None:
    """
    Wrap the 'market_refresh' job.

    After the original job runs:
    - Read latest AI signal → cache 'ai_signals'
    - Read latest sentiment → cache 'market_sentiment'
    - Upsert analysis results into the Durable_Store
    """
    original_func = scheduler.get_job("market_refresh").func

    def wrapped() -> None:
        logger.info("scheduler_event: market_update_run started")
        # 1. Run the original job
        try:
            original_func()
        except Exception as exc:
            logger.error("market_refresh original job raised: %s", exc)
            alert_manager.record("scheduler_failures")

        # 2. Read latest AI signal
        ai_signal_dict: dict | None = None
        try:
            signal = engine_cache.read_latest_signal()
            if signal is not None:
                ai_signal_dict = dataclasses.asdict(signal)
                cache.set("ai_signals", ai_signal_dict)
                logger.debug("engine_bridge: updated ai_signals cache (market_refresh)")
        except Exception as exc:
            logger.error(
                "engine_bridge: failed to update ai_signals (market_refresh): %s", exc
            )

        # 3. Read latest sentiment from parquet
        sentiment_dict: dict | None = None
        try:
            sentiment_dict = _read_latest_sentiment_dict()
            if sentiment_dict is not None:
                cache.set("market_sentiment", sentiment_dict)
                logger.debug(
                    "engine_bridge: updated market_sentiment cache (market_refresh)"
                )
        except Exception as exc:
            logger.error(
                "engine_bridge: failed to update market_sentiment (market_refresh): %s", exc
            )

        # 4. Upsert analysis results into Durable_Store
        try:
            now = datetime.now(tz=timezone.utc)
            durable_store.upsert_analysis_results(
                date=now,
                sentiment_dict=sentiment_dict,
                sector_strength_list=cache.get("sector_strength"),
                ai_signal_dict=ai_signal_dict,
            )
        except Exception as exc:
            logger.error(
                "engine_bridge: durable_store upsert failed (market_refresh): %s", exc
            )

    scheduler.modify_job("market_refresh", func=wrapped)


def start_engine(cache: ResultCache) -> None:
    """
    Build the engine scheduler, wrap each job to write results to the
    Result_Cache and Durable_Store, then start the scheduler.

    This is the ONLY place scheduler.start() is called.
    Must not be imported by any router.
    """
    scheduler = build_scheduler()
    _wrap_news_sentiment_job(scheduler, cache)
    _wrap_institutional_flow_job(scheduler, cache)
    _wrap_market_refresh_job(scheduler, cache)
    scheduler.start()
    logger.info("Engine scheduler started")
