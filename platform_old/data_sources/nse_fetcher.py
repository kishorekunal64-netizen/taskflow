"""
NSE dataset fetcher — free public endpoints only.
Used as priority-1 fallback before Yahoo Finance and Stooq.

Endpoints used:
  - NSE historical index data (CSV download)
  - NSE FII/DII institutional flow (JSON)

All results are cached locally under finintelligence/data/.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger("platform.data_sources.nse_fetcher")

_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# NSE symbol → index name mapping for historical data
_NSE_INDEX_MAP = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
    "^CNXFMCG": "NIFTY FMCG",
    "^CNXAUTO": "NIFTY AUTO",
    "^CNXPHARMA": "NIFTY PHARMA",
    "^CNXMETAL": "NIFTY METAL",
}

_NSE_HIST_URL = "https://www.nseindia.com/api/historical/indicesHistory"
_NSE_FII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"

_DATA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "finintelligence", "data"
)


def fetch_index_candles(symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV candles for an NSE index symbol.
    Returns a normalised DataFrame or None on failure.
    """
    index_name = _NSE_INDEX_MAP.get(symbol)
    if index_name is None:
        logger.debug("nse_fetcher: no NSE mapping for symbol %s", symbol)
        return None

    end = datetime.now(tz=timezone.utc)
    start = end - pd.Timedelta(days=days)

    params = {
        "indexType": index_name,
        "from": start.strftime("%d-%m-%Y"),
        "to": end.strftime("%d-%m-%Y"),
    }

    t0 = time.monotonic()
    try:
        session = requests.Session()
        # NSE requires a session cookie — prime it first
        session.get("https://www.nseindia.com", headers=_HEADERS, timeout=10)
        resp = session.get(_NSE_HIST_URL, params=params, headers=_HEADERS, timeout=30)
        latency_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "NSE API | url=%s | status=%s | latency_ms=%d",
            _NSE_HIST_URL, resp.status_code, latency_ms,
        )

        if resp.status_code != 200:
            return None

        data = resp.json()
        records = data.get("data", {}).get("indexCloseOnlineRecords", [])
        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.rename(columns={
            "EOD_TIMESTAMP": "timestamp",
            "EOD_OPEN_INDEX_VAL": "open",
            "EOD_HIGH_INDEX_VAL": "high",
            "EOD_LOW_INDEX_VAL": "low",
            "EOD_CLOSING_INDEX_VAL": "close",
        })
        df["volume"] = 0
        df["symbol"] = symbol
        df["timeframe"] = "1D"
        df["timestamp"] = pd.to_datetime(df["timestamp"], dayfirst=True, utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df[["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"]]
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "NSE API | url=%s | latency_ms=%d | error=%s",
            _NSE_HIST_URL, latency_ms, exc,
        )
        return None


def fetch_institutional_flows() -> Optional[pd.DataFrame]:
    """
    Fetch FII/DII daily flow data from NSE public API.
    Returns a normalised DataFrame or None on failure.
    """
    t0 = time.monotonic()
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=_HEADERS, timeout=10)
        resp = session.get(_NSE_FII_URL, headers=_HEADERS, timeout=30)
        latency_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "NSE FII API | url=%s | status=%s | latency_ms=%d",
            _NSE_FII_URL, resp.status_code, latency_ms,
        )

        if resp.status_code != 200:
            return None

        records = resp.json()
        if not records:
            return None

        df = pd.DataFrame(records)
        # Normalise column names to match existing schema
        col_map = {
            "date": "date",
            "buyValue": "fii_buy",
            "sellValue": "fii_sell",
            "netValue": "fii_net",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["date"] = pd.to_datetime(df.get("date", pd.Series(dtype=str)), errors="coerce")
        df = df.dropna(subset=["date"])
        return df

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "NSE FII API | url=%s | latency_ms=%d | error=%s",
            _NSE_FII_URL, latency_ms, exc,
        )
        return None
