import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResultCache:
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _data: dict = field(default_factory=lambda: {
        "market_sentiment": None,
        "sector_strength": None,
        "institutional_flows": None,
        "ai_signals": None,
    }, init=False)

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)


cache = ResultCache()
