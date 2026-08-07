from __future__ import annotations

import inspect
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine

from .config import AppConfig, ResourceConfig, load_config
from .crud import create_row, delete_row, get_row, list_rows, update_row
from .db import build_registry
from .hooks import import_callable
from .rate_limit import MemoryRateLimiter, RedisRateLimiter
from .security import authenticate_request, create_api_key, has_permission, init_security, revoke_api_key, write_audit
from .settings import settings

log = logging.getLogger("json_api_forge")


class APIKeyCreate(BaseModel):
    name: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


def create_app() -> FastAPI:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    config = load_config()
    if config.rate_limit.backend == "redis":
        if not settings.redis_url:
            raise RuntimeError("rate_limit.backend is redis but REDIS_URL is not configured")
        limiter = RedisRateLimiter(settings.redis_url)
    elif config.rate_limit.backend == "memory":
        limiter = MemoryRateLimiter()
    else:
        raise RuntimeError(f"Unsupported rate limit backend: {config.rate_limit.backend}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = config
        app.state.registry = await build_registry(config)
        internal_url = settings.internal_database_url
        if internal_url.startswith("sqlite+aiosqlite:///"):
            from pathlib import Path
            db_path = internal_url[len("sqlite+aiosqlite:///"):]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        app.state.internal_engine = create_async_engine(internal_url, pool_pre_ping=True)
        await init_security(app.state.internal_engine)
        log.info("JSON API Forge started with %d resources", len(config.resources))
        yield
        await app.state.registry.dispose()
        await app.state.internal_engine.dispose()
        await limiter.close()

    app = FastAPI(
        title=config.name, version=config.version,
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url="/redoc" if config.docs_enabled else None,
        default_response_class=ORJSONResponse, lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=config.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.principal = None
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            status_code = response.status_code if response is not None else 500
            log.info("%s %s %s %.1fms request_id=%s", request.method, request.url.path, status_code, elapsed, request_id)
            if response is not None:
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
            if config.audit_enabled and hasattr(app.state, "internal_engine"):
                p = getattr(request.state, "principal", None)
                try:
                    await write_audit(
                        app.state.internal_engine, request_id=request_id,
                        principal_kind=getattr(p, "kind", "unresolved"),
                        principal_subject=getattr(p, "subject", "unresolved"),
                        method=request.method, path=request.url.path, status_code=status_code,
                        duration_ms=int(elapsed),
                    )
                except Exception:
                    log.exception("Failed to write audit record")

    async def principal_for(request: Request):
        principal = await authenticate_request(request, config, app.state.internal_engine)
        request.state.principal = principal
        if config.rate_limit.enabled:
            identity = f"{principal.kind}:{principal.subject}:{request.url.path}"
            await limiter.check(identity, config.rate_limit.requests, config.rate_limit.window_seconds)
        return principal

    def require(principal, permission: str | None):
        if not has_permission(principal, permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok", "name": config.name, "version": config.version}

    @app.get(f"{config.api_prefix}/meta", tags=["system"])
    async def meta(request: Request):
        principal = await principal_for(request)
        require(principal, "system.meta.read")
        return {
            "name": config.name, "version": config.version,
            "resources": [{"path": r.path, "actions": r.allowed_actions} for r in config.resources if r.enabled],
            "principal": {"kind": principal.kind, "subject": principal.subject, "roles": sorted(principal.roles)},
        }

    @app.post(f"{config.api_prefix}/admin/api-keys", tags=["admin"])
    async def admin_create_key(request: Request, body: APIKeyCreate):
        principal = await principal_for(request)
        require(principal, "admin.keys.create")
        return await create_api_key(app.state.internal_engine, name=body.name, roles=body.roles, permissions=body.permissions, expires_at=body.expires_at)

    @app.delete(f"{config.api_prefix}/admin/api-keys/{{key_id}}", tags=["admin"])
    async def admin_revoke_key(key_id: int, request: Request):
        principal = await principal_for(request)
        require(principal, "admin.keys.revoke")
        return {"revoked": await revoke_api_key(app.state.internal_engine, key_id)}

    def register_resource(resource: ResourceConfig):
        base = f"{config.api_prefix}/{resource.path.strip('/')}"
        tag = resource.path.strip("/").replace("/", "-") or "resource"
        table_key = (resource.database, resource.table)

        if "list" in resource.allowed_actions:
            async def list_handler(request: Request, _r=resource, _tk=table_key):
                p = await principal_for(request); require(p, _r.permissions.get("list", f"{_r.path}.list"))
                table = app.state.registry.tables[_tk]; engine = app.state.registry.engines[_r.database]
                return await list_rows(request, engine, table, _r, p)
            app.add_api_route(base, list_handler, methods=["GET"], tags=[tag], name=f"list_{tag}")

        if "read" in resource.allowed_actions:
            async def read_handler(item_id: str, request: Request, _r=resource, _tk=table_key):
                p = await principal_for(request); require(p, _r.permissions.get("read", f"{_r.path}.read"))
                table = app.state.registry.tables[_tk]; engine = app.state.registry.engines[_r.database]
                return await get_row(engine, table, _r, p, item_id)
            app.add_api_route(base + "/{item_id}", read_handler, methods=["GET"], tags=[tag], name=f"read_{tag}")

        if "create" in resource.allowed_actions:
            async def create_handler(request: Request, payload: dict[str, Any] = Body(...), _r=resource, _tk=table_key):
                p = await principal_for(request); require(p, _r.permissions.get("create", f"{_r.path}.create"))
                table = app.state.registry.tables[_tk]; engine = app.state.registry.engines[_r.database]
                return await create_row(engine, table, _r, p, payload)
            app.add_api_route(base, create_handler, methods=["POST"], tags=[tag], name=f"create_{tag}")

        if "update" in resource.allowed_actions:
            async def update_handler(item_id: str, request: Request, payload: dict[str, Any] = Body(...), _r=resource, _tk=table_key):
                p = await principal_for(request); require(p, _r.permissions.get("update", f"{_r.path}.update"))
                table = app.state.registry.tables[_tk]; engine = app.state.registry.engines[_r.database]
                return await update_row(engine, table, _r, p, item_id, payload)
            app.add_api_route(base + "/{item_id}", update_handler, methods=["PATCH", "PUT"], tags=[tag], name=f"update_{tag}")

        if "delete" in resource.allowed_actions:
            async def delete_handler(item_id: str, request: Request, _r=resource, _tk=table_key):
                p = await principal_for(request); require(p, _r.permissions.get("delete", f"{_r.path}.delete"))
                table = app.state.registry.tables[_tk]; engine = app.state.registry.engines[_r.database]
                return await delete_row(engine, table, _r, p, item_id)
            app.add_api_route(base + "/{item_id}", delete_handler, methods=["DELETE"], tags=[tag], name=f"delete_{tag}")

    for resource in config.resources:
        if resource.enabled:
            register_resource(resource)

    for endpoint in config.custom_endpoints:
        handler = import_callable(endpoint.handler)
        async def custom_handler(request: Request, payload: dict[str, Any] | None = Body(default=None), _e=endpoint, _h=handler):
            p = await principal_for(request); require(p, _e.permission)
            kwargs = {"request": request, "payload": payload, "principal": p, "app": app}
            result = _h(**kwargs)
            if inspect.isawaitable(result): result = await result
            return result
        app.add_api_route(f"{config.api_prefix}/{endpoint.path.strip('/')}", custom_handler, methods=[endpoint.method.upper()], summary=endpoint.summary, tags=["custom"])

    return app
