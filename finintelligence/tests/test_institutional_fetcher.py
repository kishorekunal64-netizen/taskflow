"""
Tests for finintelligence/institutional_fetcher.py

Covers:
  - Property 3: FII/DII Flow Validation (PBT)
  - Unit tests: valid parsing, endpoint failure, deduplication
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from finintelligence.institutional_fetcher import _parse_flow_record, fetch_institutional_flows
from finintelligence.models import InstitutionalFlow


def _valid_raw(fii_buy=100.0, fii_sell=80.0, dii_buy=50.0, dii_sell=40.0, date="2024-01-15"):
    return {"date": date, "fii_buy": fii_buy, "fii_sell": fii_sell,
            "dii_buy": dii_buy, "dii_sell": dii_sell}


# ---------------------------------------------------------------------------
# Property 3: FII/DII Flow Validation
# Feature: finintelligence-market-analysis, Property 3: FII/DII Flow Validation
# Validates: Requirements 3.5
# ---------------------------------------------------------------------------

_negative_float = st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False)
_non_numeric = st.one_of(st.text(min_size=1), st.none())
_invalid_value = st.one_of(_negative_float, _non_numeric)
_valid_positive = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)


@st.composite
def _record_with_invalid_field(draw):
    field = draw(st.sampled_from(["fii_buy", "fii_sell", "dii_buy", "dii_sell"]))
    record = {
        "date": "2024-01-15",
        "fii_buy":  draw(_valid_positive),
        "fii_sell": draw(_valid_positive),
        "dii_buy":  draw(_valid_positive),
        "dii_sell": draw(_valid_positive),
    }
    record[field] = draw(_invalid_value)
    return record


@given(_record_with_invalid_field())
@settings(max_examples=100)
def test_property3_invalid_record_rejected(raw):
    # Feature: finintelligence-market-analysis, Property 3: FII/DII Flow Validation
    # Validates: Requirements 3.5
    result = _parse_flow_record(raw)
    assert result is None, f"Expected None for invalid record {raw}, got {result}"


@given(
    fii_buy=_valid_positive,
    fii_sell=_valid_positive,
    dii_buy=_valid_positive,
    dii_sell=_valid_positive,
)
@settings(max_examples=100)
def test_property3_valid_record_accepted(fii_buy, fii_sell, dii_buy, dii_sell):
    # Feature: finintelligence-market-analysis, Property 3: FII/DII Flow Validation
    # Validates: Requirements 3.5
    raw = {"date": "2024-06-01", "fii_buy": fii_buy, "fii_sell": fii_sell,
           "dii_buy": dii_buy, "dii_sell": dii_sell}
    result = _parse_flow_record(raw)
    assert isinstance(result, InstitutionalFlow), \
        f"Expected InstitutionalFlow for valid record {raw}, got {result}"
    assert abs(result.fii_net - (fii_buy - fii_sell)) < 1e-9
    assert abs(result.dii_net - (dii_buy - dii_sell)) < 1e-9


# ---------------------------------------------------------------------------
# Unit tests: _parse_flow_record
# ---------------------------------------------------------------------------

class TestParseFlowRecord:
    def test_valid_record_returns_institutional_flow(self):
        result = _parse_flow_record(_valid_raw())
        assert isinstance(result, InstitutionalFlow)
        assert result.fii_buy == 100.0
        assert result.fii_sell == 80.0
        assert result.fii_net == 20.0
        assert result.dii_buy == 50.0
        assert result.dii_sell == 40.0
        assert result.dii_net == 10.0

    def test_date_parsed_to_utc_midnight(self):
        result = _parse_flow_record(_valid_raw(date="2024-03-15"))
        assert result is not None
        assert result.date == datetime(2024, 3, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_nse_camelcase_field_names_accepted(self):
        raw = {"date": "2024-01-10", "fiiBuyValue": 200.0, "fiiSellValue": 150.0,
               "diiBuyValue": 90.0, "diiSellValue": 70.0}
        result = _parse_flow_record(raw)
        assert isinstance(result, InstitutionalFlow)
        assert result.fii_buy == 200.0
        assert result.fii_net == 50.0

    def test_negative_fii_buy_returns_none(self):
        assert _parse_flow_record(_valid_raw(fii_buy=-1.0)) is None

    def test_negative_fii_sell_returns_none(self):
        assert _parse_flow_record(_valid_raw(fii_sell=-0.5)) is None

    def test_negative_dii_buy_returns_none(self):
        assert _parse_flow_record(_valid_raw(dii_buy=-100.0)) is None

    def test_negative_dii_sell_returns_none(self):
        assert _parse_flow_record(_valid_raw(dii_sell=-0.01)) is None

    def test_non_numeric_fii_buy_returns_none(self):
        assert _parse_flow_record(_valid_raw(fii_buy="not_a_number")) is None

    def test_non_numeric_dii_sell_returns_none(self):
        assert _parse_flow_record(_valid_raw(dii_sell="N/A")) is None

    def test_none_value_returns_none(self):
        assert _parse_flow_record(_valid_raw(fii_buy=None)) is None

    def test_zero_values_are_valid(self):
        result = _parse_flow_record(_valid_raw(fii_buy=0.0, fii_sell=0.0,
                                               dii_buy=0.0, dii_sell=0.0))
        assert isinstance(result, InstitutionalFlow)
        assert result.fii_net == 0.0
        assert result.dii_net == 0.0

    def test_fii_net_can_be_negative(self):
        result = _parse_flow_record(_valid_raw(fii_buy=50.0, fii_sell=200.0))
        assert isinstance(result, InstitutionalFlow)
        assert result.fii_net == -150.0

    def test_missing_date_returns_none(self):
        raw = {"fii_buy": 100.0, "fii_sell": 80.0, "dii_buy": 50.0, "dii_sell": 40.0}
        assert _parse_flow_record(raw) is None

    def test_invalid_date_string_returns_none(self):
        assert _parse_flow_record(_valid_raw(date="not-a-date")) is None


# ---------------------------------------------------------------------------
# Unit tests: fetch_institutional_flows
# ---------------------------------------------------------------------------

class TestFetchInstitutionalFlows:

    def _make_nse_response(self, records):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = records
        return mock_resp

    def _make_error_response(self, status_code=500):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        return mock_resp

    @patch("finintelligence.institutional_fetcher.cache_manager.read_institutional_flows")
    @patch("finintelligence.institutional_fetcher.cache_manager.write_institutional_flows")
    @patch("finintelligence.institutional_fetcher.requests.get")
    def test_valid_nse_response_appends_new_records(self, mock_get, mock_write, mock_read):
        mock_read.return_value = pd.DataFrame()
        nse_records = [
            {"date": "2024-01-15", "fiiBuyValue": 1000.0, "fiiSellValue": 800.0,
             "diiBuyValue": 500.0, "diiSellValue": 400.0},
        ]
        mock_get.return_value = self._make_nse_response(nse_records)
        result = fetch_institutional_flows()
        assert not result.empty
        assert len(result) == 1
        assert result.iloc[0]["fii_buy"] == 1000.0
        mock_write.assert_called_once()

    @patch("finintelligence.institutional_fetcher.cache_manager.read_institutional_flows")
    @patch("finintelligence.institutional_fetcher.cache_manager.write_institutional_flows")
    @patch("finintelligence.institutional_fetcher.requests.get")
    def test_existing_dates_not_re_appended(self, mock_get, mock_write, mock_read):
        existing = pd.DataFrame([{
            "date": pd.Timestamp("2024-01-15", tz="UTC"),
            "fii_buy": 1000.0, "fii_sell": 800.0, "fii_net": 200.0,
            "dii_buy": 500.0, "dii_sell": 400.0, "dii_net": 100.0,
        }])
        mock_read.return_value = existing
        nse_records = [
            {"date": "2024-01-15", "fiiBuyValue": 1000.0, "fiiSellValue": 800.0,
             "diiBuyValue": 500.0, "diiSellValue": 400.0},
        ]
        mock_get.return_value = self._make_nse_response(nse_records)
        result = fetch_institutional_flows()
        assert len(result) == 1
        mock_write.assert_not_called()

    @patch("finintelligence.institutional_fetcher.cache_manager.read_institutional_flows")
    @patch("finintelligence.institutional_fetcher.cache_manager.write_institutional_flows")
    @patch("finintelligence.institutional_fetcher.requests.get")
    def test_endpoint_failure_returns_cached_data_no_raise(self, mock_get, mock_write, mock_read):
        cached = pd.DataFrame([{
            "date": pd.Timestamp("2024-01-10", tz="UTC"),
            "fii_buy": 500.0, "fii_sell": 400.0, "fii_net": 100.0,
            "dii_buy": 200.0, "dii_sell": 150.0, "dii_net": 50.0,
        }])
        mock_read.return_value = cached
        mock_get.return_value = self._make_error_response(503)
        result = fetch_institutional_flows()
        assert len(result) == 1
        assert result.iloc[0]["fii_buy"] == 500.0
        mock_write.assert_not_called()

    @patch("finintelligence.institutional_fetcher.cache_manager.read_institutional_flows")
    @patch("finintelligence.institutional_fetcher.cache_manager.write_institutional_flows")
    @patch("finintelligence.institutional_fetcher.requests.get")
    def test_network_error_no_cache_returns_empty_no_raise(self, mock_get, mock_write, mock_read):
        mock_read.return_value = pd.DataFrame()
        mock_get.side_effect = ConnectionError("network unreachable")
        result = fetch_institutional_flows()
        assert isinstance(result, pd.DataFrame)
        mock_write.assert_not_called()

    @patch("finintelligence.institutional_fetcher.cache_manager.read_institutional_flows")
    @patch("finintelligence.institutional_fetcher.cache_manager.write_institutional_flows")
    @patch("finintelligence.institutional_fetcher.requests.get")
    def test_invalid_records_filtered_before_append(self, mock_get, mock_write, mock_read):
        mock_read.return_value = pd.DataFrame()
        nse_records = [
            {"date": "2024-01-15", "fiiBuyValue": 1000.0, "fiiSellValue": 800.0,
             "diiBuyValue": 500.0, "diiSellValue": 400.0},
            {"date": "2024-01-16", "fiiBuyValue": -50.0, "fiiSellValue": 800.0,
             "diiBuyValue": 500.0, "diiSellValue": 400.0},
        ]
        mock_get.return_value = self._make_nse_response(nse_records)
        result = fetch_institutional_flows()
        assert len(result) == 1
        assert result.iloc[0]["fii_buy"] == 1000.0
