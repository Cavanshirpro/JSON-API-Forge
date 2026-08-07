from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from hashlib import sha256
from typing import Any


class MemoryTTLCache:
    def __init__(self, max_entries: int = 10_000):
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._generations: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        now = time.monotonic()
        async with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        async with self._lock:
            self._data[key] = (time.monotonic() + max(ttl, 1), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def generation(self, namespace: str) -> int:
        return self._generations.get(namespace, 0)

    async def bump_generation(self, namespace: str) -> int:
        async with self._lock:
            value = self._generations.get(namespace, 0) + 1
            self._generations[namespace] = value
            return value

    async def close(self) -> None:
        async with self._lock:
            self._data.clear()


class RedisTTLCache:
    def __init__(self, url: str, prefix: str = "forge"):
        from redis.asyncio import from_url
        self.redis = from_url(url, encoding=None, decode_responses=False)
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}:cache:{key}"

    def _gen_key(self, namespace: str) -> str:
        return f"{self.prefix}:gen:{namespace}"

    async def get(self, key: str) -> bytes | None:
        return await self.redis.get(self._key(key))

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        await self.redis.set(self._key(key), value, ex=max(ttl, 1))

    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    async def generation(self, namespace: str) -> int:
        value = await self.redis.get(self._gen_key(namespace))
        return int(value or 0)

    async def bump_generation(self, namespace: str) -> int:
        return int(await self.redis.incr(self._gen_key(namespace)))

    async def close(self) -> None:
        await self.redis.aclose()


class TieredCache:
    """L1 process cache + L2 Redis. L2 is authoritative for generation counters."""
    def __init__(self, memory: MemoryTTLCache, redis: RedisTTLCache):
        self.memory = memory
        self.redis = redis

    async def get(self, key: str) -> bytes | None:
        value = await self.memory.get(key)
        if value is not None:
            return value
        value = await self.redis.get(key)
        if value is not None:
            await self.memory.set(key, value, ttl=5)
        return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        await asyncio.gather(
            self.redis.set(key, value, ttl),
            self.memory.set(key, value, min(ttl, 10)),
        )

    async def delete(self, key: str) -> None:
        await asyncio.gather(self.memory.delete(key), self.redis.delete(key))

    async def generation(self, namespace: str) -> int:
        return await self.redis.generation(namespace)

    async def bump_generation(self, namespace: str) -> int:
        value = await self.redis.bump_generation(namespace)
        await self.memory.bump_generation(namespace)
        return value

    async def close(self) -> None:
        await asyncio.gather(self.memory.close(), self.redis.close())


class CacheManager:
    def __init__(self, backend, prefix: str = "forge"):
        self.backend = backend
        self.prefix = prefix
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def generation(self, namespace: str) -> int:
        return await self.backend.generation(namespace)

    async def make_key(self, namespace: str, payload: Any) -> str:
        generation = await self.generation(namespace)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        digest = sha256(raw).hexdigest()
        return f"{namespace}:g{generation}:{digest}"

    async def get_json(self, key: str) -> Any | None:
        value = await self.backend.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        await self.backend.set(key, json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"), ttl)

    async def get_or_set_json(self, key: str, ttl: int, loader):
        cached = await self.get_json(key)
        if cached is not None:
            return cached, True
        lock = await self._lock_for(key)
        async with lock:
            cached = await self.get_json(key)
            if cached is not None:
                return cached, True
            value = await loader()
            await self.set_json(key, value, ttl)
            return value, False

    async def invalidate_namespace(self, namespace: str) -> int:
        return await self.backend.bump_generation(namespace)

    async def close(self) -> None:
        await self.backend.close()


def build_cache(config, redis_url: str | None):
    if not config.enabled:
        return None
    if config.backend == "memory":
        return CacheManager(MemoryTTLCache(config.max_entries), config.key_prefix)
    if not redis_url:
        raise RuntimeError(f"cache.backend={config.backend!r} requires REDIS_URL")
    redis_cache = RedisTTLCache(redis_url, config.key_prefix)
    if config.backend == "redis":
        return CacheManager(redis_cache, config.key_prefix)
    return CacheManager(TieredCache(MemoryTTLCache(config.max_entries), redis_cache), config.key_prefix)
