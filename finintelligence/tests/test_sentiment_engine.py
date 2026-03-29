"""
Tests for finintelligence/sentiment_engine.py

Covers:
  - Property 5: Sentiment Score Bounds (PBT) — composite always in [-1.0, 1.0]
  - Property 6: Sentiment Classification Correctness (PBT)
  - Unit tests: known FII values → expected signal, macro keyword counting,
    _classify boundary values (-0.3, 0.0, 0.3)
"""

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintelligence.sentiment_engine import (
    _classify,
    _composite,
    _institutional_signal,
    _macro_score,
)


# ---------------------------------------------------------------------------
# Property 5: Sentiment Score Bounds
# Feature: finintelligence-market-analysis, Property 5: Sentiment Score Bounds
# Validates: Requirements 6.5
# ---------------------------------------------------------------------------

@given(
    index_momentum=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
    sector_perf=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
    institutional_signal=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
    macro_score=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=100)
def test_property5_composite_score_always_in_bounds(
    index_momentum, sector_perf, institutional_signal, macro_score
):
    # Feature: finintelligence-market-analysis, Property 5: Sentiment Score Bounds
    # Validates: Requirements 6.5
    signals = {
        "index_momentum":       index_momentum,
        "sector_perf":          sector_perf,
        "institutional_signal": institutional_signal,
        "macro_score":          macro_score,
    }
    score = _composite(signals)
    assert -1.0 <= score <= 1.0, (
        f"Composite score {score} out of bounds for signals {signals}"
    )


# ---------------------------------------------------------------------------
# Property 6: Sentiment Classification Correctness
# Feature: finintelligence-market-analysis, Property 6: Sentiment Classification Correctness
# Validates: Requirements 6.6
# ---------------------------------------------------------------------------

@given(score=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=100)
def test_property6_classification_correctness(score):
    # Feature: finintelligence-market-analysis, Property 6: Sentiment Classification Correctness
    # Validates: Requirements 6.6
    classification = _classify(score)

    assert classification in {"Bearish", "Neutral", "Bullish"}, (
        f"Invalid classification '{classification}' for score {score}"
    )

    if score < -0.3:
        assert classification == "Bearish", (
            f"Expected Bearish for score {score}, got {classification}"
        )
    elif score > 0.3:
        assert classification == "Bullish", (
            f"Expected Bullish for score {score}, got {classification}"
        )
    else:
        assert classification == "Neutral", (
            f"Expected Neutral for score {score}, got {classification}"
        )


# ---------------------------------------------------------------------------
# Unit tests: _institutional_signal
# ---------------------------------------------------------------------------

class TestInstitutionalSignal:

    def _make_flows(self, fii_net_values: list[float]) -> pd.DataFrame:
        return pd.DataFrame({"fii_net": fii_net_values})

    def test_empty_df_returns_zero(self):
        assert _institutional_signal(pd.DataFrame()) == 0.0

    def test_missing_fii_net_column_returns_zero(self):
        df = pd.DataFrame({"dii_net": [100.0, 200.0]})
        assert _institutional_signal(df) == 0.0

    def test_single_row_returns_zero(self):
        # Need at least 2 rows to compute std
        df = self._make_flows([500.0])
        assert _institutional_signal(df) == 0.0

    def test_constant_series_returns_zero(self):
        # std = 0 → return 0.0
        df = self._make_flows([100.0] * 20)
        assert _institutional_signal(df) == 0.0

    def test_known_values_positive_z_score(self):
        # mean=100, std=10, latest=120 → z=2.0 → clamped to 1.0
        values = [100.0] * 19 + [120.0]
        df = self._make_flows(values)
        result = _institutional_signal(df)
        # z = (120 - ~100) / ~0 ... let's use a controlled example
        # mean of [100]*19 + [120] = (19*100 + 120)/20 = 2020/20 = 101
        # std (ddof=1) ≈ sqrt(sum((xi-101)^2)/19) = sqrt((19*1 + 361)/19) = sqrt(380/19) ≈ 4.47
        # z = (120 - 101) / 4.47 ≈ 4.25 → clamped to 1.0
        assert result == pytest.approx(1.0)

    def test_known_values_negative_z_score(self):
        # Symmetric: latest is very low → z < -1 → clamped to -1.0
        values = [100.0] * 19 + [80.0]
        df = self._make_flows(values)
        result = _institutional_signal(df)
        # z = (80 - mean) / std → large negative → clamped to -1.0
        assert result == pytest.approx(-1.0)

    def test_result_clamped_to_minus_one(self):
        # Extreme negative outlier
        df = self._make_flows([0.0] * 19 + [-1_000_000.0])
        result = _institutional_signal(df)
        assert result == -1.0

    def test_result_clamped_to_plus_one(self):
        # Extreme positive outlier
        df = self._make_flows([0.0] * 19 + [1_000_000.0])
        result = _institutional_signal(df)
        assert result == 1.0

    def test_moderate_z_score_not_clamped(self):
        # Construct data where z ≈ 0.5 (within [-1, 1])
        # mean=0, std=2, latest=1 → z=0.5
        values = [-2.0, 2.0, -2.0, 2.0, 1.0]
        df = self._make_flows(values)
        result = _institutional_signal(df)
        assert -1.0 <= result <= 1.0

    def test_uses_last_20_rows_window(self):
        # Provide 25 rows; only last 20 should be used for mean/std
        # First 5 rows are extreme outliers that should be ignored
        values = [1_000_000.0] * 5 + [100.0] * 19 + [120.0]
        df = self._make_flows(values)
        result = _institutional_signal(df)
        # With window=20: last 20 = [100]*19 + [120] → z ≈ 4.25 → clamped to 1.0
        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Unit tests: _macro_score
# ---------------------------------------------------------------------------

class TestMacroScore:

    def _make_news(self, headlines: list[str]) -> pd.DataFrame:
        return pd.DataFrame({"headline": headlines})

    def test_empty_df_returns_zero(self):
        assert _macro_score(pd.DataFrame()) == 0

    def test_no_text_columns_returns_zero(self):
        df = pd.DataFrame({"published": ["2024-01-01"]})
        assert _macro_score(df) == 0

    def test_no_matching_keywords_returns_zero(self):
        df = self._make_news(["Stock market rally", "Tech earnings beat estimates"])
        assert _macro_score(df) == 0

    def test_rbi_keyword_matches(self):
        df = self._make_news(["RBI holds repo rate steady"])
        assert _macro_score(df) == 1

    def test_repo_rate_keyword_matches(self):
        df = self._make_news(["repo rate cut expected next quarter"])
        assert _macro_score(df) == 1

    def test_monetary_policy_keyword_matches(self):
        df = self._make_news(["Monetary policy committee meets today"])
        assert _macro_score(df) == 1

    def test_union_budget_keyword_matches(self):
        df = self._make_news(["Union Budget 2024 highlights"])
        assert _macro_score(df) == 1

    def test_fiscal_deficit_keyword_matches(self):
        df = self._make_news(["fiscal deficit widens to 5.8% of GDP"])
        assert _macro_score(df) == 1

    def test_us_fed_keyword_matches(self):
        df = self._make_news(["US Fed signals rate pause"])
        assert _macro_score(df) == 1

    def test_federal_reserve_keyword_matches(self):
        df = self._make_news(["Federal Reserve minutes released"])
        assert _macro_score(df) == 1

    def test_interest_rate_keyword_matches(self):
        df = self._make_news(["interest rate hike fears grip markets"])
        assert _macro_score(df) == 1

    def test_inflation_keyword_matches(self):
        df = self._make_news(["inflation rises to 6.2% in December"])
        assert _macro_score(df) == 1

    def test_cpi_keyword_matches(self):
        df = self._make_news(["CPI data released today"])
        assert _macro_score(df) == 1

    def test_wpi_keyword_matches(self):
        df = self._make_news(["WPI inflation eases to 2.1%"])
        assert _macro_score(df) == 1

    def test_geopolitical_keyword_matches(self):
        df = self._make_news(["geopolitical tensions weigh on markets"])
        assert _macro_score(df) == 1

    def test_war_keyword_matches(self):
        df = self._make_news(["war in Eastern Europe escalates"])
        assert _macro_score(df) == 1

    def test_sanctions_keyword_matches(self):
        df = self._make_news(["new sanctions imposed on Russia"])
        assert _macro_score(df) == 1

    def test_conflict_keyword_matches(self):
        df = self._make_news(["Middle East conflict impacts oil prices"])
        assert _macro_score(df) == 1

    def test_case_insensitive_matching(self):
        df = self._make_news(["rbi REPO RATE monetary POLICY"])
        # All in one headline → counts as 1 entry
        assert _macro_score(df) == 1

    def test_multiple_matching_headlines_counted_separately(self):
        df = self._make_news([
            "RBI holds rates",
            "inflation data released",
            "no macro news here",
            "Federal Reserve meeting",
        ])
        assert _macro_score(df) == 3

    def test_one_headline_with_multiple_keywords_counts_once(self):
        # A single headline matching multiple keywords still counts as 1
        df = self._make_news(["RBI inflation CPI repo rate Federal Reserve"])
        assert _macro_score(df) == 1

    def test_summary_column_also_searched(self):
        df = pd.DataFrame({
            "headline": ["Market update"],
            "summary":  ["RBI announces repo rate cut"],
        })
        assert _macro_score(df) == 1

    def test_headline_and_summary_combined_per_row(self):
        # headline has no keyword, summary has keyword → row counts
        df = pd.DataFrame({
            "headline": ["Stocks rise"],
            "summary":  ["inflation concerns persist"],
        })
        assert _macro_score(df) == 1


# ---------------------------------------------------------------------------
# Unit tests: _classify boundary values
# ---------------------------------------------------------------------------

class TestClassify:

    def test_exactly_minus_0_3_is_neutral(self):
        assert _classify(-0.3) == "Neutral"

    def test_just_below_minus_0_3_is_bearish(self):
        assert _classify(-0.30001) == "Bearish"

    def test_zero_is_neutral(self):
        assert _classify(0.0) == "Neutral"

    def test_exactly_0_3_is_neutral(self):
        assert _classify(0.3) == "Neutral"

    def test_just_above_0_3_is_bullish(self):
        assert _classify(0.30001) == "Bullish"

    def test_minus_1_is_bearish(self):
        assert _classify(-1.0) == "Bearish"

    def test_plus_1_is_bullish(self):
        assert _classify(1.0) == "Bullish"

    def test_minus_0_5_is_bearish(self):
        assert _classify(-0.5) == "Bearish"

    def test_0_5_is_bullish(self):
        assert _classify(0.5) == "Bullish"

    def test_0_1_is_neutral(self):
        assert _classify(0.1) == "Neutral"

    def test_minus_0_1_is_neutral(self):
        assert _classify(-0.1) == "Neutral"


# ---------------------------------------------------------------------------
# Unit tests: _composite formula
# ---------------------------------------------------------------------------

class TestComposite:

    def test_all_zero_signals_gives_negative_composite(self):
        # macro_score=0 → normalised_macro = 0*2-1 = -1.0
        # weighted_sum = 0 + 0 + 0 + 0.15 * (-1.0) = -0.15
        signals = {"index_momentum": 0.0, "sector_perf": 0.0,
                   "institutional_signal": 0.0, "macro_score": 0}
        result = _composite(signals)
        assert result == pytest.approx(-0.15, abs=1e-9)

    def test_all_max_signals_gives_plus_one(self):
        # index_momentum=1, sector_perf=1, institutional=1, macro_score=5+
        # macro_normalised = min(5/5,1)*2-1 = 1.0
        # weighted_sum = 0.30+0.25+0.30+0.15 = 1.0 → clamped to 1.0
        signals = {"index_momentum": 1.0, "sector_perf": 1.0,
                   "institutional_signal": 1.0, "macro_score": 5}
        result = _composite(signals)
        assert result == pytest.approx(1.0)

    def test_all_min_signals_gives_minus_one(self):
        # index_momentum=-1, sector_perf=-1, institutional=-1, macro_score=0
        # macro_normalised = -1.0
        # weighted_sum = -0.30-0.25-0.30-0.15 = -1.0 → clamped to -1.0
        signals = {"index_momentum": -1.0, "sector_perf": -1.0,
                   "institutional_signal": -1.0, "macro_score": 0}
        result = _composite(signals)
        assert result == pytest.approx(-1.0)

    def test_macro_score_5_normalises_to_1(self):
        # macro_score=5 → normalised_macro_01=1.0 → macro_normalised=1.0
        signals = {"index_momentum": 0.0, "sector_perf": 0.0,
                   "institutional_signal": 0.0, "macro_score": 5}
        result = _composite(signals)
        # 0.15 * 1.0 = 0.15
        assert result == pytest.approx(0.15, abs=1e-9)

    def test_macro_score_above_5_capped_at_1(self):
        # macro_score=10 → same as macro_score=5
        s1 = {"index_momentum": 0.0, "sector_perf": 0.0,
              "institutional_signal": 0.0, "macro_score": 5}
        s2 = {"index_momentum": 0.0, "sector_perf": 0.0,
              "institutional_signal": 0.0, "macro_score": 10}
        assert _composite(s1) == pytest.approx(_composite(s2))

    def test_extreme_inputs_clamped(self):
        # Inputs outside [-1,1] should still produce clamped output
        signals = {"index_momentum": 100.0, "sector_perf": 100.0,
                   "institutional_signal": 100.0, "macro_score": 999}
        result = _composite(signals)
        assert result == pytest.approx(1.0)

    def test_result_always_in_bounds(self):
        for idx in [-1.0, 0.0, 1.0]:
            for sec in [-1.0, 0.0, 1.0]:
                for inst in [-1.0, 0.0, 1.0]:
                    for macro in [0, 3, 5, 10]:
                        signals = {"index_momentum": idx, "sector_perf": sec,
                                   "institutional_signal": inst, "macro_score": macro}
                        result = _composite(signals)
                        assert -1.0 <= result <= 1.0
