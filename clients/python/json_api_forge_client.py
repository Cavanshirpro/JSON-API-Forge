from __future__ import annotations

import ipaddress
from typing import Any, Self
from urllib.parse import quote, unquote, urlsplit

import httpx


class ForgeAPIError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"Forge API error {status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _segment(value: Any, label: str) -> str:
    text = str(value)
    if not text or text in {".", ".."} or any(char in text for char in "/\\\r\n\0"):
        raise ValueError(f"{label} must be one non-empty URL path segment")
    return quote(text, safe="-._~")


class ForgeClient:
    """Small, defensive async reference client for JSON API Forge."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 10.0,
        allow_http: bool = False,
        max_response_bytes: int = 4 * 1024 * 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        parsed = urlsplit(base_url)
        host = parsed.hostname or ""
        if (
            not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and not (allow_http and parsed.scheme == "http" and _is_loopback(host)))
        ):
            raise ValueError("base_url must be HTTPS without credentials/query/fragment; HTTP is loopback-only")
        decoded_parts = unquote(parsed.path).split("/")
        if "\\" in parsed.path or any(part in {".", ".."} for part in decoded_parts):
            raise ValueError("base_url contains an unsafe path segment")
        if not api_key or any(char in api_key for char in "\r\n"):
            raise ValueError("api_key must be non-empty and contain no line breaks")
        if timeout <= 0 or max_response_bytes < 1024:
            raise ValueError("timeout and max_response_bytes must be positive")

        self.base_url = base_url.rstrip("/")
        self.max_response_bytes = max_response_bytes
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        parsed = urlsplit(path)
        decoded_parts = unquote(parsed.path).split("/")
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or "\\" in parsed.path
            or any(part in {".", ".."} for part in decoded_parts)
        ):
            raise ValueError("path must be an absolute-origin path without traversal, query, or fragment")
        if kwargs.get("follow_redirects"):
            raise ValueError("redirect following is disabled to protect credentials")
        response = await self.client.request(method, path, **kwargs)
        if len(response.content) > self.max_response_bytes:
            raise ForgeAPIError(response.status_code, "response exceeded the configured size limit")
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        if response.is_error or response.is_redirect:
            raise ForgeAPIError(response.status_code, payload)
        return payload

    async def rpc(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self.request("POST", f"/rpc/{_segment(name, 'operation name')}", json=payload or {}, headers=headers)

    async def list(self, resource: str, **params: Any) -> Any:
        return await self.request("GET", f"/{_segment(resource, 'resource')}", params=params)

    async def get(self, resource: str, item_id: Any) -> Any:
        return await self.request("GET", f"/{_segment(resource, 'resource')}/{_segment(item_id, 'item id')}")

    async def create(self, resource: str, payload: dict[str, Any]) -> Any:
        return await self.request("POST", f"/{_segment(resource, 'resource')}", json=payload)

    async def update(self, resource: str, item_id: Any, payload: dict[str, Any]) -> Any:
        return await self.request(
            "PATCH",
            f"/{_segment(resource, 'resource')}/{_segment(item_id, 'item id')}",
            json=payload,
        )

    async def delete(self, resource: str, item_id: Any) -> Any:
        return await self.request("DELETE", f"/{_segment(resource, 'resource')}/{_segment(item_id, 'item id')}")

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
