"""
FinIntelligence Market Analysis System — module-level configuration constants.
All values are read-only at runtime; no mutation after import.
"""

import os

# ---------------------------------------------------------------------------
# Tracked symbols
# ---------------------------------------------------------------------------

SYMBOLS: list[str] = [
    "^NSEI",       # NIFTY 50
    "^NSEBANK",    # BANKNIFTY
    "^CNXIT",      # Nifty IT
    "^CNXFMCG",    # Nifty FMCG
    "^CNXAUTO",    # Nifty Auto
    "^CNXPHARMA",  # Nifty Pharma
    "^CNXMETAL",   # Nifty Metal
    "^NSEMDCP50",  # Nifty Midcap 50
    "^CNXSC",      # Nifty Smallcap
]

SECTOR_SYMBOLS: list[str] = [
    "^CNXIT",
    "^CNXFMCG",
    "^CNXAUTO",
    "^CNXPHARMA",
    "^CNXMETAL",
]

# ---------------------------------------------------------------------------
# Timeframes
# ---------------------------------------------------------------------------

TIMEFRAMES: list[str] = ["1D", "4H", "1H", "15M", "5M"]

# Staleness thresholds in minutes per timeframe
STALENESS_THRESHOLDS: dict[str, int] = {
    "5M": 5,
    "15M": 15,
    "1H": 60,
    "4H": 240,
    "1D": 1440,
}

# ---------------------------------------------------------------------------
# News RSS feeds
# ---------------------------------------------------------------------------

RSS_URLS: list[str] = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.investing.com/rss/news.rss",
]

# ---------------------------------------------------------------------------
# Local data directories
# ---------------------------------------------------------------------------

DATA_DIR: str = os.path.join(os.path.dirname(__file__), "data")
MARKET_DIR: str = os.path.join(DATA_DIR, "market")
SECTOR_DIR: str = os.path.join(DATA_DIR, "sector")
INSTITUTIONAL_DIR: str = os.path.join(DATA_DIR, "institutional")
SENTIMENT_DIR: str = os.path.join(DATA_DIR, "sentiment")

# ---------------------------------------------------------------------------
# Event detection thresholds
# ---------------------------------------------------------------------------

EVENT_THRESHOLDS: dict[str, float] = {
    "index_pct": 1.0,      # abs % change on NIFTY/BANKNIFTY to trigger AI
    "sector_pct": 2.0,     # abs % change on any sector index to trigger AI
    "fii_std_dev": 2.0,    # z-score threshold for FII net flow spike
    "macro_score": 3,      # minimum macro keyword hits in hourly news cycle
}

# ---------------------------------------------------------------------------
# NSE trading hours (Asia/Kolkata)
# ---------------------------------------------------------------------------

TRADING_HOURS: dict[str, str] = {
    "start": "09:15",
    "end": "15:30",
    "tz": "Asia/Kolkata",
}
