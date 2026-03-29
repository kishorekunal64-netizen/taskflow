"""
Unit tests for finintelligence/feature_generator.py
"""

import math
from unittest.mock import patch

import pandas as pd
import pytest

from finintelligence.feature_generator import (
    compute_features,
    compute_sma,
    compute_volatility,
    price_vs_sma,
)


# ---------------------------------------------------------------------------
# compute_sma
# ---------------------------------------------------------------------------

def test_compute_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = compute_sma(s, 3)
    # First two values are NaN; third is (1+2+3)/3 = 2.0
    assert math.isnan(result.iloc[0])
    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_compute_sma_period_equals_length():
    s = pd.Series([10.0, 20.0, 30.0])
    result = compute_sma(s, 3)
    assert result.iloc[-1] == pytest.approx(20.0)


def test_compute_sma_returns_series():
    s = pd.Series(range(10), dtype=float)
    result = compute_sma(s, 5)
    assert isinstance(result, pd.Series)
    assert len(result) == len(s)


# ---------------------------------------------------------------------------
# compute_volatility
# ---------------------------------------------------------------------------

def test_compute_volatility_constant_series_is_zero():
    s = pd.Series([100.0] * 30)
    vol = compute_volatility(s, window=20)
    assert vol == pytest.approx(0.0, abs=1e-10)


def test_compute_volatility_returns_float():
    s = pd.Series([float(i) for i in range(1, 31)])
    vol = compute_volatility(s, window=20)
    assert isinstance(vol, float)


def test_compute_volatility_insufficient_data_returns_nan():
    s = pd.Series([100.0, 101.0])  # only 2 points, window=20
    vol = compute_volatility(s, window=20)
    assert math.isnan(vol)


# ---------------------------------------------------------------------------
# price_vs_sma
# ---------------------------------------------------------------------------

def test_price_vs_sma_above():
    assert price_vs_sma(110.0, 100.0) == "above"


def test_price_vs_sma_below():
    assert price_vs_sma(90.0, 100.0) == "below"


def test_price_vs_sma_equal_is_above():
    assert price_vs_sma(100.0, 100.0) == "above"


# ---------------------------------------------------------------------------
# compute_features
# ---------------------------------------------------------------------------

def _make_candle_df(n: int = 250) -> pd.DataFrame:
    """Create a minimal candle DataFrame with `n` rows."""
    import numpy as np
    prices = 100.0 + pd.Series(range(n), dtype=float) * 0.1
    return pd.DataFrame({"close": prices})


def test_compute_features_empty_df_returns_none_indicators():
    with patch("finintelligence.feature_generator.read_candles", return_value=pd.DataFrame()):
        result = compute_features("^NSEI", "1D")

    assert result["symbol"] == "^NSEI"
    assert result["timeframe"] == "1D"
    assert result["close"] is None
    assert result["sma50"] is None
    assert result["sma200"] is None
    assert result["price_vs_sma50"] is None
    assert result["price_vs_sma200"] is None
    assert result["volatility_20d"] is None
    assert result["pct_change_1d"] is None
    assert result["candle_count"] == 0


def test_compute_features_sufficient_data():
    df = _make_candle_df(250)
    with patch("finintelligence.feature_generator.read_candles", return_value=df):
        result = compute_features("^NSEI", "1D")

    assert result["symbol"] == "^NSEI"
    assert result["timeframe"] == "1D"
    assert isinstance(result["close"], float)
    assert isinstance(result["sma50"], float)
    assert isinstance(result["sma200"], float)
    assert result["price_vs_sma50"] in ("above", "below")
    assert result["price_vs_sma200"] in ("above", "below")
    assert isinstance(result["volatility_20d"], float)
    assert isinstance(result["pct_change_1d"], float)
    assert result["candle_count"] == 250


def test_compute_features_insufficient_for_sma200():
    """With only 100 candles, SMA200 should be None."""
    df = _make_candle_df(100)
    with patch("finintelligence.feature_generator.read_candles", return_value=df):
        result = compute_features("^NSEI", "1D")

    assert result["sma50"] is not None   # 100 >= 50
    assert result["sma200"] is None      # 100 < 200
    assert result["price_vs_sma200"] is None


def test_compute_features_single_candle():
    """Single candle: no pct_change, no volatility, no SMA."""
    df = pd.DataFrame({"close": [100.0]})
    with patch("finintelligence.feature_generator.read_candles", return_value=df):
        result = compute_features("^NSEI", "1D")

    assert result["close"] == pytest.approx(100.0)
    assert result["candle_count"] == 1
    assert result["pct_change_1d"] is None
    assert result["sma50"] is None
    assert result["sma200"] is None


def test_compute_features_uppercase_columns():
    """Column names with uppercase should be normalised."""
    df = pd.DataFrame({"Close": [float(i) for i in range(1, 60)]})
    with patch("finintelligence.feature_generator.read_candles", return_value=df):
        result = compute_features("^NSEI", "1D")

    assert result["close"] is not None
    assert result["candle_count"] == 59
