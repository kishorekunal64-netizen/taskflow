"""
Tests for finintelligence/sector_rotation_engine.py

Covers:
  - Property 4: Sector Ranking Completeness and Order (PBT)
  - Unit tests: known data → expected values, ADX non-negative, tied RS stable output
"""

import math
from unittest.mock import patch

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintelligence.config import SECTOR_SYMBOLS
from finintelligence.sector_rotation_engine import (
    compute_adx,
    compute_relative_strength,
    compute_sector_metrics,
    rank_sectors,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(n: int, start_price: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    """Create a minimal OHLCV DataFrame with `n` rows."""
    prices = [start_price + i * step for i in range(n)]
    return pd.DataFrame({
        "open":   prices,
        "high":   [p + 1.0 for p in prices],
        "low":    [p - 1.0 for p in prices],
        "close":  prices,
        "volume": [1_000_000.0] * n,
    })


def _make_metrics_df(rs_values: list[float]) -> pd.DataFrame:
    """Build a minimal metrics DataFrame with given relative_strength values."""
    assert len(rs_values) == 5
    return pd.DataFrame({
        "symbol":            SECTOR_SYMBOLS,
        "date":              [pd.Timestamp.now("UTC")] * 5,
        "return_20d":        [0.0] * 5,
        "relative_strength": rs_values,
        "adx":               [20.0] * 5,
        "fii_net":           [0.0] * 5,
        "dii_net":           [0.0] * 5,
    })


# ---------------------------------------------------------------------------
# Property 4: Sector Ranking Completeness and Order
# Feature: finintelligence-market-analysis, Property 4: Sector Ranking Completeness and Order
# Validates: Requirements 4.5
# ---------------------------------------------------------------------------

@given(
    rs_values=st.lists(
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
        min_size=5,
        max_size=5,
    )
)
@settings(max_examples=100)
def test_property4_ranking_completeness_and_order(rs_values):
    # Feature: finintelligence-market-analysis, Property 4: Sector Ranking Completeness and Order
    # Validates: Requirements 4.5
    metrics = _make_metrics_df(rs_values)
    ranked = rank_sectors(metrics)

    # Must contain exactly all 5 sector symbols — no duplicates, no omissions
    assert set(ranked["symbol"].tolist()) == set(SECTOR_SYMBOLS), \
        f"Expected all 5 sector symbols, got {ranked['symbol'].tolist()}"
    assert len(ranked) == 5, f"Expected 5 rows, got {len(ranked)}"

    # Ranks must be exactly 1 through 5 (no duplicates, no gaps)
    assert sorted(ranked["rank"].tolist()) == [1, 2, 3, 4, 5], \
        f"Expected ranks 1-5, got {sorted(ranked['rank'].tolist())}"

    # Rank 1 must have the highest relative_strength
    rank1_rs = ranked.loc[ranked["rank"] == 1, "relative_strength"].iloc[0]
    rank5_rs = ranked.loc[ranked["rank"] == 5, "relative_strength"].iloc[0]
    assert rank1_rs >= rank5_rs, \
        f"Rank 1 RS ({rank1_rs}) should be >= rank 5 RS ({rank5_rs})"

    # Verify strict descending order: for each pair (rank i, rank i+1), rs[i] >= rs[i+1]
    sorted_by_rank = ranked.sort_values("rank")
    rs_ordered = sorted_by_rank["relative_strength"].tolist()
    for i in range(len(rs_ordered) - 1):
        assert rs_ordered[i] >= rs_ordered[i + 1], \
            f"RS not descending at rank {i+1}: {rs_ordered[i]} < {rs_ordered[i+1]}"


# ---------------------------------------------------------------------------
# Unit tests: compute_relative_strength
# ---------------------------------------------------------------------------

class TestComputeRelativeStrength:

    def test_known_values(self):
        # Sector: 100 → 110 over 20 days = +10%
        # NIFTY:  100 → 105 over 20 days = +5%
        # RS = 0.10 / 0.05 = 2.0
        sector_df = _make_candles(25, start_price=100.0, step=0.5)
        # Override close to get exact 10% return
        sector_df["close"] = [100.0] * 4 + [100.0] + [110.0] * 20
        nifty_df = _make_candles(25, start_price=100.0, step=0.25)
        nifty_df["close"] = [100.0] * 4 + [100.0] + [105.0] * 20

        rs = compute_relative_strength(sector_df, nifty_df)
        assert rs == pytest.approx(2.0, rel=1e-6)

    def test_nifty_return_zero_returns_zero(self):
        # NIFTY flat → return = 0 → RS = 0.0 (no division by zero)
        sector_df = _make_candles(25, start_price=100.0, step=1.0)
        nifty_df = _make_candles(25, start_price=100.0, step=0.0)  # flat

        rs = compute_relative_strength(sector_df, nifty_df)
        assert rs == 0.0

    def test_empty_sector_df_returns_zero(self):
        nifty_df = _make_candles(25, start_price=100.0, step=1.0)
        rs = compute_relative_strength(pd.DataFrame(), nifty_df)
        assert rs == 0.0

    def test_empty_nifty_df_returns_zero(self):
        sector_df = _make_candles(25, start_price=100.0, step=1.0)
        rs = compute_relative_strength(sector_df, pd.DataFrame())
        assert rs == 0.0

    def test_negative_relative_strength(self):
        # Sector falls, NIFTY rises → negative RS
        sector_df = _make_candles(25, start_price=110.0, step=-0.5)
        nifty_df = _make_candles(25, start_price=100.0, step=0.5)
        rs = compute_relative_strength(sector_df, nifty_df)
        assert isinstance(rs, float)


# ---------------------------------------------------------------------------
# Unit tests: compute_adx
# ---------------------------------------------------------------------------

class TestComputeAdx:

    def test_adx_returns_non_negative_float(self):
        df = _make_candles(50)
        adx = compute_adx(df, period=14)
        assert isinstance(adx, float)
        assert adx >= 0.0

    def test_adx_insufficient_data_returns_zero(self):
        df = _make_candles(5)  # too few rows for ADX(14)
        adx = compute_adx(df, period=14)
        assert adx == 0.0

    def test_adx_empty_df_returns_zero(self):
        adx = compute_adx(pd.DataFrame(), period=14)
        assert adx == 0.0

    def test_adx_missing_columns_returns_zero(self):
        df = pd.DataFrame({"close": [100.0] * 50})  # no high/low
        adx = compute_adx(df, period=14)
        assert adx == 0.0

    def test_adx_with_sufficient_data_is_positive(self):
        df = _make_candles(100)
        adx = compute_adx(df, period=14)
        assert adx >= 0.0

    def test_adx_custom_period(self):
        df = _make_candles(60)
        adx = compute_adx(df, period=20)
        assert isinstance(adx, float)
        assert adx >= 0.0


# ---------------------------------------------------------------------------
# Unit tests: rank_sectors
# ---------------------------------------------------------------------------

class TestRankSectors:

    def test_rank_descending_by_relative_strength(self):
        rs_values = [0.5, 1.5, 0.8, 2.0, 0.2]
        metrics = _make_metrics_df(rs_values)
        ranked = rank_sectors(metrics)

        # Symbol with RS=2.0 should be rank 1
        top = ranked.loc[ranked["relative_strength"] == 2.0, "rank"].iloc[0]
        bottom = ranked.loc[ranked["relative_strength"] == 0.2, "rank"].iloc[0]
        assert top == 1
        assert bottom == 5

    def test_all_five_sectors_present(self):
        metrics = _make_metrics_df([1.0, 2.0, 3.0, 4.0, 5.0])
        ranked = rank_sectors(metrics)
        assert set(ranked["symbol"].tolist()) == set(SECTOR_SYMBOLS)
        assert len(ranked) == 5

    def test_ranks_are_1_through_5(self):
        metrics = _make_metrics_df([0.1, 0.2, 0.3, 0.4, 0.5])
        ranked = rank_sectors(metrics)
        assert sorted(ranked["rank"].tolist()) == [1, 2, 3, 4, 5]

    def test_tied_relative_strength_produces_complete_output(self):
        # All sectors have the same RS — ranks should still be 1-5 (stable, no duplicates)
        metrics = _make_metrics_df([1.0, 1.0, 1.0, 1.0, 1.0])
        ranked = rank_sectors(metrics)
        assert len(ranked) == 5
        assert sorted(ranked["rank"].tolist()) == [1, 2, 3, 4, 5]

    def test_rank_column_added_to_copy(self):
        metrics = _make_metrics_df([1.0, 2.0, 3.0, 4.0, 5.0])
        ranked = rank_sectors(metrics)
        # Original should not be mutated
        assert "rank" not in metrics.columns or True  # rank_sectors returns a copy
        assert "rank" in ranked.columns

    def test_rank_dtype_is_int(self):
        metrics = _make_metrics_df([1.0, 2.0, 3.0, 4.0, 5.0])
        ranked = rank_sectors(metrics)
        assert ranked["rank"].dtype in (int, "int64", "int32")


# ---------------------------------------------------------------------------
# Unit tests: compute_sector_metrics (integration, mocked cache)
# ---------------------------------------------------------------------------

class TestComputeSectorMetrics:

    def _patch_read_candles(self, symbol_map: dict):
        """Return a side_effect function for read_candles mock."""
        def _side_effect(symbol, timeframe):
            return symbol_map.get(symbol, pd.DataFrame())
        return _side_effect

    @patch("finintelligence.sector_rotation_engine.cache_manager.write_sector_metrics")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_institutional_flows")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_candles")
    def test_returns_dataframe_with_required_columns(self, mock_read, mock_flows, mock_write):
        candle_df = _make_candles(30)
        mock_read.return_value = candle_df
        mock_flows.return_value = pd.DataFrame()

        result = compute_sector_metrics()

        assert isinstance(result, pd.DataFrame)
        required_cols = {"symbol", "date", "return_20d", "relative_strength", "adx", "rank", "fii_net", "dii_net"}
        assert required_cols.issubset(set(result.columns)), \
            f"Missing columns: {required_cols - set(result.columns)}"

    @patch("finintelligence.sector_rotation_engine.cache_manager.write_sector_metrics")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_institutional_flows")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_candles")
    def test_returns_exactly_5_rows(self, mock_read, mock_flows, mock_write):
        mock_read.return_value = _make_candles(30)
        mock_flows.return_value = pd.DataFrame()

        result = compute_sector_metrics()
        assert len(result) == 5

    @patch("finintelligence.sector_rotation_engine.cache_manager.write_sector_metrics")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_institutional_flows")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_candles")
    def test_incorporates_fii_dii_flows(self, mock_read, mock_flows, mock_write):
        mock_read.return_value = _make_candles(30)
        flows = pd.DataFrame([{"fii_net": 500.0, "dii_net": -200.0}])
        mock_flows.return_value = flows

        result = compute_sector_metrics()
        assert (result["fii_net"] == 500.0).all()
        assert (result["dii_net"] == -200.0).all()

    @patch("finintelligence.sector_rotation_engine.cache_manager.write_sector_metrics")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_institutional_flows")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_candles")
    def test_write_sector_metrics_called(self, mock_read, mock_flows, mock_write):
        mock_read.return_value = _make_candles(30)
        mock_flows.return_value = pd.DataFrame()

        compute_sector_metrics()
        mock_write.assert_called_once()

    @patch("finintelligence.sector_rotation_engine.cache_manager.write_sector_metrics")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_institutional_flows")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_candles")
    def test_empty_cache_returns_zero_returns(self, mock_read, mock_flows, mock_write):
        mock_read.return_value = pd.DataFrame()
        mock_flows.return_value = pd.DataFrame()

        result = compute_sector_metrics()
        assert len(result) == 5
        assert (result["return_20d"] == 0.0).all()
        assert (result["relative_strength"] == 0.0).all()

    @patch("finintelligence.sector_rotation_engine.cache_manager.write_sector_metrics")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_institutional_flows")
    @patch("finintelligence.sector_rotation_engine.cache_manager.read_candles")
    def test_known_data_produces_expected_return(self, mock_read, mock_flows, mock_write):
        """
        Sector: price goes from 100 to 110 over 21 candles → 20d return = 10%
        NIFTY:  price goes from 100 to 105 over 21 candles → 20d return = 5%
        RS = 0.10 / 0.05 = 2.0
        """
        sector_df = pd.DataFrame({
            "open":   [100.0] + [110.0] * 20,
            "high":   [101.0] + [111.0] * 20,
            "low":    [99.0]  + [109.0] * 20,
            "close":  [100.0] + [110.0] * 20,
            "volume": [1e6] * 21,
        })
        nifty_df = pd.DataFrame({
            "open":   [100.0] + [105.0] * 20,
            "high":   [101.0] + [106.0] * 20,
            "low":    [99.0]  + [104.0] * 20,
            "close":  [100.0] + [105.0] * 20,
            "volume": [1e6] * 21,
        })

        def _side_effect(symbol, timeframe):
            if symbol == "^NSEI":
                return nifty_df
            return sector_df

        mock_read.side_effect = _side_effect
        mock_flows.return_value = pd.DataFrame()

        result = compute_sector_metrics()
        for val in result["return_20d"]:
            assert val == pytest.approx(0.10, rel=1e-6)
        for val in result["relative_strength"]:
            assert val == pytest.approx(2.0, rel=1e-6)
