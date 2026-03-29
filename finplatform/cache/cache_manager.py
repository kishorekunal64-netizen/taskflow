"""
Cache factory. Reads CACHE_BACKEND env var (default: memory).
Usage:
    from finplatform.cache.cache_manager import get_cache
    cache = get_cache()
    cache.set("key", value)
"""

import os
from typing import Any, Optional


def get_cache():
    backend = os.environ.get("CACHE_BACKEND", "memory").lower()
    if backend == "redis":
        from finplatform.cache.redis_cache import RedisCache
        return RedisCache()
    from finplatform.cache.memory_cache import MemoryCache
    return MemoryCache()
