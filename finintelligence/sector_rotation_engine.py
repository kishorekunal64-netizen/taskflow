"""
FinIntelligence Market Analysis System — Sector Rotation Engine.
Computes 20-day return, relative strength vs NIFTY_50, ADX(14), and sector ranking.
"""

import pandas as pd

from finintelligence import cache_manager
from finintelligence.config import SECTOR_SYMBOLS
from finintelligence.logger import get_logger

logger = get_logger("finintelligence.sector_rotation_engine")

_NIFTY_SYMBOL = "^NSEI"
_TIMEFRAME = "1D"
_RETURN_WINDOW = 20


def compute_relative_strength(sector_df: pd.DataFrame, nifty_df: pd.DataFrame) -> float:
    """
    Compute relative strength of a sector vs NIFTY_50 over a 20-day window.

    Returns sector_return_20d / nifty_return_20d.
    Returns 0.0 if nifty_return_20d is 0 (avoid division by zero).
    """
    sector_return = _compute_return_20d(sector_df)
    nifty_return = _compute_return_20d(nifty_df)

    if nifty_return == 0.0:
        return 0.0
    return sector_return / nifty_return


def compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    """
    Compute ADX(period) using pandas-ta.

    Returns the latest ADX value as a float.
    Returns 0.0 if computation fails or data is insufficient.
    """
    try:
        import pandas_ta as ta  # noqa: F401 — imported for side-effect (df.ta accessor)

        work = df.copy()
        # Normalise column names to lowercase
        work.columns = [c.lower() for c in work.columns]

        required = {"high", "low", "close"}
        if not required.issubset(set(work.columns)):
            logger.warning("compute_adx: missing required columns (high/low/close)")
            return 0.0

        if len(work) < period + 1:
            logger.warning("compute_adx: insufficient data (%d rows) for period %d", len(work), period)
            return 0.0

        adx_df = work.ta.adx(length=period)
        if adx_df is None or adx_df.empty:
            return 0.0

        # pandas-ta names the ADX column "ADX_{period}"
        adx_col = f"ADX_{period}"
        if adx_col not in adx_df.columns:
            # Fall back to first column
            adx_col = adx_df.columns[0]

        latest = adx_df[adx_col].dropna()
        if latest.empty:
            return 0.0

        return float(latest.iloc[-1])
    except Exception as exc:
        logger.warning("compute_adx failed: %s", exc)
        return 0.0


def rank_sectors(metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Assign ranks 1–5 to sectors by relative_strength descending.
    Rank 1 = highest relative_strength.

    Returns a copy of the DataFrame with a 'rank' column added.
    All 5 sectors must always be present.
    """
    result = metrics.copy()
    # rank() with method='first' gives stable ordering for ties (ascending=False → rank 1 = highest)
    result["rank"] = (
        result["relative_strength"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    return result


def compute_sector_metrics() -> pd.DataFrame:
    """
    Compute sector rotation metrics for all 5 SECTOR_SYMBOLS.

    Steps:
    1. Read 1D candles from cache for all 5 sector indices + NIFTY_50
    2. Compute 20-day price return for each sector
    3. Compute relative_strength vs NIFTY_50
    4. Compute ADX(14) for each sector
    5. Incorporate latest FII/DII net flows from institutional cache
    6. Call rank_sectors to assign ranks
    7. Write results via cache_manager.write_sector_metrics

    Returns DataFrame with columns:
        symbol, date, return_20d, relative_strength, adx, rank, fii_net, dii_net
    """
    # --- Load NIFTY_50 candles ---
    nifty_df = cache_manager.read_candles(_NIFTY_SYMBOL, _TIMEFRAME)
    if nifty_df is not None:
        nifty_df.columns = [c.lower() for c in nifty_df.columns]

    # --- Load institutional flows ---
    flows_df = cache_manager.read_institutional_flows()
    fii_net = 0.0
    dii_net = 0.0
    if flows_df is not None and not flows_df.empty:
        latest_flow = flows_df.iloc[-1]
        fii_net = float(latest_flow.get("fii_net", 0.0))
        dii_net = float(latest_flow.get("dii_net", 0.0))

    rows = []
    for symbol in SECTOR_SYMBOLS:
        sector_df = cache_manager.read_candles(symbol, _TIMEFRAME)
        if sector_df is not None:
            sector_df.columns = [c.lower() for c in sector_df.columns]

        return_20d = _compute_return_20d(sector_df)
        rel_strength = compute_relative_strength(sector_df, nifty_df)
        adx = compute_adx(sector_df) if sector_df is not None and not sector_df.empty else 0.0

        # Determine the date from the latest candle
        date = _latest_date(sector_df)

        rows.append({
            "symbol": symbol,
            "date": date,
            "return_20d": return_20d,
            "relative_strength": rel_strength,
            "adx": adx,
            "fii_net": fii_net,
            "dii_net": dii_net,
        })

    metrics = pd.DataFrame(rows)
    metrics = rank_sectors(metrics)

    try:
        cache_manager.write_sector_metrics(metrics)
    except Exception as exc:
        logger.error("compute_sector_metrics: write_sector_metrics failed: %s", exc)

    return metrics


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_return_20d(df: pd.DataFrame) -> float:
    """
    Compute 20-day price return from a candle DataFrame.
    Returns (close[-1] - close[-21]) / close[-21].
    Returns 0.0 if insufficient data or computation fails.
    """
    try:
        if df is None or df.empty:
            return 0.0
        close = df["close"].dropna().reset_index(drop=True)
        if len(close) < _RETURN_WINDOW + 1:
            return 0.0
        start_price = float(close.iloc[-(  _RETURN_WINDOW + 1)])
        end_price = float(close.iloc[-1])
        if start_price == 0.0:
            return 0.0
        return (end_price - start_price) / start_price
    except Exception as exc:
        logger.warning("_compute_return_20d failed: %s", exc)
        return 0.0


def _latest_date(df: pd.DataFrame) -> pd.Timestamp:
    """Return the latest timestamp from a candle DataFrame, or today's date."""
    try:
        if df is None or df.empty:
            return pd.Timestamp.now("UTC").normalize()
        for col in ("timestamp", "date", "datetime"):
            if col in df.columns:
                return pd.to_datetime(df[col].iloc[-1], utc=True)
        # If no timestamp column, use today
        return pd.Timestamp.now("UTC").normalize()
    except Exception:
        return pd.Timestamp.now("UTC").normalize()
