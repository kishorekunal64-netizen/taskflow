"""
FinIntelligence Market Analysis System — OHLCV data fetcher.

Downloads OHLCV data from Yahoo Finance (primary) with Stooq fallback.
Checks cache staleness before downloading; skips download if fresh.

Timeframe → yfinance interval/period mapping:
  1D  → interval="1d",  period="2y"
  4H  → interval="1h",  period="730d"  (resampled to 4H)
  1H  → interval="1h",  period="730d"
  15M → interval="15m", period="60d"
  5M  → interval="5m",  period="60d"

Stooq symbol mapping: strip "^", lowercase, append ".in" for Indian indices.
"""

import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

from finintelligence import cache_manager
from finintelligence.config import SYMBOLS, TIMEFRAMES
from finintelligence.logger import get_logger, record_error

logger = get_logger("finintelligence.data_fetcher")

# ---------------------------------------------------------------------------
# Timeframe → yfinance parameters
# ---------------------------------------------------------------------------

_YF_PARAMS: dict[str, dict] = {
    "1D":  {"interval": "1d",  "period": "2y"},
    "4H":  {"interval": "1h",  "period": "730d"},
    "1H":  {"interval": "1h",  "period": "730d"},
    "15M": {"interval": "15m", "period": "60d"},
    "5M":  {"interval": "5m",  "period": "60d"},
}

# Minimum candles required per symbol/timeframe
_MIN_CANDLES = 365


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_symbol(symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Fetch OHLCV data for a single (symbol, timeframe) pair.

    1. If cache is fresh → return cached data immediately.
    2. Try Yahoo Finance (_fetch_yfinance).
    3. On empty/malformed YF response → try Stooq (_fetch_stooq).
    4. On all-source failure → log and return empty DataFrame (no raise).
    5. On success → write to cache via cache_manager.write_candles.
    """
    if not cache_manager.is_stale(symbol, timeframe):
        logger.debug("Cache fresh for %s/%s — skipping download", symbol, timeframe)
        return cache_manager.read_candles(symbol, timeframe)

    df = _fetch_yfinance(symbol, timeframe)

    if df is None or df.empty or len(df) < _MIN_CANDLES:
        logger.warning(
            "Yahoo Finance returned insufficient data for %s/%s (got %d candles) — trying Stooq",
            symbol, timeframe, len(df) if df is not None else 0,
        )
        df = _fetch_stooq(symbol, timeframe)

    if df is None or df.empty:
        _log_all_sources_failed(symbol, timeframe)
        return pd.DataFrame()

    cache_manager.write_candles(symbol, timeframe, df)
    logger.info(
        "Fetched %d candles for %s/%s — cache updated",
        len(df), symbol, timeframe,
    )
    return df


def fetch_all() -> None:
    """
    Iterate over all SYMBOLS × TIMEFRAMES and call fetch_symbol for each.
    Failures are logged inside fetch_symbol; this function never raises.
    """
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            try:
                fetch_symbol(symbol, timeframe)
            except Exception as exc:  # belt-and-suspenders guard
                logger.error(
                    "Unexpected error in fetch_all for %s/%s: %s",
                    symbol, timeframe, exc, exc_info=True,
                )
                record_error("data_fetcher")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _fetch_yfinance(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """
    Download OHLCV data from Yahoo Finance using yfinance.

    Logs every API call with URL (ticker), status, and latency_ms.
    Returns a normalised DataFrame or None on failure.
    """
    params = _YF_PARAMS.get(timeframe)
    if params is None:
        logger.error("Unknown timeframe '%s' — no yfinance params defined", timeframe)
        return None

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    t0 = time.monotonic()
    status = "ok"
    try:
        ticker = yf.Ticker(symbol)
        raw: pd.DataFrame = ticker.history(
            interval=params["interval"],
            period=params["period"],
            auto_adjust=True,
            actions=False,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        if raw is None or raw.empty:
            status = "empty"
            logger.warning(
                "API call | url=%s | status=%s | latency_ms=%d",
                url, status, latency_ms,
            )
            return None

        logger.info(
            "API call | url=%s | status=%s | latency_ms=%d",
            url, status, latency_ms,
        )

        df = _normalise_yf(raw, symbol, timeframe)

        # Resample 1H data to 4H when timeframe is "4H"
        if timeframe == "4H":
            df = _resample_to_4h(df)

        return df

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = f"error:{type(exc).__name__}"
        logger.error(
            "API call | url=%s | status=%s | latency_ms=%d | error=%s",
            url, status, latency_ms, exc,
        )
        record_error("data_fetcher")
        return None


def _fetch_stooq(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """
    Download daily OHLCV data from Stooq as a CSV fallback.

    Stooq symbol mapping:
      - Strip "^", lowercase, append ".in" for Indian indices (e.g. "^NSEI" → "nsei.in")
      - Special case: "^NSEI" → "^nsei.in" per Stooq convention

    Only daily data is available from Stooq; used as fallback for any timeframe.
    Logs every API call with URL, status, and latency_ms.
    Returns a normalised DataFrame or None on failure.
    """
    stooq_symbol = _to_stooq_symbol(symbol)
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"

    t0 = time.monotonic()
    status = "ok"
    try:
        response = requests.get(url, timeout=30)
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = str(response.status_code)

        logger.info(
            "API call | url=%s | status=%s | latency_ms=%d",
            url, status, latency_ms,
        )

        if response.status_code != 200:
            logger.warning(
                "Stooq returned HTTP %d for symbol %s",
                response.status_code, symbol,
            )
            return None

        from io import StringIO
        df_raw = pd.read_csv(StringIO(response.text))

        if df_raw.empty or "Close" not in df_raw.columns:
            logger.warning("Stooq response empty or malformed for symbol %s", symbol)
            return None

        df = _normalise_stooq(df_raw, symbol, timeframe)
        return df

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = f"error:{type(exc).__name__}"
        logger.error(
            "API call | url=%s | status=%s | latency_ms=%d | error=%s",
            url, status, latency_ms, exc,
        )
        record_error("data_fetcher")
        return None


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_yf(raw: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """Convert yfinance DataFrame to the standard OHLCV schema."""
    df = raw.copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    # Keep only OHLCV columns
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = float("nan")
    df = df[["open", "high", "low", "close", "volume"]].copy()
    df["symbol"] = symbol
    df["timeframe"] = timeframe
    df.index.name = "timestamp"
    df = df.reset_index()
    return df


def _normalise_stooq(raw: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """Convert Stooq CSV DataFrame to the standard OHLCV schema."""
    df = raw.copy()
    # Stooq columns: Date, Open, High, Low, Close, Volume
    col_map = {
        "Date": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=col_map)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = float("nan")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["symbol"] = symbol
    df["timeframe"] = timeframe
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample a 1H OHLCV DataFrame to 4H candles.
    Expects a 'timestamp' column with UTC-aware datetimes.
    """
    df = df.copy()
    df = df.set_index("timestamp")
    symbol = df["symbol"].iloc[0] if "symbol" in df.columns else ""
    timeframe = "4H"

    ohlcv = df[["open", "high", "low", "close", "volume"]]
    resampled = ohlcv.resample("4h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(how="all")

    resampled["symbol"] = symbol
    resampled["timeframe"] = timeframe
    resampled.index.name = "timestamp"
    return resampled.reset_index()


def _to_stooq_symbol(symbol: str) -> str:
    """
    Convert a Yahoo Finance symbol to its Stooq equivalent.

    Rules:
    - Strip leading "^", lowercase
    - Append ".in" for Indian NSE indices
    Examples:
      "^NSEI"     → "nsei.in"
      "^NSEBANK"  → "nsebank.in"
      "^CNXIT"    → "cnxit.in"
    """
    # Remove leading ^ and lowercase
    s = symbol.lstrip("^").lower()
    # All tracked symbols are Indian NSE indices — append .in
    if not s.endswith(".in"):
        s = s + ".in"
    return s


def _log_all_sources_failed(symbol: str, timeframe: str) -> None:
    """Log a structured failure entry when all data sources are exhausted."""
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    logger.error(
        "All sources failed | source=yfinance+stooq | symbol=%s | timeframe=%s | timestamp=%s",
        symbol, timeframe, timestamp,
    )
    record_error("data_fetcher")
