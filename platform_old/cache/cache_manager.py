"""
Cache factory. Reads CACHE_BACKEND env var (default: memory).
Usage:
    from platform.cache.cache_manager import get_cache
    cache = get_cache()
    cache.set("key", value)
"""

import os
from typing import Any, Optional


def get_cache():
    backend = os.environ.get("CACHE_BACKEND", "memory").lower()
    if backend == "redis":
        from platform.cache.redis_cache import RedisCache
        return RedisCache()
    from platform.cache.memory_cache import MemoryCache
    return MemoryCache()
