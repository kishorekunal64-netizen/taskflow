# Requirements Document

## Introduction

FinIntelligence Market Analysis System is a standalone Python application that provides institutional-grade market intelligence for Indian equity markets. The system ingests multi-timeframe OHLCV data, institutional flow data (FII/DII), sector rotation metrics, and financial news from free public sources. It synthesizes these inputs through a sentiment engine and AI analysis engine to produce market outlook signals and alerts. A built-in scheduler drives periodic data refresh cycles, and all data is cached locally to avoid redundant downloads.

## Glossary

- **System**: The FinIntelligence Market Analysis System as a whole
- **Data_Fetcher**: The component responsible for downloading OHLCV market data from Yahoo Finance, NSE datasets, and Stooq
- **Cache_Manager**: The component responsible for reading and writing Parquet/DuckDB/SQLite local cache files
- **Institutional_Flow_Fetcher**: The component responsible for downloading FII/DII data from NSE and NSDL public datasets
- **Sector_Rotation_Engine**: The component that computes sector rotation metrics including price movement, trend strength, institutional flow, and relative strength vs NIFTY
- **Sentiment_Engine**: The component that aggregates index momentum, sector performance, institutional flows, and macro events into a composite sentiment score
- **News_Ingester**: The component that fetches and parses RSS feeds from Reuters, Economic Times, Moneycontrol, and Investing.com
- **AI_Analysis_Engine**: The component that combines market structure, flows, and sentiment to produce outlook signals
- **Event_Detector**: The component that monitors thresholds and triggers AI analysis on qualifying market events
- **Scheduler**: The APScheduler-based component that drives periodic data refresh jobs
- **Logger**: The component that records API calls, data downloads, AI inference runs, and errors with threshold-based alerts
- **NIFTY_50**: NSE benchmark index of 50 large-cap Indian equities (Yahoo Finance ticker: ^NSEI)
- **BANKNIFTY**: NSE banking sector index (Yahoo Finance ticker: ^NSEBANK)
- **Sector_Index**: One of IT (^CNXIT), FMCG (^CNXFMCG), AUTO (^CNXAUTO), PHARMA (^CNXPHARMA), METAL (^CNXMETAL)
- **NIFTY_MIDCAP**: NSE midcap index (Yahoo Finance ticker: ^NSEMDCP50)
- **NIFTY_SMALLCAP**: NSE smallcap index (Yahoo Finance ticker: ^CNXSC)
- **Timeframe**: One of 1D, 4H, 1H, 15M, 5M representing OHLCV candle intervals
- **FII**: Foreign Institutional Investor — tracks foreign equity buy/sell flows on NSE
- **DII**: Domestic Institutional Investor — tracks domestic mutual fund and insurance equity flows on NSE
- **Candle**: A single OHLCV record (Open, High, Low, Close, Volume) for a given symbol and timeframe
- **Outlook_Signal**: A structured output from the AI_Analysis_Engine containing market direction, confidence level, and supporting rationale
- **Macro_Event**: A significant economic or geopolitical event parsed from news feeds that may affect market direction
- **Relative_Strength**: The ratio of a sector index's return to NIFTY_50's return over a rolling window

---

## Requirements

### Requirement 1: Multi-Timeframe Market Data Ingestion

**User Story:** As a market analyst, I want the system to fetch OHLCV data for all tracked indices across multiple timeframes, so that I can perform multi-timeframe technical analysis.

#### Acceptance Criteria

1. THE Data_Fetcher SHALL fetch OHLCV Candle data for NIFTY_50, BANKNIFTY, NIFTY_MIDCAP, NIFTY_SMALLCAP, and all five Sector_Indices
2. THE Data_Fetcher SHALL fetch data for all five Timeframes: 1D, 4H, 1H, 15M, and 5M
3. THE Data_Fetcher SHALL fetch a minimum of 365 Candles per symbol per Timeframe
4. WHEN Yahoo Finance is the primary source and returns an empty or malformed response, THE Data_Fetcher SHALL attempt to fetch the same data from Stooq as a fallback source
5. IF all configured data sources return an error for a given symbol and Timeframe, THEN THE Data_Fetcher SHALL log the failure with source name, symbol, Timeframe, HTTP status code, and timestamp, and SHALL skip that symbol-Timeframe combination without halting the overall fetch cycle
6. THE Data_Fetcher SHALL use only free, publicly accessible data sources: Yahoo Finance (via yfinance), NSE public datasets, and Stooq

---

### Requirement 2: Local Data Caching

**User Story:** As a system operator, I want all downloaded data cached locally, so that repeated runs do not re-download data that is already available and up to date.

#### Acceptance Criteria

1. THE Cache_Manager SHALL store all OHLCV Candle data in Parquet format under the `/data/market/` directory, partitioned by symbol and Timeframe
2. THE Cache_Manager SHALL store institutional flow data in DuckDB or SQLite format under the `/data/institutional/` directory
3. THE Cache_Manager SHALL store sector rotation metrics under the `/data/sector/` directory
4. THE Cache_Manager SHALL store sentiment scores and news data under the `/data/sentiment/` directory
5. WHEN the Data_Fetcher requests data for a symbol and Timeframe, THE Cache_Manager SHALL return cached data if the cache entry exists and was written within the staleness threshold for that Timeframe (5M: 5 minutes, 15M: 15 minutes, 1H: 60 minutes, 4H: 240 minutes, 1D: 1440 minutes)
6. WHEN cached data is stale or absent, THE Cache_Manager SHALL allow the Data_Fetcher to proceed with a live download and SHALL overwrite the cache entry upon successful download
7. IF a cache write operation fails due to a filesystem error, THEN THE Cache_Manager SHALL log the error with file path and exception detail, and SHALL return the freshly downloaded data to the caller without raising an exception

---

### Requirement 3: Institutional Flow Data Ingestion

**User Story:** As a market analyst, I want FII and DII buying, selling, and net flow data ingested daily, so that I can assess institutional participation in the market.

#### Acceptance Criteria

1. THE Institutional_Flow_Fetcher SHALL fetch daily FII gross buy, gross sell, and net buy/sell values from NSE or NSDL public data endpoints
2. THE Institutional_Flow_Fetcher SHALL fetch daily DII gross buy, gross sell, and net buy/sell values from NSE or NSDL public data endpoints
3. WHEN new institutional flow data is available for a trading date not yet present in the cache, THE Institutional_Flow_Fetcher SHALL append the new records to the institutional flow store
4. IF the NSE or NSDL endpoint returns an error or is unreachable, THEN THE Institutional_Flow_Fetcher SHALL log the failure with endpoint URL, HTTP status code, and timestamp, and SHALL retain the most recently cached institutional flow data for downstream consumers
5. THE Institutional_Flow_Fetcher SHALL parse flow values as numeric types (float) and SHALL reject records where gross buy or gross sell values are non-numeric or negative

---

### Requirement 4: Sector Rotation Analysis

**User Story:** As a market analyst, I want sector rotation metrics computed for all tracked sector indices, so that I can identify which sectors are gaining or losing institutional and price momentum.

#### Acceptance Criteria

1. THE Sector_Rotation_Engine SHALL compute the rolling 20-day price return for each Sector_Index
2. THE Sector_Rotation_Engine SHALL compute the Relative_Strength of each Sector_Index against NIFTY_50 over a rolling 20-day window
3. THE Sector_Rotation_Engine SHALL compute trend strength for each Sector_Index using the ADX indicator with a 14-period lookback on 1D Candle data
4. THE Sector_Rotation_Engine SHALL incorporate the most recent FII and DII net flow values from the institutional flow store into the sector rotation output
5. WHEN sector rotation metrics are computed, THE Sector_Rotation_Engine SHALL rank all Sector_Indices by Relative_Strength in descending order
6. THE Sector_Rotation_Engine SHALL store computed sector rotation results to the `/data/sector/` cache path via the Cache_Manager

---

### Requirement 5: News Ingestion

**User Story:** As a market analyst, I want financial news headlines ingested from multiple RSS feeds, so that I can monitor macro events and sentiment-relevant news in near real time.

#### Acceptance Criteria

1. THE News_Ingester SHALL fetch RSS feeds from Reuters, Economic Times, Moneycontrol, and Investing.com using feedparser
2. THE News_Ingester SHALL parse each feed entry and extract: headline, publication timestamp, source name, and summary text
3. WHEN a feed entry is missing a publication timestamp, THE News_Ingester SHALL record the ingestion timestamp as the publication timestamp
4. THE News_Ingester SHALL deduplicate feed entries by headline text within a 24-hour rolling window before storing
5. IF a feed URL is unreachable or returns a malformed feed, THEN THE News_Ingester SHALL log the failure with feed URL and error detail, and SHALL continue processing remaining feed URLs
6. THE News_Ingester SHALL store parsed news records to the `/data/sentiment/` cache path via the Cache_Manager

---

### Requirement 6: Sentiment Engine

**User Story:** As a market analyst, I want a composite sentiment score computed from multiple market signals, so that I can gauge overall market mood at a glance.

#### Acceptance Criteria

1. THE Sentiment_Engine SHALL compute index momentum as the rate of change of NIFTY_50 close price over a rolling 5-day window using 1D Candle data
2. THE Sentiment_Engine SHALL compute sector performance as the average 5-day return across all five Sector_Indices
3. THE Sentiment_Engine SHALL incorporate the most recent FII net flow value, normalised against a 20-day rolling mean and standard deviation, as an institutional flow signal
4. THE Sentiment_Engine SHALL assign a Macro_Event score by counting news entries in the last 24 hours that contain keywords associated with RBI policy, Union Budget, US Fed, inflation, or geopolitical events
5. THE Sentiment_Engine SHALL combine the four signals (index momentum, sector performance, institutional flow, macro event score) into a single composite sentiment score in the range [-1.0, 1.0]
6. THE Sentiment_Engine SHALL classify the composite score as Bearish (score < -0.3), Neutral (-0.3 ≤ score ≤ 0.3), or Bullish (score > 0.3)
7. THE Sentiment_Engine SHALL store the composite score, classification, and individual signal values to the `/data/sentiment/` cache path via the Cache_Manager

---

### Requirement 7: Event Detection and AI Analysis Triggering

**User Story:** As a market analyst, I want the system to automatically trigger AI analysis when significant market events occur, so that I receive timely signals without manual intervention.

#### Acceptance Criteria

1. THE Event_Detector SHALL monitor the most recent 1D Candle close-to-close percentage change for NIFTY_50 and BANKNIFTY after each 15-minute data refresh
2. WHEN the absolute close-to-close percentage change for NIFTY_50 or BANKNIFTY exceeds 1.0%, THE Event_Detector SHALL trigger the AI_Analysis_Engine
3. WHEN the absolute 1D close-to-close percentage change for any Sector_Index exceeds 2.0%, THE Event_Detector SHALL trigger the AI_Analysis_Engine
4. WHEN the absolute FII net flow value for the most recent trading date exceeds two standard deviations of the 20-day rolling FII net flow, THE Event_Detector SHALL trigger the AI_Analysis_Engine
5. WHEN a Macro_Event score of 3 or more is recorded by the Sentiment_Engine within a single hourly news cycle, THE Event_Detector SHALL trigger the AI_Analysis_Engine
6. THE Event_Detector SHALL record each trigger event with trigger type, triggering value, threshold value, and timestamp before invoking the AI_Analysis_Engine

---

### Requirement 8: AI Analysis Engine

**User Story:** As a market analyst, I want an AI analysis engine that synthesises market structure, institutional flows, and sentiment into actionable outlook signals, so that I can make informed trading decisions.

#### Acceptance Criteria

1. THE AI_Analysis_Engine SHALL accept as input: the latest multi-timeframe Candle data for NIFTY_50 and BANKNIFTY, the current sector rotation rankings, the composite sentiment score and classification, and the most recent FII/DII net flow values
2. THE AI_Analysis_Engine SHALL produce an Outlook_Signal containing: market direction (Bullish / Bearish / Neutral), confidence level (0.0–1.0), primary supporting factors (list of strings), and a plain-language rationale summary
3. THE AI_Analysis_Engine SHALL derive market structure from the 1D and 4H Candle data by identifying whether price is above or below the 50-period and 200-period simple moving averages
4. THE AI_Analysis_Engine SHALL incorporate the Sentiment_Engine classification and composite score as a weighted input to the Outlook_Signal direction determination
5. THE AI_Analysis_Engine SHALL incorporate the top-ranked and bottom-ranked Sector_Index from the Sector_Rotation_Engine output as supporting factors in the Outlook_Signal
6. WHEN the AI_Analysis_Engine produces an Outlook_Signal, THE AI_Analysis_Engine SHALL store the signal with a UTC timestamp to the `/data/sentiment/` cache path via the Cache_Manager
7. THE AI_Analysis_Engine SHALL complete signal generation within 30 seconds of being triggered

---

### Requirement 9: Scheduled Data Refresh

**User Story:** As a system operator, I want data refresh jobs to run automatically on a schedule, so that the system stays current without manual intervention.

#### Acceptance Criteria

1. THE Scheduler SHALL execute a market data refresh job every 15 minutes during NSE trading hours (09:15–15:30 IST, Monday–Friday)
2. THE Scheduler SHALL execute a news ingestion job every 60 minutes, seven days a week
3. THE Scheduler SHALL execute an institutional flow data refresh job once daily at 18:00 IST on trading days (Monday–Friday)
4. THE Scheduler SHALL execute a sector rotation and sentiment computation job immediately after each successful institutional flow refresh
5. WHEN a scheduled job raises an unhandled exception, THE Scheduler SHALL log the job name, exception type, exception message, and stack trace, and SHALL reschedule the job for its next regular interval without halting other scheduled jobs
6. THE Scheduler SHALL use APScheduler with the Asia/Kolkata timezone for all job schedules

---

### Requirement 10: Logging and Alerting

**User Story:** As a system operator, I want comprehensive structured logging with threshold-based alerts, so that I can monitor system health and diagnose failures quickly.

#### Acceptance Criteria

1. THE Logger SHALL record every outbound API call with: timestamp, target URL, HTTP method, response status code, and response latency in milliseconds
2. THE Logger SHALL record every data download completion with: timestamp, symbol, Timeframe, number of Candles received, and cache write status
3. THE Logger SHALL record every AI_Analysis_Engine inference run with: timestamp, trigger type, input data summary, Outlook_Signal direction, confidence level, and duration in milliseconds
4. THE Logger SHALL record every error with: timestamp, component name, error type, error message, and stack trace
5. WHEN the number of errors logged within any 60-minute rolling window exceeds 10, THE Logger SHALL emit a threshold alert log entry at CRITICAL level containing the error count and the 60-minute window start time
6. THE Logger SHALL write all log entries to a rotating file handler with a maximum file size of 10 MB and a retention of 5 backup files
7. THE Logger SHALL also write all log entries at WARNING level and above to standard error output
