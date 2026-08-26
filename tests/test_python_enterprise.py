from __future__ import annotations

import asyncio
import json
import sys
import types
from collections import Counter
from pathlib import Path

import httpx
import pytest

from json_api_forge import (
    AsyncForgeClient,
    AsyncForgeCluster,
    CircuitBreakerPolicy,
    ForgeClient,
    ForgeCluster,
    ForgeEndpoint,
    ForgeHTTPError,
    ForgeTransportError,
    RetryPolicy,
    RoutingStrategy,
)
from json_api_forge.integrations import AsyncDDMForgeClient, YoungLionForgeClient, as_ddm, ddm_available


def _no_wait_retry(attempts: int = 3) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=attempts,
        backoff_seconds=0,
        max_backoff_seconds=0,
        jitter_ratio=0,
    )


def test_retry_policy_preserves_request_identity_and_observes_attempts() -> None:
    seen_ids: list[str] = []
    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_ids.append(request.headers["X-Request-ID"])
        status = 503 if len(seen_ids) == 1 else 200
        return httpx.Response(status, json={"attempt": len(seen_ids)})

    with ForgeClient(
        "https://forge.test",
        transport=httpx.MockTransport(handler),
        retry_policy=_no_wait_retry(),
        observer=observed.append,
    ) as client:
        response = client.request("GET", "health")

    assert response.data == {"attempt": 2}
    assert len(set(seen_ids)) == 1
    assert [event.status_code for event in observed] == [503, 200]
    assert [event.attempt for event in observed] == [1, 2]


@pytest.mark.parametrize("idempotency_key,expected_calls", [(None, 1), ("order-42", 2)])
def test_unsafe_request_retry_requires_idempotency_key(idempotency_key: str | None, expected_calls: int) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"detail": "busy"})

    with ForgeClient(
        "https://forge.test",
        transport=httpx.MockTransport(handler),
        retry_policy=_no_wait_retry(2),
    ) as client:
        with pytest.raises(ForgeHTTPError):
            client.request("POST", "api/demo/v1/orders", json_body={}, idempotency_key=idempotency_key)
    assert calls == expected_calls


def test_iter_items_is_bounded_and_ordered() -> None:
    source = [{"id": index} for index in range(8)]
    requested_offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        requested_offsets.append(offset)
        return httpx.Response(200, json={"items": source[offset : offset + limit]})

    with ForgeClient("https://forge.test", transport=httpx.MockTransport(handler)) as client:
        items = list(client.iter_items("demo", "records", page_size=3, max_items=7))

    assert items == source[:7]
    assert requested_offsets == [0, 3, 6]


def test_cluster_fails_over_and_opens_failed_endpoint_circuit() -> None:
    calls: Counter[str] = Counter()

    def factory(endpoint: ForgeEndpoint) -> ForgeClient:
        def handler(request: httpx.Request) -> httpx.Response:
            calls[endpoint.name] += 1
            if endpoint.name == "primary":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(200, json={"endpoint": endpoint.name})

        return ForgeClient(endpoint.base_url, transport=httpx.MockTransport(handler))

    endpoints = [ForgeEndpoint("primary", "https://primary.test"), ForgeEndpoint("secondary", "https://secondary.test")]
    with ForgeCluster(
        endpoints,
        circuit_breaker=CircuitBreakerPolicy(failure_threshold=1, recovery_seconds=60),
        client_factory=factory,
    ) as cluster:
        first = cluster.request("GET", "health")
        second = cluster.request("GET", "health")

    assert first.data == {"endpoint": "secondary"}
    assert second.data == {"endpoint": "secondary"}
    assert calls == Counter(primary=1, secondary=2)


def test_cluster_never_fails_over_unsafe_request_without_idempotency_key() -> None:
    calls: Counter[str] = Counter()

    def factory(endpoint: ForgeEndpoint) -> ForgeClient:
        def handler(request: httpx.Request) -> httpx.Response:
            calls[endpoint.name] += 1
            if endpoint.name == "primary":
                raise httpx.ConnectError("write outcome is unknown", request=request)
            return httpx.Response(201, json={"created": True})

        return ForgeClient(endpoint.base_url, transport=httpx.MockTransport(handler))

    endpoints = [ForgeEndpoint("primary", "https://primary.test"), ForgeEndpoint("secondary", "https://secondary.test")]
    with ForgeCluster(endpoints, client_factory=factory) as cluster:
        with pytest.raises(ForgeTransportError, match="write outcome is unknown"):
            cluster.request("POST", "api/demo/v1/jobs", json_body={"name": "one"})

    assert calls == Counter(primary=1)


def test_cluster_idempotent_failover_preserves_request_id() -> None:
    request_ids: list[str] = []

    def factory(endpoint: ForgeEndpoint) -> ForgeClient:
        def handler(request: httpx.Request) -> httpx.Response:
            request_ids.append(request.headers["X-Request-ID"])
            if endpoint.name == "primary":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(201, json={"created": True})

        return ForgeClient(endpoint.base_url, transport=httpx.MockTransport(handler))

    endpoints = [ForgeEndpoint("primary", "https://primary.test"), ForgeEndpoint("secondary", "https://secondary.test")]
    with ForgeCluster(endpoints, client_factory=factory) as cluster:
        response = cluster.request(
            "POST",
            "api/demo/v1/jobs",
            json_body={"name": "one"},
            idempotency_key="job-one",
        )

    assert response.data == {"created": True}
    assert len(request_ids) == 2
    assert len(set(request_ids)) == 1


def test_rendezvous_routing_is_stable_for_a_tenant() -> None:
    def factory(endpoint: ForgeEndpoint) -> ForgeClient:
        return ForgeClient(
            endpoint.base_url,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"endpoint": endpoint.name})),
        )

    endpoints = [
        ForgeEndpoint("eu", "https://eu.test"),
        ForgeEndpoint("us", "https://us.test"),
        ForgeEndpoint("ap", "https://ap.test"),
    ]
    with ForgeCluster(endpoints, strategy=RoutingStrategy.RENDEZVOUS, client_factory=factory) as cluster:
        selected = {cluster.request("GET", "health", routing_key="tenant-acme").data["endpoint"] for _ in range(12)}
    assert len(selected) == 1


def test_bulk_create_preserves_input_order_and_captures_item_failures() -> None:
    def factory(endpoint: ForgeEndpoint) -> ForgeClient:
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            if payload["sequence"] == 2:
                return httpx.Response(422, json={"detail": "invalid row"})
            return httpx.Response(201, json=payload)

        return ForgeClient(endpoint.base_url, transport=httpx.MockTransport(handler))

    with ForgeCluster([ForgeEndpoint("only", "https://forge.test")], client_factory=factory) as cluster:
        results = cluster.bulk_create(
            "enterprise",
            "records",
            ({"sequence": sequence} for sequence in range(5)),
            max_workers=3,
            idempotency_key=lambda index, _payload: f"row-{index}",
        )

    assert [result.index for result in results] == list(range(5))
    assert [result.succeeded for result in results] == [True, True, False, True, True]
    assert isinstance(results[2].error, ForgeHTTPError)


def test_bulk_helpers_reject_unbounded_input() -> None:
    client = ForgeClient("https://forge.test", transport=httpx.MockTransport(lambda _: httpx.Response(201, json={})))
    with ForgeCluster([ForgeEndpoint("only", "https://forge.test")], client_factory=lambda _: client) as cluster:
        with pytest.raises(ValueError, match="max_items"):
            cluster.bulk_create("demo", "records", ({"id": value} for value in range(3)), max_items=2)


def test_cluster_helpers_reject_unsafe_path_segments() -> None:
    client = ForgeClient("https://forge.test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
    with ForgeCluster([ForgeEndpoint("only", "https://forge.test")], client_factory=lambda _: client) as cluster:
        with pytest.raises(ValueError, match="unsafe"):
            cluster.call_operation("../admin", "publish", {})


def test_async_cluster_failover_bulk_and_operation() -> None:
    async def run() -> None:
        calls: Counter[str] = Counter()

        def factory(endpoint: ForgeEndpoint) -> AsyncForgeClient:
            async def handler(request: httpx.Request) -> httpx.Response:
                calls[endpoint.name] += 1
                if endpoint.name == "primary":
                    raise httpx.ConnectError("offline", request=request)
                return httpx.Response(200, json={"path": request.url.path})

            return AsyncForgeClient(endpoint.base_url, transport=httpx.MockTransport(handler))

        endpoints = [ForgeEndpoint("primary", "https://primary.test"), ForgeEndpoint("secondary", "https://secondary.test")]
        async with AsyncForgeCluster(
            endpoints,
            circuit_breaker=CircuitBreakerPolicy(failure_threshold=1, recovery_seconds=60),
            client_factory=factory,
        ) as cluster:
            response = await cluster.call_operation("project one", "rebuild", {"scope": "all"}, idempotency_key="job-1")

            async def value(index: int) -> int:
                await asyncio.sleep(0)
                if index == 2:
                    raise ValueError("bad item")
                return index * 2

            bulk = await cluster.bulk((lambda index=index: value(index) for index in range(4)), concurrency=2)

        assert response.data["path"].endswith("/api/project one/v1/rpc/rebuild")
        assert [item.value for item in bulk] == [0, 2, None, 6]
        assert isinstance(bulk[2].error, ValueError)
        assert calls["primary"] == 1

    asyncio.run(run())


def test_younglion_ddm_integration_is_lazy_and_recursive(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDDM:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return self.value

    fake_module = types.ModuleType("YoungLion")
    fake_module.DDM = FakeDDM
    monkeypatch.setitem(sys.modules, "YoungLion", fake_module)

    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"saved": bodies[-1]})

    assert ddm_available()
    assert isinstance(as_ddm({"ok": True}), FakeDDM)
    raw = ForgeClient("https://forge.test", transport=httpx.MockTransport(handler))
    with YoungLionForgeClient(raw) as client:
        response = client.create_item("demo", "events", FakeDDM({"nested": FakeDDM({"id": 7})}))

    assert bodies == [{"nested": {"id": 7}}]
    assert isinstance(response.data, FakeDDM)
    assert response.data.to_dict() == {"saved": {"nested": {"id": 7}}}


def test_async_ddm_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDDM:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return self.value

    fake_module = types.ModuleType("YoungLion")
    fake_module.DDM = FakeDDM
    monkeypatch.setitem(sys.modules, "YoungLion", fake_module)

    async def run() -> None:
        raw = AsyncForgeClient(
            "https://forge.test",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True})),
        )
        async with AsyncDDMForgeClient(raw) as client:
            response = await client.call_operation("demo", "refresh", FakeDDM({"id": 1}))
        assert isinstance(response.data, FakeDDM)

    asyncio.run(run())


def test_optional_dependencies_target_current_younglion_line() -> None:
    import tomllib

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["optional-dependencies"]["younglion"] == ["YoungLion>=0.1.0,<0.2"]
    assert project["optional-dependencies"]["ddm"] == ["YoungLion>=0.1.0,<0.2"]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RetryPolicy(max_attempts=0),
        lambda: RetryPolicy(backoff_seconds=2, max_backoff_seconds=1),
        lambda: ForgeEndpoint("bad/name", "https://forge.test", weight=0),
        lambda: CircuitBreakerPolicy(failure_threshold=0),
    ],
)
def test_enterprise_option_bounds(factory) -> None:
    with pytest.raises(ValueError):
        factory()


def test_retry_policy_validation_permits_and_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = [
        lambda: RetryPolicy(multiplier=0),
        lambda: RetryPolicy(jitter_ratio=2),
        lambda: RetryPolicy(retry_statuses=frozenset({399})),
    ]
    for factory in invalid:
        with pytest.raises(ValueError):
            factory()

    policy = RetryPolicy(backoff_seconds=1, max_backoff_seconds=3, jitter_ratio=0.5)
    assert policy.permits("GET", idempotency_key=None)
    assert not policy.permits("POST", idempotency_key=None)
    assert policy.permits("POST", idempotency_key="job-1")
    assert policy.delay(1, retry_after="9") == 3
    assert policy.delay(1, retry_after="invalid") >= 0
    monkeypatch.setattr("json_api_forge.options.random.uniform", lambda _low, _high: 0.25)
    assert policy.delay(2) == 2.25
    assert RetryPolicy(backoff_seconds=0, max_backoff_seconds=0).delay(1) == 0
