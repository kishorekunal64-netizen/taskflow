"""
FinIntelligence Market Analysis System — local cache read/write interface.
Abstracts Parquet (OHLCV, sector, sentiment) and DuckDB (institutional flows).
All read failures return empty pd.DataFrame; write failures log and return.
"""

import os
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb

from finintelligence.config import (
    MARKET_DIR,
    INSTITUTIONAL_DIR,
    SECTOR_DIR,
    SENTIMENT_DIR,
    STALENESS_THRESHOLDS,
)
from finintelligence.logger import get_logger
from finintelligence.models import OutlookSignal, SentimentResult

logger = get_logger("finintelligence.cache_manager")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sanitize_symbol(symbol: str) -> str:
    """Remove ^ from symbol for use in filesystem paths."""
    return symbol.replace("^", "")


def _candle_path(symbol: str, timeframe: str) -> str:
    safe = _sanitize_symbol(symbol)
    return os.path.join(MARKET_DIR, safe, f"{timeframe}.parquet")


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------

def is_stale(symbol: str, timeframe: str) -> bool:
    """
    Return True if the cached Parquet file for (symbol, timeframe) does not
    exist or its mtime is older than STALENESS_THRESHOLDS[timeframe] minutes.
    """
    path = _candle_path(symbol, timeframe)
    if not os.path.exists(path):
        return True
    threshold_minutes = STALENESS_THRESHOLDS.get(timeframe, 0)
    age_seconds = time.time() - os.path.getmtime(path)
    return age_seconds > threshold_minutes * 60


# ---------------------------------------------------------------------------
# OHLCV candles
# ---------------------------------------------------------------------------

def read_candles(symbol: str, timeframe: str) -> pd.DataFrame:
    """Read cached candles for (symbol, timeframe). Returns empty DataFrame on failure."""
    path = _candle_path(symbol, timeframe)
    try:
        return pq.read_table(path).to_pandas()
    except Exception as exc:
        logger.debug("read_candles(%s, %s) failed: %s", symbol, timeframe, exc)
        return pd.DataFrame()


def write_candles(symbol: str, timeframe: str, df: pd.DataFrame) -> None:
    """Write candles DataFrame to Parquet. Logs and returns on failure."""
    path = _candle_path(symbol, timeframe)
    try:
        _ensure_dir(path)
        table = pa.Table.from_pandas(df)
        pq.write_table(table, path)
    except Exception as exc:
        logger.error("write_candles(%s, %s) failed at %s: %s", symbol, timeframe, path, exc)


# ---------------------------------------------------------------------------
# Institutional flows (DuckDB)
# ---------------------------------------------------------------------------

_FLOWS_DB = os.path.join(INSTITUTIONAL_DIR, "flows.db")
_FLOWS_TABLE = "institutional_flows"


def read_institutional_flows() -> pd.DataFrame:
    """Read all institutional flow records from DuckDB. Returns empty DataFrame on failure."""
    try:
        os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
        con = duckdb.connect(_FLOWS_DB)
        # Return empty if table doesn't exist yet
        tables = con.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        if _FLOWS_TABLE not in table_names:
            con.close()
            return pd.DataFrame()
        df = con.execute(f"SELECT * FROM {_FLOWS_TABLE}").df()
        con.close()
        return df
    except Exception as exc:
        logger.error("read_institutional_flows() failed at %s: %s", _FLOWS_DB, exc)
        return pd.DataFrame()


def write_institutional_flows(df: pd.DataFrame) -> None:
    """Write institutional flows DataFrame to DuckDB. Logs and returns on failure."""
    try:
        os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
        con = duckdb.connect(_FLOWS_DB)
        con.execute(f"CREATE TABLE IF NOT EXISTS {_FLOWS_TABLE} AS SELECT * FROM df LIMIT 0")
        con.execute(f"INSERT INTO {_FLOWS_TABLE} SELECT * FROM df")
        con.close()
    except Exception as exc:
        logger.error("write_institutional_flows() failed at %s: %s", _FLOWS_DB, exc)


# ---------------------------------------------------------------------------
# Sector metrics
# ---------------------------------------------------------------------------

_SECTOR_PATH = os.path.join(SECTOR_DIR, "sector_metrics.parquet")


def read_sector_metrics() -> pd.DataFrame:
    """Read sector metrics Parquet. Returns empty DataFrame on failure."""
    try:
        return pq.read_table(_SECTOR_PATH).to_pandas()
    except Exception as exc:
        logger.debug("read_sector_metrics() failed at %s: %s", _SECTOR_PATH, exc)
        return pd.DataFrame()


def write_sector_metrics(df: pd.DataFrame) -> None:
    """Write sector metrics DataFrame to Parquet. Logs and returns on failure."""
    try:
        _ensure_dir(_SECTOR_PATH)
        table = pa.Table.from_pandas(df)
        pq.write_table(table, _SECTOR_PATH)
    except Exception as exc:
        logger.error("write_sector_metrics() failed at %s: %s", _SECTOR_PATH, exc)


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

_NEWS_PATH = os.path.join(SENTIMENT_DIR, "news.parquet")


def read_news(hours: int = 24) -> pd.DataFrame:
    """
    Read news entries from the last `hours` hours.
    Returns empty DataFrame on failure or if no data exists.
    """
    try:
        df = pq.read_table(_NEWS_PATH).to_pandas()
        if df.empty:
            return df
        if "published" in df.columns:
            cutoff = pd.Timestamp.utcnow() - pd.Timedelta(hours=hours)
            # Handle both tz-aware and tz-naive timestamps
            ts = pd.to_datetime(df["published"], utc=True, errors="coerce")
            df = df[ts >= cutoff].reset_index(drop=True)
        return df
    except Exception as exc:
        logger.debug("read_news() failed at %s: %s", _NEWS_PATH, exc)
        return pd.DataFrame()


def write_news(df: pd.DataFrame) -> None:
    """
    Append new news rows to Parquet, deduplicating by headline.
    Logs and returns on failure.
    """
    try:
        _ensure_dir(_NEWS_PATH)
        if os.path.exists(_NEWS_PATH):
            existing = pq.read_table(_NEWS_PATH).to_pandas()
            combined = pd.concat([existing, df], ignore_index=True)
        else:
            combined = df.copy()
        if "headline" in combined.columns:
            combined = combined.drop_duplicates(subset=["headline"], keep="last")
        table = pa.Table.from_pandas(combined)
        pq.write_table(table, _NEWS_PATH)
    except Exception as exc:
        logger.error("write_news() failed at %s: %s", _NEWS_PATH, exc)


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

_SENTIMENT_PATH = os.path.join(SENTIMENT_DIR, "sentiment.parquet")


def write_sentiment(result: SentimentResult) -> None:
    """Append a SentimentResult record to Parquet. Logs and returns on failure."""
    try:
        _ensure_dir(_SENTIMENT_PATH)
        row = {
            "timestamp": result.timestamp,
            "index_momentum": result.index_momentum,
            "sector_perf": result.sector_perf,
            "institutional_signal": result.institutional_signal,
            "macro_score": result.macro_score,
            "composite_score": result.composite_score,
            "classification": result.classification,
        }
        new_df = pd.DataFrame([row])
        if os.path.exists(_SENTIMENT_PATH):
            existing = pq.read_table(_SENTIMENT_PATH).to_pandas()
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df
        table = pa.Table.from_pandas(combined)
        pq.write_table(table, _SENTIMENT_PATH)
    except Exception as exc:
        logger.error("write_sentiment() failed at %s: %s", _SENTIMENT_PATH, exc)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

_SIGNALS_PATH = os.path.join(SENTIMENT_DIR, "signals.parquet")


def write_signal(signal: OutlookSignal) -> None:
    """Append an OutlookSignal record to Parquet. Logs and returns on failure."""
    try:
        _ensure_dir(_SIGNALS_PATH)
        row = {
            "timestamp": signal.timestamp,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "supporting_factors": str(signal.supporting_factors),
            "rationale": signal.rationale,
        }
        new_df = pd.DataFrame([row])
        if os.path.exists(_SIGNALS_PATH):
            existing = pq.read_table(_SIGNALS_PATH).to_pandas()
            combined = pd.concat([existing, new_df], ignore_index=True)
        else:
            combined = new_df
        table = pa.Table.from_pandas(combined)
        pq.write_table(table, _SIGNALS_PATH)
    except Exception as exc:
        logger.error("write_signal() failed at %s: %s", _SIGNALS_PATH, exc)


def read_latest_signal() -> Optional[OutlookSignal]:
    """
    Read the most recent OutlookSignal from Parquet.
    Returns None if no signals exist or on read failure.
    """
    try:
        df = pq.read_table(_SIGNALS_PATH).to_pandas()
        if df.empty:
            return None
        row = df.iloc[-1]
        # Parse supporting_factors back from string representation
        factors_raw = row.get("supporting_factors", "[]")
        try:
            import ast
            factors = ast.literal_eval(str(factors_raw))
            if not isinstance(factors, list):
                factors = [str(factors_raw)]
        except Exception:
            factors = [str(factors_raw)]
        return OutlookSignal(
            timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime(),
            direction=str(row["direction"]),
            confidence=float(row["confidence"]),
            supporting_factors=factors,
            rationale=str(row.get("rationale", "")),
        )
    except Exception as exc:
        logger.debug("read_latest_signal() failed at %s: %s", _SIGNALS_PATH, exc)
        return None
