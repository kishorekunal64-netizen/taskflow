"""
FinIntelligence Market Analysis System — FII/DII institutional flow fetcher.

Downloads daily FII/DII gross buy, gross sell, and net values from NSE/NSDL
public endpoints. Appends only new trading dates not already in cache.

Primary source:  NSE FII/DII Trade React API
Fallback source: NSDL FII/DII CSV download

On endpoint failure → logs URL + HTTP status + timestamp, returns last cached flows.
Every API call is logged with URL, status, and latency_ms.
"""

import io
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

from finintelligence import cache_manager
from finintelligence.logger import get_logger, record_error
from finintelligence.models import InstitutionalFlow

logger = get_logger("finintelligence.institutional_fetcher")

# ---------------------------------------------------------------------------
# Endpoint constants
# ---------------------------------------------------------------------------

_NSE_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_NSDL_URL = "https://www.nsdl.co.in/download/FII_DII_Data.csv"

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}

# NSE JSON field → InstitutionalFlow field mapping
_NSE_FIELD_MAP = {
    "date":         "date",
    "fiiBuyValue":  "fii_buy",
    "fiiSellValue": "fii_sell",
    "diiBuyValue":  "dii_buy",
    "diiSellValue": "dii_sell",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_institutional_flows() -> pd.DataFrame:
    """
    Fetch daily FII/DII institutional flow data.

    1. Try NSE primary endpoint (_fetch_nse).
    2. On NSE failure → try NSDL CSV fallback (_fetch_nsdl).
    3. On all-source failure → log and return last cached flows (no raise).
    4. Parse each raw record via _parse_flow_record; skip None results.
    5. Append only new trading dates not already in cache.
    6. Write updated DataFrame to cache via cache_manager.write_institutional_flows.

    Returns the full (cached + new) DataFrame of institutional flows.
    """
    cached_df = cache_manager.read_institutional_flows()

    # Determine already-cached dates for deduplication
    cached_dates: set[str] = set()
    if not cached_df.empty and "date" in cached_df.columns:
        cached_dates = {
            pd.Timestamp(d).strftime("%Y-%m-%d")
            for d in cached_df["date"]
        }

    # Attempt primary source
    raw_records = _fetch_nse()

    # Fallback to NSDL if NSE failed
    if raw_records is None:
        raw_records = _fetch_nsdl()

    # All sources failed — return cached data
    if raw_records is None:
        logger.warning(
            "All institutional flow sources failed — returning last cached data "
            "(cached_rows=%d)",
            len(cached_df),
        )
        return cached_df

    # Parse and validate each record
    new_flows: list[InstitutionalFlow] = []
    for raw in raw_records:
        flow = _parse_flow_record(raw)
        if flow is None:
            continue
        date_key = flow.date.strftime("%Y-%m-%d")
        if date_key in cached_dates:
            logger.debug("Skipping already-cached date %s", date_key)
            continue
        new_flows.append(flow)

    if not new_flows:
        logger.info(
            "No new institutional flow records to append (cached_rows=%d)",
            len(cached_df),
        )
        return cached_df

    # Convert new flows to DataFrame
    new_df = pd.DataFrame([
        {
            "date":     f.date,
            "fii_buy":  f.fii_buy,
            "fii_sell": f.fii_sell,
            "fii_net":  f.fii_net,
            "dii_buy":  f.dii_buy,
            "dii_sell": f.dii_sell,
            "dii_net":  f.dii_net,
        }
        for f in new_flows
    ])

    # Merge with cached data
    if cached_df.empty:
        combined_df = new_df
    else:
        combined_df = pd.concat([cached_df, new_df], ignore_index=True)

    combined_df = combined_df.sort_values("date").reset_index(drop=True)

    cache_manager.write_institutional_flows(combined_df)
    logger.info(
        "Appended %d new institutional flow records (total_rows=%d)",
        len(new_flows), len(combined_df),
    )
    return combined_df


def _parse_flow_record(raw: dict) -> Optional[InstitutionalFlow]:
    """
    Parse a single raw institutional flow record dict into an InstitutionalFlow.

    Validation rules:
    - Attempts float conversion for fii_buy, fii_sell, dii_buy, dii_sell.
    - Returns None if any conversion fails (non-numeric value).
    - Returns None if any of fii_buy, fii_sell, dii_buy, dii_sell < 0.
    - fii_net and dii_net are computed (not validated for sign).

    Returns InstitutionalFlow on success, None on any validation failure.
    """
    try:
        fii_buy  = float(raw.get("fii_buy",  raw.get("fiiBuyValue",  None)))
        fii_sell = float(raw.get("fii_sell", raw.get("fiiSellValue", None)))
        dii_buy  = float(raw.get("dii_buy",  raw.get("diiBuyValue",  None)))
        dii_sell = float(raw.get("dii_sell", raw.get("diiSellValue", None)))
    except (TypeError, ValueError):
        logger.debug("_parse_flow_record: non-numeric value in record %s", raw)
        return None

    if fii_buy < 0 or fii_sell < 0 or dii_buy < 0 or dii_sell < 0:
        logger.debug(
            "_parse_flow_record: negative value rejected — "
            "fii_buy=%.2f fii_sell=%.2f dii_buy=%.2f dii_sell=%.2f",
            fii_buy, fii_sell, dii_buy, dii_sell,
        )
        return None

    # Parse date — accept datetime, pd.Timestamp, or string
    raw_date = raw.get("date", raw.get("Date", None))
    try:
        ts = pd.Timestamp(raw_date)
        if pd.isna(ts):
            raise ValueError("date is NaT/None")
        date = ts.to_pydatetime().replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
    except Exception:
        logger.debug("_parse_flow_record: unparseable date '%s' in record %s", raw_date, raw)
        return None

    return InstitutionalFlow(
        date=date,
        fii_buy=fii_buy,
        fii_sell=fii_sell,
        fii_net=fii_buy - fii_sell,
        dii_buy=dii_buy,
        dii_sell=dii_sell,
        dii_net=dii_buy - dii_sell,
    )


# ---------------------------------------------------------------------------
# Private fetch helpers
# ---------------------------------------------------------------------------

def _fetch_nse() -> Optional[list[dict]]:
    """
    Fetch FII/DII data from the NSE primary endpoint.

    Logs URL, HTTP status, and latency_ms for every call.
    Returns a list of raw record dicts on success, None on failure.
    """
    t0 = time.monotonic()
    status = "ok"
    try:
        response = requests.get(_NSE_URL, headers=_NSE_HEADERS, timeout=30)
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = str(response.status_code)

        logger.info(
            "API call | url=%s | status=%s | latency_ms=%d",
            _NSE_URL, status, latency_ms,
        )

        if response.status_code != 200:
            _log_endpoint_failure(_NSE_URL, status, latency_ms)
            return None

        data = response.json()

        # NSE returns a JSON array directly
        if not isinstance(data, list):
            logger.warning(
                "NSE endpoint returned unexpected structure (type=%s) — expected list",
                type(data).__name__,
            )
            return None

        return data

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = f"error:{type(exc).__name__}"
        logger.error(
            "API call | url=%s | status=%s | latency_ms=%d | error=%s",
            _NSE_URL, status, latency_ms, exc,
        )
        record_error("institutional_fetcher")
        return None


def _fetch_nsdl() -> Optional[list[dict]]:
    """
    Fetch FII/DII data from the NSDL CSV fallback endpoint.

    Logs URL, HTTP status, and latency_ms for every call.
    Returns a list of raw record dicts on success, None on failure.
    """
    t0 = time.monotonic()
    status = "ok"
    try:
        response = requests.get(_NSDL_URL, timeout=30)
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = str(response.status_code)

        logger.info(
            "API call | url=%s | status=%s | latency_ms=%d",
            _NSDL_URL, status, latency_ms,
        )

        if response.status_code != 200:
            _log_endpoint_failure(_NSDL_URL, status, latency_ms)
            return None

        df = pd.read_csv(io.StringIO(response.text))

        if df.empty:
            logger.warning("NSDL CSV response is empty")
            return None

        # Normalise column names to lowercase with underscores
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Map NSDL column names to internal names
        col_aliases = {
            "fii_buy":       ["fii_buy", "fii_gross_purchase", "fii_purchase"],
            "fii_sell":      ["fii_sell", "fii_gross_sales", "fii_sales"],
            "dii_buy":       ["dii_buy", "dii_gross_purchase", "dii_purchase"],
            "dii_sell":      ["dii_sell", "dii_gross_sales", "dii_sales"],
            "date":          ["date", "trade_date"],
        }
        for target, aliases in col_aliases.items():
            if target not in df.columns:
                for alias in aliases:
                    if alias in df.columns:
                        df = df.rename(columns={alias: target})
                        break

        return df.to_dict(orient="records")

    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = f"error:{type(exc).__name__}"
        logger.error(
            "API call | url=%s | status=%s | latency_ms=%d | error=%s",
            _NSDL_URL, status, latency_ms, exc,
        )
        record_error("institutional_fetcher")
        return None


def _log_endpoint_failure(url: str, status: str, latency_ms: int) -> None:
    """Log a structured endpoint failure entry (Requirement 3.4)."""
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    logger.error(
        "Endpoint failure | url=%s | status=%s | latency_ms=%d | timestamp=%s",
        url, status, latency_ms, timestamp,
    )
    record_error("institutional_fetcher")
