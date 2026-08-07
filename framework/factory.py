from __future__ import annotations

import asyncio
import inspect
import copy
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Body, Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, Response, StreamingResponse
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .audit import AuditWriter
from .cache import build_cache
from .config import CustomEndpointConfig, DataSourceConfig, OperationConfig, ProjectConfig, ResourceConfig, load_config
from .crud import batch_create_rows, count_rows, create_row, delete_row, get_row, list_rows, update_row
from .datasources import DataSourceManager
from .db import build_registry
from .domain import expand_feature_packs
from .events import build_event_hub, sse_encode
from .hooks import import_callable
from .media import build_media_store, delete_media, get_media_meta, make_signed_media_token, save_media, verify_signed_media_token
from .mongo import build_mongo_registry, count_documents, create_document, delete_document, get_document, list_documents, update_document
from .observability import metrics_payload, observe
from .operations import claim_idempotency, complete_idempotency, execute_operation, idempotency_digest, release_idempotency
from .protection import ConcurrencyGate, ip_allowed
from .rate_limit import MemoryRateLimiter, RedisRateLimiter
from .responses import render_response
from .security import authenticate_request, create_api_key, has_permission, init_security, issue_jwt, list_api_keys, revoke_api_key
from .settings import settings
from .validation import openapi_parameters, validate_json_schema, validate_request_parameters

log = logging.getLogger("json_api_forge")


class APIKeyCreate(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
    rate_requests: int | None = Field(default=None, ge=1)
    rate_window_seconds: int | None = Field(default=None, ge=1)
    rate_burst: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None


class JWTCreate(BaseModel):
    subject: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    tenant_id: str | None = None
    exp_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)


@dataclass
class ProjectRuntime:
    config: ProjectConfig
    registry: Any = None
    mongo_registry: Any = None
    limiter: Any = None
    cache: Any = None
    gate: ConcurrencyGate | None = None
    media_store: Any = None
    data_sources: DataSourceManager | None = None
    event_hub: EventHub | None = None


def _resource_namespace(project: ProjectConfig, resource: ResourceConfig) -> str:
    return f"{project.slug}:{resource.database}:{resource.table}"


def _operation_namespace(project: ProjectConfig, operation: OperationConfig) -> str:
    return f"{project.slug}:operation:{operation.name}"


def _data_namespace(project: ProjectConfig, source: DataSourceConfig) -> str:
    return f"{project.slug}:data:{source.name}"


async def _invoke_hook(handler, **kwargs):
    result = handler(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _hide_internal_signature(func):
    """Keep closure-bound `_...` defaults out of FastAPI dependency/query parsing.

    Dynamic route factories bind config/runtime objects through Python defaults. FastAPI would otherwise
    interpret those defaults as public request parameters. The real Python callable keeps the defaults,
    while the signature FastAPI sees contains only client-controlled parameters.
    """
    signature = inspect.signature(func)
    public = [parameter for name, parameter in signature.parameters.items() if not name.startswith("_")]
    func.__signature__ = signature.replace(parameters=public)
    return func


def _hidden_route(route_decorator):
    def register(func):
        return route_decorator(_hide_internal_signature(func))
    return register


def create_app() -> FastAPI:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    forge = load_config()
    for project in forge.projects:
        expand_feature_packs(project)

    runtimes = {p.slug: ProjectRuntime(config=p) for p in forge.projects}
    internal_url = settings.internal_database_url
    if internal_url.startswith("sqlite+aiosqlite:///"):
        db_path = internal_url[len("sqlite+aiosqlite:///"):]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.internal_engine = create_async_engine(internal_url, pool_pre_ping=True)
        await init_security(app.state.internal_engine)
        app.state.audit_writer = AuditWriter(app.state.internal_engine)
        await app.state.audit_writer.start()

        for runtime in runtimes.values():
            cfg = runtime.config
            runtime.registry = await build_registry(cfg)
            runtime.mongo_registry = await build_mongo_registry(cfg)
            if cfg.rate_limit.backend == "redis":
                if not settings.redis_url:
                    raise RuntimeError(f"Project {cfg.slug}: Redis rate limiter requires REDIS_URL")
                runtime.limiter = RedisRateLimiter(settings.redis_url)
            else:
                runtime.limiter = MemoryRateLimiter()
            runtime.cache = build_cache(cfg.cache, settings.redis_url)
            runtime.gate = ConcurrencyGate(cfg.protection.max_concurrent_requests, cfg.protection.max_queue_wait_seconds, cfg.protection.reject_when_saturated)
            runtime.data_sources = DataSourceManager(cfg)
            runtime.event_hub = build_event_hub(cfg.realtime.backend, settings.redis_url, cfg.realtime.redis_prefix, cfg.slug)
            if cfg.media.enabled:
                runtime.media_store = build_media_store(cfg.media)
            log.info("Loaded project=%s resources=%d operations=%d data_sources=%d prefix=%s", cfg.slug, len(cfg.resources), len(cfg.operations), len(cfg.data_sources), cfg.api_prefix)
        app.state.runtimes = runtimes
        yield

        for runtime in runtimes.values():
            if runtime.registry: await runtime.registry.dispose()
            if runtime.mongo_registry: await runtime.mongo_registry.dispose()
            if runtime.limiter: await runtime.limiter.close()
            if runtime.cache: await runtime.cache.close()
            if runtime.data_sources: await runtime.data_sources.close()
            if runtime.event_hub: await runtime.event_hub.close()
        await app.state.audit_writer.close()
        await app.state.internal_engine.dispose()

    app = FastAPI(
        title=forge.name,
        version=forge.version,
        description="Multi-project JSON-defined FastAPI backend runtime",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    gzip_min = min(p.protection.gzip_minimum_size for p in forge.projects)
    app.add_middleware(GZipMiddleware, minimum_size=gzip_min)
    trusted_hosts = sorted({host for p in forge.projects for host in p.protection.trusted_hosts})
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts or ["*"])

    def runtime_for_path(path: str) -> ProjectRuntime | None:
        matches = [rt for rt in runtimes.values() if path == rt.config.api_prefix or path.startswith(rt.config.api_prefix.rstrip("/") + "/")]
        return max(matches, key=lambda rt: len(rt.config.api_prefix or ""), default=None)

    @app.middleware("http")
    async def protection_and_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.principal = None
        request.state.project_slug = None
        runtime = runtime_for_path(request.url.path)
        start = time.perf_counter()
        response = None
        status_code = 500
        try:
            if runtime:
                cfg = runtime.config
                request.state.project_slug = cfg.slug
                origin = request.headers.get("origin")
                origin_allowed = bool(origin and ("*" in cfg.cors_origins or origin in cfg.cors_origins))
                if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
                    if origin and not origin_allowed:
                        raise HTTPException(status_code=403, detail="CORS origin is not allowed for this project")
                    response = Response(status_code=204)
                    if origin_allowed:
                        response.headers["Access-Control-Allow-Origin"] = "*" if "*" in cfg.cors_origins else origin
                        response.headers["Vary"] = "Origin"
                        response.headers["Access-Control-Allow-Methods"] = request.headers.get("access-control-request-method", "GET")
                        response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
                    status_code = response.status_code
                    return response
                if cfg.security.require_https and request.url.scheme != "https": raise HTTPException(status_code=400, detail="HTTPS is required")
                if not ip_allowed(request, cfg.security.allowed_ips, cfg.security.denied_ips): raise HTTPException(status_code=403, detail="Client IP is not allowed")
                length = request.headers.get("content-length")
                if length:
                    try:
                        if int(length) > cfg.protection.max_request_body_bytes: raise HTTPException(status_code=413, detail="Request body is too large")
                    except ValueError as exc: raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
                async with runtime.gate:
                    try:
                        response = await asyncio.wait_for(call_next(request), timeout=cfg.protection.request_timeout_seconds)
                    except asyncio.TimeoutError as exc:
                        raise HTTPException(status_code=504, detail="Request timed out") from exc
            else:
                response = await call_next(request)
            status_code = response.status_code
            return response
        except HTTPException as exc:
            response = ORJSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers or {})
            status_code = exc.status_code
            return response
        finally:
            elapsed_s = time.perf_counter() - start
            if response is not None:
                if runtime:
                    origin = request.headers.get("origin")
                    cfg = runtime.config
                    if origin and ("*" in cfg.cors_origins or origin in cfg.cors_origins):
                        response.headers["Access-Control-Allow-Origin"] = "*" if "*" in cfg.cors_origins else origin
                        response.headers["Vary"] = "Origin"
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            project_slug = runtime.config.slug if runtime else "global"
            observe(project_slug, request.method, status_code, elapsed_s)
            if runtime and runtime.config.audit_enabled and hasattr(app.state, "audit_writer"):
                p = getattr(request.state, "principal", None)
                app.state.audit_writer.submit(
                    project_slug=runtime.config.slug, request_id=request_id,
                    principal_kind=getattr(p, "kind", "unresolved"), principal_subject=getattr(p, "subject", "unresolved")[:160],
                    method=request.method[:12], path=request.url.path[:512], status_code=status_code, duration_ms=int(elapsed_s * 1000),
                )
            log.info("%s %s %s %.1fms request_id=%s", request.method, request.url.path, status_code, elapsed_s * 1000, request_id)

    async def principal_for(request: Request, runtime: ProjectRuntime):
        cfg = runtime.config
        principal = await authenticate_request(request, cfg, app.state.internal_engine)
        request.state.principal = principal
        if cfg.rate_limit.enabled:
            identity = f"{cfg.slug}:{principal.kind}:{principal.subject}:{request.method}:{request.url.path}"
            try:
                await runtime.limiter.check(identity, principal.rate_requests or cfg.rate_limit.requests, principal.rate_window_seconds or cfg.rate_limit.window_seconds, principal.rate_burst or cfg.rate_limit.burst)
            except HTTPException:
                raise
            except Exception as exc:
                if cfg.rate_limit.fail_open:
                    log.warning("Rate limiter unavailable; fail_open=true project=%s error=%s", cfg.slug, type(exc).__name__)
                else:
                    raise HTTPException(status_code=503, detail="Rate limiter is temporarily unavailable", headers={"Retry-After": "1"}) from exc
        return principal

    def require(principal, permission: str | None):
        if not has_permission(principal, permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")

    @_hidden_route(app.get("/health", tags=["system"]))
    async def health():
        return {"status": "ok", "name": forge.name, "version": forge.version, "projects": [{"slug": p.slug, "prefix": p.api_prefix, "resources": len(p.resources), "operations": len(p.operations)} for p in forge.projects]}

    @_hidden_route(app.get("/ready", tags=["system"]))
    async def ready():
        checks = {}
        for slug, runtime in runtimes.items():
            project_ok, databases, mongo = True, {}, {}
            for alias, engine in runtime.registry.engines.items():
                try:
                    async with engine.connect() as conn: await conn.execute(text("SELECT 1"))
                    databases[alias] = "ok"
                except Exception as exc:
                    databases[alias] = f"error:{type(exc).__name__}"; project_ok = False
            if runtime.mongo_registry:
                for alias, client in runtime.mongo_registry.clients.items():
                    try:
                        await client.admin.command("ping"); mongo[alias] = "ok"
                    except Exception as exc:
                        mongo[alias] = f"error:{type(exc).__name__}"; project_ok = False
            shared = {}
            for name, service in (("cache", runtime.cache), ("rate_limit", runtime.limiter), ("realtime", runtime.event_hub)):
                if service is None: continue
                try:
                    shared[name] = "ok" if await service.ping() else "error:false"
                    if shared[name] != "ok": project_ok = False
                except Exception as exc:
                    shared[name] = f"error:{type(exc).__name__}"; project_ok = False
            checks[slug] = {
                "status": "ok" if project_ok else "degraded",
                "databases": databases, "mongo": mongo, "services": shared,
            }
        if not all(v["status"] == "ok" for v in checks.values()):
            raise HTTPException(status_code=503, detail={"status": "degraded", "projects": checks})
        return {"status": "ready", "projects": checks}

    if any(p.observability.metrics_enabled for p in forge.projects):
        metrics_path = next(p.observability.metrics_path for p in forge.projects if p.observability.metrics_enabled)
        @_hidden_route(app.get(metrics_path, include_in_schema=False))
        async def metrics():
            payload, content_type = metrics_payload()
            return Response(payload, media_type=content_type)

    def register_project(runtime: ProjectRuntime):
        project = runtime.config
        prefix = project.api_prefix.rstrip("/")
        dependency_specs = {d.name: d for d in project.dependencies}

        def add_route(path: str, endpoint, *, methods: list[str], name: str, **kwargs):
            """Register one APIRoute per HTTP method with a clean signature and stable unique operation ID."""
            clean = _hide_internal_signature(endpoint)
            method_list = [m.upper() for m in methods]
            for method in method_list:
                route_name = f"{name}_{method.lower()}" if len(method_list) > 1 else name
                app.add_api_route(path, clean, methods=[method], name=route_name, **kwargs)

        def fastapi_dependencies(names: list[str]):
            deps = []
            for name in names:
                spec = dependency_specs.get(name)
                if not spec: raise RuntimeError(f"Project {project.slug}: unknown dependency {name!r}")
                deps.append(Depends(import_callable(spec.callable), use_cache=spec.use_cache))
            return deps

        @_hidden_route(app.get(f"{prefix}/meta", tags=[f"{project.slug}:system"], name=f"{project.slug}_meta"))
        async def meta(request: Request, _rt=runtime, _project=project):
            principal = await principal_for(request, _rt); require(principal, "system.meta.read")
            return {
                "project": _project.slug, "name": _project.name, "version": _project.version,
                "resources": [{"path": r.path, "actions": r.allowed_actions, "backend": "sql"} for r in _project.resources if r.enabled] + [{"path": r.path, "actions": r.allowed_actions, "backend": "mongodb"} for r in _project.mongo_resources if r.enabled],
                "operations": [{"name": o.name, "path": o.path, "method": o.method} for o in _project.operations],
                "data_sources": [{"name": d.name, "path": d.path, "type": d.type} for d in _project.data_sources],
                "event_channels": [e.name for e in _project.event_channels],
                "features": {"media": _project.media.enabled, "messaging": _project.features.messaging.enabled, "social": _project.features.social.enabled, "gaming": _project.features.gaming.enabled},
                "principal": {"kind": principal.kind, "subject": principal.subject, "roles": sorted(principal.roles)},
            }

        if project.docs_enabled:
            @_hidden_route(app.get(f"{prefix}/_openapi.json", include_in_schema=False, name=f"{project.slug}_project_openapi"))
            async def project_openapi(_prefix=prefix, _project=project):
                schema = copy.deepcopy(app.openapi())
                schema["info"]["title"] = f"{_project.name} API"
                schema["info"]["version"] = _project.version
                schema["paths"] = {path: value for path, value in schema.get("paths", {}).items() if path.startswith(_prefix + "/") and not path.endswith("/_openapi.json")}
                components = schema.setdefault("components", {})
                schemes = components.setdefault("securitySchemes", {})
                schemes["ForgeApiKey"] = {
                    "type": "apiKey", "in": "header", "name": _project.security.api_key_header,
                    "description": "Project-scoped Forge API key. Prefer a narrow key per bot/plugin/service."
                }
                if _project.security.jwt_enabled:
                    schemes["ForgeBearer"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
                # Alternatives: API key OR bearer token. Individual endpoints may still allow anonymous access
                # when their permission is null; runtime permission checks remain authoritative.
                schema["security"] = [{"ForgeApiKey": []}] + ([{"ForgeBearer": []}] if _project.security.jwt_enabled else [])
                if "webhooks" in schema:
                    schema["webhooks"] = {name: value for name, value in schema["webhooks"].items() if name.startswith(_project.slug + ".")}
                return schema

            @_hidden_route(app.get(f"{prefix}/_docs", include_in_schema=False, name=f"{project.slug}_project_docs"))
            async def project_docs(request: Request, _prefix=prefix, _project=project):
                root = request.scope.get("root_path", "").rstrip("/")
                return get_swagger_ui_html(openapi_url=f"{root}{_prefix}/_openapi.json", title=f"{_project.name} - Swagger UI")

            @_hidden_route(app.get(f"{prefix}/_redoc", include_in_schema=False, name=f"{project.slug}_project_redoc"))
            async def project_redoc(request: Request, _prefix=prefix, _project=project):
                root = request.scope.get("root_path", "").rstrip("/")
                return get_redoc_html(openapi_url=f"{root}{_prefix}/_openapi.json", title=f"{_project.name} - ReDoc")

        @_hidden_route(app.post(f"{prefix}/admin/api-keys", tags=[f"{project.slug}:admin"], name=f"{project.slug}_create_key"))
        async def admin_create_key(request: Request, body: APIKeyCreate, _rt=runtime, _project=project):
            principal = await principal_for(request, _rt); require(principal, "admin.keys.create")
            return await create_api_key(app.state.internal_engine, project_slug=_project.slug, name=body.name, roles=body.roles, permissions=body.permissions, expires_at=body.expires_at, tenant_id=body.tenant_id, rate_requests=body.rate_requests, rate_window_seconds=body.rate_window_seconds, rate_burst=body.rate_burst)

        @_hidden_route(app.get(f"{prefix}/admin/api-keys", tags=[f"{project.slug}:admin"], name=f"{project.slug}_list_keys"))
        async def admin_list_keys(request: Request, _rt=runtime, _project=project):
            principal = await principal_for(request, _rt); require(principal, "admin.keys.list")
            return {"items": await list_api_keys(app.state.internal_engine, _project.slug)}

        @_hidden_route(app.delete(f"{prefix}/admin/api-keys/{{key_id}}", tags=[f"{project.slug}:admin"], name=f"{project.slug}_revoke_key"))
        async def admin_revoke_key(key_id: int, request: Request, _rt=runtime, _project=project):
            principal = await principal_for(request, _rt); require(principal, "admin.keys.revoke")
            return {"revoked": await revoke_api_key(app.state.internal_engine, _project.slug, key_id)}

        if project.security.jwt_enabled and project.security.jwt_provider == "local_hs256":
            @_hidden_route(app.post(f"{prefix}/admin/jwt", tags=[f"{project.slug}:admin"], name=f"{project.slug}_issue_jwt"))
            async def admin_issue_jwt(request: Request, body: JWTCreate, _rt=runtime, _project=project):
                principal = await principal_for(request, _rt); require(principal, "admin.jwt.issue")
                return {"token": issue_jwt(body.subject, _project.slug, body.roles, body.permissions, body.exp_minutes or _project.security.jwt_exp_minutes, body.tenant_id), "token_type": "bearer"}

        def register_resource(resource: ResourceConfig):
            base = f"{prefix}/{resource.path.strip('/')}"
            tag = f"{project.slug}:{resource.path.strip('/').replace('/', '-')}"
            table_key = (resource.database, resource.table)
            namespace = _resource_namespace(project, resource)

            def cache_enabled(kind: str) -> bool:
                if runtime.cache is None or resource.cache.enabled is False: return False
                return project.cache.cache_lists if kind == "list" else project.cache.cache_reads
            def ttl(kind: str) -> int:
                if kind == "list" and resource.cache.list_ttl_seconds is not None: return resource.cache.list_ttl_seconds
                if kind == "read" and resource.cache.read_ttl_seconds is not None: return resource.cache.read_ttl_seconds
                return resource.cache.ttl_seconds or project.cache.default_ttl_seconds

            if "list" in resource.allowed_actions:
                async def list_handler(request: Request, _r=resource, _tk=table_key, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("list", f"{_r.path}.list"))
                    table, engine = _rt.registry.tables[_tk], _rt.registry.engines[_r.database]
                    if cache_enabled("list"):
                        key = await _rt.cache.make_key(_ns, {"kind": "list", "query": sorted(request.query_params.multi_items()), "tenant": p.tenant_id})
                        async def loader(): return await list_rows(request, engine, table, _r, p)
                        value, hit = await _rt.cache.get_or_set_json(key, ttl("list"), loader, _r.cache.stale_ttl_seconds if _r.cache.stale_ttl_seconds is not None else project.cache.stale_ttl_seconds)
                        return {**value, "_cache": "hit" if hit else "miss"}
                    return await list_rows(request, engine, table, _r, p)
                add_route(base, list_handler, methods=["GET"], tags=[tag], name=f"{project.slug}_list_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if resource.count_enabled and "list" in resource.allowed_actions:
                async def count_handler(request: Request, _r=resource, _tk=table_key, _rt=runtime):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("list", f"{_r.path}.list"))
                    return await count_rows(request, _rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p)
                add_route(base + "/_count", count_handler, methods=["GET"], tags=[tag], name=f"{project.slug}_count_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "read" in resource.allowed_actions:
                async def read_handler(item_id: str, request: Request, _r=resource, _tk=table_key, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("read", f"{_r.path}.read"))
                    table, engine = _rt.registry.tables[_tk], _rt.registry.engines[_r.database]
                    if cache_enabled("read"):
                        key = await _rt.cache.make_key(_ns, {"kind": "read", "id": item_id, "tenant": p.tenant_id})
                        async def loader(): return await get_row(engine, table, _r, p, item_id)
                        value, _ = await _rt.cache.get_or_set_json(key, ttl("read"), loader, _r.cache.stale_ttl_seconds if _r.cache.stale_ttl_seconds is not None else project.cache.stale_ttl_seconds)
                        return value
                    return await get_row(engine, table, _r, p, item_id)
                add_route(base + "/{item_id}", read_handler, methods=["GET"], tags=[tag], name=f"{project.slug}_read_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "create" in resource.allowed_actions:
                async def create_handler(request: Request, payload: dict[str, Any] = Body(...), _r=resource, _tk=table_key, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("create", f"{_r.path}.create"))
                    value = await create_row(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, payload)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base, create_handler, methods=["POST"], tags=[tag], name=f"{project.slug}_create_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))
                if resource.batch_enabled:
                    async def batch_create_handler(request: Request, payload: list[dict[str, Any]] = Body(...), _r=resource, _tk=table_key, _rt=runtime, _ns=namespace):
                        p = await principal_for(request, _rt); require(p, _r.permissions.get("create", f"{_r.path}.create"))
                        value = await batch_create_rows(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, payload)
                        if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                        return value
                    add_route(base + "/_batch", batch_create_handler, methods=["POST"], tags=[tag], name=f"{project.slug}_batch_create_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "update" in resource.allowed_actions:
                async def update_handler(item_id: str, request: Request, payload: dict[str, Any] = Body(...), _r=resource, _tk=table_key, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("update", f"{_r.path}.update"))
                    value = await update_row(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, item_id, payload)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base + "/{item_id}", update_handler, methods=["PATCH", "PUT"], tags=[tag], name=f"{project.slug}_update_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "delete" in resource.allowed_actions:
                async def delete_handler(item_id: str, request: Request, _r=resource, _tk=table_key, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("delete", f"{_r.path}.delete"))
                    value = await delete_row(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, item_id)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base + "/{item_id}", delete_handler, methods=["DELETE"], tags=[tag], name=f"{project.slug}_delete_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

        for resource in project.resources:
            if resource.enabled: register_resource(resource)

        def register_mongo_resource(resource):
            if runtime.mongo_registry is None:
                raise RuntimeError(f"Project {project.slug}: Mongo resource configured without mongo_databases")
            if resource.database not in runtime.mongo_registry.databases:
                raise RuntimeError(f"Project {project.slug}: unknown Mongo database alias {resource.database!r}")
            base = f"{prefix}/{resource.path.strip('/')}"
            tag = f"{project.slug}:mongo:{resource.path.strip('/').replace('/', '-')}"
            namespace = f"{project.slug}:mongo:{resource.database}:{resource.collection}"

            def mongo_cache_enabled(kind: str) -> bool:
                if runtime.cache is None or resource.cache.enabled is False: return False
                return project.cache.cache_lists if kind == "list" else project.cache.cache_reads
            def mongo_ttl(kind: str) -> int:
                if kind == "list" and resource.cache.list_ttl_seconds is not None: return resource.cache.list_ttl_seconds
                if kind == "read" and resource.cache.read_ttl_seconds is not None: return resource.cache.read_ttl_seconds
                return resource.cache.ttl_seconds or project.cache.default_ttl_seconds

            if "list" in resource.allowed_actions:
                async def mongo_list(request: Request, _r=resource, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("list", f"{_r.path}.list"))
                    db = _rt.mongo_registry.databases[_r.database]
                    if mongo_cache_enabled("list"):
                        key = await _rt.cache.make_key(_ns, {"kind":"list","query":sorted(request.query_params.multi_items()),"tenant":p.tenant_id})
                        async def loader(): return await list_documents(request, db, _r, p)
                        value, hit = await _rt.cache.get_or_set_json(key, mongo_ttl("list"), loader, _r.cache.stale_ttl_seconds if _r.cache.stale_ttl_seconds is not None else project.cache.stale_ttl_seconds)
                        return {**value, "_cache":"hit" if hit else "miss"}
                    return await list_documents(request, db, _r, p)
                add_route(base, mongo_list, methods=["GET"], tags=[tag], name=f"{project.slug}_mongo_list_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

                async def mongo_count(request: Request, _r=resource, _rt=runtime):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("list", f"{_r.path}.list"))
                    return await count_documents(request, _rt.mongo_registry.databases[_r.database], _r, p)
                add_route(base + "/_count", mongo_count, methods=["GET"], tags=[tag], name=f"{project.slug}_mongo_count_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "read" in resource.allowed_actions:
                async def mongo_read(item_id: str, request: Request, _r=resource, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("read", f"{_r.path}.read"))
                    db = _rt.mongo_registry.databases[_r.database]
                    if mongo_cache_enabled("read"):
                        key = await _rt.cache.make_key(_ns, {"kind":"read","id":item_id,"tenant":p.tenant_id})
                        async def loader(): return await get_document(db, _r, p, item_id)
                        value, _ = await _rt.cache.get_or_set_json(key, mongo_ttl("read"), loader, _r.cache.stale_ttl_seconds if _r.cache.stale_ttl_seconds is not None else project.cache.stale_ttl_seconds)
                        return value
                    return await get_document(db, _r, p, item_id)
                add_route(base + "/{item_id}", mongo_read, methods=["GET"], tags=[tag], name=f"{project.slug}_mongo_read_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "create" in resource.allowed_actions:
                async def mongo_create(request: Request, payload: dict[str, Any] = Body(...), _r=resource, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("create", f"{_r.path}.create"))
                    value = await create_document(_rt.mongo_registry.databases[_r.database], _r, p, payload)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base, mongo_create, methods=["POST"], tags=[tag], name=f"{project.slug}_mongo_create_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "update" in resource.allowed_actions:
                async def mongo_update(item_id: str, request: Request, payload: dict[str, Any] = Body(...), _r=resource, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("update", f"{_r.path}.update"))
                    value = await update_document(_rt.mongo_registry.databases[_r.database], _r, p, item_id, payload)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base + "/{item_id}", mongo_update, methods=["PATCH", "PUT"], tags=[tag], name=f"{project.slug}_mongo_update_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

            if "delete" in resource.allowed_actions:
                async def mongo_delete(item_id: str, request: Request, _r=resource, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _r.permissions.get("delete", f"{_r.path}.delete"))
                    value = await delete_document(_rt.mongo_registry.databases[_r.database], _r, p, item_id)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base + "/{item_id}", mongo_delete, methods=["DELETE"], tags=[tag], name=f"{project.slug}_mongo_delete_{resource.path}", dependencies=fastapi_dependencies(resource.dependencies))

        for resource in project.mongo_resources:
            if resource.enabled: register_mongo_resource(resource)

        for index, operation in enumerate(project.operations):
            namespace = _operation_namespace(project, operation)
            openapi_extra = {}
            if operation.input_schema:
                openapi_extra["requestBody"] = {"content": {"application/json": {"schema": operation.input_schema}}}
            if operation.parameters:
                openapi_extra["parameters"] = openapi_parameters(operation.parameters)
            async def operation_handler(request: Request, background_tasks: BackgroundTasks, payload: Any = Body(default=None), _op=operation, _rt=runtime, _ns=namespace):
                p = await principal_for(request, _rt); require(p, _op.permission)
                validate_request_parameters(request, _op.parameters)
                if _op.database not in _rt.registry.engines: raise HTTPException(status_code=500, detail=f"Unknown operation database: {_op.database}")
                idem_key = request.headers.get(project.security.idempotency_header) if _op.idempotency else None
                digest = None
                claimed = False
                if _op.idempotency:
                    if not idem_key: raise HTTPException(status_code=400, detail=f"Missing {project.security.idempotency_header} header")
                    digest = idempotency_digest(project.slug, _op.name, p, idem_key)
                    state, previous = await claim_idempotency(
                        app.state.internal_engine, project.slug, _op.name, digest,
                        pending_ttl_seconds=project.security.idempotency_pending_ttl_seconds,
                    )
                    if state == "complete":
                        return {**previous, "_idempotent_replay": True} if isinstance(previous, dict) else previous
                    if state == "pending":
                        raise HTTPException(status_code=409, detail="An identical idempotent operation is still in progress", headers={"Retry-After": "1"})
                    claimed = True
                try:
                    async def loader(): return await execute_operation(_rt.registry.engines[_op.database], _op, body=payload, request=request, principal=p)
                    if _op.cache.enabled and _rt.cache:
                        key = await _rt.cache.make_key(_ns, {"query": sorted(request.query_params.multi_items()), "path": dict(request.path_params), "body": payload, "principal": p.subject if _op.cache.vary_by_principal else None, "tenant": p.tenant_id})
                        result, hit = await _rt.cache.get_or_set_json(key, _op.cache.ttl_seconds, loader, _op.cache.stale_ttl_seconds if _op.cache.stale_ttl_seconds is not None else project.cache.stale_ttl_seconds)
                        if isinstance(result, dict): result = {**result, "_cache": "hit" if hit else "miss"}
                    else:
                        result = await loader()
                    for path in _op.invalidate_resources:
                        target = next((r for r in project.resources if r.path == path), None)
                        if target and _rt.cache: await _rt.cache.invalidate_namespace(_resource_namespace(project, target))
                    for operation_name in _op.invalidate_operations:
                        target_op = next((o for o in project.operations if o.name == operation_name), None)
                        if target_op and _rt.cache: await _rt.cache.invalidate_namespace(_operation_namespace(project, target_op))
                    if digest and claimed:
                        await complete_idempotency(app.state.internal_engine, project.slug, _op.name, digest, result)
                except Exception:
                    if digest and claimed:
                        await release_idempotency(app.state.internal_engine, project.slug, _op.name, digest)
                    raise
                for hook_path in _op.background_hooks:
                    background_tasks.add_task(_invoke_hook, import_callable(hook_path), request=request, payload=payload, principal=p, result=result, app=app, project=project)
                return result
            add_route(f"{prefix}/{operation.path.strip('/')}", operation_handler, methods=[operation.method], tags=operation.tags or [f"{project.slug}:rpc"], name=f"{project.slug}_operation_{index}_{operation.name}", summary=operation.summary, description=operation.description, deprecated=operation.deprecated, openapi_extra=openapi_extra or None, dependencies=fastapi_dependencies(operation.dependencies))

        for index, source in enumerate(project.data_sources):
            if not source.enabled:
                continue
            base = f"{prefix}/{source.path.strip('/')}"
            namespace = _data_namespace(project, source)
            method = source.method if source.type == "http" else "GET"
            async def data_read(request: Request, payload: Any = Body(default=None), _s=source, _rt=runtime, _ns=namespace, _method=method):
                p = await principal_for(request, _rt); require(p, _s.read_permission or _s.permission)
                validate_request_parameters(request, _s.parameters)
                async def loader(): return await _rt.data_sources.read(_s, request, payload)
                if _s.cache_ttl_seconds > 0 and _rt.cache and _method == "GET":
                    key = await _rt.cache.make_key(_ns, {"query": sorted(request.query_params.multi_items()), "body": payload, "principal": p.subject})
                    result, hit = await _rt.cache.get_or_set_json(key, _s.cache_ttl_seconds, loader, _s.stale_ttl_seconds if _s.stale_ttl_seconds is not None else project.cache.stale_ttl_seconds)
                    return {**result, "_cache": "hit" if hit else "miss"} if isinstance(result, dict) else result
                return await loader()
            data_openapi = {"parameters": openapi_parameters(source.parameters)} if source.parameters else None
            add_route(base, data_read, methods=[method], tags=[f"{project.slug}:data"], name=f"{project.slug}_data_{index}_{source.name}", dependencies=fastapi_dependencies(source.dependencies), openapi_extra=data_openapi)
            if source.writable:
                async def data_create(request: Request, payload: dict[str, Any] = Body(...), _s=source, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _s.write_permission or _s.permission)
                    value = await _rt.data_sources.create(_s, payload)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                async def data_update(item_id: str, request: Request, payload: dict[str, Any] = Body(...), _s=source, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _s.write_permission or _s.permission)
                    value = await _rt.data_sources.update(_s, item_id, payload)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                async def data_delete(item_id: str, request: Request, _s=source, _rt=runtime, _ns=namespace):
                    p = await principal_for(request, _rt); require(p, _s.write_permission or _s.permission)
                    value = await _rt.data_sources.delete(_s, item_id)
                    if _rt.cache: await _rt.cache.invalidate_namespace(_ns)
                    return value
                add_route(base, data_create, methods=["POST"], tags=[f"{project.slug}:data"], name=f"{project.slug}_data_create_{index}", dependencies=fastapi_dependencies(source.dependencies))
                add_route(base + "/{item_id}", data_update, methods=["PATCH", "PUT"], tags=[f"{project.slug}:data"], name=f"{project.slug}_data_update_{index}", dependencies=fastapi_dependencies(source.dependencies))
                add_route(base + "/{item_id}", data_delete, methods=["DELETE"], tags=[f"{project.slug}:data"], name=f"{project.slug}_data_delete_{index}", dependencies=fastapi_dependencies(source.dependencies))

        for index, endpoint in enumerate(project.custom_endpoints):
            handler = import_callable(endpoint.handler)
            openapi_extra = dict(endpoint.openapi_extra or {})
            if endpoint.parameters:
                openapi_extra["parameters"] = openapi_parameters(endpoint.parameters)
            if endpoint.input_mode != "none":
                media_map = {"json":"application/json", "form":"application/x-www-form-urlencoded", "text":"text/plain", "bytes":"application/octet-stream"}
                body_schema = endpoint.input_schema or ({"type":"string", "format":"binary"} if endpoint.input_mode == "bytes" else {"type":"string"} if endpoint.input_mode == "text" else {"type":"object"})
                openapi_extra.setdefault("requestBody", {"content": {media_map[endpoint.input_mode]: {"schema": body_schema}}})

            async def custom_handler(request: Request, background_tasks: BackgroundTasks, _e=endpoint, _h=handler, _rt=runtime):
                p = await principal_for(request, _rt); require(p, _e.permission)
                validate_request_parameters(request, _e.parameters)
                if _e.input_mode == "none":
                    payload = None
                elif _e.input_mode == "json":
                    raw = await request.body()
                    if not raw:
                        payload = None
                    else:
                        try:
                            import orjson
                            payload = orjson.loads(raw)
                        except Exception as exc:
                            raise HTTPException(status_code=400, detail="Invalid JSON request body") from exc
                elif _e.input_mode == "form":
                    form = await request.form(); payload = dict(form)
                elif _e.input_mode == "text":
                    payload = (await request.body()).decode("utf-8")
                else:
                    payload = await request.body()
                if _e.input_mode in {"json", "form"}: validate_json_schema(payload, _e.input_schema, label=f"endpoint:{_e.path}")
                kwargs = {"request": request, "payload": payload, "principal": p, "app": app, "project": project}
                result = await _invoke_hook(_h, **kwargs)
                for hook_path in _e.background_hooks:
                    background_tasks.add_task(_invoke_hook, import_callable(hook_path), **kwargs, result=result)
                return render_response(_e.response, result)
            add_route(f"{prefix}/{endpoint.path.strip('/')}", custom_handler, methods=[endpoint.method.upper()], summary=endpoint.summary, description=endpoint.description, tags=endpoint.tags or [f"{project.slug}:custom"], name=f"{project.slug}_custom_{index}", deprecated=endpoint.deprecated, include_in_schema=endpoint.include_in_schema, dependencies=fastapi_dependencies(endpoint.dependencies), openapi_extra=openapi_extra or None)

        for index, channel in enumerate(project.event_channels):
            base = f"{prefix}/{channel.path.strip('/')}"
            async def publish_event(request: Request, payload: Any = Body(...), _c=channel, _rt=runtime):
                p = await principal_for(request, _rt); require(p, _c.publish_permission)
                import orjson
                if len(orjson.dumps(payload)) > _c.max_message_bytes:
                    raise HTTPException(status_code=413, detail=f"Event exceeds max_message_bytes={_c.max_message_bytes}")
                delivered = await _rt.event_hub.publish(_c.name, {"channel": _c.name, "event": payload, "publisher": p.subject, "request_id": request.state.request_id})
                return {"published": True, "delivered": delivered}
            add_route(base, publish_event, methods=["POST"], tags=[f"{project.slug}:events"], name=f"{project.slug}_event_publish_{index}")

            if channel.sse_enabled:
                async def event_stream(request: Request, _c=channel, _rt=runtime):
                    p = await principal_for(request, _rt); require(p, _c.subscribe_permission)
                    async def stream():
                        subscription = _rt.event_hub.subscribe(_c.name, _c.queue_size)
                        try:
                            while True:
                                try:
                                    event = await asyncio.wait_for(anext(subscription), timeout=_c.heartbeat_seconds)
                                    yield sse_encode(event)
                                except asyncio.TimeoutError:
                                    yield b": heartbeat\n\n"
                                if await request.is_disconnected(): break
                        finally:
                            await subscription.aclose()
                    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
                add_route(base + "/stream", event_stream, methods=["GET"], tags=[f"{project.slug}:events"], name=f"{project.slug}_event_sse_{index}")

            if channel.websocket_enabled:
                async def websocket_endpoint(websocket: WebSocket, _c=channel, _rt=runtime, _project=project):
                    try:
                        p = await authenticate_request(websocket, _project, app.state.internal_engine)
                        require(p, _c.subscribe_permission)
                        if _project.rate_limit.enabled:
                            await _rt.limiter.check(f"{_project.slug}:{p.kind}:{p.subject}:WS:{websocket.url.path}", p.rate_requests or _project.rate_limit.requests, p.rate_window_seconds or _project.rate_limit.window_seconds, p.rate_burst or _project.rate_limit.burst)
                        await _rt.event_hub.connect_ws(_c.name, websocket)
                        while True:
                            message = await websocket.receive_text()
                            if len(message.encode("utf-8")) > _c.max_message_bytes:
                                await websocket.close(code=1009); break
                            require(p, _c.publish_permission)
                            await _rt.event_hub.publish(_c.name, {"channel": _c.name, "event": message, "publisher": p.subject})
                    except WebSocketDisconnect:
                        pass
                    except HTTPException:
                        try: await websocket.close(code=1008)
                        except Exception: pass
                    finally:
                        await _rt.event_hub.disconnect_ws(_c.name, websocket)
                app.add_api_websocket_route(base + "/ws", _hide_internal_signature(websocket_endpoint), name=f"{project.slug}_event_ws_{index}")

        if project.media.enabled:
            @_hidden_route(app.post(f"{prefix}/media", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_upload"))
            async def media_upload(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...), _rt=runtime, _project=project):
                p = await principal_for(request, _rt); require(p, _project.media.upload_permission)
                result = await save_media(engine=app.state.internal_engine, store=_rt.media_store, project_slug=_project.slug, config=_project.media, upload=file, owner_subject=p.subject)
                for hook_path in _project.media.post_upload_hooks:
                    background_tasks.add_task(_invoke_hook, import_callable(hook_path), media=result, principal=p, app=app, project=_project)
                return result

            @_hidden_route(app.post(f"{prefix}/media/_batch", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_batch_upload"))
            async def media_batch_upload(request: Request, background_tasks: BackgroundTasks, files: list[UploadFile] = File(...), _rt=runtime, _project=project):
                p = await principal_for(request, _rt); require(p, _project.media.upload_permission)
                if not files or len(files) > _project.media.max_batch_files:
                    raise HTTPException(status_code=422, detail=f"Batch media count must be 1..{_project.media.max_batch_files}")
                items = []
                for file in files:
                    item = await save_media(engine=app.state.internal_engine, store=_rt.media_store, project_slug=_project.slug, config=_project.media, upload=file, owner_subject=p.subject)
                    items.append(item)
                    for hook_path in _project.media.post_upload_hooks:
                        background_tasks.add_task(_invoke_hook, import_callable(hook_path), media=item, principal=p, app=app, project=_project)
                return {"items": items, "count": len(items)}

            @_hidden_route(app.get(f"{prefix}/media/{{media_id}}/meta", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_meta"))
            async def media_meta(media_id: str, request: Request, _rt=runtime, _project=project):
                p = await principal_for(request, _rt)
                if not _project.media.public: require(p, _project.media.read_permission)
                return await get_media_meta(app.state.internal_engine, _project.slug, media_id)

            @_hidden_route(app.post(f"{prefix}/media/{{media_id}}/signed-url", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_signed_url"))
            async def media_signed_url(media_id: str, request: Request, _rt=runtime, _project=project):
                p = await principal_for(request, _rt); require(p, _project.media.read_permission)
                if not _project.media.signed_urls_enabled: raise HTTPException(status_code=404, detail="Signed media URLs are disabled")
                await get_media_meta(app.state.internal_engine, _project.slug, media_id)
                token = make_signed_media_token(_project.slug, media_id, _project.media.signed_url_ttl_seconds)
                return {"path": f"{_project.api_prefix.rstrip('/')}/media/{media_id}?token={token}", "expires_in": _project.media.signed_url_ttl_seconds}

            @_hidden_route(app.get(f"{prefix}/media/{{media_id}}", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_get"))
            async def media_get(media_id: str, request: Request, token: str | None = None, _rt=runtime, _project=project):
                p = await principal_for(request, _rt)
                signed = _project.media.signed_urls_enabled and verify_signed_media_token(_project.slug, media_id, token)
                if not _project.media.public and not signed: require(p, _project.media.read_permission)
                meta = await get_media_meta(app.state.internal_engine, _project.slug, media_id)
                path = _rt.media_store.path_for(meta["storage_key"])
                if not path.exists(): raise HTTPException(status_code=404, detail="Media object is missing from storage")
                return FileResponse(path, media_type=meta["content_type"], filename=meta["original_name"])

            @_hidden_route(app.delete(f"{prefix}/media/{{media_id}}", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_delete"))
            async def media_delete_route(media_id: str, request: Request, _rt=runtime, _project=project):
                p = await principal_for(request, _rt); require(p, _project.media.delete_permission)
                if _project.media.owner_delete_only:
                    meta = await get_media_meta(app.state.internal_engine, _project.slug, media_id)
                    if meta["owner_subject"] != p.subject and not has_permission(p, _project.media.admin_permission):
                        raise HTTPException(status_code=403, detail="Only the media owner may delete this object")
                return {"deleted": await delete_media(app.state.internal_engine, _rt.media_store, _project.slug, media_id)}

        for index, webhook in enumerate(project.webhook_docs):
            async def documented_webhook(payload: Any = Body(...)):
                return None
            extra = {"requestBody": {"content": {"application/json": {"schema": webhook.payload_schema}}}} if webhook.payload_schema else None
            app.webhooks.add_api_route(f"{project.slug}.{webhook.name}", documented_webhook, methods=[webhook.method], summary=webhook.summary, description=webhook.description, name=f"{project.slug}_webhook_doc_{index}", openapi_extra=extra)

    for runtime in runtimes.values(): register_project(runtime)
    return app
