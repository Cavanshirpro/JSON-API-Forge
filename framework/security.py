from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, select, insert, update
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import AppConfig
from .settings import settings

_internal_meta = MetaData()
audit_table = Table(
    "_forge_audit", _internal_meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("request_id", String(64), nullable=False, index=True),
    Column("principal_kind", String(32), nullable=False),
    Column("principal_subject", String(160), nullable=False),
    Column("method", String(12), nullable=False),
    Column("path", String(512), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("duration_ms", Integer, nullable=False),
)

api_keys_table = Table(
    "_forge_api_keys", _internal_meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(120), nullable=False),
    Column("prefix", String(16), nullable=False, index=True),
    Column("key_hash", String(64), nullable=False, unique=True),
    Column("roles", Text, nullable=False, default=""),
    Column("permissions", Text, nullable=False, default=""),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


@dataclass
class Principal:
    kind: str
    subject: str
    roles: set[str]
    permissions: set[str]
    tenant_id: str | None = None
    key_id: int | None = None


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_api_key() -> str:
    return "jf_" + secrets.token_urlsafe(36)


async def init_security(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(_internal_meta.create_all)


def _expand_role_permissions(config: AppConfig, roles: set[str]) -> set[str]:
    out: set[str] = set()
    seen: set[str] = set()
    def walk(role: str):
        if role in seen: return
        seen.add(role)
        spec = config.roles.get(role)
        if not spec: return
        out.update(spec.permissions)
        for parent in spec.inherits:
            walk(parent)
    for r in roles:
        walk(r)
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


async def authenticate_request(request: Request, config: AppConfig, engine: AsyncEngine) -> Principal:
    header = config.security.api_key_header
    raw_key = request.headers.get(header)
    if not raw_key and config.security.allow_query_api_key:
        raw_key = request.query_params.get("api_key")

    bootstrap = config.security.bootstrap_admin_key or settings.bootstrap_admin_key
    if raw_key and bootstrap and hmac.compare_digest(raw_key, bootstrap):
        return Principal(kind="bootstrap", subject="bootstrap-admin", roles={"admin"}, permissions={"*"})

    if raw_key:
        key_hash = hash_key(raw_key)
        async with engine.connect() as conn:
            row = (await conn.execute(select(api_keys_table).where(api_keys_table.c.key_hash == key_hash))).mappings().first()
        if not row or not row["enabled"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired API key")
        roles = {x for x in row["roles"].split(",") if x}
        direct = {x for x in row["permissions"].split(",") if x}
        return Principal(
            kind="api_key", subject=row["name"], roles=roles,
            permissions=direct | _expand_role_permissions(config, roles), key_id=row["id"]
        )

    auth = request.headers.get("Authorization", "")
    if config.security.jwt_enabled and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
        roles = set(payload.get("roles", []))
        direct = set(payload.get("permissions", []))
        return Principal(
            kind="jwt", subject=str(payload.get("sub", "unknown")), roles=roles,
            permissions=direct | _expand_role_permissions(config, roles), tenant_id=payload.get("tenant_id")
        )

    return Principal(kind="anonymous", subject="anonymous", roles=set(), permissions=set())


async def create_api_key(engine: AsyncEngine, *, name: str, roles: list[str], permissions: list[str], expires_at: datetime | None = None) -> dict[str, Any]:
    raw = make_api_key()
    values = dict(
        name=name, prefix=raw[:12], key_hash=hash_key(raw), roles=",".join(sorted(set(roles))),
        permissions=",".join(sorted(set(permissions))), enabled=True, expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    async with engine.begin() as conn:
        result = await conn.execute(insert(api_keys_table).values(**values))
        key_id = result.inserted_primary_key[0]
    return {"id": key_id, "api_key": raw, "name": name, "roles": roles, "permissions": permissions, "expires_at": expires_at}


async def revoke_api_key(engine: AsyncEngine, key_id: int) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(update(api_keys_table).where(api_keys_table.c.id == key_id).values(enabled=False))
    return bool(result.rowcount)


def issue_jwt(subject: str, roles: list[str], permissions: list[str], exp_minutes: int, tenant_id: str | None = None) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"sub": subject, "roles": roles, "permissions": permissions, "iat": now, "exp": now + timedelta(minutes=exp_minutes)}
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def write_audit(engine: AsyncEngine, *, request_id: str, principal_kind: str, principal_subject: str, method: str, path: str, status_code: int, duration_ms: int) -> None:
    values = dict(
        created_at=datetime.now(timezone.utc), request_id=request_id, principal_kind=principal_kind,
        principal_subject=principal_subject[:160], method=method[:12], path=path[:512],
        status_code=status_code, duration_ms=duration_ms,
    )
    async with engine.begin() as conn:
        await conn.execute(insert(audit_table).values(**values))
