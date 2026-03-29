"""
FinIntelligence Market Analysis System — APScheduler job definitions.

Defines and registers all four periodic job types with a BackgroundScheduler
configured for the Asia/Kolkata timezone.

Jobs:
  - market_refresh_job:     every 15 min, Mon–Fri 09:15–15:30 IST
  - news_ingestion_job:     every 60 min, 7 days/week
  - institutional_flow_job: daily 18:00 IST, Mon–Fri
  - sector_sentiment_job:   chained after institutional_flow_job

`build_scheduler()` registers all jobs and returns the scheduler without
starting it — `main.py` calls `.start()`.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import traceback
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from finintelligence import data_fetcher, feature_generator, institutional_fetcher
from finintelligence import news_ingester, sector_rotation_engine, sentiment_engine
from finintelligence.event_detector import check_and_trigger
from finintelligence.logger import get_logger

logger = get_logger("finintelligence.scheduler")

_IST = pytz.timezone("Asia/Kolkata")

# Trading-hours guard constants (IST)
_MARKET_OPEN_HOUR = 9
_MARKET_OPEN_MINUTE = 15
_MARKET_CLOSE_HOUR = 15
_MARKET_CLOSE_MINUTE = 30


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------

def market_refresh_job() -> None:
    """
    Fetch all OHLCV data, compute features per symbol, and check event thresholds.

    Guard: skip if current IST time is before 09:15 or after 15:30.
    On exception: log job name + full traceback; do NOT re-raise.
    """
    try:
        now_ist = datetime.now(tz=_IST)
        open_minutes = _MARKET_OPEN_HOUR * 60 + _MARKET_OPEN_MINUTE
        close_minutes = _MARKET_CLOSE_HOUR * 60 + _MARKET_CLOSE_MINUTE
        current_minutes = now_ist.hour * 60 + now_ist.minute

        if current_minutes < open_minutes or current_minutes > close_minutes:
            logger.debug(
                "market_refresh_job: skipping — current IST time %02d:%02d is outside "
                "trading hours 09:15–15:30",
                now_ist.hour, now_ist.minute,
            )
            return

        logger.info("market_refresh_job: starting at IST %s", now_ist.strftime("%H:%M"))

        # Fetch all OHLCV data
        data_fetcher.fetch_all()

        # Compute features per symbol and aggregate
        from finintelligence.config import SYMBOLS, TIMEFRAMES
        aggregated_features: dict = {}
        for symbol in SYMBOLS:
            for timeframe in TIMEFRAMES:
                try:
                    features = feature_generator.compute_features(symbol, timeframe)
                    # Use 1D features for event detection (primary timeframe)
                    if timeframe == "1D":
                        aggregated_features[symbol] = features
                except Exception as exc:
                    logger.warning(
                        "market_refresh_job: compute_features failed for %s/%s — %s",
                        symbol, timeframe, exc,
                    )

        # Compute sentiment for event detection
        try:
            from finintelligence import sentiment_engine as _se
            sentiment = _se.compute_sentiment()
        except Exception as exc:
            logger.warning("market_refresh_job: compute_sentiment failed — %s", exc)
            sentiment = None

        # Load sector metrics and flows for event detection
        try:
            from finintelligence import cache_manager
            sector_df = cache_manager.read_sector_metrics()
            flows_df = cache_manager.read_institutional_flows()
        except Exception as exc:
            logger.warning("market_refresh_job: cache read failed — %s", exc)
            import pandas as pd
            sector_df = pd.DataFrame()
            flows_df = pd.DataFrame()

        # Check and trigger AI analysis if thresholds breached
        if sentiment is not None:
            try:
                check_and_trigger(aggregated_features, sentiment, sector_df, flows_df)
            except Exception as exc:
                logger.warning("market_refresh_job: check_and_trigger failed — %s", exc)

        logger.info("market_refresh_job: completed")

    except Exception:
        logger.error(
            "market_refresh_job: unhandled exception\n%s",
            traceback.format_exc(),
        )


def news_ingestion_job() -> None:
    """
    Ingest all RSS feeds and compute composite sentiment.

    On exception: log job name + full traceback; do NOT re-raise.
    """
    try:
        logger.info("news_ingestion_job: starting")
        news_ingester.ingest_all_feeds()
        sentiment_engine.compute_sentiment()
        logger.info("news_ingestion_job: completed")
    except Exception:
        logger.error(
            "news_ingestion_job: unhandled exception\n%s",
            traceback.format_exc(),
        )


def institutional_flow_job() -> None:
    """
    Fetch institutional flows, then chain into sector_sentiment_job.

    On exception: log job name + full traceback; do NOT re-raise.
    """
    try:
        logger.info("institutional_flow_job: starting")
        institutional_fetcher.fetch_institutional_flows()
        # Chain: sector rotation + sentiment after successful flow fetch
        sector_sentiment_job()
        logger.info("institutional_flow_job: completed")
    except Exception:
        logger.error(
            "institutional_flow_job: unhandled exception\n%s",
            traceback.format_exc(),
        )


def sector_sentiment_job() -> None:
    """
    Compute sector rotation metrics and composite sentiment.

    On exception: log job name + full traceback; do NOT re-raise.
    """
    try:
        logger.info("sector_sentiment_job: starting")
        sector_rotation_engine.compute_sector_metrics()
        sentiment_engine.compute_sentiment()
        logger.info("sector_sentiment_job: completed")
    except Exception:
        logger.error(
            "sector_sentiment_job: unhandled exception\n%s",
            traceback.format_exc(),
        )


# ---------------------------------------------------------------------------
# Scheduler builder
# ---------------------------------------------------------------------------

def build_scheduler() -> BackgroundScheduler:
    """
    Create and configure a BackgroundScheduler with all four jobs registered.

    Does NOT start the scheduler — caller is responsible for calling .start().

    Returns
    -------
    BackgroundScheduler
        Configured scheduler with Asia/Kolkata timezone and all jobs added.
    """
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # Job 1: Market refresh — every 15 min, Mon–Fri, hours 9–15
    # The CronTrigger fires at :00, :15, :30, :45 within hours 9–15.
    # An in-job guard skips execution before 09:15 and after 15:30.
    scheduler.add_job(
        market_refresh_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute="*/15",
            timezone="Asia/Kolkata",
        ),
        id="market_refresh",
        name="Market Refresh (15-min)",
        misfire_grace_time=60,
        coalesce=True,
    )

    # Job 2: News ingestion — every 60 minutes, 7 days/week
    scheduler.add_job(
        news_ingestion_job,
        trigger=IntervalTrigger(hours=1, timezone="Asia/Kolkata"),
        id="news_ingestion",
        name="News Ingestion (hourly)",
        misfire_grace_time=120,
        coalesce=True,
    )

    # Job 3: Institutional flow — daily 18:00 IST, Mon–Fri
    scheduler.add_job(
        institutional_flow_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=18,
            minute=0,
            timezone="Asia/Kolkata",
        ),
        id="institutional_flow",
        name="Institutional Flow (daily 18:00 IST)",
        misfire_grace_time=300,
        coalesce=True,
    )

    logger.info(
        "build_scheduler: registered 3 jobs "
        "(market_refresh, news_ingestion, institutional_flow); "
        "sector_sentiment_job is chained inside institutional_flow_job"
    )
    return scheduler
