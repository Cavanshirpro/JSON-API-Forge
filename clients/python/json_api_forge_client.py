from __future__ import annotations

from typing import Any
import httpx


class ForgeAPIError(RuntimeError):
    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"Forge API error {status_code}: {payload}")
        self.status_code = status_code
        self.payload = payload


class ForgeClient:
    """Small async client used by desktop apps, Discord bots, plugins and game servers."""
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def request(self, method: str, path: str, **kwargs) -> Any:
        response = await self.client.request(method, path, **kwargs)
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        if response.is_error:
            raise ForgeAPIError(response.status_code, payload)
        return payload

    async def rpc(self, name: str, payload: dict[str, Any] | None = None, *, idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self.request("POST", f"/rpc/{name}", json=payload or {}, headers=headers)

    async def list(self, resource: str, **params) -> Any:
        return await self.request("GET", f"/{resource.strip('/')}", params=params)

    async def get(self, resource: str, item_id: Any) -> Any:
        return await self.request("GET", f"/{resource.strip('/')}/{item_id}")

    async def create(self, resource: str, payload: dict[str, Any]) -> Any:
        return await self.request("POST", f"/{resource.strip('/')}", json=payload)

    async def update(self, resource: str, item_id: Any, payload: dict[str, Any]) -> Any:
        return await self.request("PATCH", f"/{resource.strip('/')}/{item_id}", json=payload)

    async def delete(self, resource: str, item_id: Any) -> Any:
        return await self.request("DELETE", f"/{resource.strip('/')}/{item_id}")

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
