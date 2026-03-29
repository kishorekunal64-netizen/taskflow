"""In-memory cache backend (default)."""

import threading
from typing import Any, Optional


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._data.get(key)

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._data
