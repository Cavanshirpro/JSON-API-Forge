from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..client import ForgeClient, _route, _segment
from .ddm import DDMForgeClient, _plain


class YoungLionForgeClient(DDMForgeClient):
    """DDM-native facade intended for large YoungLion-backed systems."""

    def create_item(self, project: str, resource: str, payload: Any, *, idempotency_key: str | None = None):
        return self.request(
            "POST",
            f"api/{_segment(project)}/v1/{_route(resource)}",
            json_body=_plain(payload),
            idempotency_key=idempotency_key,
        )

    def update_item(self, project: str, resource: str, item_id: str, payload: Any):
        return self.request(
            "PATCH",
            f"api/{_segment(project)}/v1/{_route(resource)}/{_segment(item_id)}",
            json_body=_plain(payload),
        )

    def list_items(self, project: str, resource: str, *, params: Mapping[str, Any] | None = None):
        return self.request("GET", f"api/{_segment(project)}/v1/{_route(resource)}", params=params)

    @classmethod
    def connect(cls, base_url: str, **kwargs: Any) -> YoungLionForgeClient:
        return cls(ForgeClient(base_url, **kwargs))

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> YoungLionForgeClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
