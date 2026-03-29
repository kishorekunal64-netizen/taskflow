"""
Redis cache backend.
Only imported when CACHE_BACKEND=redis. Requires 'redis' package.
Falls back gracefully if Redis is unavailable.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("platform.cache.redis")

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


class RedisCache:
    def __init__(self) -> None:
        try:
            import redis  # type: ignore
            self._client = redis.from_url(_REDIS_URL, decode_responses=True)
            self._client.ping()
            logger.info("RedisCache: connected to %s", _REDIS_URL)
        except Exception as exc:
            logger.warning("RedisCache: could not connect (%s) — falling back to no-op", exc)
            self._client = None

    def set(self, key: str, value: Any) -> None:
        if self._client is None:
            return
        try:
            self._client.set(key, json.dumps(value))
        except Exception as exc:
            logger.error("RedisCache.set(%s) failed: %s", key, exc)

    def get(self, key: str) -> Optional[Any]:
        if self._client is None:
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:
            logger.error("RedisCache.get(%s) failed: %s", key, exc)
            return None

    def exists(self, key: str) -> bool:
        if self._client is None:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception as exc:
            logger.error("RedisCache.exists(%s) failed: %s", key, exc)
            return False
