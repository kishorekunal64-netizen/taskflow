"""
FinIntelligence Market Analysis System — Event Detector.

Monitors computed metrics against configured thresholds and returns a
TriggerEvent when a significant market event is detected.

Idempotency guard: a (window_key, trigger_type) tuple is stored in a
module-level set; duplicate triggers within the same 15-minute window
are suppressed (return None).

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from finintelligence.config import EVENT_THRESHOLDS
from finintelligence.logger import get_logger
from finintelligence.models import SentimentResult, TriggerEvent

logger = get_logger("finintelligence.event_detector")

# ---------------------------------------------------------------------------
# Idempotency guard — module-level set of (window_key, trigger_type) tuples
# ---------------------------------------------------------------------------

_triggered_set: set[tuple[str, str]] = set()

# ---------------------------------------------------------------------------
# Threshold constants (sourced from config)
# ---------------------------------------------------------------------------

_INDEX_PCT_THRESHOLD: float = EVENT_THRESHOLDS["index_pct"]      # 1.0
_SECTOR_PCT_THRESHOLD: float = EVENT_THRESHOLDS["sector_pct"]    # 2.0
_FII_STD_THRESHOLD: float = EVENT_THRESHOLDS["fii_std_dev"]      # 2.0
_MACRO_SCORE_THRESHOLD: int = int(EVENT_THRESHOLDS["macro_score"])  # 3

# Index symbols that trigger the index_move check
_INDEX_SYMBOLS = {"^NSEI", "^NSEBANK"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_and_trigger(
    features: dict,
    sentiment: SentimentResult,
    sector_metrics: pd.DataFrame,
    flows_df: pd.DataFrame,
) -> TriggerEvent | None:
    """
    Evaluate all four threshold conditions in order and return the first
    TriggerEvent that fires and has not already been recorded in the current
    15-minute window.

    Parameters
    ----------
    features:
        Dict keyed by symbol → feature dict from feature_generator.
        Each feature dict must contain at least 'pct_change_1d'.
    sentiment:
        SentimentResult from the sentiment engine.
    sector_metrics:
        DataFrame with sector feature dicts; must contain 'pct_change_1d'
        and 'symbol' columns (or be a dict-of-dicts keyed by symbol).
    flows_df:
        DataFrame with 'fii_net' column, one row per trading date.

    Returns
    -------
    TriggerEvent if a new (non-duplicate) threshold is breached, else None.
    """
    now = datetime.now(tz=timezone.utc)
    window_key = f"{now.strftime('%Y-%m-%d %H')}:{(now.minute // 15) * 15:02d}"

    # Evaluate conditions in priority order
    checks = [
        ("index_move",  lambda: _check_index_move(features),         _INDEX_PCT_THRESHOLD),
        ("sector_move", lambda: _check_sector_move(sector_metrics),   _SECTOR_PCT_THRESHOLD),
        ("fii_spike",   lambda: _check_fii_spike(flows_df),           _FII_STD_THRESHOLD),
        ("macro_event", lambda: _check_macro_score(sentiment),        float(_MACRO_SCORE_THRESHOLD)),
    ]

    for trigger_type, check_fn, threshold_value in checks:
        try:
            triggered, triggering_value = check_fn()
        except Exception as exc:
            logger.warning("check_and_trigger: error in %s check — %s", trigger_type, exc)
            continue

        if not triggered:
            continue

        if _is_duplicate(window_key, trigger_type):
            logger.debug(
                "Duplicate trigger suppressed: type=%s window=%s",
                trigger_type, window_key,
            )
            continue

        # Record and return
        _triggered_set.add((window_key, trigger_type))
        event = TriggerEvent(
            timestamp=now,
            trigger_type=trigger_type,
            triggering_value=triggering_value,
            threshold_value=threshold_value,
        )
        logger.info(
            "TriggerEvent: type=%s triggering_value=%.4f threshold=%.4f timestamp=%s",
            trigger_type,
            triggering_value,
            threshold_value,
            now.isoformat(),
        )
        return event

    return None


# ---------------------------------------------------------------------------
# Individual threshold checks — each returns (triggered: bool, value: float)
# ---------------------------------------------------------------------------

def _check_index_move(features: dict) -> tuple[bool, float]:
    """
    Returns (True, abs_pct_change) if any index symbol (^NSEI or ^NSEBANK)
    has abs(pct_change_1d) > 1.0%.

    `features` is a dict keyed by symbol → feature dict.
    Falls back gracefully if a symbol is missing or pct_change_1d is None.
    """
    best_value = 0.0
    for symbol in _INDEX_SYMBOLS:
        feat = features.get(symbol)
        if feat is None:
            continue
        pct = feat.get("pct_change_1d")
        if pct is None:
            continue
        try:
            abs_pct = abs(float(pct))
        except (TypeError, ValueError):
            continue
        if abs_pct > best_value:
            best_value = abs_pct
        if abs_pct > _INDEX_PCT_THRESHOLD:
            return True, abs_pct
    return False, best_value


def _check_sector_move(sector_metrics: pd.DataFrame) -> tuple[bool, float]:
    """
    Returns (True, abs_pct_change) if any sector has abs(pct_change_1d) > 2.0%.

    `sector_metrics` is expected to be a DataFrame with a 'pct_change_1d' column.
    Also accepts a dict keyed by symbol → feature dict (same shape as `features`).
    """
    best_value = 0.0

    # Support both DataFrame and dict-of-dicts
    if isinstance(sector_metrics, pd.DataFrame):
        if sector_metrics.empty or "pct_change_1d" not in sector_metrics.columns:
            return False, 0.0
        for val in sector_metrics["pct_change_1d"].dropna():
            try:
                abs_pct = abs(float(val))
            except (TypeError, ValueError):
                continue
            if abs_pct > best_value:
                best_value = abs_pct
            if abs_pct > _SECTOR_PCT_THRESHOLD:
                return True, abs_pct
    elif isinstance(sector_metrics, dict):
        for sym, feat in sector_metrics.items():
            if not isinstance(feat, dict):
                continue
            pct = feat.get("pct_change_1d")
            if pct is None:
                continue
            try:
                abs_pct = abs(float(pct))
            except (TypeError, ValueError):
                continue
            if abs_pct > best_value:
                best_value = abs_pct
            if abs_pct > _SECTOR_PCT_THRESHOLD:
                return True, abs_pct

    return False, best_value


def _check_fii_spike(flows_df: pd.DataFrame) -> tuple[bool, float]:
    """
    Returns (True, abs_fii_net) if the most recent FII net flow exceeds
    mean + 2 * std over the 20-day rolling window.

    Condition: abs(fii_net[-1]) > mean + 2 * std
    Returns (False, 0.0) on insufficient data (< 2 rows) or zero std.
    """
    if flows_df is None or flows_df.empty or "fii_net" not in flows_df.columns:
        return False, 0.0

    series = flows_df["fii_net"].dropna()
    if len(series) < 2:
        return False, 0.0

    window = min(20, len(series))
    tail = series.iloc[-window:]
    mean = float(tail.mean())
    std = float(tail.std(ddof=1))

    if std == 0.0 or pd.isna(std):
        return False, 0.0

    latest = float(series.iloc[-1])
    abs_latest = abs(latest)
    threshold_val = mean + _FII_STD_THRESHOLD * std

    if abs_latest > threshold_val:
        return True, abs_latest
    return False, abs_latest


def _check_macro_score(sentiment: SentimentResult) -> tuple[bool, float]:
    """
    Returns (True, macro_score) if sentiment.macro_score >= 3.
    """
    score = sentiment.macro_score
    if score >= _MACRO_SCORE_THRESHOLD:
        return True, float(score)
    return False, float(score)


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _is_duplicate(window_key: str, trigger_type: str) -> bool:
    """Return True if (window_key, trigger_type) has already been triggered."""
    return (window_key, trigger_type) in _triggered_set


def _reset_triggered_set() -> None:
    """Clear the idempotency guard. Intended for testing only."""
    _triggered_set.clear()
