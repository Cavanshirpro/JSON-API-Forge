from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
_IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None


class ResponseTooLarge(RuntimeError):
    pass


class ResilientHTTPClient:
    """Reusable outbound client with pooling, bounded retries and a circuit breaker.

    The optional `max_response_bytes` limit is enforced while streaming bytes from
    the upstream. This prevents a small declarative proxy route from buffering an
    unbounded response into a Forge worker.
    """

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_connections: int = 200,
        max_keepalive: int = 50,
        failure_threshold: int = 5,
        reset_seconds: float = 30.0,
    ):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_keepalive),
            follow_redirects=False,
        )
        self.failure_threshold = max(1, int(failure_threshold))
        self.reset_seconds = max(0.1, float(reset_seconds))
        self.states: dict[str, CircuitState] = {}

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            raw = response.headers.get("Retry-After")
            if raw:
                try:
                    return min(max(float(raw), 0.0), 10.0)
                except ValueError:
                    pass
        return min(0.25 * (2**attempt), 2.0)

    async def _send_once(self, method: str, url: str, *, max_response_bytes: int | None = None, **kwargs) -> httpx.Response:
        request = self.client.build_request(method, url, **kwargs)
        response = await self.client.send(request, stream=True)
        try:
            if max_response_bytes is not None:
                raw_length = response.headers.get("content-length")
                if raw_length:
                    try:
                        if int(raw_length) > max_response_bytes:
                            raise ResponseTooLarge(f"Upstream response exceeds max_response_bytes={max_response_bytes}")
                    except ValueError:
                        pass
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if max_response_bytes is not None and total > max_response_bytes:
                    raise ResponseTooLarge(f"Upstream response exceeds max_response_bytes={max_response_bytes}")
                chunks.append(chunk)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
                request=request,
                extensions=response.extensions,
            )
        finally:
            await response.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 2,
        retry_non_idempotent: bool = False,
        max_response_bytes: int | None = None,
        **kwargs,
    ) -> httpx.Response:
        method = method.upper()
        host = httpx.URL(url).host or "unknown"
        state = self.states.setdefault(host, CircuitState())
        now = time.monotonic()
        if state.opened_at is not None and now - state.opened_at < self.reset_seconds:
            raise RuntimeError(f"Circuit open for {host}")
        if state.opened_at is not None:
            state.opened_at = None
            state.failures = 0

        configured_retries = max(0, int(retries))
        effective_retries = configured_retries if method in _IDEMPOTENT_METHODS or retry_non_idempotent else 0
        last: Exception | None = None

        for attempt in range(effective_retries + 1):
            response: httpx.Response | None = None
            try:
                response = await self._send_once(method, url, max_response_bytes=max_response_bytes, **kwargs)
                if response.status_code not in _RETRYABLE_STATUS:
                    response.raise_for_status()
                    state.failures = 0
                    return response
                response.raise_for_status()
                state.failures = 0
                return response
            except ResponseTooLarge:
                # Size is a policy failure, not a transient upstream outage.
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    raise
                last = exc
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = exc

            state.failures += 1
            if state.failures >= self.failure_threshold:
                state.opened_at = time.monotonic()
            if attempt < effective_retries:
                await asyncio.sleep(self._retry_delay(attempt, response))

        assert last is not None
        raise last

    async def close(self):
        await self.client.aclose()
