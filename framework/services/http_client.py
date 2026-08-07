from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None


class ResilientHTTPClient:
    """Reusable outbound client with connection pooling, retries and a simple circuit breaker."""
    def __init__(self, *, timeout: float = 10.0, max_connections: int = 200, max_keepalive: int = 50,
                 failure_threshold: int = 5, reset_seconds: float = 30.0):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_keepalive),
        )
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.states: dict[str, CircuitState] = {}

    async def request(self, method: str, url: str, *, retries: int = 2, **kwargs):
        host = httpx.URL(url).host or "unknown"
        state = self.states.setdefault(host, CircuitState())
        now = time.monotonic()
        if state.opened_at is not None and now - state.opened_at < self.reset_seconds:
            raise RuntimeError(f"Circuit open for {host}")
        if state.opened_at is not None:
            state.opened_at = None
            state.failures = 0

        last = None
        for attempt in range(retries + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                state.failures = 0
                return response
            except (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last = exc
                state.failures += 1
                if state.failures >= self.failure_threshold:
                    state.opened_at = time.monotonic()
                if attempt < retries:
                    await asyncio.sleep(min(0.25 * (2 ** attempt), 2.0))
        raise last

    async def close(self):
        await self.client.aclose()
