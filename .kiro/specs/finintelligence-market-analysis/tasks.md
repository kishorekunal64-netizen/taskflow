# Implementation Plan: FinIntelligence Market Analysis System

## Overview

Standalone Python application delivering institutional-grade market intelligence for Indian equity markets. Built incrementally: environment → models → infrastructure → ingestion → analysis → orchestration → tests.

## Tasks

- [x] 1. Environment setup
  - Create `finintelligence/requirements.txt` with all dependencies: `yfinance`, `pandas`, `pyarrow`, `duckdb`, `feedparser`, `pandas-ta`, `apscheduler`, `hypothesis`, `pytest`, `pytest-mock`
  - Create `finintelligence/data/market/`, `finintelligence/data/sector/`, `finintelligence/data/institutional/`, `finintelligence/data/sentiment/` directories (add `.gitkeep` to each)
  - Create `finintelligence/config.py` with all module-level constants: `SYMBOLS`, `TIMEFRAMES`, `STALENESS_THRESHOLDS`, `RSS_URLS`, `DATA_DIR`, `MARKET_DIR`, `SECTOR_DIR`, `INSTITUTIONAL_DIR`, `SENTIMENT_DIR`, `EVENT_THRESHOLDS`, `TRADING_HOURS`
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 9.6_

- [x] 2. Data models
  - Create `finintelligence/models.py` with all six dataclasses: `Candle`, `InstitutionalFlow`, `SectorMetrics`, `SentimentResult`, `OutlookSignal`, `TriggerEvent`
  - Each dataclass must use `@dataclass` with typed fields exactly as specified in the design; `OutlookSignal.supporting_factors` uses `field(default_factory=list)`
  - _Requirements: 1.1, 3.1, 4.1, 6.5, 7.6, 8.2_

- [x] 3. Logger
  - Create `finintelligence/logger.py` implementing `get_logger(name)`, `record_error(component)`, and `check_error_threshold()`
  - `RotatingFileHandler`: max 10 MB, 5 backups, ALL levels; `StreamHandler(sys.stderr)`: WARNING and above only
  - Rolling 60-minute error counter: emit exactly one CRITICAL entry when count exceeds 10 in any window
  - Logger must never raise — if file handler fails, fall back to stderr only
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [x] 4. Cache Manager
  - Create `finintelligence/cache_manager.py` implementing all functions: `is_stale`, `read_candles`, `write_candles`, `read_institutional_flows`, `write_institutional_flows`, `read_sector_metrics`, `write_sector_metrics`, `read_news`, `write_news`, `write_sentiment`, `write_signal`, `read_latest_signal`
  - Parquet path convention: `{MARKET_DIR}/{symbol}/{timeframe}.parquet`; institutional flows stored in DuckDB at `{INSTITUTIONAL_DIR}/flows.db`
  - `is_stale` compares file mtime against `STALENESS_THRESHOLDS[timeframe]` in minutes
  - Cache read failures return empty `pd.DataFrame`, never raise; write failures log path + exception and return in-memory data to caller
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 4.1 Write property test for cache round-trip (Property 1)
    - **Property 1: Cache Round-Trip** — write then read must produce equivalent object with no data loss or type coercion
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    - Use `st.data_frames()` with typed columns; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_cache_manager.py`

  - [ ]* 4.2 Write property test for cache staleness bounds (Property 2)
    - **Property 2: Cache Staleness Bounds** — `is_stale()` returns False within threshold window, True outside it, for all five timeframes
    - **Validates: Requirements 2.5, 2.6**
    - Use `st.timedeltas()` within/outside each threshold; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_cache_manager.py`

  - [ ]* 4.3 Write unit tests for Cache Manager
    - Test Parquet write/read round-trip with known DataFrame
    - Test DuckDB write/read for institutional flows
    - Test `is_stale` boundary conditions for each timeframe
    - Test write failure path: filesystem error → logs + returns in-memory data, no exception raised
    - File: `finintelligence/tests/test_cache_manager.py`

- [x] 5. Data Fetcher
  - Create `finintelligence/data_fetcher.py` implementing `fetch_symbol`, `fetch_all`, `_fetch_yfinance`, `_fetch_stooq`
  - Check `cache_manager.is_stale()` before downloading; skip download if fresh
  - On Yahoo Finance empty/malformed response → fall back to `_fetch_stooq`; on all-source failure → log and skip without raising
  - Minimum 365 candles per symbol/timeframe; write result to cache via `cache_manager.write_candles`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 6. Institutional Fetcher
  - Create `finintelligence/institutional_fetcher.py` implementing `fetch_institutional_flows` and `_parse_flow_record`
  - `_parse_flow_record` returns `None` for any record where `fii_buy`, `fii_sell`, `dii_buy`, or `dii_sell` is non-numeric or negative
  - Append only new trading dates not already in cache; on endpoint failure → log URL + status, return last cached flows
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 6.1 Write property test for FII/DII flow validation (Property 3)
    - **Property 3: FII/DII Flow Validation** — records with negative or non-numeric gross buy/sell must be rejected (return None) and never appear in the store
    - **Validates: Requirements 3.5**
    - Use `st.floats(max_value=-0.01)` and `st.text()` for invalid field values; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_institutional_fetcher.py`

  - [ ]* 6.2 Write unit tests for Institutional Fetcher
    - Test valid record parsing produces correct `InstitutionalFlow` dataclass
    - Test endpoint failure path: returns cached data, no exception raised
    - Test deduplication: existing trading dates are not re-appended
    - File: `finintelligence/tests/test_institutional_fetcher.py`

- [x] 7. News Ingester
  - Create `finintelligence/news_ingester.py` implementing `ingest_all_feeds`, `_parse_feed`, `_deduplicate`
  - Missing publication timestamp → use ingestion timestamp; unreachable/malformed feed → log and continue to next URL
  - Deduplicate by headline text within 24-hour rolling window before storing
  - Store to `/data/sentiment/` via `cache_manager.write_news`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 8. Feature Generator
  - Create `finintelligence/feature_generator.py` implementing `compute_features`, `compute_sma`, `compute_volatility`, `price_vs_sma`
  - `compute_sma(series, period)` returns a `pd.Series`; `compute_volatility(series, window=20)` returns a float
  - `price_vs_sma(close, sma)` returns `"above"` or `"below"`
  - `compute_features` reads candles from cache and returns a dict of computed indicators
  - _Requirements: 8.3_

- [x] 9. Sector Rotation Engine
  - Create `finintelligence/sector_rotation_engine.py` implementing `compute_sector_metrics`, `compute_relative_strength`, `compute_adx`, `rank_sectors`
  - Reads 1D candles from cache for all 5 sector indices + NIFTY_50; incorporates latest FII/DII net flows
  - `rank_sectors` assigns ranks 1–5 by `relative_strength` descending (rank 1 = highest); writes results via `cache_manager.write_sector_metrics`
  - ADX computed via `pandas-ta` with 14-period lookback
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 9.1 Write property test for sector ranking completeness and order (Property 4)
    - **Property 4: Sector Ranking Completeness and Order** — output contains exactly all 5 sector symbols, ranks 1–5, ordered strictly by relative_strength descending
    - **Validates: Requirements 4.5**
    - Use `st.lists(st.floats(allow_nan=False), min_size=5, max_size=5)` for relative_strength values; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_sector_rotation_engine.py`

  - [ ]* 9.2 Write unit tests for Sector Rotation Engine
    - Test known OHLCV data produces expected 20-day return and relative strength values
    - Test ADX computation returns a non-negative float
    - Test ranking with tied relative_strength values produces stable, complete output
    - File: `finintelligence/tests/test_sector_rotation_engine.py`

- [x] 10. Checkpoint — ensure all tests pass so far
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Sentiment Engine
  - Create `finintelligence/sentiment_engine.py` implementing `compute_sentiment`, `_index_momentum`, `_sector_performance`, `_institutional_signal`, `_macro_score`, `_composite`, `_classify`
  - Signal weights: index momentum 30%, sector performance 25%, institutional flow 30%, macro event score 15%
  - `_composite` clamps weighted sum to `[-1.0, 1.0]`; `_classify` returns `"Bearish"` if `s < -0.3`, `"Neutral"` if `-0.3 ≤ s ≤ 0.3`, `"Bullish"` if `s > 0.3`
  - Reads news from cache via `cache_manager.read_news`; stores result via `cache_manager.write_sentiment`
  - On missing institutional flows → use last cached value and log staleness warning
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 11.1 Write property test for sentiment score bounds (Property 5)
    - **Property 5: Sentiment Score Bounds** — composite score is always in `[-1.0, 1.0]` for any valid input combination
    - **Validates: Requirements 6.5**
    - Use `st.floats(min_value=-10, max_value=10)` × 4 signals; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_sentiment_engine.py`

  - [ ]* 11.2 Write property test for sentiment classification correctness (Property 6)
    - **Property 6: Sentiment Classification Correctness** — classification is exactly Bearish/Neutral/Bullish per score thresholds, no invalid strings
    - **Validates: Requirements 6.6**
    - Use `st.floats(min_value=-1.0, max_value=1.0)`; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_sentiment_engine.py`

  - [ ]* 11.3 Write unit tests for Sentiment Engine
    - Test known FII net flow values produce expected normalised institutional signal
    - Test macro keyword matching counts correctly for each keyword category
    - Test `_classify` boundary values: exactly -0.3, 0.0, 0.3
    - File: `finintelligence/tests/test_sentiment_engine.py`

- [x] 12. Event Detector
  - Create `finintelligence/event_detector.py` implementing `check_and_trigger`, `_check_index_move`, `_check_sector_move`, `_check_fii_spike`, `_check_macro_score`, `_is_duplicate`
  - Threshold logic: index move `abs(chg) > 1.0%`, sector move `abs(chg) > 2.0%`, FII spike `abs(fii_net) > mean + 2*std` (20-day rolling), macro event `macro_score >= 3`
  - Idempotency guard: store `(window_key, trigger_type)` tuples in memory; suppress duplicate triggers within same 15-minute window
  - Records `TriggerEvent` with all required fields before returning
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 12.1 Write property test for event threshold trigger (Property 7)
    - **Property 7: Event Threshold Trigger** — any market state meeting at least one threshold condition must produce a non-None TriggerEvent with correct trigger_type, triggering_value, threshold_value
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.6**
    - Use `st.floats()` with threshold-crossing strategies for each condition; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_event_detector.py`

  - [ ]* 12.2 Write property test for event trigger idempotency (Property 8)
    - **Property 8: Event Trigger Idempotency** — same market state called twice in same 15-minute window produces trigger on first call, None on all subsequent calls
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5**
    - Fixed market state above threshold, repeated calls; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_event_detector.py`

  - [ ]* 12.3 Write unit tests for Event Detector
    - Test each threshold condition independently with boundary values
    - Test that market state below all thresholds returns None
    - Test idempotency guard resets correctly after 15-minute window expires
    - File: `finintelligence/tests/test_event_detector.py`

- [x] 13. AI Analysis Engine
  - Create `finintelligence/ai_analysis_engine.py` implementing `generate_signal`, `_market_structure`, `_direction_vote`, `_confidence`, `_supporting_factors`, `_rationale`
  - Market structure: price vs SMA50 and SMA200 on 1D and 4H candles
  - Weighted vote: structure 40%, sentiment classification 35%, FII net direction 25%; direction = majority vote
  - `_confidence` returns normalised weighted agreement score in `[0.0, 1.0]`
  - `supporting_factors` must include strings referencing rank-1 and rank-5 sector symbols
  - `rationale` is a non-empty plain-language summary assembled from factors
  - On missing/malformed input → log input summary + error, return None (no signal stored)
  - Must complete within 30 seconds (all in-memory pandas, no network calls)
  - Stores signal via `cache_manager.write_signal`
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 13.1 Write property test for OutlookSignal completeness (Property 9)
    - **Property 9: OutlookSignal Completeness** — for any valid input combination, direction is in {Bullish, Bearish, Neutral}, confidence in [0.0, 1.0], supporting_factors is non-empty list of strings, rationale is non-empty string
    - **Validates: Requirements 8.2**
    - Composite strategy over all input types; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_ai_analysis_engine.py`

  - [ ]* 13.2 Write property test for top/bottom sector in supporting factors (Property 10)
    - **Property 10: Top and Bottom Sector in Supporting Factors** — supporting_factors must reference rank-1 and rank-5 sector symbols for any sector ranking permutation
    - **Validates: Requirements 8.5**
    - Use `st.permutations(SECTOR_SYMBOLS)` for sector rankings; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_ai_analysis_engine.py`

  - [ ]* 13.3 Write unit tests for AI Analysis Engine
    - Test known candle data above SMA50 and SMA200 produces Bullish structure vote
    - Test direction vote with conflicting signals produces correct weighted majority
    - Test missing input data returns None without raising
    - File: `finintelligence/tests/test_ai_analysis_engine.py`

- [x] 14. Checkpoint — ensure all tests pass so far
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Scheduler
  - Create `finintelligence/scheduler.py` implementing `build_scheduler`, `market_refresh_job`, `news_ingestion_job`, `institutional_flow_job`, `sector_sentiment_job`
  - `BackgroundScheduler(timezone="Asia/Kolkata")`
  - Market refresh: `CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/15")` with 09:15 start guard
  - News ingestion: `IntervalTrigger(hours=1)`
  - Institutional flow: `CronTrigger(day_of_week="mon-fri", hour=18, minute=0)`
  - `sector_sentiment_job` chained after `institutional_flow_job`
  - On job exception: log job name + full traceback; reschedule at next regular interval; do not halt other jobs
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 15.1 Write property test for scheduler timezone correctness (Property 11)
    - **Property 11: Scheduler Timezone Correctness** — all registered job next_run_times must be in Asia/Kolkata timezone (UTC+5:30)
    - **Validates: Requirements 9.6**
    - Deterministic check: inspect scheduler config after `build_scheduler()`; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_scheduler.py`

  - [ ]* 15.2 Write unit tests for Scheduler
    - Test all four job types are registered after `build_scheduler()`
    - Test job exception handler logs traceback and does not re-raise
    - Test market refresh job does not fire outside 09:15–15:30 window
    - File: `finintelligence/tests/test_scheduler.py`

- [x] 16. Logger property and unit tests
  - Create `finintelligence/tests/test_logger.py`

  - [ ]* 16.1 Write property test for error threshold CRITICAL alert (Property 12)
    - **Property 12: Error Threshold CRITICAL Alert** — sequences > 10 errors in 60-minute window emit exactly one CRITICAL entry; sequences ≤ 10 must not
    - **Validates: Requirements 10.5**
    - Use `st.integers(min_value=0, max_value=20)` for error counts; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_logger.py`

  - [ ]* 16.2 Write property test for log entry field completeness (Property 13)
    - **Property 13: Log Entry Field Completeness** — every loggable event type contains all required fields (API call, download, inference run, error)
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**
    - Use `st.sampled_from(EVENT_TYPES)` + field strategies; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_logger.py`

  - [ ]* 16.3 Write property test for WARNING-level logs reaching stderr (Property 14)
    - **Property 14: WARNING-Level Logs Reach stderr** — WARNING/ERROR/CRITICAL appear on sys.stderr; DEBUG/INFO must not
    - **Validates: Requirements 10.7**
    - Use `st.sampled_from` over log levels; capture stderr with `io.StringIO`; run `@settings(max_examples=100)`
    - File: `finintelligence/tests/test_logger.py`

  - [ ]* 16.4 Write unit tests for Logger
    - Test rotating file handler is configured with 10 MB max size and 5 backups
    - Test stderr handler threshold is WARNING
    - Test `record_error` increments counter correctly
    - Test logger never raises when file handler fails (simulate with mock)
    - File: `finintelligence/tests/test_logger.py`

- [x] 17. Main entry point
  - Create `finintelligence/main.py` implementing `main()`: bootstrap logger, initialise cache manager, call `build_scheduler()`, start scheduler, block on `KeyboardInterrupt` for graceful shutdown
  - Graceful shutdown: call `scheduler.shutdown()` on `KeyboardInterrupt`, log shutdown event
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 18. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `@settings(max_examples=100)` and a comment: `# Feature: finintelligence-market-analysis, Property {N}: {property_text}`
- Unit tests use `pytest` with `unittest.mock` for mocking external calls
- All components catch exceptions at their boundary and log via `logger.py`; no unhandled exceptions propagate to the scheduler
