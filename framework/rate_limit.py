from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from hashlib import sha256

from fastapi import HTTPException


@dataclass
class Bucket:
    tokens: float
    updated: float


class MemoryRateLimiter:
    """Token-bucket limiter with burst support."""
    def __init__(self):
        self._buckets: dict[str, Bucket] = {}
        self._lock = asyncio.Lock()

    async def check(self, identity: str, limit: int, window_seconds: int, burst: int | None = None) -> None:
        capacity = float(burst or limit)
        refill_per_sec = float(limit) / max(float(window_seconds), 1.0)
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(identity)
            if bucket is None:
                bucket = Bucket(tokens=capacity, updated=now)
                self._buckets[identity] = bucket
            bucket.tokens = min(capacity, bucket.tokens + (now - bucket.updated) * refill_per_sec)
            bucket.updated = now
            if bucket.tokens < 1.0:
                retry = max(1, int((1.0 - bucket.tokens) / refill_per_sec))
                raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry)})
            bucket.tokens -= 1.0

    async def close(self) -> None:
        self._buckets.clear()


class RedisRateLimiter:
    LUA = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local rate = tonumber(ARGV[2])
    local capacity = tonumber(ARGV[3])
    local ttl = tonumber(ARGV[4])
    local data = redis.call('HMGET', key, 'tokens', 'ts')
    local tokens = tonumber(data[1])
    local ts = tonumber(data[2])
    if tokens == nil then tokens = capacity end
    if ts == nil then ts = now end
    tokens = math.min(capacity, tokens + (now - ts) * rate)
    local allowed = 0
    if tokens >= 1 then
      tokens = tokens - 1
      allowed = 1
    end
    redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
    redis.call('EXPIRE', key, ttl)
    return {allowed, tokens}
    """

    def __init__(self, url: str):
        from redis.asyncio import from_url
        self.redis = from_url(url, encoding="utf-8", decode_responses=True)

    async def check(self, identity: str, limit: int, window_seconds: int, burst: int | None = None) -> None:
        capacity = float(burst or limit)
        rate = float(limit) / max(float(window_seconds), 1.0)
        digest = sha256(identity.encode("utf-8")).hexdigest()[:40]
        key = f"json-api-forge:rl:{digest}"
        now = time.time()
        allowed, tokens = await self.redis.eval(self.LUA, 1, key, now, rate, capacity, max(window_seconds * 2, 2))
        if int(allowed) != 1:
            retry = max(1, int((1.0 - float(tokens)) / rate))
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry)})

    async def close(self) -> None:
        await self.redis.aclose()
