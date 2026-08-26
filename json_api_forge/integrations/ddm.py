from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..client import AsyncForgeClient, ForgeClient, _segment
from ..errors import ForgeIntegrationError
from ..models import ForgeResponse


def _ddm_type():
    try:
        from YoungLion import DDM
    except ImportError as exc:
        raise ForgeIntegrationError("YoungLion DDM is not installed; use 'pip install json-api-forge-client[ddm]'") from exc
    return DDM


def ddm_available() -> bool:
    try:
        _ddm_type()
    except ForgeIntegrationError:
        return False
    return True


def _plain(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if converted is value:
            raise ForgeIntegrationError("YoungLion DDM.to_dict() returned the original object")
        return _plain(converted)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def as_ddm(value: Any):
    DDM = _ddm_type()
    if isinstance(value, DDM):
        return value
    if isinstance(value, Mapping):
        return DDM(dict(value))
    return DDM({"value": value})


class DDMForgeClient:
    """YoungLion DDM conversion facade over a normal sync Forge client."""

    def __init__(self, client: ForgeClient):
        self.client = client

    def request(self, method: str, path: str, **kwargs: Any) -> ForgeResponse[Any]:
        if "json_body" in kwargs:
            kwargs["json_body"] = _plain(kwargs["json_body"])
        response = self.client.request(method, path, **kwargs)
        return ForgeResponse(
            data=as_ddm(response.data),
            status_code=response.status_code,
            request_id=response.request_id,
            idempotent_replay=response.idempotent_replay,
            cache_status=response.cache_status,
        )

    def call_operation(self, project: str, operation: str, payload: Any, *, idempotency_key: str | None = None):
        return self.request(
            "POST",
            f"api/{_segment(project)}/v1/rpc/{_segment(operation)}",
            json_body=_plain(payload),
            idempotency_key=idempotency_key,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> DDMForgeClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


class AsyncDDMForgeClient:
    def __init__(self, client: AsyncForgeClient):
        self.client = client

    async def request(self, method: str, path: str, **kwargs: Any) -> ForgeResponse[Any]:
        if "json_body" in kwargs:
            kwargs["json_body"] = _plain(kwargs["json_body"])
        response = await self.client.request(method, path, **kwargs)
        return ForgeResponse(
            data=as_ddm(response.data),
            status_code=response.status_code,
            request_id=response.request_id,
            idempotent_replay=response.idempotent_replay,
            cache_status=response.cache_status,
        )

    async def call_operation(self, project: str, operation: str, payload: Any, *, idempotency_key: str | None = None):
        return await self.request(
            "POST",
            f"api/{_segment(project)}/v1/rpc/{_segment(operation)}",
            json_body=_plain(payload),
            idempotency_key=idempotency_key,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> AsyncDDMForgeClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        await self.aclose()
