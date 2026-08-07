from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from hashlib import sha256

from fastapi import HTTPException


class MemoryRateLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, identity: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        floor = now - window_seconds
        async with self._lock:
            q = self._events[identity]
            while q and q[0] < floor:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            q.append(now)

    async def close(self) -> None:
        return None


class RedisRateLimiter:
    def __init__(self, url: str):
        from redis.asyncio import from_url
        self.redis = from_url(url, encoding="utf-8", decode_responses=True)

    async def check(self, identity: str, limit: int, window_seconds: int) -> None:
        bucket = int(time.time()) // window_seconds
        digest = sha256(identity.encode("utf-8")).hexdigest()[:32]
        key = f"json-api-forge:rl:{digest}:{bucket}"
        value = await self.redis.incr(key)
        if value == 1:
            await self.redis.expire(key, window_seconds + 2)
        if value > limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    async def close(self) -> None:
        await self.redis.aclose()
