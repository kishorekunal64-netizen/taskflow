"""
FinIntelligence Market Analysis System — data models.
All models are Python dataclasses. Serialisation to/from Parquet uses pyarrow.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Candle:
    symbol: str
    timeframe: str          # "1D" | "4H" | "1H" | "15M" | "5M"
    timestamp: datetime     # UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class InstitutionalFlow:
    date: datetime          # trading date, UTC midnight
    fii_buy: float          # gross buy (crores)
    fii_sell: float         # gross sell (crores)
    fii_net: float          # net = buy - sell
    dii_buy: float
    dii_sell: float
    dii_net: float


@dataclass
class SectorMetrics:
    symbol: str             # e.g. "^CNXIT"
    date: datetime
    return_20d: float       # 20-day price return as decimal
    relative_strength: float  # sector_return_20d / nifty_return_20d
    adx: float              # ADX(14) value
    rank: int               # 1 = strongest, 5 = weakest


@dataclass
class SentimentResult:
    timestamp: datetime     # UTC
    index_momentum: float   # normalised [-1, 1]
    sector_perf: float      # normalised [-1, 1]
    institutional_signal: float  # z-score normalised, clamped [-1, 1]
    macro_score: int        # raw count of macro keyword hits
    composite_score: float  # weighted sum, clamped [-1.0, 1.0]
    classification: str     # "Bullish" | "Neutral" | "Bearish"


@dataclass
class OutlookSignal:
    timestamp: datetime     # UTC
    direction: str          # "Bullish" | "Bearish" | "Neutral"
    confidence: float       # [0.0, 1.0]
    supporting_factors: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class TriggerEvent:
    timestamp: datetime     # UTC
    trigger_type: str       # "index_move" | "sector_move" | "fii_spike" | "macro_event"
    triggering_value: float
    threshold_value: float
