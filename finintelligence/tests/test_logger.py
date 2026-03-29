"""
Tests for finintelligence/logger.py

Covers:
  - Property 12: Error Threshold CRITICAL Alert (PBT)
  - Property 13: Log Entry Field Completeness (PBT)
  - Property 14: WARNING-Level Logs Reach stderr (PBT)
  - Unit tests: file handler config, stderr threshold, record_error counter,
    logger never raises on file handler failure, check_error_threshold window reset
"""

from __future__ import annotations

import io
import logging
import sys
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import finintelligence.logger as logger_module
from finintelligence.logger import (
    _reset_logger_state,
    check_error_threshold,
    get_logger,
    record_error,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_logger(name: str = "test.logger") -> logging.Logger:
    """Reset module state and return a freshly configured logger."""
    _reset_logger_state()
    return get_logger(name)


def _count_critical_records(records: list[logging.LogRecord]) -> int:
    return sum(1 for r in records if r.levelno == logging.CRITICAL)


# ---------------------------------------------------------------------------
# Property 12: Error Threshold CRITICAL Alert
# Feature: finintelligence-market-analysis, Property 12: Error Threshold CRITICAL Alert
# Validates: Requirements 10.5
# ---------------------------------------------------------------------------

@given(st.integers(min_value=0, max_value=20))
@settings(max_examples=100)
def test_property12_error_threshold_critical_alert(error_count: int):
    # Feature: finintelligence-market-analysis, Property 12: Error Threshold CRITICAL Alert
    # Validates: Requirements 10.5
    _reset_logger_state()

    # Inject timestamps directly into module state — all within the last 30 minutes
    now = datetime.utcnow()
    logger_module._error_timestamps = [
        now - timedelta(minutes=i % 30) for i in range(error_count)
    ]
    logger_module._critical_alert_emitted = False
    logger_module._last_window_key = None

    # Capture log records via a handler attached to the internal logger
    _reset_logger_state()
    lg = get_logger("finintelligence.logger")

    # Re-inject state after get_logger (which resets it)
    logger_module._error_timestamps = [
        now - timedelta(minutes=i % 30) for i in range(error_count)
    ]
    logger_module._critical_alert_emitted = False
    logger_module._last_window_key = None

    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    capture_handler = _Capture(level=logging.DEBUG)
    lg.addHandler(capture_handler)

    try:
        check_error_threshold()

        critical_count = _count_critical_records(captured)

        if error_count > 10:
            assert critical_count == 1, (
                f"Expected exactly 1 CRITICAL for {error_count} errors, got {critical_count}"
            )
        else:
            assert critical_count == 0, (
                f"Expected 0 CRITICAL for {error_count} errors (≤10), got {critical_count}"
            )
    finally:
        lg.removeHandler(capture_handler)
        _reset_logger_state()


# ---------------------------------------------------------------------------
# Property 13: Log Entry Field Completeness
# Feature: finintelligence-market-analysis, Property 13: Log Entry Field Completeness
# Validates: Requirements 10.1, 10.2, 10.3, 10.4
# ---------------------------------------------------------------------------

# Required fields per event type
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "api_call": ["timestamp", "url", "method", "status_code", "latency_ms"],
    "download": ["timestamp", "symbol", "timeframe", "candle_count", "cache_status"],
    "inference_run": [
        "timestamp", "trigger_type", "input_summary",
        "direction", "confidence", "duration_ms",
    ],
    "error": ["timestamp", "component", "error_type", "message", "stack_trace"],
}

_EVENT_TYPES = list(_REQUIRED_FIELDS.keys())


def _build_log_entry(event_type: str, draw) -> dict:
    """Build a minimal valid log entry dict for the given event type."""
    base = {"timestamp": draw(st.datetimes()).isoformat()}

    if event_type == "api_call":
        return {
            **base,
            "url": draw(st.text(min_size=1, max_size=100)),
            "method": draw(st.sampled_from(["GET", "POST", "PUT", "DELETE"])),
            "status_code": draw(st.integers(min_value=100, max_value=599)),
            "latency_ms": draw(st.floats(min_value=0.0, max_value=60000.0, allow_nan=False)),
        }
    elif event_type == "download":
        return {
            **base,
            "symbol": draw(st.text(min_size=1, max_size=20)),
            "timeframe": draw(st.sampled_from(["1D", "4H", "1H", "15M", "5M"])),
            "candle_count": draw(st.integers(min_value=0, max_value=10000)),
            "cache_status": draw(st.sampled_from(["hit", "miss", "written"])),
        }
    elif event_type == "inference_run":
        return {
            **base,
            "trigger_type": draw(st.sampled_from(
                ["index_move", "sector_move", "fii_spike", "macro_event"]
            )),
            "input_summary": draw(st.text(min_size=1, max_size=200)),
            "direction": draw(st.sampled_from(["Bullish", "Bearish", "Neutral"])),
            "confidence": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
            "duration_ms": draw(st.floats(min_value=0.0, max_value=30000.0, allow_nan=False)),
        }
    else:  # error
        return {
            **base,
            "component": draw(st.text(min_size=1, max_size=50)),
            "error_type": draw(st.text(min_size=1, max_size=50)),
            "message": draw(st.text(min_size=1, max_size=500)),
            "stack_trace": draw(st.text(min_size=0, max_size=2000)),
        }


@given(st.data())
@settings(max_examples=100)
def test_property13_log_entry_field_completeness(data):
    # Feature: finintelligence-market-analysis, Property 13: Log Entry Field Completeness
    # Validates: Requirements 10.1, 10.2, 10.3, 10.4
    event_type = data.draw(st.sampled_from(_EVENT_TYPES))
    entry = _build_log_entry(event_type, data.draw)

    required = _REQUIRED_FIELDS[event_type]
    for field in required:
        assert field in entry, (
            f"Event type '{event_type}' is missing required field '{field}'. "
            f"Entry keys: {list(entry.keys())}"
        )
        assert entry[field] is not None, (
            f"Event type '{event_type}' field '{field}' must not be None"
        )


# ---------------------------------------------------------------------------
# Property 14: WARNING-Level Logs Reach stderr
# Feature: finintelligence-market-analysis, Property 14: WARNING-Level Logs Reach stderr
# Validates: Requirements 10.7
# ---------------------------------------------------------------------------

_ALL_LEVELS = [
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
]


@given(st.sampled_from(_ALL_LEVELS))
@settings(max_examples=100)
def test_property14_warning_and_above_reach_stderr(level: int):
    # Feature: finintelligence-market-analysis, Property 14: WARNING-Level Logs Reach stderr
    # Validates: Requirements 10.7
    _reset_logger_state()

    fake_stderr = io.StringIO()

    with patch("finintelligence.logger.sys") as mock_sys:
        mock_sys.stderr = fake_stderr
        lg = get_logger("finintelligence.prop14")

    # Emit a uniquely identifiable message
    marker = f"PROP14_MARKER_{level}_{id(fake_stderr)}"
    lg.log(level, marker)

    # Flush all handlers
    for handler in lg.handlers:
        handler.flush()

    output = fake_stderr.getvalue()

    if level >= logging.WARNING:
        assert marker in output, (
            f"Level {logging.getLevelName(level)} message should appear on stderr "
            f"but was not found. stderr content: {output!r}"
        )
    else:
        assert marker not in output, (
            f"Level {logging.getLevelName(level)} message must NOT appear on stderr "
            f"but was found. stderr content: {output!r}"
        )

    _reset_logger_state()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestRotatingFileHandlerConfig:

    def test_file_handler_max_bytes_is_10mb(self):
        _reset_logger_state()
        with patch("finintelligence.logger.os.makedirs"):
            with patch("finintelligence.logger.RotatingFileHandler") as mock_rfh:
                mock_rfh.return_value = MagicMock(spec=RotatingFileHandler)
                mock_rfh.return_value.level = logging.DEBUG
                mock_rfh.return_value.setLevel = MagicMock()
                mock_rfh.return_value.setFormatter = MagicMock()
                get_logger("test.file_handler")

        mock_rfh.assert_called_once()
        _, kwargs = mock_rfh.call_args
        assert kwargs.get("maxBytes") == 10 * 1024 * 1024, (
            f"Expected maxBytes=10485760, got {kwargs.get('maxBytes')}"
        )

    def test_file_handler_backup_count_is_5(self):
        _reset_logger_state()
        with patch("finintelligence.logger.os.makedirs"):
            with patch("finintelligence.logger.RotatingFileHandler") as mock_rfh:
                mock_rfh.return_value = MagicMock(spec=RotatingFileHandler)
                mock_rfh.return_value.level = logging.DEBUG
                mock_rfh.return_value.setLevel = MagicMock()
                mock_rfh.return_value.setFormatter = MagicMock()
                get_logger("test.backup_count")

        _, kwargs = mock_rfh.call_args
        assert kwargs.get("backupCount") == 5, (
            f"Expected backupCount=5, got {kwargs.get('backupCount')}"
        )


class TestStderrHandlerThreshold:

    def test_stderr_handler_level_is_warning(self):
        _reset_logger_state()
        lg = _fresh_logger("test.stderr_threshold")

        stderr_handlers = [
            h for h in lg.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert len(stderr_handlers) >= 1, "No StreamHandler found on logger"

        for h in stderr_handlers:
            assert h.level == logging.WARNING, (
                f"stderr StreamHandler level is {h.level}, expected {logging.WARNING}"
            )

    def test_stderr_handler_does_not_emit_debug(self):
        _reset_logger_state()
        fake_stderr = io.StringIO()
        with patch("finintelligence.logger.sys") as mock_sys:
            mock_sys.stderr = fake_stderr
            lg = get_logger("test.no_debug_stderr")

        lg.debug("this_debug_message_should_not_appear")
        for h in lg.handlers:
            h.flush()

        assert "this_debug_message_should_not_appear" not in fake_stderr.getvalue()

    def test_stderr_handler_does_not_emit_info(self):
        _reset_logger_state()
        fake_stderr = io.StringIO()
        with patch("finintelligence.logger.sys") as mock_sys:
            mock_sys.stderr = fake_stderr
            lg = get_logger("test.no_info_stderr")

        lg.info("this_info_message_should_not_appear")
        for h in lg.handlers:
            h.flush()

        assert "this_info_message_should_not_appear" not in fake_stderr.getvalue()


class TestRecordError:

    def test_record_error_increments_counter(self):
        _reset_logger_state()
        assert len(logger_module._error_timestamps) == 0
        record_error("test_component")
        assert len(logger_module._error_timestamps) == 1

    def test_record_error_increments_multiple_times(self):
        _reset_logger_state()
        for i in range(5):
            record_error("component_a")
        assert len(logger_module._error_timestamps) == 5

    def test_record_error_timestamps_are_recent(self):
        _reset_logger_state()
        before = datetime.utcnow()
        record_error("component_b")
        after = datetime.utcnow()

        ts = logger_module._error_timestamps[0]
        assert before <= ts <= after, (
            f"Recorded timestamp {ts} is not between {before} and {after}"
        )

    def test_record_error_calls_check_threshold(self):
        _reset_logger_state()
        with patch("finintelligence.logger.check_error_threshold") as mock_check:
            record_error("component_c")
            mock_check.assert_called_once()


class TestLoggerNeverRaises:

    def test_logger_does_not_raise_when_file_handler_fails(self):
        _reset_logger_state()
        with patch(
            "finintelligence.logger.RotatingFileHandler",
            side_effect=OSError("disk full"),
        ):
            # Must not raise — falls back to stderr only
            lg = get_logger("test.no_raise")

        assert lg is not None
        # Should still have the stderr handler
        stderr_handlers = [
            h for h in lg.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, RotatingFileHandler)
        ]
        assert len(stderr_handlers) >= 1, (
            "Logger should have at least one stderr handler even when file handler fails"
        )

    def test_logger_can_emit_after_file_handler_fails(self):
        _reset_logger_state()
        with patch(
            "finintelligence.logger.RotatingFileHandler",
            side_effect=OSError("permission denied"),
        ):
            lg = get_logger("test.emit_after_fail")

        # Should not raise when emitting
        lg.warning("test warning after file handler failure")
        lg.error("test error after file handler failure")


class TestCheckErrorThresholdWindowReset:

    def test_critical_flag_resets_on_new_hour_window(self):
        _reset_logger_state()
        now = datetime.utcnow()

        # Simulate: we are in a previous hour window with flag already set
        previous_hour = now - timedelta(hours=1)
        logger_module._last_window_key = previous_hour.strftime("%Y-%m-%d %H")
        logger_module._critical_alert_emitted = True
        # Add 11 errors in the current window
        logger_module._error_timestamps = [
            now - timedelta(minutes=i) for i in range(11)
        ]

        # Ensure logger is initialised so check_error_threshold can emit
        get_logger("finintelligence.logger")

        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        lg = logging.getLogger("finintelligence.logger")
        cap = _Capture(level=logging.DEBUG)
        lg.addHandler(cap)

        try:
            check_error_threshold()
            # Flag should have been reset and CRITICAL emitted for the new window
            assert logger_module._critical_alert_emitted is True
            assert _count_critical_records(captured) == 1, (
                "Expected CRITICAL to be emitted after window reset with >10 errors"
            )
        finally:
            lg.removeHandler(cap)
            _reset_logger_state()

    def test_critical_not_emitted_twice_in_same_window(self):
        _reset_logger_state()
        now = datetime.utcnow()
        current_window = now.strftime("%Y-%m-%d %H")

        # Pre-set: already emitted in this window
        logger_module._last_window_key = current_window
        logger_module._critical_alert_emitted = True
        logger_module._error_timestamps = [
            now - timedelta(minutes=i) for i in range(15)
        ]

        get_logger("finintelligence.logger")

        captured: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        lg = logging.getLogger("finintelligence.logger")
        cap = _Capture(level=logging.DEBUG)
        lg.addHandler(cap)

        try:
            check_error_threshold()
            assert _count_critical_records(captured) == 0, (
                "CRITICAL must not be emitted twice in the same window"
            )
        finally:
            lg.removeHandler(cap)
            _reset_logger_state()

    def test_errors_outside_60min_window_are_pruned(self):
        _reset_logger_state()
        now = datetime.utcnow()

        # 5 old errors (>60 min ago) + 3 recent errors — total in window = 3
        old = [now - timedelta(minutes=61 + i) for i in range(5)]
        recent = [now - timedelta(minutes=i) for i in range(3)]
        logger_module._error_timestamps = old + recent

        check_error_threshold()

        # Only recent ones should remain
        assert len(logger_module._error_timestamps) == 3, (
            f"Expected 3 timestamps after pruning, got {len(logger_module._error_timestamps)}"
        )
        _reset_logger_state()
