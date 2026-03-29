"""
Tests for finintelligence/ai_analysis_engine.py

Covers:
  - Property 9: OutlookSignal Completeness (PBT)
  - Property 10: Top/Bottom Sector in Supporting Factors (PBT)
  - Unit tests: known candle data above SMA → Bullish structure,
    conflicting signals → correct weighted majority, missing input → None
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintelligence.ai_analysis_engine import (
    _confidence,
    _direction_vote,
    _market_structure,
    _rationale,
    _supporting_factors,
    generate_signal,
)
from finintelligence.config import SECTOR_SYMBOLS
from finintelligence.models import OutlookSignal, SentimentResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sentiment(classification: str = "Neutral", score: float = 0.0) -> SentimentResult:
    return SentimentResult(
        timestamp=datetime.now(tz=timezone.utc),
        index_momentum=0.0,
        sector_perf=0.0,
        institutional_signal=0.0,
        macro_score=0,
        composite_score=score,
        classification=classification,
    )


def _make_candle_df(n: int, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    """Create a simple rising candle DataFrame with `n` rows."""
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({"close": closes})


def _make_flows(fii_net: float) -> pd.DataFrame:
    return pd.DataFrame({"fii_net": [fii_net]})


def _make_sector_metrics(symbols: list[str] | None = None) -> pd.DataFrame:
    """Build a sector_metrics DataFrame with the given symbol order (rank by position)."""
    if symbols is None:
        symbols = SECTOR_SYMBOLS
    rows = []
    for i, sym in enumerate(symbols):
        rows.append({
            "symbol": sym,
            "date": datetime.now(tz=timezone.utc),
            "return_20d": 0.01 * (len(symbols) - i),
            "relative_strength": float(len(symbols) - i),
            "adx": 20.0,
            "rank": i + 1,
        })
    return pd.DataFrame(rows)


def _make_candles_dict(n: int = 250) -> dict:
    """Build a minimal candles dict for ^NSEI and ^NSEBANK on 1D and 4H."""
    df = _make_candle_df(n)
    return {
        "^NSEI": {"1D": df.copy(), "4H": df.copy()},
        "^NSEBANK": {"1D": df.copy(), "4H": df.copy()},
    }


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_VALID_CLASSIFICATIONS = st.sampled_from(["Bullish", "Bearish", "Neutral"])


@st.composite
def sentiment_strategy(draw):
    classification = draw(_VALID_CLASSIFICATIONS)
    score = draw(st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    return _make_sentiment(classification, score)


@st.composite
def flows_strategy(draw):
    fii_net = draw(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
    return _make_flows(fii_net)


@st.composite
def candles_strategy(draw):
    """Generate a valid candles dict with enough data for SMA50 and SMA200."""
    n = draw(st.integers(min_value=200, max_value=300))
    return _make_candles_dict(n)


@st.composite
def sector_metrics_strategy(draw):
    """Generate a valid sector_metrics DataFrame with all 5 sectors ranked."""
    # Permute the sector symbols to vary rankings
    perm = draw(st.permutations(SECTOR_SYMBOLS))
    return _make_sector_metrics(list(perm))


# ---------------------------------------------------------------------------
# Property 9: OutlookSignal Completeness
# Feature: finintelligence-market-analysis, Property 9: OutlookSignal Completeness
# Validates: Requirements 8.2
# ---------------------------------------------------------------------------

@given(
    candles=candles_strategy(),
    sector_metrics=sector_metrics_strategy(),
    sentiment=sentiment_strategy(),
    flows_df=flows_strategy(),
)
@settings(max_examples=100)
def test_property9_outlook_signal_completeness(candles, sector_metrics, sentiment, flows_df):
    # Feature: finintelligence-market-analysis, Property 9: OutlookSignal Completeness
    # Validates: Requirements 8.2
    with patch("finintelligence.ai_analysis_engine.cache_manager") as mock_cm:
        mock_cm.write_signal.return_value = None
        signal = generate_signal(candles, sector_metrics, sentiment, flows_df)

    assert signal is not None, "generate_signal returned None for valid inputs"

    assert signal.direction in {"Bullish", "Bearish", "Neutral"}, (
        f"direction '{signal.direction}' not in valid set"
    )
    assert 0.0 <= signal.confidence <= 1.0, (
        f"confidence {signal.confidence} out of [0.0, 1.0]"
    )
    assert isinstance(signal.supporting_factors, list) and len(signal.supporting_factors) > 0, (
        "supporting_factors must be a non-empty list"
    )
    assert isinstance(signal.rationale, str) and len(signal.rationale) > 0, (
        "rationale must be a non-empty string"
    )


# ---------------------------------------------------------------------------
# Property 10: Top and Bottom Sector in Supporting Factors
# Feature: finintelligence-market-analysis, Property 10: Top and Bottom Sector in Supporting Factors
# Validates: Requirements 8.5
# ---------------------------------------------------------------------------

@given(perm=st.permutations(SECTOR_SYMBOLS))
@settings(max_examples=100)
def test_property10_top_bottom_sector_in_supporting_factors(perm):
    # Feature: finintelligence-market-analysis, Property 10: Top and Bottom Sector in Supporting Factors
    # Validates: Requirements 8.5
    sector_metrics = _make_sector_metrics(list(perm))
    structure = {}
    sentiment = _make_sentiment("Neutral", 0.0)

    factors = _supporting_factors(structure, sector_metrics, sentiment)

    # Rank 1 = first in perm (highest relative_strength)
    top_symbol = perm[0]
    # Rank 5 = last in perm (lowest relative_strength)
    bottom_symbol = perm[-1]

    factors_text = " ".join(factors)
    assert top_symbol in factors_text, (
        f"Rank-1 sector '{top_symbol}' not found in supporting_factors: {factors}"
    )
    assert bottom_symbol in factors_text, (
        f"Rank-5 sector '{bottom_symbol}' not found in supporting_factors: {factors}"
    )


# ---------------------------------------------------------------------------
# Unit tests: _market_structure
# ---------------------------------------------------------------------------

class TestMarketStructure:

    def test_price_above_sma50_and_sma200(self):
        # 250 rising candles: latest close is well above both SMAs
        df = _make_candle_df(250, start=100.0, step=1.0)
        candles = {"^NSEI": {"1D": df}}
        structure = _market_structure(candles)

        assert structure.get("^NSEI_1D_sma50") == "above"
        assert structure.get("^NSEI_1D_sma200") == "above"

    def test_price_below_sma50_and_sma200(self):
        # 250 falling candles: latest close is well below both SMAs
        df = _make_candle_df(250, start=350.0, step=-1.0)
        candles = {"^NSEI": {"1D": df}}
        structure = _market_structure(candles)

        assert structure.get("^NSEI_1D_sma50") == "below"
        assert structure.get("^NSEI_1D_sma200") == "below"

    def test_insufficient_data_for_sma200(self):
        # Only 100 candles: SMA50 computed, SMA200 not
        df = _make_candle_df(100)
        candles = {"^NSEI": {"1D": df}}
        structure = _market_structure(candles)

        assert "^NSEI_1D_sma50" in structure
        assert "^NSEI_1D_sma200" not in structure

    def test_empty_df_produces_no_keys(self):
        candles = {"^NSEI": {"1D": pd.DataFrame()}}
        structure = _market_structure(candles)
        assert "^NSEI_1D_sma50" not in structure
        assert "^NSEI_1D_sma200" not in structure

    def test_multiple_symbols_and_timeframes(self):
        df = _make_candle_df(250)
        candles = {
            "^NSEI": {"1D": df.copy(), "4H": df.copy()},
            "^NSEBANK": {"1D": df.copy(), "4H": df.copy()},
        }
        structure = _market_structure(candles)

        expected_keys = [
            "^NSEI_1D_sma50", "^NSEI_1D_sma200",
            "^NSEI_4H_sma50", "^NSEI_4H_sma200",
            "^NSEBANK_1D_sma50", "^NSEBANK_1D_sma200",
            "^NSEBANK_4H_sma50", "^NSEBANK_4H_sma200",
        ]
        for key in expected_keys:
            assert key in structure, f"Missing key: {key}"

    def test_uppercase_columns_normalised(self):
        df = pd.DataFrame({"Close": [float(i) for i in range(1, 260)]})
        candles = {"^NSEI": {"1D": df}}
        structure = _market_structure(candles)
        assert "^NSEI_1D_sma50" in structure


# ---------------------------------------------------------------------------
# Unit tests: _direction_vote
# ---------------------------------------------------------------------------

class TestDirectionVote:

    def test_all_bullish_signals_returns_bullish(self):
        # All structure keys "above", Bullish sentiment, positive FII
        structure = {
            "^NSEI_1D_sma50": "above", "^NSEI_1D_sma200": "above",
            "^NSEI_4H_sma50": "above", "^NSEI_4H_sma200": "above",
        }
        sentiment = _make_sentiment("Bullish", 0.5)
        flows = _make_flows(1000.0)
        assert _direction_vote(structure, sentiment, flows) == "Bullish"

    def test_all_bearish_signals_returns_bearish(self):
        structure = {
            "^NSEI_1D_sma50": "below", "^NSEI_1D_sma200": "below",
            "^NSEI_4H_sma50": "below", "^NSEI_4H_sma200": "below",
        }
        sentiment = _make_sentiment("Bearish", -0.5)
        flows = _make_flows(-1000.0)
        assert _direction_vote(structure, sentiment, flows) == "Bearish"

    def test_conflicting_signals_weighted_majority(self):
        # Structure: 3 above, 1 below → struct_raw = (3-1)/4 = 0.5 → struct_score = 0.20
        # Sentiment: Bearish → sent_score = -0.35
        # FII: positive → fii_score = +0.25
        # total = 0.20 - 0.35 + 0.25 = 0.10 → Bullish
        structure = {
            "^NSEI_1D_sma50": "above",
            "^NSEI_1D_sma200": "above",
            "^NSEI_4H_sma50": "above",
            "^NSEI_4H_sma200": "below",
        }
        sentiment = _make_sentiment("Bearish", -0.5)
        flows = _make_flows(500.0)
        result = _direction_vote(structure, sentiment, flows)
        assert result == "Bullish"

    def test_empty_structure_neutral_sentiment_zero_fii_returns_neutral(self):
        structure = {}
        sentiment = _make_sentiment("Neutral", 0.0)
        flows = _make_flows(0.0)
        assert _direction_vote(structure, sentiment, flows) == "Neutral"

    def test_bearish_sentiment_dominates_neutral_structure_and_zero_fii(self):
        # struct_score = 0, sent_score = -0.35, fii_score = 0 → total = -0.35 → Bearish
        structure = {}
        sentiment = _make_sentiment("Bearish", -0.5)
        flows = _make_flows(0.0)
        assert _direction_vote(structure, sentiment, flows) == "Bearish"


# ---------------------------------------------------------------------------
# Unit tests: _confidence
# ---------------------------------------------------------------------------

class TestConfidence:

    def test_all_zero_votes_returns_half(self):
        assert _confidence([0.0, 0.0, 0.0]) == 0.5

    def test_all_same_sign_returns_one(self):
        assert _confidence([0.4, 0.35, 0.25]) == pytest.approx(1.0)

    def test_perfectly_opposing_votes_returns_zero(self):
        # sum = 0, total_abs = 0.8 → 0/0.8 = 0.0
        assert _confidence([0.4, -0.4]) == pytest.approx(0.0)

    def test_result_always_in_bounds(self):
        import random
        for _ in range(50):
            votes = [random.uniform(-1.0, 1.0) for _ in range(3)]
            c = _confidence(votes)
            assert 0.0 <= c <= 1.0

    def test_partial_agreement(self):
        # votes = [0.4, 0.35, -0.25] → sum = 0.5, total_abs = 1.0 → 0.5
        result = _confidence([0.4, 0.35, -0.25])
        assert result == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Unit tests: generate_signal — missing/malformed input returns None
# ---------------------------------------------------------------------------

class TestGenerateSignalValidation:

    def _valid_args(self):
        return (
            _make_candles_dict(250),
            _make_sector_metrics(),
            _make_sentiment("Neutral", 0.0),
            _make_flows(0.0),
        )

    def test_none_candles_returns_none(self):
        _, sm, sent, flows = self._valid_args()
        result = generate_signal(None, sm, sent, flows)
        assert result is None

    def test_empty_candles_dict_returns_none(self):
        _, sm, sent, flows = self._valid_args()
        result = generate_signal({}, sm, sent, flows)
        assert result is None

    def test_none_sentiment_returns_none(self):
        candles, sm, _, flows = self._valid_args()
        result = generate_signal(candles, sm, None, flows)
        assert result is None

    def test_non_dataframe_sector_metrics_returns_none(self):
        candles, _, sent, flows = self._valid_args()
        result = generate_signal(candles, "not-a-df", sent, flows)
        assert result is None

    def test_non_dataframe_flows_returns_none(self):
        candles, sm, sent, _ = self._valid_args()
        result = generate_signal(candles, sm, sent, "not-a-df")
        assert result is None

    def test_valid_inputs_returns_signal(self):
        candles, sm, sent, flows = self._valid_args()
        with patch("finintelligence.ai_analysis_engine.cache_manager") as mock_cm:
            mock_cm.write_signal.return_value = None
            result = generate_signal(candles, sm, sent, flows)
        assert result is not None
        assert isinstance(result, OutlookSignal)

    def test_no_exception_raised_on_bad_input(self):
        # Should never raise, only return None
        try:
            result = generate_signal(None, None, None, None)
            assert result is None
        except Exception as exc:
            pytest.fail(f"generate_signal raised an exception: {exc}")

    def test_signal_stored_via_cache_manager(self):
        candles, sm, sent, flows = self._valid_args()
        with patch("finintelligence.ai_analysis_engine.cache_manager") as mock_cm:
            mock_cm.write_signal.return_value = None
            result = generate_signal(candles, sm, sent, flows)
        assert result is not None
        mock_cm.write_signal.assert_called_once()


# ---------------------------------------------------------------------------
# Unit tests: _supporting_factors
# ---------------------------------------------------------------------------

class TestSupportingFactors:

    def test_includes_top_and_bottom_sector(self):
        sector_metrics = _make_sector_metrics(SECTOR_SYMBOLS)
        structure = {}
        sentiment = _make_sentiment("Neutral", 0.0)

        factors = _supporting_factors(structure, sector_metrics, sentiment)
        factors_text = " ".join(factors)

        # Rank 1 = SECTOR_SYMBOLS[0], Rank 5 = SECTOR_SYMBOLS[-1]
        assert SECTOR_SYMBOLS[0] in factors_text
        assert SECTOR_SYMBOLS[-1] in factors_text

    def test_includes_sentiment_classification(self):
        sector_metrics = _make_sector_metrics()
        structure = {}
        sentiment = _make_sentiment("Bullish", 0.5)

        factors = _supporting_factors(structure, sector_metrics, sentiment)
        factors_text = " ".join(factors)

        assert "Bullish" in factors_text

    def test_includes_sma_position_when_available(self):
        sector_metrics = _make_sector_metrics()
        structure = {"^NSEI_1D_sma200": "above", "^NSEI_1D_sma50": "above"}
        sentiment = _make_sentiment("Neutral", 0.0)

        factors = _supporting_factors(structure, sector_metrics, sentiment)
        factors_text = " ".join(factors)

        assert "SMA200" in factors_text
        assert "SMA50" in factors_text

    def test_non_empty_with_empty_sector_metrics(self):
        structure = {}
        sentiment = _make_sentiment("Neutral", 0.0)

        factors = _supporting_factors(structure, pd.DataFrame(), sentiment)
        assert len(factors) > 0

    def test_non_empty_with_empty_structure(self):
        sector_metrics = _make_sector_metrics()
        sentiment = _make_sentiment("Neutral", 0.0)

        factors = _supporting_factors({}, sector_metrics, sentiment)
        assert len(factors) > 0


# ---------------------------------------------------------------------------
# Unit tests: _rationale
# ---------------------------------------------------------------------------

class TestRationale:

    def test_non_empty_string(self):
        signal = OutlookSignal(
            timestamp=datetime.now(tz=timezone.utc),
            direction="Bullish",
            confidence=0.75,
            supporting_factors=["Top sector: ^CNXIT", "Sentiment: Bullish"],
            rationale="",
        )
        result = _rationale(signal)
        assert isinstance(result, str) and len(result) > 0

    def test_contains_direction(self):
        signal = OutlookSignal(
            timestamp=datetime.now(tz=timezone.utc),
            direction="Bearish",
            confidence=0.6,
            supporting_factors=["Some factor"],
            rationale="",
        )
        result = _rationale(signal)
        assert "Bearish" in result

    def test_contains_factors(self):
        signal = OutlookSignal(
            timestamp=datetime.now(tz=timezone.utc),
            direction="Neutral",
            confidence=0.5,
            supporting_factors=["Factor A", "Factor B"],
            rationale="",
        )
        result = _rationale(signal)
        assert "Factor A" in result
        assert "Factor B" in result

    def test_empty_factors_still_non_empty(self):
        signal = OutlookSignal(
            timestamp=datetime.now(tz=timezone.utc),
            direction="Neutral",
            confidence=0.5,
            supporting_factors=[],
            rationale="",
        )
        result = _rationale(signal)
        assert isinstance(result, str) and len(result) > 0
