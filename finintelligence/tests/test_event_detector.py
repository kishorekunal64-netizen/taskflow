"""
Tests for finintelligence/event_detector.py

Covers:
  - Property 7: Event Threshold Trigger (PBT) — any state meeting ≥1 threshold
    produces a non-None TriggerEvent with correct fields
  - Property 8: Event Trigger Idempotency (PBT) — same state twice in same
    window → first call triggers, second returns None
  - Unit tests: each threshold independently, below-all returns None,
    idempotency guard resets after window expires
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintelligence.event_detector import (
    _check_fii_spike,
    _check_index_move,
    _check_macro_score,
    _check_sector_move,
    _is_duplicate,
    _reset_triggered_set,
    check_and_trigger,
)
from finintelligence.models import SentimentResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sentiment(macro_score: int = 0) -> SentimentResult:
    return SentimentResult(
        timestamp=datetime.now(tz=timezone.utc),
        index_momentum=0.0,
        sector_perf=0.0,
        institutional_signal=0.0,
        macro_score=macro_score,
        composite_score=0.0,
        classification="Neutral",
    )


def _make_flows(fii_net_values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"fii_net": fii_net_values})


def _make_sector_df(pct_changes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"pct_change_1d": pct_changes})


def _features_with_index(nsei_pct: float | None = None, nsebank_pct: float | None = None) -> dict:
    features: dict = {}
    if nsei_pct is not None:
        features["^NSEI"] = {"pct_change_1d": nsei_pct}
    if nsebank_pct is not None:
        features["^NSEBANK"] = {"pct_change_1d": nsebank_pct}
    return features


# ---------------------------------------------------------------------------
# Property 7: Event Threshold Trigger
# Feature: finintelligence-market-analysis, Property 7: Event Threshold Trigger
# Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6
# ---------------------------------------------------------------------------

# Strategy: generate a market state that breaches at least one threshold.
# We pick one of four trigger types and generate a value that exceeds it.

@st.composite
def triggering_market_state(draw):
    """
    Draw a market state that satisfies at least one threshold condition.
    Returns (features, sentiment, sector_df, flows_df, expected_trigger_type).
    """
    trigger_choice = draw(st.sampled_from(["index_move", "sector_move", "fii_spike", "macro_event"]))

    # Default: nothing triggers
    features: dict = {}
    sentiment = _make_sentiment(macro_score=0)
    sector_df = _make_sector_df([])
    flows_df = _make_flows([0.0] * 20)

    if trigger_choice == "index_move":
        # abs(pct) > 1.0
        pct = draw(st.floats(min_value=1.01, max_value=20.0, allow_nan=False, allow_infinity=False))
        sign = draw(st.sampled_from([1.0, -1.0]))
        symbol = draw(st.sampled_from(["^NSEI", "^NSEBANK"]))
        features = {symbol: {"pct_change_1d": sign * pct}}

    elif trigger_choice == "sector_move":
        # abs(pct) > 2.0
        pct = draw(st.floats(min_value=2.01, max_value=20.0, allow_nan=False, allow_infinity=False))
        sign = draw(st.sampled_from([1.0, -1.0]))
        sector_df = _make_sector_df([sign * pct])

    elif trigger_choice == "fii_spike":
        # abs(fii_net[-1]) > mean + 2*std
        # Use 19 values of 0.0 and one extreme outlier
        outlier = draw(st.floats(min_value=1000.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False))
        sign = draw(st.sampled_from([1.0, -1.0]))
        flows_df = _make_flows([0.0] * 19 + [sign * outlier])

    else:  # macro_event
        # macro_score >= 3
        score = draw(st.integers(min_value=3, max_value=20))
        sentiment = _make_sentiment(macro_score=score)

    return features, sentiment, sector_df, flows_df, trigger_choice


@given(state=triggering_market_state())
@settings(max_examples=100)
def test_property7_triggering_state_produces_event(state):
    # Feature: finintelligence-market-analysis, Property 7: Event Threshold Trigger
    # Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6
    features, sentiment, sector_df, flows_df, expected_type = state

    _reset_triggered_set()

    event = check_and_trigger(features, sentiment, sector_df, flows_df)

    assert event is not None, (
        f"Expected TriggerEvent for trigger_type={expected_type}, got None"
    )
    assert event.trigger_type in {"index_move", "sector_move", "fii_spike", "macro_event"}, (
        f"Invalid trigger_type: {event.trigger_type}"
    )
    assert isinstance(event.triggering_value, float), (
        f"triggering_value must be float, got {type(event.triggering_value)}"
    )
    assert isinstance(event.threshold_value, float), (
        f"threshold_value must be float, got {type(event.threshold_value)}"
    )
    assert event.triggering_value >= event.threshold_value or event.trigger_type == "macro_event", (
        f"triggering_value {event.triggering_value} should be >= threshold {event.threshold_value}"
    )
    assert isinstance(event.timestamp, datetime), (
        f"timestamp must be datetime, got {type(event.timestamp)}"
    )


# ---------------------------------------------------------------------------
# Property 8: Event Trigger Idempotency
# Feature: finintelligence-market-analysis, Property 8: Event Trigger Idempotency
# Validates: Requirements 7.2, 7.3, 7.4, 7.5
# ---------------------------------------------------------------------------

@given(state=triggering_market_state())
@settings(max_examples=100)
def test_property8_idempotency_same_window(state):
    # Feature: finintelligence-market-analysis, Property 8: Event Trigger Idempotency
    # Validates: Requirements 7.2, 7.3, 7.4, 7.5
    features, sentiment, sector_df, flows_df, _ = state

    _reset_triggered_set()

    # Pin the clock to a fixed window so both calls share the same window_key
    fixed_now = datetime(2024, 6, 15, 10, 7, 0, tzinfo=timezone.utc)  # minute=7 → bucket :00

    with patch("finintelligence.event_detector.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        first = check_and_trigger(features, sentiment, sector_df, flows_df)
        second = check_and_trigger(features, sentiment, sector_df, flows_df)

    assert first is not None, "First call should produce a TriggerEvent"
    assert second is None, "Second call in same window should return None"


# ---------------------------------------------------------------------------
# Unit tests: _check_index_move
# ---------------------------------------------------------------------------

class TestCheckIndexMove:

    def test_nsei_above_threshold_triggers(self):
        features = {"^NSEI": {"pct_change_1d": 1.5}}
        triggered, val = _check_index_move(features)
        assert triggered is True
        assert val == pytest.approx(1.5)

    def test_nsebank_above_threshold_triggers(self):
        features = {"^NSEBANK": {"pct_change_1d": -2.0}}
        triggered, val = _check_index_move(features)
        assert triggered is True
        assert val == pytest.approx(2.0)

    def test_exactly_at_threshold_does_not_trigger(self):
        features = {"^NSEI": {"pct_change_1d": 1.0}}
        triggered, _ = _check_index_move(features)
        assert triggered is False

    def test_below_threshold_does_not_trigger(self):
        features = {"^NSEI": {"pct_change_1d": 0.5}, "^NSEBANK": {"pct_change_1d": 0.8}}
        triggered, _ = _check_index_move(features)
        assert triggered is False

    def test_missing_symbol_does_not_raise(self):
        triggered, val = _check_index_move({})
        assert triggered is False
        assert val == 0.0

    def test_none_pct_change_skipped(self):
        features = {"^NSEI": {"pct_change_1d": None}}
        triggered, _ = _check_index_move(features)
        assert triggered is False

    def test_negative_pct_uses_abs(self):
        features = {"^NSEI": {"pct_change_1d": -1.5}}
        triggered, val = _check_index_move(features)
        assert triggered is True
        assert val == pytest.approx(1.5)

    def test_non_index_symbol_ignored(self):
        features = {"^CNXIT": {"pct_change_1d": 5.0}}
        triggered, _ = _check_index_move(features)
        assert triggered is False


# ---------------------------------------------------------------------------
# Unit tests: _check_sector_move
# ---------------------------------------------------------------------------

class TestCheckSectorMove:

    def test_sector_above_threshold_triggers(self):
        df = _make_sector_df([2.5])
        triggered, val = _check_sector_move(df)
        assert triggered is True
        assert val == pytest.approx(2.5)

    def test_negative_sector_move_triggers(self):
        df = _make_sector_df([-3.0])
        triggered, val = _check_sector_move(df)
        assert triggered is True
        assert val == pytest.approx(3.0)

    def test_exactly_at_threshold_does_not_trigger(self):
        df = _make_sector_df([2.0])
        triggered, _ = _check_sector_move(df)
        assert triggered is False

    def test_below_threshold_does_not_trigger(self):
        df = _make_sector_df([0.5, 1.0, 1.9])
        triggered, _ = _check_sector_move(df)
        assert triggered is False

    def test_empty_df_does_not_trigger(self):
        triggered, val = _check_sector_move(pd.DataFrame())
        assert triggered is False
        assert val == 0.0

    def test_missing_column_does_not_trigger(self):
        df = pd.DataFrame({"symbol": ["^CNXIT"]})
        triggered, _ = _check_sector_move(df)
        assert triggered is False

    def test_dict_input_supported(self):
        sector_dict = {"^CNXIT": {"pct_change_1d": 3.0}}
        triggered, val = _check_sector_move(sector_dict)
        assert triggered is True
        assert val == pytest.approx(3.0)

    def test_multiple_sectors_first_breach_returned(self):
        df = _make_sector_df([0.5, 2.5, 3.0])
        triggered, val = _check_sector_move(df)
        assert triggered is True
        assert val == pytest.approx(2.5)  # first breach wins


# ---------------------------------------------------------------------------
# Unit tests: _check_fii_spike
# ---------------------------------------------------------------------------

class TestCheckFiiSpike:

    def test_extreme_outlier_triggers(self):
        flows = _make_flows([0.0] * 19 + [1_000_000.0])
        triggered, val = _check_fii_spike(flows)
        assert triggered is True
        assert val > 0

    def test_negative_extreme_outlier_triggers(self):
        flows = _make_flows([0.0] * 19 + [-1_000_000.0])
        triggered, val = _check_fii_spike(flows)
        assert triggered is True

    def test_normal_value_does_not_trigger(self):
        # All values equal → std=0 → no trigger
        flows = _make_flows([100.0] * 20)
        triggered, _ = _check_fii_spike(flows)
        assert triggered is False

    def test_empty_df_does_not_trigger(self):
        triggered, val = _check_fii_spike(pd.DataFrame())
        assert triggered is False
        assert val == 0.0

    def test_single_row_does_not_trigger(self):
        flows = _make_flows([500.0])
        triggered, _ = _check_fii_spike(flows)
        assert triggered is False

    def test_missing_fii_net_column_does_not_trigger(self):
        df = pd.DataFrame({"dii_net": [100.0, 200.0]})
        triggered, _ = _check_fii_spike(df)
        assert triggered is False

    def test_zero_std_does_not_trigger(self):
        flows = _make_flows([50.0] * 20)
        triggered, _ = _check_fii_spike(flows)
        assert triggered is False

    def test_known_spike_calculation(self):
        # 19 zeros + 1 large value: mean≈large/20, std≈large/sqrt(20)
        # abs(latest) > mean + 2*std should hold for extreme outlier
        flows = _make_flows([0.0] * 19 + [100.0])
        triggered, val = _check_fii_spike(flows)
        # mean = 5.0, std ≈ 22.36, threshold = 5 + 2*22.36 = 49.72
        # abs(100) = 100 > 49.72 → should trigger
        assert triggered is True
        assert val == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Unit tests: _check_macro_score
# ---------------------------------------------------------------------------

class TestCheckMacroScore:

    def test_score_at_threshold_triggers(self):
        sentiment = _make_sentiment(macro_score=3)
        triggered, val = _check_macro_score(sentiment)
        assert triggered is True
        assert val == pytest.approx(3.0)

    def test_score_above_threshold_triggers(self):
        sentiment = _make_sentiment(macro_score=5)
        triggered, val = _check_macro_score(sentiment)
        assert triggered is True

    def test_score_below_threshold_does_not_trigger(self):
        sentiment = _make_sentiment(macro_score=2)
        triggered, _ = _check_macro_score(sentiment)
        assert triggered is False

    def test_score_zero_does_not_trigger(self):
        sentiment = _make_sentiment(macro_score=0)
        triggered, _ = _check_macro_score(sentiment)
        assert triggered is False


# ---------------------------------------------------------------------------
# Unit tests: check_and_trigger — integration
# ---------------------------------------------------------------------------

class TestCheckAndTrigger:

    def setup_method(self):
        _reset_triggered_set()

    def test_below_all_thresholds_returns_none(self):
        features = {"^NSEI": {"pct_change_1d": 0.5}, "^NSEBANK": {"pct_change_1d": 0.3}}
        sentiment = _make_sentiment(macro_score=1)
        sector_df = _make_sector_df([0.5, 1.0])
        flows_df = _make_flows([100.0] * 20)

        result = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert result is None

    def test_index_move_triggers_event(self):
        features = {"^NSEI": {"pct_change_1d": 1.5}}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([100.0] * 20)

        event = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert event is not None
        assert event.trigger_type == "index_move"
        assert event.triggering_value == pytest.approx(1.5)
        assert event.threshold_value == pytest.approx(1.0)

    def test_sector_move_triggers_event(self):
        features = {}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([3.0])
        flows_df = _make_flows([100.0] * 20)

        event = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert event is not None
        assert event.trigger_type == "sector_move"
        assert event.triggering_value == pytest.approx(3.0)
        assert event.threshold_value == pytest.approx(2.0)

    def test_fii_spike_triggers_event(self):
        features = {}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([0.0] * 19 + [100.0])

        event = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert event is not None
        assert event.trigger_type == "fii_spike"

    def test_macro_event_triggers_event(self):
        features = {}
        sentiment = _make_sentiment(macro_score=4)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([100.0] * 20)

        event = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert event is not None
        assert event.trigger_type == "macro_event"
        assert event.triggering_value == pytest.approx(4.0)
        assert event.threshold_value == pytest.approx(3.0)

    def test_index_move_takes_priority_over_sector(self):
        # Both index and sector breach — index_move should win (checked first)
        features = {"^NSEI": {"pct_change_1d": 2.0}}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([3.0])
        flows_df = _make_flows([100.0] * 20)

        event = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert event is not None
        assert event.trigger_type == "index_move"

    def test_trigger_event_has_utc_timestamp(self):
        features = {"^NSEI": {"pct_change_1d": 2.0}}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([100.0] * 20)

        event = check_and_trigger(features, sentiment, sector_df, flows_df)
        assert event is not None
        assert event.timestamp.tzinfo is not None

    def test_idempotency_same_window_returns_none_on_second_call(self):
        features = {"^NSEI": {"pct_change_1d": 2.0}}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([100.0] * 20)

        fixed_now = datetime(2024, 6, 15, 10, 7, 0, tzinfo=timezone.utc)

        with patch("finintelligence.event_detector.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            first = check_and_trigger(features, sentiment, sector_df, flows_df)
            second = check_and_trigger(features, sentiment, sector_df, flows_df)

        assert first is not None
        assert second is None

    def test_idempotency_guard_resets_after_window_expires(self):
        features = {"^NSEI": {"pct_change_1d": 2.0}}
        sentiment = _make_sentiment(macro_score=0)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([100.0] * 20)

        window1 = datetime(2024, 6, 15, 10, 7, 0, tzinfo=timezone.utc)   # bucket :00
        window2 = datetime(2024, 6, 15, 10, 16, 0, tzinfo=timezone.utc)  # bucket :15

        with patch("finintelligence.event_detector.datetime") as mock_dt:
            mock_dt.now.return_value = window1
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            first = check_and_trigger(features, sentiment, sector_df, flows_df)

        with patch("finintelligence.event_detector.datetime") as mock_dt:
            mock_dt.now.return_value = window2
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            second = check_and_trigger(features, sentiment, sector_df, flows_df)

        assert first is not None
        assert second is not None, "New window should allow a new trigger"

    def test_different_trigger_types_in_same_window_both_allowed(self):
        # First call: index_move triggers
        # Second call: no index move but macro_event triggers → different type, allowed
        fixed_now = datetime(2024, 6, 15, 10, 7, 0, tzinfo=timezone.utc)

        features_index = {"^NSEI": {"pct_change_1d": 2.0}}
        features_none: dict = {}
        sentiment_low = _make_sentiment(macro_score=0)
        sentiment_high = _make_sentiment(macro_score=5)
        sector_df = _make_sector_df([0.5])
        flows_df = _make_flows([100.0] * 20)

        with patch("finintelligence.event_detector.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            first = check_and_trigger(features_index, sentiment_low, sector_df, flows_df)
            second = check_and_trigger(features_none, sentiment_high, sector_df, flows_df)

        assert first is not None
        assert first.trigger_type == "index_move"
        assert second is not None
        assert second.trigger_type == "macro_event"


# ---------------------------------------------------------------------------
# Unit tests: _is_duplicate
# ---------------------------------------------------------------------------

class TestIsDuplicate:

    def setup_method(self):
        _reset_triggered_set()

    def test_new_key_not_duplicate(self):
        assert _is_duplicate("2024-06-15 10:00", "index_move") is False

    def test_after_trigger_is_duplicate(self):
        from finintelligence.event_detector import _triggered_set
        _triggered_set.add(("2024-06-15 10:00", "index_move"))
        assert _is_duplicate("2024-06-15 10:00", "index_move") is True

    def test_different_window_not_duplicate(self):
        from finintelligence.event_detector import _triggered_set
        _triggered_set.add(("2024-06-15 10:00", "index_move"))
        assert _is_duplicate("2024-06-15 10:15", "index_move") is False

    def test_different_type_not_duplicate(self):
        from finintelligence.event_detector import _triggered_set
        _triggered_set.add(("2024-06-15 10:00", "index_move"))
        assert _is_duplicate("2024-06-15 10:00", "macro_event") is False
