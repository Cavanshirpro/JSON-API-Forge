from __future__ import annotations

import httpx
import pytest

from clients.python.json_api_forge_client import ForgeAPIError, ForgeClient


@pytest.mark.parametrize(
    "url,allow_http",
    [
        ("http://api.example.com", True),
        ("https://user:secret@api.example.com", False),
        ("https://api.example.com/base/../admin", False),
        ("https://api.example.com?token=secret", False),
    ],
)
def test_reference_client_rejects_unsafe_base_urls(url: str, allow_http: bool) -> None:
    with pytest.raises(ValueError):
        ForgeClient(url, "test-key", allow_http=allow_http)


@pytest.mark.asyncio
async def test_reference_client_keeps_credentials_on_the_configured_origin() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async with ForgeClient(
        "https://api.example.com/api/tasks/v1",
        "test-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert await client.get("tasks", "item 1") == {"ok": True}
        with pytest.raises(ValueError):
            await client.request("GET", "https://attacker.invalid/collect")

    assert str(seen[0].url) == "https://api.example.com/api/tasks/v1/tasks/item%201"
    assert seen[0].headers["X-API-Key"] == "test-key"


@pytest.mark.asyncio
async def test_reference_client_rejects_redirects_and_large_responses() -> None:
    responses = iter(
        [
            httpx.Response(302, headers={"Location": "https://attacker.invalid/collect"}),
            httpx.Response(200, content=b"x" * 1025),
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    async with ForgeClient(
        "https://api.example.com",
        "test-key",
        max_response_bytes=1024,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ForgeAPIError) as redirect:
            await client.request("GET", "/health")
        assert redirect.value.status_code == 302
        with pytest.raises(ForgeAPIError, match="size limit"):
            await client.request("GET", "/health")
