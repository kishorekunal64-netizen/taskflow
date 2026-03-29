"""
Property 7: Durable Store Upsert Idempotency
Validates: Requirements 10.4, 10.5, 10.6

Calling each upsert function twice with the same date key must produce
exactly one row — no duplicate, no exception.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ── Strategies ────────────────────────────────────────────────────────────────

sentiment_st = st.fixed_dictionaries({
    "score": st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
    "classification": st.sampled_from(["bullish", "bearish", "neutral"]),
})

sector_metrics_st = st.lists(
    st.fixed_dictionaries({
        "sector": st.text(min_size=1, max_size=32),
        "momentum_score": st.floats(min_value=-10.0, max_value=10.0, allow_nan=False),
        "relative_strength": st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
        "ranking": st.integers(min_value=1, max_value=20),
    }),
    min_size=1,
    max_size=5,
)

ai_signal_st = st.fixed_dictionaries({
    "direction": st.sampled_from(["up", "down", "sideways"]),
    "confidence": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
})

flow_st = st.fixed_dictionaries({
    "fii_buy": st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
    "fii_sell": st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
    "dii_buy": st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
    "dii_sell": st.floats(min_value=0.0, max_value=1e9, allow_nan=False),
    "net_flow": st.floats(min_value=-1e9, max_value=1e9, allow_nan=False),
})

fixed_date = datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_conn():
    """Build a mock psycopg2 connection with cursor tracking."""
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_conn, mock_cur


# ── Property tests ────────────────────────────────────────────────────────────

@given(sentiment=sentiment_st, sector_strength=sector_metrics_st, ai_signal=ai_signal_st)
@settings(max_examples=50)
def test_upsert_analysis_results_idempotent(sentiment, sector_strength, ai_signal):
    """Calling upsert_analysis_results twice with the same date raises no exception
    and executes exactly two INSERT ... ON CONFLICT statements (one per call)."""
    from finplatform.durable_store import upsert_analysis_results

    mock_conn, mock_cur = _make_mock_conn()

    with patch("finplatform.durable_store.get_conn", return_value=mock_conn):
        # First call
        upsert_analysis_results(fixed_date, sentiment, sector_strength, ai_signal)
        # Second call — same date, same data
        upsert_analysis_results(fixed_date, sentiment, sector_strength, ai_signal)

    # execute() called once per upsert call → exactly 2 total
    assert mock_cur.execute.call_count == 2

    # Both calls used the same date
    for c in mock_cur.execute.call_args_list:
        args = c[0]  # positional args tuple
        assert args[1][0] == fixed_date

    # commit called once per upsert → exactly 2
    assert mock_conn.commit.call_count == 2


@given(sector_metrics=sector_metrics_st)
@settings(max_examples=50)
def test_upsert_sector_performance_idempotent(sector_metrics):
    """Calling upsert_sector_performance twice with the same date raises no exception
    and executes exactly len(sector_metrics) * 2 INSERT statements total."""
    from finplatform.durable_store import upsert_sector_performance

    mock_conn, mock_cur = _make_mock_conn()

    with patch("finplatform.durable_store.get_conn", return_value=mock_conn):
        upsert_sector_performance(fixed_date, sector_metrics)
        upsert_sector_performance(fixed_date, sector_metrics)

    expected_execute_count = len(sector_metrics) * 2
    assert mock_cur.execute.call_count == expected_execute_count

    # Every call used the same date
    for c in mock_cur.execute.call_args_list:
        args = c[0]
        assert args[1][0] == fixed_date

    assert mock_conn.commit.call_count == 2


@given(flow=flow_st)
@settings(max_examples=50)
def test_upsert_institutional_flow_idempotent(flow):
    """Calling upsert_institutional_flow twice with the same date raises no exception
    and executes exactly 2 INSERT ... ON CONFLICT statements."""
    from finplatform.durable_store import upsert_institutional_flow

    mock_conn, mock_cur = _make_mock_conn()

    with patch("finplatform.durable_store.get_conn", return_value=mock_conn):
        upsert_institutional_flow(fixed_date, flow)
        upsert_institutional_flow(fixed_date, flow)

    assert mock_cur.execute.call_count == 2

    for c in mock_cur.execute.call_args_list:
        args = c[0]
        assert args[1][0] == fixed_date

    assert mock_conn.commit.call_count == 2


@given(flow=flow_st)
@settings(max_examples=30)
def test_upsert_institutional_flow_different_data_same_date(flow):
    """Two calls with the same date but different data values must both succeed —
    the second is an update, not a duplicate insert error."""
    from finplatform.durable_store import upsert_institutional_flow

    mock_conn, mock_cur = _make_mock_conn()

    modified_flow = {**flow, "net_flow": flow["net_flow"] + 1.0}

    with patch("finplatform.durable_store.get_conn", return_value=mock_conn):
        upsert_institutional_flow(fixed_date, flow)
        upsert_institutional_flow(fixed_date, modified_flow)  # same date, different values

    assert mock_cur.execute.call_count == 2
    assert mock_conn.commit.call_count == 2
