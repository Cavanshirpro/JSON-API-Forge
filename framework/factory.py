from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, ORJSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .audit import AuditWriter
from .cache import build_cache
from .config import ProjectConfig, ResourceConfig, load_config
from .crud import create_row, delete_row, get_row, list_rows, update_row
from .db import build_registry
from .domain import expand_feature_packs
from .hooks import import_callable
from .media import build_media_store, delete_media, get_media_meta, save_media
from .protection import ConcurrencyGate, ip_allowed
from .rate_limit import MemoryRateLimiter, RedisRateLimiter
from .security import authenticate_request, create_api_key, has_permission, init_security, revoke_api_key
from .settings import settings

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


@dataclass
class ProjectRuntime:
    config: ProjectConfig
    registry: Any = None
    limiter: Any = None
    cache: Any = None
    gate: ConcurrencyGate | None = None
    media_store: Any = None


def _resource_namespace(project: ProjectConfig, resource: ResourceConfig) -> str:
    return f"{project.slug}:{resource.database}:{resource.table}"


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
            if cfg.rate_limit.backend == "redis":
                if not settings.redis_url:
                    raise RuntimeError(f"Project {cfg.slug}: Redis rate limiter requires REDIS_URL")
                runtime.limiter = RedisRateLimiter(settings.redis_url)
            else:
                runtime.limiter = MemoryRateLimiter()
            runtime.cache = build_cache(cfg.cache, settings.redis_url)
            runtime.gate = ConcurrencyGate(
                cfg.protection.max_concurrent_requests,
                cfg.protection.max_queue_wait_seconds,
                cfg.protection.reject_when_saturated,
            )
            if cfg.media.enabled:
                runtime.media_store = build_media_store(cfg.media)
            log.info("Loaded project=%s resources=%d prefix=%s", cfg.slug, len(cfg.resources), cfg.api_prefix)

        app.state.runtimes = runtimes
        yield

        for runtime in runtimes.values():
            if runtime.registry:
                await runtime.registry.dispose()
            if runtime.limiter:
                await runtime.limiter.close()
            if runtime.cache:
                await runtime.cache.close()
        await app.state.audit_writer.close()
        await app.state.internal_engine.dispose()

    app = FastAPI(
        title=forge.name,
        version=forge.version,
        description="Multi-project JSON-defined API runtime",
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
                if cfg.security.require_https and request.url.scheme != "https":
                    raise HTTPException(status_code=400, detail="HTTPS is required")
                if not ip_allowed(request, cfg.security.allowed_ips, cfg.security.denied_ips):
                    raise HTTPException(status_code=403, detail="Client IP is not allowed")
                length = request.headers.get("content-length")
                if length:
                    try:
                        if int(length) > cfg.protection.max_request_body_bytes:
                            raise HTTPException(status_code=413, detail="Request body is too large")
                    except ValueError:
                        raise HTTPException(status_code=400, detail="Invalid Content-Length")

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
            elapsed = (time.perf_counter() - start) * 1000
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
            if runtime and runtime.config.audit_enabled and hasattr(app.state, "audit_writer"):
                p = getattr(request.state, "principal", None)
                app.state.audit_writer.submit(
                    project_slug=runtime.config.slug,
                    request_id=request_id,
                    principal_kind=getattr(p, "kind", "unresolved"),
                    principal_subject=getattr(p, "subject", "unresolved")[:160],
                    method=request.method[:12],
                    path=request.url.path[:512],
                    status_code=status_code,
                    duration_ms=int(elapsed),
                )
            log.info("%s %s %s %.1fms request_id=%s", request.method, request.url.path, status_code, elapsed, request_id)

    async def principal_for(request: Request, runtime: ProjectRuntime):
        cfg = runtime.config
        principal = await authenticate_request(request, cfg, app.state.internal_engine)
        request.state.principal = principal
        if cfg.rate_limit.enabled:
            identity = f"{cfg.slug}:{principal.kind}:{principal.subject}:{request.method}:{request.url.path}"
            await runtime.limiter.check(
                identity,
                principal.rate_requests or cfg.rate_limit.requests,
                principal.rate_window_seconds or cfg.rate_limit.window_seconds,
                principal.rate_burst or cfg.rate_limit.burst,
            )
        return principal

    def require(principal, permission: str | None):
        if not has_permission(principal, permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")

    @app.get("/health", tags=["system"])
    async def health():
        return {
            "status": "ok",
            "name": forge.name,
            "version": forge.version,
            "projects": [{"slug": p.slug, "prefix": p.api_prefix, "resources": len(p.resources)} for p in forge.projects],
        }

    @app.get("/ready", tags=["system"])
    async def ready():
        checks = {}
        for slug, runtime in runtimes.items():
            project_ok = True
            databases = {}
            for alias, engine in runtime.registry.engines.items():
                try:
                    async with engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                    databases[alias] = "ok"
                except Exception as exc:
                    databases[alias] = f"error:{type(exc).__name__}"
                    project_ok = False
            checks[slug] = {"status": "ok" if project_ok else "degraded", "databases": databases}
        ok = all(v["status"] == "ok" for v in checks.values())
        if not ok:
            raise HTTPException(status_code=503, detail={"status": "degraded", "projects": checks})
        return {"status": "ready", "projects": checks}

    def register_project(runtime: ProjectRuntime):
        project = runtime.config
        prefix = project.api_prefix.rstrip("/")

        @app.get(f"{prefix}/meta", tags=[f"{project.slug}:system"], name=f"{project.slug}_meta")
        async def meta(request: Request, _rt=runtime):
            principal = await principal_for(request, _rt)
            require(principal, "system.meta.read")
            return {
                "project": project.slug,
                "name": project.name,
                "version": project.version,
                "resources": [{"path": r.path, "actions": r.allowed_actions} for r in project.resources if r.enabled],
                "features": {
                    "media": project.media.enabled,
                    "messaging": project.features.messaging.enabled,
                    "social": project.features.social.enabled,
                    "gaming": project.features.gaming.enabled,
                },
                "principal": {"kind": principal.kind, "subject": principal.subject, "roles": sorted(principal.roles)},
            }

        @app.post(f"{prefix}/admin/api-keys", tags=[f"{project.slug}:admin"], name=f"{project.slug}_create_key")
        async def admin_create_key(request: Request, body: APIKeyCreate, _rt=runtime):
            principal = await principal_for(request, _rt)
            require(principal, "admin.keys.create")
            return await create_api_key(
                app.state.internal_engine,
                project_slug=project.slug,
                name=body.name,
                roles=body.roles,
                permissions=body.permissions,
                expires_at=body.expires_at,
                tenant_id=body.tenant_id,
                rate_requests=body.rate_requests,
                rate_window_seconds=body.rate_window_seconds,
                rate_burst=body.rate_burst,
            )

        @app.delete(f"{prefix}/admin/api-keys/{{key_id}}", tags=[f"{project.slug}:admin"], name=f"{project.slug}_revoke_key")
        async def admin_revoke_key(key_id: int, request: Request, _rt=runtime):
            principal = await principal_for(request, _rt)
            require(principal, "admin.keys.revoke")
            return {"revoked": await revoke_api_key(app.state.internal_engine, project.slug, key_id)}

        def register_resource(resource: ResourceConfig):
            base = f"{prefix}/{resource.path.strip('/')}"
            tag = f"{project.slug}:{resource.path.strip('/').replace('/', '-')}"
            table_key = (resource.database, resource.table)
            namespace = _resource_namespace(project, resource)

            def cache_enabled(kind: str) -> bool:
                if runtime.cache is None:
                    return False
                if resource.cache.enabled is False:
                    return False
                if kind == "list":
                    return project.cache.cache_lists
                return project.cache.cache_reads

            def ttl(kind: str) -> int:
                if kind == "list" and resource.cache.list_ttl_seconds is not None:
                    return resource.cache.list_ttl_seconds
                if kind == "read" and resource.cache.read_ttl_seconds is not None:
                    return resource.cache.read_ttl_seconds
                return resource.cache.ttl_seconds or project.cache.default_ttl_seconds

            if "list" in resource.allowed_actions:
                async def list_handler(request: Request, _r=resource, _tk=table_key, _rt=runtime):
                    p = await principal_for(request, _rt)
                    require(p, _r.permissions.get("list", f"{_r.path}.list"))
                    table = _rt.registry.tables[_tk]
                    engine = _rt.registry.engines[_r.database]
                    if cache_enabled("list"):
                        key = await _rt.cache.make_key(namespace, {
                            "kind": "list", "query": sorted(request.query_params.multi_items()),
                            "tenant": p.tenant_id, "subject": p.subject if _r.tenant_field else None,
                        })
                        async def loader():
                            return await list_rows(request, engine, table, _r, p)
                        value, hit = await _rt.cache.get_or_set_json(key, ttl("list"), loader)
                        return {**value, "_cache": "hit" if hit else "miss"}
                    return await list_rows(request, engine, table, _r, p)
                app.add_api_route(base, list_handler, methods=["GET"], tags=[tag], name=f"{project.slug}_list_{tag}")

            if "read" in resource.allowed_actions:
                async def read_handler(item_id: str, request: Request, _r=resource, _tk=table_key, _rt=runtime):
                    p = await principal_for(request, _rt)
                    require(p, _r.permissions.get("read", f"{_r.path}.read"))
                    table = _rt.registry.tables[_tk]
                    engine = _rt.registry.engines[_r.database]
                    if cache_enabled("read"):
                        key = await _rt.cache.make_key(namespace, {"kind": "read", "id": item_id, "tenant": p.tenant_id})
                        async def loader():
                            return await get_row(engine, table, _r, p, item_id)
                        value, _ = await _rt.cache.get_or_set_json(key, ttl("read"), loader)
                        return value
                    return await get_row(engine, table, _r, p, item_id)
                app.add_api_route(base + "/{item_id}", read_handler, methods=["GET"], tags=[tag], name=f"{project.slug}_read_{tag}")

            if "create" in resource.allowed_actions:
                async def create_handler(request: Request, payload: dict[str, Any] = Body(...), _r=resource, _tk=table_key, _rt=runtime):
                    p = await principal_for(request, _rt)
                    require(p, _r.permissions.get("create", f"{_r.path}.create"))
                    value = await create_row(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, payload)
                    if _rt.cache:
                        await _rt.cache.invalidate_namespace(namespace)
                    return value
                app.add_api_route(base, create_handler, methods=["POST"], tags=[tag], name=f"{project.slug}_create_{tag}")

            if "update" in resource.allowed_actions:
                async def update_handler(item_id: str, request: Request, payload: dict[str, Any] = Body(...), _r=resource, _tk=table_key, _rt=runtime):
                    p = await principal_for(request, _rt)
                    require(p, _r.permissions.get("update", f"{_r.path}.update"))
                    value = await update_row(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, item_id, payload)
                    if _rt.cache:
                        await _rt.cache.invalidate_namespace(namespace)
                    return value
                app.add_api_route(base + "/{item_id}", update_handler, methods=["PATCH", "PUT"], tags=[tag], name=f"{project.slug}_update_{tag}")

            if "delete" in resource.allowed_actions:
                async def delete_handler(item_id: str, request: Request, _r=resource, _tk=table_key, _rt=runtime):
                    p = await principal_for(request, _rt)
                    require(p, _r.permissions.get("delete", f"{_r.path}.delete"))
                    value = await delete_row(_rt.registry.engines[_r.database], _rt.registry.tables[_tk], _r, p, item_id)
                    if _rt.cache:
                        await _rt.cache.invalidate_namespace(namespace)
                    return value
                app.add_api_route(base + "/{item_id}", delete_handler, methods=["DELETE"], tags=[tag], name=f"{project.slug}_delete_{tag}")

        for resource in project.resources:
            if resource.enabled:
                register_resource(resource)

        for index, endpoint in enumerate(project.custom_endpoints):
            handler = import_callable(endpoint.handler)
            async def custom_handler(request: Request, payload: dict[str, Any] | None = Body(default=None), _e=endpoint, _h=handler, _rt=runtime):
                p = await principal_for(request, _rt)
                require(p, _e.permission)
                kwargs = {"request": request, "payload": payload, "principal": p, "app": app, "project": project}
                result = _h(**kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return result
            app.add_api_route(
                f"{prefix}/{endpoint.path.strip('/')}", custom_handler,
                methods=[endpoint.method.upper()], summary=endpoint.summary,
                tags=[f"{project.slug}:custom"], name=f"{project.slug}_custom_{index}",
            )

        if project.media.enabled:
            @app.post(f"{prefix}/media", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_upload")
            async def media_upload(request: Request, file: UploadFile = File(...), _rt=runtime):
                p = await principal_for(request, _rt)
                require(p, project.media.upload_permission)
                return await save_media(
                    engine=app.state.internal_engine, store=_rt.media_store, project_slug=project.slug,
                    config=project.media, upload=file, owner_subject=p.subject,
                )

            @app.get(f"{prefix}/media/{{media_id}}/meta", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_meta")
            async def media_meta(media_id: str, request: Request, _rt=runtime):
                p = await principal_for(request, _rt)
                if not project.media.public:
                    require(p, project.media.read_permission)
                return await get_media_meta(app.state.internal_engine, project.slug, media_id)

            @app.get(f"{prefix}/media/{{media_id}}", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_get")
            async def media_get(media_id: str, request: Request, _rt=runtime):
                p = await principal_for(request, _rt)
                if not project.media.public:
                    require(p, project.media.read_permission)
                meta = await get_media_meta(app.state.internal_engine, project.slug, media_id)
                path = _rt.media_store.path_for(meta["storage_key"])
                if not path.exists():
                    raise HTTPException(status_code=404, detail="Media object is missing from storage")
                return FileResponse(path, media_type=meta["content_type"], filename=meta["original_name"])

            @app.delete(f"{prefix}/media/{{media_id}}", tags=[f"{project.slug}:media"], name=f"{project.slug}_media_delete")
            async def media_delete(media_id: str, request: Request, _rt=runtime):
                p = await principal_for(request, _rt)
                require(p, project.media.delete_permission)
                return {"deleted": await delete_media(app.state.internal_engine, _rt.media_store, project.slug, media_id)}

    for runtime in runtimes.values():
        register_project(runtime)

    return app
