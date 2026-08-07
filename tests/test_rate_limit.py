import asyncio

from fastapi import HTTPException

from framework.rate_limit import MemoryRateLimiter


def test_memory_token_bucket_rejects_over_burst():
    async def run():
        limiter = MemoryRateLimiter()
        await limiter.check("x", limit=1, window_seconds=60, burst=1)
        try:
            await limiter.check("x", limit=1, window_seconds=60, burst=1)
        except HTTPException as exc:
            assert exc.status_code == 429
        else:
            raise AssertionError("expected rate limit")
    asyncio.run(run())
