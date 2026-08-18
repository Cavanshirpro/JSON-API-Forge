from __future__ import annotations

import asyncio
import ipaddress
import json
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

from .errors import ForgeHTTPError, ForgeResponseTooLarge, ForgeTransportError
from .models import ForgeResponse, JsonObject, RequestAttempt
from .options import RetryPolicy

_JSON_ACCEPT = "application/json"


def _notify(observer: Callable[[RequestAttempt], None] | None, event: RequestAttempt) -> None:
    if observer is None:
        return
    try:
        observer(event)
    except Exception:
        # Observability must not change application request semantics.
        return


def _base_url(value: str, *, allow_insecure_http: bool) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    try:
        loopback = host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or "\\" in value or "\0" in value:
        raise ValueError("base_url must be an absolute HTTP(S) URL without embedded credentials")
    if parsed.scheme == "http" and not (allow_insecure_http and loopback):
        raise ValueError("plain HTTP requires allow_insecure_http=True and a loopback host")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain a query or fragment")
    decoded_parts = unquote(parsed.path).split("/")
    if any(part in {".", ".."} for part in decoded_parts):
        raise ValueError("base_url must not contain traversal segments")
    return value.rstrip("/") + "/"


def _relative_path(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith("//") or "\\" in value or "\0" in value:
        raise ValueError("request path must be relative to the configured Forge server")
    if parsed.fragment:
        raise ValueError("request path must not contain a fragment")
    parts = [part for part in unquote(parsed.path).split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError("request path must not contain traversal segments")
    normalized = "/".join(parts)
    return normalized + (f"?{parsed.query}" if parsed.query else "")


def _segment(value: str) -> str:
    if not value or value in {".", ".."} or any(ch in value for ch in "/\\\r\n\0"):
        raise ValueError("path segment is empty or unsafe")
    return quote(value, safe="-._~")


def _route(value: str) -> str:
    parts = value.split("/")
    if not parts or any(not part for part in parts):
        raise ValueError("route must contain non-empty path segments")
    return "/".join(_segment(part) for part in parts)


def _headers(
    api_key: str | None,
    request_id: str | None,
    idempotency_key: str | None,
    extra: Mapping[str, str] | None,
) -> dict[str, str]:
    values = {"Accept": _JSON_ACCEPT, "X-Request-ID": request_id or str(uuid.uuid4())}
    if api_key:
        values["X-API-Key"] = api_key
    if idempotency_key:
        if len(idempotency_key) > 256 or any(ch in idempotency_key for ch in "\r\n\0"):
            raise ValueError("idempotency_key is too long or contains control characters")
        values["Idempotency-Key"] = idempotency_key
    for name, value in (extra or {}).items():
        if any(ch in name or ch in value for ch in "\r\n\0"):
            raise ValueError("header names and values cannot contain control line breaks or NUL")
        values[name] = value
    return values


def _decode_response(response: httpx.Response, content: bytes, *, expect_json: bool) -> ForgeResponse[Any]:
    detail: Any
    try:
        decoded = json.loads(content) if content else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded = None
    if response.is_redirect:
        raise ForgeHTTPError(
            response.status_code,
            "Redirects are disabled to keep credentials on the configured origin",
            response.headers.get("X-Request-ID"),
            response.headers.get("Retry-After"),
        )
    if response.is_error:
        if isinstance(decoded, dict) and "detail" in decoded:
            detail = decoded["detail"]
        elif decoded is not None:
            detail = decoded
        else:
            detail = content.decode("utf-8", errors="replace")[:2048] or response.reason_phrase
        raise ForgeHTTPError(
            response.status_code,
            detail,
            response.headers.get("X-Request-ID"),
            response.headers.get("Retry-After"),
        )
    if expect_json and decoded is None and content:
        raise ForgeHTTPError(response.status_code, "Server returned non-JSON content", response.headers.get("X-Request-ID"))
    data = decoded if expect_json else content
    return ForgeResponse(
        data=data,
        status_code=response.status_code,
        request_id=response.headers.get("X-Request-ID"),
        idempotent_replay=response.headers.get("X-Forge-Idempotent-Replay", "").lower() == "true",
        cache_status=response.headers.get("X-Forge-Cache"),
    )


def _bounded_content(response: httpx.Response, max_response_bytes: int) -> bytes:
    raw_length = response.headers.get("Content-Length")
    if raw_length:
        try:
            if int(raw_length) > max_response_bytes:
                raise ForgeResponseTooLarge(f"Response exceeds max_response_bytes={max_response_bytes}")
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_response_bytes:
            raise ForgeResponseTooLarge(f"Response exceeds max_response_bytes={max_response_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


async def _bounded_content_async(response: httpx.Response, max_response_bytes: int) -> bytes:
    raw_length = response.headers.get("Content-Length")
    if raw_length:
        try:
            if int(raw_length) > max_response_bytes:
                raise ForgeResponseTooLarge(f"Response exceeds max_response_bytes={max_response_bytes}")
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_response_bytes:
            raise ForgeResponseTooLarge(f"Response exceeds max_response_bytes={max_response_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


class ForgeClient:
    """Synchronous, bounded client for one JSON API Forge server."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        max_response_bytes: int = 8 * 1024 * 1024,
        allow_insecure_http: bool = False,
        transport: httpx.BaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        observer: Callable[[RequestAttempt], None] | None = None,
    ):
        if api_key is not None and (not api_key or len(api_key) > 4096 or any(ch in api_key for ch in "\r\n\0")):
            raise ValueError("api_key must be non-empty, at most 4096 characters, and contain no control line breaks or NUL")
        if int(max_response_bytes) < 1024:
            raise ValueError("max_response_bytes must be at least 1024")
        self.api_key = api_key
        self.max_response_bytes = int(max_response_bytes)
        self.retry_policy = retry_policy
        self.observer = observer
        self._client = httpx.Client(
            base_url=_base_url(base_url, allow_insecure_http=allow_insecure_http),
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        expect_json: bool = True,
    ) -> ForgeResponse[Any]:
        normalized_method = method.upper()
        normalized_path = _relative_path(path)
        effective_request_id = request_id or str(uuid.uuid4())
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                with self._client.stream(
                    normalized_method,
                    normalized_path,
                    json=json_body,
                    params=params,
                    headers=_headers(self.api_key, effective_request_id, idempotency_key, headers),
                ) as response:
                    content = _bounded_content(response, self.max_response_bytes)
                result = _decode_response(response, content, expect_json=expect_json)
            except ForgeResponseTooLarge as exc:
                _notify(
                    self.observer,
                    RequestAttempt(normalized_method, normalized_path, attempt, time.monotonic() - started, None, None, str(exc)),
                )
                raise
            except ForgeHTTPError as exc:
                _notify(
                    self.observer,
                    RequestAttempt(
                        normalized_method,
                        normalized_path,
                        attempt,
                        time.monotonic() - started,
                        exc.status_code,
                        exc.request_id,
                        str(exc),
                    ),
                )
                policy = self.retry_policy
                if (
                    policy is None
                    or attempt >= policy.max_attempts
                    or exc.status_code not in policy.retry_statuses
                    or not policy.permits(normalized_method, idempotency_key=idempotency_key)
                ):
                    raise
                time.sleep(policy.delay(attempt, retry_after=exc.retry_after))
                continue
            except httpx.HTTPError as exc:
                wrapped = ForgeTransportError(str(exc))
                _notify(
                    self.observer,
                    RequestAttempt(normalized_method, normalized_path, attempt, time.monotonic() - started, None, None, str(wrapped)),
                )
                policy = self.retry_policy
                if (
                    policy is None
                    or attempt >= policy.max_attempts
                    or not policy.permits(normalized_method, idempotency_key=idempotency_key)
                ):
                    raise wrapped from exc
                time.sleep(policy.delay(attempt))
                continue
            _notify(
                self.observer,
                RequestAttempt(
                    normalized_method,
                    normalized_path,
                    attempt,
                    time.monotonic() - started,
                    result.status_code,
                    result.request_id,
                    None,
                ),
            )
            return result

    def health(self) -> ForgeResponse[JsonObject]:
        return self.request("GET", "health")

    def metadata(self, project: str) -> ForgeResponse[JsonObject]:
        return self.request("GET", f"api/{_segment(project)}/v1/meta")

    def list_items(self, project: str, resource: str, *, params: Mapping[str, Any] | None = None) -> ForgeResponse[JsonObject]:
        return self.request("GET", f"api/{_segment(project)}/v1/{_route(resource)}", params=params)

    def get_item(self, project: str, resource: str, item_id: str) -> ForgeResponse[JsonObject]:
        return self.request("GET", f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}")

    def create_item(self, project: str, resource: str, payload: Mapping[str, Any], *, idempotency_key: str | None = None):
        return self.request(
            "POST",
            f"api/{_segment(project)}/v1/{_route(resource)}",
            json_body=dict(payload),
            idempotency_key=idempotency_key,
        )

    def update_item(self, project: str, resource: str, item_id: str, payload: Mapping[str, Any], *, replace: bool = False):
        return self.request(
            "PUT" if replace else "PATCH",
            f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}",
            json_body=dict(payload),
        )

    def delete_item(self, project: str, resource: str, item_id: str):
        return self.request("DELETE", f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}")

    def call_operation(self, project: str, operation: str, payload: Mapping[str, Any], *, idempotency_key: str | None = None):
        return self.request(
            "POST",
            f"api/{_segment(project)}/v1/rpc/{_segment(operation)}",
            json_body=dict(payload),
            idempotency_key=idempotency_key,
        )

    def iter_items(
        self,
        project: str,
        resource: str,
        *,
        params: Mapping[str, Any] | None = None,
        page_size: int = 100,
        max_items: int = 10_000,
    ) -> Iterator[JsonObject]:
        if not 1 <= page_size <= 1000 or not 1 <= max_items <= 1_000_000:
            raise ValueError("page_size or max_items is outside the supported bounds")
        offset = 0
        yielded = 0
        base_params = dict(params or {})
        while yielded < max_items:
            page_params = {**base_params, "limit": min(page_size, max_items - yielded), "offset": offset}
            response = self.list_items(project, resource, params=page_params)
            if not isinstance(response.data, dict) or not isinstance(response.data.get("items"), list):
                raise ForgeHTTPError(response.status_code, "List response does not contain an items array", response.request_id)
            items = response.data["items"]
            for item in items:
                if not isinstance(item, dict):
                    raise ForgeHTTPError(response.status_code, "List response contains a non-object item", response.request_id)
                yield item
                yielded += 1
                if yielded >= max_items:
                    return
            if len(items) < page_params["limit"]:
                return
            offset += len(items)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ForgeClient:
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class AsyncForgeClient:
    """Asynchronous, bounded client for one JSON API Forge server."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        max_response_bytes: int = 8 * 1024 * 1024,
        allow_insecure_http: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_policy: RetryPolicy | None = None,
        observer: Callable[[RequestAttempt], None] | None = None,
    ):
        if api_key is not None and (not api_key or len(api_key) > 4096 or any(ch in api_key for ch in "\r\n\0")):
            raise ValueError("api_key must be non-empty, at most 4096 characters, and contain no control line breaks or NUL")
        if int(max_response_bytes) < 1024:
            raise ValueError("max_response_bytes must be at least 1024")
        self.api_key = api_key
        self.max_response_bytes = int(max_response_bytes)
        self.retry_policy = retry_policy
        self.observer = observer
        self._client = httpx.AsyncClient(
            base_url=_base_url(base_url, allow_insecure_http=allow_insecure_http),
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        expect_json: bool = True,
    ) -> ForgeResponse[Any]:
        normalized_method = method.upper()
        normalized_path = _relative_path(path)
        effective_request_id = request_id or str(uuid.uuid4())
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                async with self._client.stream(
                    normalized_method,
                    normalized_path,
                    json=json_body,
                    params=params,
                    headers=_headers(self.api_key, effective_request_id, idempotency_key, headers),
                ) as response:
                    content = await _bounded_content_async(response, self.max_response_bytes)
                result = _decode_response(response, content, expect_json=expect_json)
            except ForgeResponseTooLarge as exc:
                _notify(
                    self.observer,
                    RequestAttempt(normalized_method, normalized_path, attempt, time.monotonic() - started, None, None, str(exc)),
                )
                raise
            except ForgeHTTPError as exc:
                _notify(
                    self.observer,
                    RequestAttempt(
                        normalized_method,
                        normalized_path,
                        attempt,
                        time.monotonic() - started,
                        exc.status_code,
                        exc.request_id,
                        str(exc),
                    ),
                )
                policy = self.retry_policy
                if (
                    policy is None
                    or attempt >= policy.max_attempts
                    or exc.status_code not in policy.retry_statuses
                    or not policy.permits(normalized_method, idempotency_key=idempotency_key)
                ):
                    raise
                await asyncio.sleep(policy.delay(attempt, retry_after=exc.retry_after))
                continue
            except httpx.HTTPError as exc:
                wrapped = ForgeTransportError(str(exc))
                _notify(
                    self.observer,
                    RequestAttempt(normalized_method, normalized_path, attempt, time.monotonic() - started, None, None, str(wrapped)),
                )
                policy = self.retry_policy
                if (
                    policy is None
                    or attempt >= policy.max_attempts
                    or not policy.permits(normalized_method, idempotency_key=idempotency_key)
                ):
                    raise wrapped from exc
                await asyncio.sleep(policy.delay(attempt))
                continue
            _notify(
                self.observer,
                RequestAttempt(
                    normalized_method,
                    normalized_path,
                    attempt,
                    time.monotonic() - started,
                    result.status_code,
                    result.request_id,
                    None,
                ),
            )
            return result

    async def health(self) -> ForgeResponse[JsonObject]:
        return await self.request("GET", "health")

    async def metadata(self, project: str) -> ForgeResponse[JsonObject]:
        return await self.request("GET", f"api/{_segment(project)}/v1/meta")

    async def list_items(self, project: str, resource: str, *, params: Mapping[str, Any] | None = None):
        return await self.request("GET", f"api/{_segment(project)}/v1/{_route(resource)}", params=params)

    async def get_item(self, project: str, resource: str, item_id: str):
        return await self.request("GET", f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}")

    async def create_item(self, project: str, resource: str, payload: Mapping[str, Any], *, idempotency_key: str | None = None):
        return await self.request(
            "POST",
            f"api/{_segment(project)}/v1/{_route(resource)}",
            json_body=dict(payload),
            idempotency_key=idempotency_key,
        )

    async def update_item(self, project: str, resource: str, item_id: str, payload: Mapping[str, Any], *, replace: bool = False):
        return await self.request(
            "PUT" if replace else "PATCH",
            f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}",
            json_body=dict(payload),
        )

    async def delete_item(self, project: str, resource: str, item_id: str):
        return await self.request("DELETE", f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}")

    async def call_operation(self, project: str, operation: str, payload: Mapping[str, Any], *, idempotency_key: str | None = None):
        return await self.request(
            "POST",
            f"api/{_segment(project)}/v1/rpc/{_segment(operation)}",
            json_body=dict(payload),
            idempotency_key=idempotency_key,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncForgeClient:
        return self

    async def __aexit__(self, *_args) -> None:
        await self.aclose()
