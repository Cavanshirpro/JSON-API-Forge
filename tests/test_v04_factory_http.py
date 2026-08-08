from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from framework.config import ForgeConfig, ProjectConfig
from framework.protection import ConcurrencyGate
from framework.security import Principal


def _project(**overrides) -> ProjectConfig:
    data = {
        "slug": "p",
        "name": "P",
        "api_prefix": "/api/p/v1",
        "databases": {"primary": {"url": "sqlite+aiosqlite:///:memory:"}},
        "security": {"jwt_enabled": False},
        "cors_origins": ["https://client.example"],
        "cors_methods": ["GET", "POST", "OPTIONS"],
        "cors_headers": ["X-API-Key", "Content-Type", "X-Request-ID"],
        "cors_expose_headers": ["X-Request-ID", "X-Forge-Cache"],
        "rate_limit": {
            "enabled": True,
            "pre_auth_enabled": True,
            "pre_auth_requests": 1000,
            "pre_auth_window_seconds": 60,
            "requests": 100,
            "window_seconds": 60,
            "route_requests": 50,
            "route_window_seconds": 60,
        },
        "protection": {
            "max_request_body_bytes": 1024,
            "trusted_hosts": ["api.example"],
            "trusted_proxy_cidrs": ["10.0.0.0/8"],
            "gzip_minimum_size": 1024,
            "request_timeout_seconds": 2.0,
        },
        "observability": {"metrics_enabled": True, "metrics_path": "/metrics"},
    }
    for key, value in overrides.items():
        if key in {"security", "protection", "rate_limit", "observability"}:
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return ProjectConfig.model_validate(data)


class FakeLimiter:
    def __init__(self):
        self.calls = []
        self.fail = None

    async def check(self, identity, limit, window, burst=None):
        self.calls.append((identity, limit, window, burst))
        if self.fail:
            raise self.fail

    async def ping(self):
        return True

    async def close(self):
        return None


class FakeConn:
    def __init__(self, fail=False):
        self.fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        if self.fail:
            raise RuntimeError("db down")
        return None


class FakeDbEngine:
    def __init__(self, fail=False):
        self.fail = fail
        self.disposed = False

    def connect(self):
        return FakeConn(self.fail)

    async def dispose(self):
        self.disposed = True


class FakeAudit:
    def __init__(self, engine):
        self.engine = engine
        self.items = []
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    def submit(self, **item):
        self.items.append(item)

    async def close(self):
        self.closed = True


class FakeManager:
    last = None

    def __init__(self, forge):
        from framework.runtime import ProjectRuntime

        self.forge = forge
        self.runtimes = {}
        for project in forge.projects:
            runtime = ProjectRuntime(config=project)
            runtime.limiter = FakeLimiter()
            runtime.gate = ConcurrencyGate(8, 0.2, True)
            runtime.registry = SimpleNamespace(engines={"primary": FakeDbEngine()})
            runtime.mongo_registry = None
            runtime.cache = SimpleNamespace(ping=self._ok_ping)
            runtime.event_hub = SimpleNamespace(ping=self._ok_ping)
            self.runtimes[project.slug] = runtime
        self.started = False
        self.closed = False
        FakeManager.last = self

    async def _ok_ping(self):
        return True

    def for_path(self, path):
        for runtime in self.runtimes.values():
            prefix = runtime.config.api_prefix.rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return runtime
        return None

    def body_limit_for_path(self, path):
        runtime = self.for_path(path)
        return runtime.config.protection.max_request_body_bytes if runtime else None

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True


def _install_factory_fakes(monkeypatch, project: ProjectConfig):
    import framework.factory as factory

    forge = ForgeConfig(projects=[project])
    internal_engine = FakeDbEngine()

    monkeypatch.setattr(factory, "load_config", lambda *_a, **_k: forge)
    monkeypatch.setattr(factory, "ensure_no_errors", lambda *_a, **_k: [])
    monkeypatch.setattr(factory, "expand_feature_packs", lambda _p: None)
    monkeypatch.setattr(factory, "RuntimeManager", FakeManager)
    monkeypatch.setattr(factory, "create_async_engine", lambda *_a, **_k: internal_engine)

    async def init_security(*_a, **_k):
        return None

    monkeypatch.setattr(factory, "init_security", init_security)
    monkeypatch.setattr(factory, "AuditWriter", FakeAudit)
    monkeypatch.setattr(factory, "metrics_payload", lambda: (b"forge_metric 1\n", "text/plain; version=0.0.4"))
    monkeypatch.setattr(factory, "observe", lambda *_a, **_k: None)

    async def auth(request, cfg, engine):
        key = request.headers.get("X-API-Key")
        if key == "good":
            return Principal(kind="api_key", subject="api-key:1:good", roles=set(), permissions={"probe.read"})
        if key == "limited":
            return Principal(
                kind="api_key", subject="api-key:2:limited", roles=set(), permissions=set(),
                rate_requests=7, rate_window_seconds=30, rate_burst=2,
            )
        return Principal(kind="anonymous", subject="anonymous", roles=set(), permissions=set())

    monkeypatch.setattr(factory, "authenticate_request", auth)

    def register_routes(*, app, runtime, principal_for, require, **_kwargs):
        prefix = runtime.config.api_prefix.rstrip("/")

        @app.get(prefix + "/probe")
        async def probe(request: Request):
            p = await principal_for(request, runtime)
            require(p, "probe.read")
            request.state.forge_cache = "hit"
            request.state.forge_idempotent_replay = True
            return {"subject": p.subject}

        @app.get(prefix + "/private")
        async def private(request: Request):
            p = await principal_for(request, runtime)
            require(p, "probe.read")
            return {"ok": True}

        @app.post(prefix + "/echo")
        async def echo(request: Request):
            await principal_for(request, runtime)
            return {"size": len(await request.body())}

    monkeypatch.setattr(factory, "register_project_routes", register_routes)

    # Keep factory settings isolated from the real environment.
    monkeypatch.setattr(factory.settings, "internal_database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(factory.settings, "internal_schema_mode", "create")
    monkeypatch.setattr(factory.settings, "operator_token", "operator-secret")
    monkeypatch.setattr(factory.settings, "app_env", "development")
    return factory, internal_engine


def test_factory_http_security_cors_headers_rate_limits_and_global_docs(monkeypatch):
    project = _project()
    factory, internal_engine = _install_factory_fakes(monkeypatch, project)
    app = factory.create_app(apps_dir="unused")

    with TestClient(app, base_url="http://api.example") as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404

        unauth = client.get("/api/p/v1/private")
        assert unauth.status_code == 401
        forbidden = client.get("/api/p/v1/private", headers={"X-API-Key": "limited"})
        assert forbidden.status_code == 403

        response = client.get(
            "/api/p/v1/probe",
            headers={"X-API-Key": "good", "Origin": "https://client.example", "X-Request-ID": "req-123"},
        )
        assert response.status_code == 200
        assert response.json()["subject"] == "api-key:1:good"
        assert response.headers["x-request-id"] == "req-123"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-forge-cache"] == "hit"
        assert response.headers["x-forge-idempotent-replay"] == "true"
        assert response.headers["access-control-allow-origin"] == "https://client.example"
        assert "Origin" in response.headers["vary"]

        preflight = client.options(
            "/api/p/v1/probe",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-API-Key",
            },
        )
        assert preflight.status_code == 204
        assert "GET" in preflight.headers["access-control-allow-methods"]

        assert client.options(
            "/api/p/v1/probe",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
        ).status_code == 403
        assert client.options(
            "/api/p/v1/probe",
            headers={"Origin": "https://client.example", "Access-Control-Request-Method": "DELETE"},
        ).status_code == 403
        assert client.options(
            "/api/p/v1/probe",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Not-Allowed",
            },
        ).status_code == 403

        # Project-specific Host policy is enforced before authentication.
        bad_host = client.get("/api/p/v1/probe", headers={"host": "other.example", "X-API-Key": "good"})
        assert bad_host.status_code == 400

        # The streaming body guard rejects actual bytes, not only Content-Length.
        too_big = client.post("/api/p/v1/echo", content=b"x" * 2048, headers={"X-API-Key": "good"})
        assert too_big.status_code == 413

        # Rate limiter identities include pre-auth, principal-global and normalized route budgets.
        calls = FakeManager.last.runtimes["p"].limiter.calls
        identities = [item[0] for item in calls]
        assert any(":preauth:ip:" in value for value in identities)
        assert "p:api_key:api-key:1:good:global" in identities
        assert "p:api_key:api-key:1:good:route:GET:/api/p/v1/probe" in identities
        limited_global = [item for item in calls if item[0] == "p:api_key:api-key:2:limited:global"]
        assert limited_global and limited_global[-1][1:4] == (7, 30, 2)

        assert client.get("/metrics").status_code == 401
        metrics = client.get("/metrics", headers={"X-Forge-Operator-Token": "operator-secret"})
        assert metrics.status_code == 200 and b"forge_metric" in metrics.content

    assert FakeManager.last.started and FakeManager.last.closed
    assert internal_engine.disposed is True


def test_factory_readiness_redaction_operator_detail_https_and_limiter_failure(monkeypatch):
    project = _project(security={"require_https": True}, rate_limit={"fail_open": False})
    factory, _ = _install_factory_fakes(monkeypatch, project)
    app = factory.create_app(apps_dir="unused")

    with TestClient(app, base_url="http://api.example") as client:
        assert client.get("/api/p/v1/probe", headers={"X-API-Key": "good"}).status_code == 400

        # A trusted proxy may assert HTTPS; an untrusted one may not.
        proxied = client.get(
            "/api/p/v1/probe",
            headers={"X-API-Key": "good", "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.5"},
        )
        # TestClient direct peer is not in trusted CIDRs, so spoofed headers are ignored.
        assert proxied.status_code == 400

        runtime = FakeManager.last.runtimes["p"]
        runtime.registry.engines["primary"].fail = True
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json() == {"status": "degraded"}
        detailed = client.get("/ready", headers={"Authorization": "Bearer operator-secret"})
        assert detailed.status_code == 503
        assert detailed.json()["projects"]["p"]["databases"]["primary"] == "error:RuntimeError"

        runtime.registry.engines["primary"].fail = False
        runtime.config.security.require_https = False
        runtime.limiter.fail = RuntimeError("redis down")
        unavailable = client.get("/api/p/v1/probe", headers={"X-API-Key": "good"})
        assert unavailable.status_code == 503
        assert unavailable.headers["retry-after"] == "1"


def test_factory_fails_open_limiter_and_process_wide_config_conflicts(monkeypatch):
    project = _project(rate_limit={"fail_open": True})
    factory, _ = _install_factory_fakes(monkeypatch, project)
    app = factory.create_app(apps_dir="unused")
    with TestClient(app, base_url="http://api.example") as client:
        runtime = FakeManager.last.runtimes["p"]
        runtime.limiter.fail = RuntimeError("down")
        assert client.get("/api/p/v1/probe", headers={"X-API-Key": "good"}).status_code == 200

    # GZip and metrics are process-wide; incompatible project choices fail fast.
    p1 = _project(slug="a", name="A", api_prefix="/api/a/v1", protection={"gzip_minimum_size": 100}, observability={"metrics_path": "/m"})
    p2 = _project(slug="b", name="B", api_prefix="/api/b/v1", protection={"gzip_minimum_size": 200}, observability={"metrics_path": "/m"})
    monkeypatch.setattr(factory, "load_config", lambda *_a, **_k: ForgeConfig(projects=[p1, p2]))
    with pytest.raises(RuntimeError, match="gzip_minimum_size"):
        factory.create_app(apps_dir="unused")

    p2 = _project(slug="b", name="B", api_prefix="/api/b/v1", protection={"gzip_minimum_size": 100}, observability={"metrics_path": "/other"})
    monkeypatch.setattr(factory, "load_config", lambda *_a, **_k: ForgeConfig(projects=[p1, p2]))
    with pytest.raises(RuntimeError, match="metrics_path"):
        factory.create_app(apps_dir="unused")
