"""
FinIntelligence Market Analysis System — AI Analysis Engine.

Rule-based engine that synthesises market structure, institutional flows,
and sentiment into an OutlookSignal. All logic is deterministic and local;
no external LLM dependency, no network calls.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from finintelligence import cache_manager
from finintelligence.logger import get_logger
from finintelligence.models import OutlookSignal, SentimentResult

logger = get_logger("finintelligence.ai_analysis_engine")

# Symbols used for market structure analysis
_STRUCTURE_SYMBOLS = ["^NSEI", "^NSEBANK"]
_STRUCTURE_TIMEFRAMES = ["1D", "4H"]

# Voting weights
_WEIGHT_STRUCTURE = 0.40
_WEIGHT_SENTIMENT = 0.35
_WEIGHT_FII = 0.25


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_signal(
    candles: dict,
    sector_metrics: pd.DataFrame,
    sentiment: SentimentResult,
    flows_df: pd.DataFrame,
) -> Optional[OutlookSignal]:
    """
    Synthesise an OutlookSignal from market structure, sentiment, and flows.

    On missing/malformed input → log input summary + error, return None.
    Stores signal via cache_manager.write_signal on success.
    Must complete within 30 seconds (all in-memory, no network calls).
    """
    # --- Input validation ---
    try:
        _validate_inputs(candles, sector_metrics, sentiment, flows_df)
    except Exception as exc:
        logger.error(
            "generate_signal: invalid input — candles_keys=%s sector_metrics_empty=%s "
            "sentiment=%s flows_empty=%s — error: %s",
            list(candles.keys()) if isinstance(candles, dict) else type(candles).__name__,
            sector_metrics.empty if isinstance(sector_metrics, pd.DataFrame) else "not-df",
            sentiment,
            flows_df.empty if isinstance(flows_df, pd.DataFrame) else "not-df",
            exc,
        )
        return None

    try:
        # 1. Derive market structure
        structure = _market_structure(candles)

        # 2. Weighted direction vote
        direction = _direction_vote(structure, sentiment, flows_df)

        # 3. Confidence from component votes
        struct_score, sent_score, fii_score = _component_scores(structure, sentiment, flows_df)
        confidence = _confidence([struct_score, sent_score, fii_score])

        # 4. Supporting factors
        factors = _supporting_factors(structure, sector_metrics, sentiment)

        # 5. Assemble signal
        signal = OutlookSignal(
            timestamp=datetime.now(tz=timezone.utc),
            direction=direction,
            confidence=confidence,
            supporting_factors=factors,
            rationale="",
        )

        # 6. Rationale (needs the assembled signal)
        signal.rationale = _rationale(signal)

        # 7. Persist
        cache_manager.write_signal(signal)

        logger.info(
            "generate_signal: direction=%s confidence=%.4f factors=%d",
            signal.direction,
            signal.confidence,
            len(signal.supporting_factors),
        )
        return signal

    except Exception as exc:
        logger.error("generate_signal: unexpected error during signal generation: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Market structure
# ---------------------------------------------------------------------------

def _market_structure(candles: dict) -> dict:
    """
    Compute price vs SMA50 and SMA200 for each symbol + timeframe combination.

    candles: {"^NSEI": {"1D": df, "4H": df}, "^NSEBANK": {"1D": df, "4H": df}}

    Returns dict with keys like:
        "^NSEI_1D_sma50"  → "above" | "below"
        "^NSEI_1D_sma200" → "above" | "below"
        "^NSEI_4H_sma50"  → "above" | "below"
        ...
    """
    structure: dict[str, str] = {}

    for symbol, timeframe_data in candles.items():
        if not isinstance(timeframe_data, dict):
            continue
        for timeframe, df in timeframe_data.items():
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                continue

            # Normalise column names
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]

            if "close" not in df.columns:
                continue

            close_series = df["close"].dropna()
            if close_series.empty:
                continue

            latest_close = float(close_series.iloc[-1])

            # SMA50
            if len(close_series) >= 50:
                sma50 = float(close_series.rolling(50).mean().iloc[-1])
                structure[f"{symbol}_{timeframe}_sma50"] = (
                    "above" if latest_close >= sma50 else "below"
                )

            # SMA200
            if len(close_series) >= 200:
                sma200 = float(close_series.rolling(200).mean().iloc[-1])
                structure[f"{symbol}_{timeframe}_sma200"] = (
                    "above" if latest_close >= sma200 else "below"
                )

    return structure


# ---------------------------------------------------------------------------
# Direction vote
# ---------------------------------------------------------------------------

def _direction_vote(
    structure: dict,
    sentiment: SentimentResult,
    flows_df: pd.DataFrame,
) -> str:
    """
    Weighted majority vote across three components:
      - Structure (40%): count "above" vs "below" across all structure keys
      - Sentiment (35%): "Bullish" → +1, "Bearish" → -1, "Neutral" → 0
      - FII (25%): fii_net[-1] > 0 → +0.25, < 0 → -0.25, == 0 → 0

    Returns "Bullish", "Bearish", or "Neutral".
    """
    struct_score, sent_score, fii_score = _component_scores(structure, sentiment, flows_df)
    total = struct_score + sent_score + fii_score

    if total > 0:
        return "Bullish"
    if total < 0:
        return "Bearish"
    return "Neutral"


def _component_scores(
    structure: dict,
    sentiment: SentimentResult,
    flows_df: pd.DataFrame,
) -> tuple[float, float, float]:
    """
    Compute the three weighted component scores used for both direction and confidence.

    Returns (struct_score, sent_score, fii_score).
    """
    # --- Structure vote (40%) ---
    above_count = sum(1 for v in structure.values() if v == "above")
    below_count = sum(1 for v in structure.values() if v == "below")
    total_struct = above_count + below_count

    if total_struct > 0:
        struct_raw = (above_count - below_count) / total_struct  # in [-1, 1]
    else:
        struct_raw = 0.0
    struct_score = struct_raw * _WEIGHT_STRUCTURE

    # --- Sentiment vote (35%) ---
    classification = sentiment.classification if sentiment else "Neutral"
    if classification == "Bullish":
        sent_raw = 1.0
    elif classification == "Bearish":
        sent_raw = -1.0
    else:
        sent_raw = 0.0
    sent_score = sent_raw * _WEIGHT_SENTIMENT

    # --- FII vote (25%) ---
    fii_score = 0.0
    if flows_df is not None and not flows_df.empty and "fii_net" in flows_df.columns:
        fii_series = flows_df["fii_net"].dropna()
        if not fii_series.empty:
            latest_fii = float(fii_series.iloc[-1])
            if latest_fii > 0:
                fii_score = _WEIGHT_FII
            elif latest_fii < 0:
                fii_score = -_WEIGHT_FII
            # == 0 → 0.0

    return struct_score, sent_score, fii_score


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def _confidence(votes: list[float]) -> float:
    """
    Normalised weighted agreement score in [0.0, 1.0].

    confidence = abs(sum(votes)) / sum(abs(v) for v in votes)
    Returns 0.5 if all votes are zero.
    Clamped to [0.0, 1.0].
    """
    total_abs = sum(abs(v) for v in votes)
    if total_abs == 0.0:
        return 0.5

    raw = abs(sum(votes)) / total_abs
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Supporting factors
# ---------------------------------------------------------------------------

def _supporting_factors(
    structure: dict,
    sector_metrics: pd.DataFrame,
    sentiment: SentimentResult,
) -> list[str]:
    """
    Build a list of human-readable supporting factor strings.

    Always includes:
    - Rank-1 sector symbol (highest relative_strength)
    - Rank-5 sector symbol (lowest relative_strength)
    - SMA position summary for NIFTY on 1D
    - Sentiment classification with composite score
    """
    factors: list[str] = []

    # --- Sector rank factors ---
    if sector_metrics is not None and not sector_metrics.empty and "rank" in sector_metrics.columns:
        rank_col = sector_metrics["rank"]
        # Rank 1 = strongest
        top_rows = sector_metrics[rank_col == rank_col.min()]
        bottom_rows = sector_metrics[rank_col == rank_col.max()]

        if not top_rows.empty:
            top_sym = str(top_rows.iloc[0]["symbol"])
            top_rs = float(top_rows.iloc[0].get("relative_strength", 0.0))
            factors.append(
                f"Top sector: {top_sym} (relative strength: {top_rs:.2f})"
            )

        if not bottom_rows.empty:
            bot_sym = str(bottom_rows.iloc[0]["symbol"])
            bot_rs = float(bottom_rows.iloc[0].get("relative_strength", 0.0))
            factors.append(
                f"Bottom sector: {bot_sym} (relative strength: {bot_rs:.2f})"
            )
    else:
        factors.append("Sector ranking unavailable")

    # --- SMA position summary ---
    nifty_1d_sma200 = structure.get("^NSEI_1D_sma200")
    nifty_1d_sma50 = structure.get("^NSEI_1D_sma50")

    if nifty_1d_sma200:
        factors.append(f"NIFTY {nifty_1d_sma200} SMA200 on 1D")
    if nifty_1d_sma50:
        factors.append(f"NIFTY {nifty_1d_sma50} SMA50 on 1D")

    # If no NIFTY structure available, summarise what we have
    if not nifty_1d_sma200 and not nifty_1d_sma50:
        above = [k for k, v in structure.items() if v == "above"]
        below = [k for k, v in structure.items() if v == "below"]
        factors.append(
            f"Market structure: {len(above)} above SMA, {len(below)} below SMA"
        )

    # --- Sentiment classification ---
    if sentiment is not None:
        factors.append(
            f"Sentiment: {sentiment.classification} (score: {sentiment.composite_score:.2f})"
        )
    else:
        factors.append("Sentiment: unavailable")

    return factors


# ---------------------------------------------------------------------------
# Rationale
# ---------------------------------------------------------------------------

def _rationale(signal: OutlookSignal) -> str:
    """
    Plain-language summary assembled from supporting_factors.
    Returns a non-empty string.
    """
    if not signal.supporting_factors:
        return (
            f"Market outlook is {signal.direction} with "
            f"{signal.confidence:.0%} confidence."
        )

    factors_text = "; ".join(signal.supporting_factors)
    return (
        f"Market outlook is {signal.direction} with "
        f"{signal.confidence:.0%} confidence. "
        f"Key factors: {factors_text}."
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_inputs(
    candles: dict,
    sector_metrics: pd.DataFrame,
    sentiment: SentimentResult,
    flows_df: pd.DataFrame,
) -> None:
    """
    Raise ValueError if any required input is missing or malformed.
    """
    if not isinstance(candles, dict) or not candles:
        raise ValueError(f"candles must be a non-empty dict, got: {type(candles).__name__}")

    if not isinstance(sector_metrics, pd.DataFrame):
        raise ValueError(
            f"sector_metrics must be a pd.DataFrame, got: {type(sector_metrics).__name__}"
        )

    if sentiment is None:
        raise ValueError("sentiment must not be None")

    if not isinstance(flows_df, pd.DataFrame):
        raise ValueError(
            f"flows_df must be a pd.DataFrame, got: {type(flows_df).__name__}"
        )
