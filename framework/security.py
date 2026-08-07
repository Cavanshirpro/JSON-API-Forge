from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import ProjectConfig
from .settings import settings

_internal_meta = MetaData()

audit_table = Table(
    "_forge_v2_audit", _internal_meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("project_slug", String(80), nullable=False, index=True),
    Column("request_id", String(64), nullable=False, index=True),
    Column("principal_kind", String(32), nullable=False),
    Column("principal_subject", String(160), nullable=False),
    Column("method", String(12), nullable=False),
    Column("path", String(512), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("duration_ms", Integer, nullable=False),
)

api_keys_table = Table(
    "_forge_v2_api_keys", _internal_meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_slug", String(80), nullable=False, index=True),
    Column("name", String(120), nullable=False),
    Column("prefix", String(16), nullable=False, index=True),
    Column("key_hash", String(64), nullable=False, unique=True),
    Column("roles", Text, nullable=False, default=""),
    Column("permissions", Text, nullable=False, default=""),
    Column("tenant_id", String(96), nullable=True, index=True),
    Column("rate_requests", Integer, nullable=True),
    Column("rate_window_seconds", Integer, nullable=True),
    Column("rate_burst", Integer, nullable=True),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

media_table = Table(
    "_forge_v2_media", _internal_meta,
    Column("id", String(64), primary_key=True),
    Column("project_slug", String(80), nullable=False, index=True),
    Column("storage_key", String(512), nullable=False, unique=True),
    Column("original_name", String(255), nullable=False),
    Column("content_type", String(160), nullable=False),
    Column("size", Integer, nullable=False),
    Column("sha256", String(64), nullable=False, index=True),
    Column("owner_subject", String(160), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)


@dataclass
class Principal:
    kind: str
    subject: str
    roles: set[str]
    permissions: set[str]
    tenant_id: str | None = None
    key_id: int | None = None
    rate_requests: int | None = None
    rate_window_seconds: int | None = None
    rate_burst: int | None = None


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_api_key() -> str:
    return "jf2_" + secrets.token_urlsafe(36)


async def init_security(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_internal_meta.create_all)


def _expand_role_permissions(project: ProjectConfig, roles: set[str]) -> set[str]:
    out: set[str] = set()
    seen: set[str] = set()
    def walk(role: str):
        if role in seen:
            return
        seen.add(role)
        spec = project.roles.get(role)
        if not spec:
            return
        out.update(spec.permissions)
        for parent in spec.inherits:
            walk(parent)
    for role in roles:
        walk(role)
    return out


def permission_matches(granted: str, required: str) -> bool:
    if granted == "*" or granted == required:
        return True
    if granted.endswith(".*") and required.startswith(granted[:-1]):
        return True
    return False


def has_permission(principal: Principal, required: str | None) -> bool:
    if not required:
        return True
    return any(permission_matches(p, required) for p in principal.permissions)


async def authenticate_request(request: Request, project: ProjectConfig, engine: AsyncEngine) -> Principal:
    raw_key = request.headers.get(project.security.api_key_header)
    if not raw_key and project.security.allow_query_api_key:
        raw_key = request.query_params.get("api_key")

    bootstrap = project.security.bootstrap_admin_key or settings.bootstrap_admin_key
    if raw_key and bootstrap and hmac.compare_digest(raw_key, bootstrap):
        return Principal(kind="bootstrap", subject=f"{project.slug}:bootstrap-admin", roles={"admin"}, permissions={"*"})

    if raw_key:
        key_hash = hash_key(raw_key)
        async with engine.connect() as conn:
            row = (await conn.execute(select(api_keys_table).where(
                (api_keys_table.c.key_hash == key_hash) & (api_keys_table.c.project_slug == project.slug)
            ))).mappings().first()
        if not row or not row["enabled"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        expires_at = row["expires_at"]
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired API key")
        roles = {x for x in row["roles"].split(",") if x}
        direct = {x for x in row["permissions"].split(",") if x}
        return Principal(
            kind="api_key", subject=row["name"], roles=roles,
            permissions=direct | _expand_role_permissions(project, roles), key_id=row["id"],
            tenant_id=row["tenant_id"], rate_requests=row["rate_requests"],
            rate_window_seconds=row["rate_window_seconds"], rate_burst=row["rate_burst"]
        )

    auth = request.headers.get("Authorization", "")
    if project.security.jwt_enabled and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
        if payload.get("project") not in (None, project.slug):
            raise HTTPException(status_code=401, detail="Token is not valid for this project")
        roles = set(payload.get("roles", []))
        direct = set(payload.get("permissions", []))
        return Principal(
            kind="jwt", subject=str(payload.get("sub")), roles=roles,
            permissions=direct | _expand_role_permissions(project, roles), tenant_id=payload.get("tenant_id")
        )

    return Principal(kind="anonymous", subject="anonymous", roles=set(), permissions=set())


async def create_api_key(engine: AsyncEngine, *, project_slug: str, name: str, roles: list[str], permissions: list[str],
                         expires_at: datetime | None = None, tenant_id: str | None = None,
                         rate_requests: int | None = None, rate_window_seconds: int | None = None,
                         rate_burst: int | None = None) -> dict[str, Any]:
    raw = make_api_key()
    values = dict(
        project_slug=project_slug, name=name, prefix=raw[:12], key_hash=hash_key(raw), roles=",".join(sorted(set(roles))),
        permissions=",".join(sorted(set(permissions))), tenant_id=tenant_id, rate_requests=rate_requests,
        rate_window_seconds=rate_window_seconds, rate_burst=rate_burst, enabled=True, expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    async with engine.begin() as conn:
        result = await conn.execute(insert(api_keys_table).values(**values))
        key_id = result.inserted_primary_key[0]
    return {
        "id": key_id, "api_key": raw, "project": project_slug, "name": name, "roles": roles,
        "permissions": permissions, "tenant_id": tenant_id, "rate_requests": rate_requests,
        "rate_window_seconds": rate_window_seconds, "rate_burst": rate_burst, "expires_at": expires_at,
    }


async def revoke_api_key(engine: AsyncEngine, project_slug: str, key_id: int) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(update(api_keys_table).where(
            (api_keys_table.c.id == key_id) & (api_keys_table.c.project_slug == project_slug)
        ).values(enabled=False))
    return bool(result.rowcount)


def issue_jwt(subject: str, project_slug: str, roles: list[str], permissions: list[str], exp_minutes: int, tenant_id: str | None = None) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject, "project": project_slug, "roles": roles, "permissions": permissions,
        "iat": now, "exp": now + timedelta(minutes=exp_minutes),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
