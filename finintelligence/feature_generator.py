"""
FinIntelligence Market Analysis System — OHLCV feature extraction.
Computes SMA50, SMA200, volatility, and price-relative-to-MA signals
from cached candle data.
"""

import pandas as pd

from finintelligence.cache_manager import read_candles
from finintelligence.logger import get_logger

logger = get_logger("finintelligence.feature_generator")


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Compute simple moving average over `period` bars."""
    return series.rolling(window=period).mean()


def compute_volatility(series: pd.Series, window: int = 20) -> float:
    """
    Compute rolling standard deviation of log returns over `window` bars.
    Returns the most recent value as a float.
    Returns NaN if insufficient data.
    """
    returns = series.pct_change()
    vol = returns.rolling(window=window).std()
    return float(vol.iloc[-1]) if not vol.empty else float("nan")


def price_vs_sma(close: float, sma: float) -> str:
    """Return 'above' if close >= sma, else 'below'."""
    return "above" if close >= sma else "below"


def compute_features(symbol: str, timeframe: str) -> dict:
    """
    Read candles from cache for (symbol, timeframe) and compute indicators.

    Returns a dict with keys:
        symbol, timeframe, close, sma50, sma200,
        price_vs_sma50, price_vs_sma200,
        volatility_20d, pct_change_1d, candle_count

    If the cache returns an empty DataFrame, logs a warning and returns
    a dict with None values for all indicator keys.
    """
    df = read_candles(symbol, timeframe)

    base = {"symbol": symbol, "timeframe": timeframe}
    none_indicators = {
        "close": None,
        "sma50": None,
        "sma200": None,
        "price_vs_sma50": None,
        "price_vs_sma200": None,
        "volatility_20d": None,
        "pct_change_1d": None,
        "candle_count": 0,
    }

    if df is None or df.empty:
        logger.warning(
            "compute_features(%s, %s): cache returned empty DataFrame — "
            "returning None indicators",
            symbol,
            timeframe,
        )
        return {**base, **none_indicators}

    # Normalise column names to lowercase
    df.columns = [c.lower() for c in df.columns]

    if "close" not in df.columns:
        logger.warning(
            "compute_features(%s, %s): 'close' column missing — "
            "returning None indicators",
            symbol,
            timeframe,
        )
        return {**base, **none_indicators}

    close_series = df["close"].dropna().reset_index(drop=True)
    candle_count = len(close_series)

    if candle_count == 0:
        logger.warning(
            "compute_features(%s, %s): no valid close prices — "
            "returning None indicators",
            symbol,
            timeframe,
        )
        return {**base, **none_indicators}

    latest_close = float(close_series.iloc[-1])

    # SMA50
    sma50_series = compute_sma(close_series, 50)
    sma50_val = float(sma50_series.iloc[-1]) if not sma50_series.empty else None
    if pd.isna(sma50_val):
        sma50_val = None

    # SMA200
    sma200_series = compute_sma(close_series, 200)
    sma200_val = float(sma200_series.iloc[-1]) if not sma200_series.empty else None
    if pd.isna(sma200_val):
        sma200_val = None

    # price_vs_sma50 / price_vs_sma200
    pvs50 = price_vs_sma(latest_close, sma50_val) if sma50_val is not None else None
    pvs200 = price_vs_sma(latest_close, sma200_val) if sma200_val is not None else None

    # 20-day volatility
    vol = compute_volatility(close_series, window=20)
    vol_val = None if pd.isna(vol) else vol

    # 1-day pct change
    if candle_count >= 2:
        prev_close = float(close_series.iloc[-2])
        pct_change = ((latest_close - prev_close) / prev_close) * 100.0 if prev_close != 0 else None
    else:
        pct_change = None

    return {
        **base,
        "close": latest_close,
        "sma50": sma50_val,
        "sma200": sma200_val,
        "price_vs_sma50": pvs50,
        "price_vs_sma200": pvs200,
        "volatility_20d": vol_val,
        "pct_change_1d": pct_change,
        "candle_count": candle_count,
    }
