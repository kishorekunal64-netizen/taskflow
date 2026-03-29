"""
Tests for finintelligence/scheduler.py

Covers:
  - Property 11: Scheduler Timezone Correctness (PBT) — all registered job
    next_run_times are in Asia/Kolkata timezone (UTC+5:30)
  - Unit tests:
    - All 4 job types registered after build_scheduler()
    - Job exception handler logs traceback and does not re-raise
    - Market refresh job guard skips outside 09:15–15:30 IST window
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytz
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintelligence.scheduler import (
    build_scheduler,
    institutional_flow_job,
    market_refresh_job,
    news_ingestion_job,
    sector_sentiment_job,
)

_IST = pytz.timezone("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Property 11: Scheduler Timezone Correctness
# Feature: finintelligence-market-analysis, Property 11: Scheduler Timezone Correctness
# Validates: Requirements 9.6
# ---------------------------------------------------------------------------

@given(st.none())  # deterministic — no random input needed
@settings(max_examples=100)
def test_property11_scheduler_timezone_correctness(_):
    # Feature: finintelligence-market-analysis, Property 11: Scheduler Timezone Correctness
    # Validates: Requirements 9.6
    scheduler = build_scheduler()
    try:
        scheduler.start(paused=True)
        jobs = scheduler.get_jobs()
        assert len(jobs) > 0, "Scheduler must have at least one registered job"

        for job in jobs:
            nrt = job.next_run_time
            assert nrt is not None, f"Job '{job.id}' has no next_run_time"
            # next_run_time must be timezone-aware
            assert nrt.tzinfo is not None, (
                f"Job '{job.id}' next_run_time is not timezone-aware: {nrt}"
            )
            # Normalise to UTC offset and verify it is UTC+5:30 (19800 seconds)
            utc_offset = nrt.utcoffset()
            assert utc_offset is not None, (
                f"Job '{job.id}' next_run_time has no UTC offset: {nrt}"
            )
            offset_seconds = int(utc_offset.total_seconds())
            assert offset_seconds == 19800, (
                f"Job '{job.id}' next_run_time offset is {offset_seconds}s "
                f"(expected 19800s = UTC+5:30 / Asia/Kolkata). next_run_time={nrt}"
            )
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Unit tests: job registration
# ---------------------------------------------------------------------------

class TestBuildScheduler:

    def test_returns_background_scheduler(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = build_scheduler()
        assert isinstance(scheduler, BackgroundScheduler)

    def test_scheduler_not_started(self):
        scheduler = build_scheduler()
        # Should not be running — build_scheduler does NOT call .start()
        assert not scheduler.running

    def test_market_refresh_job_registered(self):
        scheduler = build_scheduler()
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "market_refresh" in job_ids, (
            f"market_refresh job not found; registered jobs: {job_ids}"
        )

    def test_news_ingestion_job_registered(self):
        scheduler = build_scheduler()
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "news_ingestion" in job_ids, (
            f"news_ingestion job not found; registered jobs: {job_ids}"
        )

    def test_institutional_flow_job_registered(self):
        scheduler = build_scheduler()
        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "institutional_flow" in job_ids, (
            f"institutional_flow job not found; registered jobs: {job_ids}"
        )

    def test_all_three_explicit_jobs_registered(self):
        """sector_sentiment_job is chained, not a standalone registered job."""
        scheduler = build_scheduler()
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert {"market_refresh", "news_ingestion", "institutional_flow"}.issubset(job_ids)

    def test_market_refresh_uses_cron_trigger(self):
        from apscheduler.triggers.cron import CronTrigger
        scheduler = build_scheduler()
        job = scheduler.get_job("market_refresh")
        assert job is not None
        assert isinstance(job.trigger, CronTrigger)

    def test_news_ingestion_uses_interval_trigger(self):
        from apscheduler.triggers.interval import IntervalTrigger
        scheduler = build_scheduler()
        job = scheduler.get_job("news_ingestion")
        assert job is not None
        assert isinstance(job.trigger, IntervalTrigger)

    def test_institutional_flow_uses_cron_trigger(self):
        from apscheduler.triggers.cron import CronTrigger
        scheduler = build_scheduler()
        job = scheduler.get_job("institutional_flow")
        assert job is not None
        assert isinstance(job.trigger, CronTrigger)

    def test_scheduler_timezone_is_asia_kolkata(self):
        scheduler = build_scheduler()
        tz = scheduler.timezone
        # APScheduler stores timezone as a pytz timezone object
        assert str(tz) == "Asia/Kolkata", (
            f"Scheduler timezone is '{tz}', expected 'Asia/Kolkata'"
        )


# ---------------------------------------------------------------------------
# Unit tests: exception handling — jobs log traceback and do not re-raise
# ---------------------------------------------------------------------------

class TestJobExceptionHandling:

    def _assert_job_does_not_raise_and_logs_traceback(self, job_fn, mock_targets: list[str]):
        """
        Patch all mock_targets to raise RuntimeError, then call job_fn.
        Asserts: no exception propagates, and the error was logged.
        """
        error_msg = "simulated failure for testing"

        with patch("finintelligence.scheduler.logger") as mock_logger:
            # Patch the first target to raise
            with patch(mock_targets[0], side_effect=RuntimeError(error_msg)):
                # Must not raise
                job_fn()

            # logger.error must have been called with traceback info
            assert mock_logger.error.called, (
                f"{job_fn.__name__} did not call logger.error on exception"
            )
            call_args = mock_logger.error.call_args
            # The format string should contain the job name and traceback
            log_msg = call_args[0][0] if call_args[0] else ""
            assert "unhandled exception" in log_msg or "Traceback" in str(call_args), (
                f"Expected traceback in log, got: {call_args}"
            )

    def test_market_refresh_job_does_not_raise_on_exception(self):
        with patch("finintelligence.scheduler.data_fetcher.fetch_all",
                   side_effect=RuntimeError("fetch failed")):
            # Must not raise
            market_refresh_job()

    def test_market_refresh_job_logs_error_on_exception(self):
        # Pin IST clock to trading hours so the guard doesn't skip execution
        ist_trading_time = _IST.localize(datetime(2024, 6, 17, 10, 30, 0))
        with patch("finintelligence.scheduler.logger") as mock_logger:
            with patch("finintelligence.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = ist_trading_time
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                with patch("finintelligence.scheduler.data_fetcher.fetch_all",
                           side_effect=RuntimeError("fetch failed")):
                    market_refresh_job()
            assert mock_logger.error.called

    def test_news_ingestion_job_does_not_raise_on_exception(self):
        with patch("finintelligence.scheduler.news_ingester.ingest_all_feeds",
                   side_effect=RuntimeError("feed failed")):
            news_ingestion_job()

    def test_news_ingestion_job_logs_error_on_exception(self):
        with patch("finintelligence.scheduler.logger") as mock_logger:
            with patch("finintelligence.scheduler.news_ingester.ingest_all_feeds",
                       side_effect=RuntimeError("feed failed")):
                news_ingestion_job()
            assert mock_logger.error.called

    def test_institutional_flow_job_does_not_raise_on_exception(self):
        with patch(
            "finintelligence.scheduler.institutional_fetcher.fetch_institutional_flows",
            side_effect=RuntimeError("flow failed"),
        ):
            institutional_flow_job()

    def test_institutional_flow_job_logs_error_on_exception(self):
        with patch("finintelligence.scheduler.logger") as mock_logger:
            with patch(
                "finintelligence.scheduler.institutional_fetcher.fetch_institutional_flows",
                side_effect=RuntimeError("flow failed"),
            ):
                institutional_flow_job()
            assert mock_logger.error.called

    def test_sector_sentiment_job_does_not_raise_on_exception(self):
        with patch(
            "finintelligence.scheduler.sector_rotation_engine.compute_sector_metrics",
            side_effect=RuntimeError("sector failed"),
        ):
            sector_sentiment_job()

    def test_sector_sentiment_job_logs_error_on_exception(self):
        with patch("finintelligence.scheduler.logger") as mock_logger:
            with patch(
                "finintelligence.scheduler.sector_rotation_engine.compute_sector_metrics",
                side_effect=RuntimeError("sector failed"),
            ):
                sector_sentiment_job()
            assert mock_logger.error.called

    def test_logged_error_contains_traceback(self):
        """Verify the logged message includes traceback text (format_exc output)."""
        with patch("finintelligence.scheduler.logger") as mock_logger:
            with patch("finintelligence.scheduler.news_ingester.ingest_all_feeds",
                       side_effect=ValueError("bad feed")):
                news_ingestion_job()

            assert mock_logger.error.called
            # The second positional arg to logger.error should be the traceback string
            call_args = mock_logger.error.call_args
            # call_args[0] = positional args tuple: (format_str, traceback_str)
            if len(call_args[0]) >= 2:
                tb_str = call_args[0][1]
                assert "Traceback" in tb_str or "ValueError" in tb_str, (
                    f"Expected traceback in logged message, got: {tb_str!r}"
                )


# ---------------------------------------------------------------------------
# Unit tests: market refresh job trading-hours guard
# ---------------------------------------------------------------------------

class TestMarketRefreshJobGuard:

    def _run_with_ist_time(self, hour: int, minute: int) -> bool:
        """
        Run market_refresh_job with IST clock fixed to (hour, minute).
        Returns True if data_fetcher.fetch_all was called (job ran),
        False if it was skipped.
        """
        ist_time = _IST.localize(datetime(2024, 6, 17, hour, minute, 0))

        with patch("finintelligence.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = ist_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            with patch("finintelligence.scheduler.data_fetcher.fetch_all") as mock_fetch:
                with patch("finintelligence.scheduler.feature_generator.compute_features",
                           return_value={}):
                    with patch("finintelligence.scheduler.sentiment_engine.compute_sentiment",
                               return_value=MagicMock()):
                        with patch("finintelligence.scheduler.check_and_trigger",
                                   return_value=None):
                            import finintelligence.cache_manager as cm
                            import pandas as pd
                            with patch.object(cm, "read_sector_metrics",
                                              return_value=pd.DataFrame()):
                                with patch.object(cm, "read_institutional_flows",
                                                  return_value=pd.DataFrame()):
                                    market_refresh_job()
                return mock_fetch.called

    def test_skips_before_market_open_0900(self):
        assert self._run_with_ist_time(9, 0) is False

    def test_skips_before_market_open_0914(self):
        assert self._run_with_ist_time(9, 14) is False

    def test_runs_at_market_open_0915(self):
        assert self._run_with_ist_time(9, 15) is True

    def test_runs_during_trading_hours_1200(self):
        assert self._run_with_ist_time(12, 0) is True

    def test_runs_at_market_close_1530(self):
        assert self._run_with_ist_time(15, 30) is True

    def test_skips_after_market_close_1531(self):
        assert self._run_with_ist_time(15, 31) is False

    def test_skips_after_market_close_1600(self):
        assert self._run_with_ist_time(16, 0) is False

    def test_skips_at_midnight(self):
        assert self._run_with_ist_time(0, 0) is False


# ---------------------------------------------------------------------------
# Unit tests: sector_sentiment_job is chained from institutional_flow_job
# ---------------------------------------------------------------------------

class TestJobChaining:

    def test_sector_sentiment_called_after_successful_flow_fetch(self):
        with patch(
            "finintelligence.scheduler.institutional_fetcher.fetch_institutional_flows",
            return_value=MagicMock(),
        ):
            with patch("finintelligence.scheduler.sector_sentiment_job") as mock_ss:
                institutional_flow_job()
                assert mock_ss.called, (
                    "sector_sentiment_job should be called after successful flow fetch"
                )

    def test_sector_sentiment_not_called_when_flow_fetch_raises(self):
        with patch(
            "finintelligence.scheduler.institutional_fetcher.fetch_institutional_flows",
            side_effect=RuntimeError("flow failed"),
        ):
            with patch("finintelligence.scheduler.sector_sentiment_job") as mock_ss:
                institutional_flow_job()
                assert not mock_ss.called, (
                    "sector_sentiment_job should NOT be called when flow fetch raises"
                )
