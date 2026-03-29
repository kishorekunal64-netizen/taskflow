"""
FinIntelligence Market Analysis System — Composite Sentiment Engine.

Aggregates four signals into a composite score in [-1.0, 1.0]:
  - Index momentum   (30%): 5-day ROC of NIFTY_50 close, normalised to [-1, 1]
  - Sector perf      (25%): average 5-day return across all 5 sectors, normalised to [-1, 1]
  - Institutional    (30%): FII net flow z-score, clamped to [-1, 1]
  - Macro score      (15%): count of macro-keyword news entries in last 24h, normalised

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from finintelligence import cache_manager
from finintelligence.config import SECTOR_SYMBOLS
from finintelligence.logger import get_logger
from finintelligence.models import SentimentResult

logger = get_logger("finintelligence.sentiment_engine")

# ---------------------------------------------------------------------------
# Macro keywords (case-insensitive)
# ---------------------------------------------------------------------------

_MACRO_KEYWORDS: list[str] = [
    "RBI",
    "repo rate",
    "monetary policy",
    "Union Budget",
    "fiscal deficit",
    "US Fed",
    "Federal Reserve",
    "interest rate",
    "inflation",
    "CPI",
    "WPI",
    "geopolitical",
    "war",
    "sanctions",
    "conflict",
]

# Pre-compiled pattern for efficiency
_MACRO_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in _MACRO_KEYWORDS),
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Signal weights
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "index_momentum":      0.30,
    "sector_perf":         0.25,
    "institutional_signal": 0.30,
    "macro_score":         0.15,
}

# ---------------------------------------------------------------------------
# Module-level cache for last known institutional flows (staleness fallback)
# ---------------------------------------------------------------------------

_last_flows_df: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_sentiment() -> SentimentResult:
    """
    Compute composite market sentiment from four signals and persist the result.

    Returns a SentimentResult with all signal values, composite score, and
    classification. On missing institutional flows, uses last cached value
    and logs a staleness warning.
    """
    global _last_flows_df

    # --- NIFTY_50 candles ---
    nifty_df = cache_manager.read_candles("^NSEI", "1D")

    # --- Sector candles ---
    sector_dfs: dict[str, pd.DataFrame] = {
        sym: cache_manager.read_candles(sym, "1D") for sym in SECTOR_SYMBOLS
    }

    # --- Institutional flows (with staleness fallback) ---
    flows_df = cache_manager.read_institutional_flows()
    if flows_df.empty:
        if _last_flows_df is not None and not _last_flows_df.empty:
            logger.warning(
                "Institutional flows unavailable; using last cached value (staleness warning)"
            )
            flows_df = _last_flows_df
        else:
            logger.warning(
                "Institutional flows unavailable and no cached value; institutional_signal=0.0"
            )
    else:
        _last_flows_df = flows_df

    # --- News ---
    news_df = cache_manager.read_news(hours=24)

    # --- Compute individual signals ---
    idx_mom = _index_momentum(nifty_df)
    sec_perf = _sector_performance(sector_dfs)
    inst_sig = _institutional_signal(flows_df)
    macro = _macro_score(news_df)

    signals = {
        "index_momentum":       idx_mom,
        "sector_perf":          sec_perf,
        "institutional_signal": inst_sig,
        "macro_score":          macro,
    }

    composite = _composite(signals)
    classification = _classify(composite)

    result = SentimentResult(
        timestamp=datetime.now(tz=timezone.utc),
        index_momentum=idx_mom,
        sector_perf=sec_perf,
        institutional_signal=inst_sig,
        macro_score=macro,
        composite_score=composite,
        classification=classification,
    )

    cache_manager.write_sentiment(result)
    logger.info(
        "Sentiment computed: composite=%.4f classification=%s "
        "(idx_mom=%.4f sec_perf=%.4f inst=%.4f macro=%d)",
        composite, classification, idx_mom, sec_perf, inst_sig, macro,
    )
    return result


# ---------------------------------------------------------------------------
# Signal helpers
# ---------------------------------------------------------------------------

def _index_momentum(nifty_df: pd.DataFrame) -> float:
    """
    5-day Rate of Change of NIFTY_50 close, normalised to [-1, 1].

    ROC = (close[-1] - close[-6]) / close[-6]
    Normalisation: clamp to [-0.05, 0.05] then scale to [-1, 1].
    (A 5% move in 5 days is treated as the extreme.)
    Returns 0.0 on insufficient data.
    """
    if nifty_df.empty or "close" not in nifty_df.columns or len(nifty_df) < 6:
        return 0.0
    try:
        close = nifty_df["close"].dropna()
        if len(close) < 6:
            return 0.0
        prev = float(close.iloc[-6])
        curr = float(close.iloc[-1])
        if prev == 0.0:
            return 0.0
        roc = (curr - prev) / prev  # e.g. 0.03 for +3%
        # Normalise: clamp to [-0.05, 0.05] → scale to [-1, 1]
        clamped = max(-0.05, min(0.05, roc))
        return clamped / 0.05
    except Exception as exc:
        logger.warning("_index_momentum failed: %s", exc)
        return 0.0


def _sector_performance(sector_dfs: dict) -> float:
    """
    Average 5-day return across all 5 sectors, normalised to [-1, 1].

    For each sector: return_5d = (close[-1] - close[-6]) / close[-6]
    Average across available sectors, then normalise by clamping to [-0.05, 0.05]
    and scaling to [-1, 1].
    Returns 0.0 if no sector data is available.
    """
    returns: list[float] = []
    for sym, df in sector_dfs.items():
        if df.empty or "close" not in df.columns or len(df) < 6:
            continue
        try:
            close = df["close"].dropna()
            if len(close) < 6:
                continue
            prev = float(close.iloc[-6])
            curr = float(close.iloc[-1])
            if prev == 0.0:
                continue
            returns.append((curr - prev) / prev)
        except Exception as exc:
            logger.debug("_sector_performance: skipping %s — %s", sym, exc)

    if not returns:
        return 0.0

    avg = sum(returns) / len(returns)
    clamped = max(-0.05, min(0.05, avg))
    return clamped / 0.05


def _institutional_signal(flows_df: pd.DataFrame) -> float:
    """
    FII net flow z-score normalised, clamped to [-1, 1].

    z = (fii_net[-1] - rolling_mean_20) / rolling_std_20
    Clamp: max(-1.0, min(1.0, z))
    Returns 0.0 if std is 0 or insufficient data (< 2 rows).
    """
    if flows_df.empty or "fii_net" not in flows_df.columns:
        return 0.0
    try:
        series = flows_df["fii_net"].dropna()
        if len(series) < 2:
            return 0.0
        window = min(20, len(series))
        tail = series.iloc[-window:]
        mean = float(tail.mean())
        std = float(tail.std(ddof=1))
        if std == 0.0 or pd.isna(std):
            return 0.0
        latest = float(series.iloc[-1])
        z = (latest - mean) / std
        return max(-1.0, min(1.0, z))
    except Exception as exc:
        logger.warning("_institutional_signal failed: %s", exc)
        return 0.0


def _macro_score(news_df: pd.DataFrame) -> int:
    """
    Count news entries in the last 24h containing at least one macro keyword.

    Searches headline and summary columns (case-insensitive).
    Returns 0 if news_df is empty or has no text columns.
    """
    if news_df.empty:
        return 0
    count = 0
    text_cols = [c for c in ("headline", "summary", "title") if c in news_df.columns]
    if not text_cols:
        return 0
    for _, row in news_df.iterrows():
        combined = " ".join(str(row[c]) for c in text_cols if pd.notna(row.get(c)))
        if _MACRO_PATTERN.search(combined):
            count += 1
    return count


def _composite(signals: dict) -> float:
    """
    Weighted sum of four signals, clamped to [-1.0, 1.0].

    macro_score is normalised:
      normalised_macro = min(macro_score / 5.0, 1.0)
      macro_normalised  = normalised_macro * 2 - 1   → maps [0,1] to [-1,1]

    weighted_sum = 0.30 * index_momentum
                 + 0.25 * sector_perf
                 + 0.30 * institutional_signal
                 + 0.15 * macro_normalised
    """
    raw_macro = signals.get("macro_score", 0)
    normalised_macro_01 = min(raw_macro / 5.0, 1.0)
    macro_normalised = normalised_macro_01 * 2.0 - 1.0  # [-1, 1]

    weighted_sum = (
        _WEIGHTS["index_momentum"]       * signals.get("index_momentum", 0.0)
        + _WEIGHTS["sector_perf"]        * signals.get("sector_perf", 0.0)
        + _WEIGHTS["institutional_signal"] * signals.get("institutional_signal", 0.0)
        + _WEIGHTS["macro_score"]        * macro_normalised
    )
    return max(-1.0, min(1.0, weighted_sum))


def _classify(score: float) -> str:
    """
    Classify composite score:
      score < -0.3  → "Bearish"
      -0.3 ≤ score ≤ 0.3 → "Neutral"
      score > 0.3   → "Bullish"
    """
    if score < -0.3:
        return "Bearish"
    if score > 0.3:
        return "Bullish"
    return "Neutral"
