from __future__ import annotations

import hashlib
import hmac
import secrets
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, UniqueConstraint, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import ProjectConfig
from .settings import settings

_internal_meta = MetaData()


_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_locks: dict[str, asyncio.Lock] = {}


def _claim(payload: dict[str, Any], dotted: str, default: Any = None) -> Any:
    current: Any = payload
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _claim_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set)):
        return {str(x) for x in value if x is not None}
    return {str(value)}


async def _get_jwks(url: str, *, ttl: int, timeout: float) -> dict[str, Any]:
    now = time.monotonic()
    cached = _jwks_cache.get(url)
    if cached and cached[0] > now:
        return cached[1]
    lock = _jwks_locks.setdefault(url, asyncio.Lock())
    async with lock:
        cached = _jwks_cache.get(url)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="JWT signing keys are temporarily unavailable") from exc
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise HTTPException(status_code=503, detail="JWT signing key endpoint returned invalid JWKS")
        _jwks_cache[url] = (now + ttl, data)
        return data


async def _decode_jwks_token(token: str, project: ProjectConfig) -> dict[str, Any]:
    cfg = project.security
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token header") from exc
    kid = header.get("kid")
    alg = header.get("alg")
    if not kid or not alg or alg not in cfg.jwt_algorithms:
        raise HTTPException(status_code=401, detail="Bearer token uses an unsupported signing key or algorithm")
    jwks = await _get_jwks(cfg.jwt_jwks_url or "", ttl=cfg.jwks_cache_ttl_seconds, timeout=cfg.jwks_timeout_seconds)
    key_data = next((key for key in jwks["keys"] if key.get("kid") == kid), None)
    if key_data is None:
        # Key rotation can happen before the local TTL expires. Force one refresh once.
        _jwks_cache.pop(cfg.jwt_jwks_url or "", None)
        jwks = await _get_jwks(cfg.jwt_jwks_url or "", ttl=cfg.jwks_cache_ttl_seconds, timeout=cfg.jwks_timeout_seconds)
        key_data = next((key for key in jwks["keys"] if key.get("kid") == kid), None)
    if key_data is None:
        raise HTTPException(status_code=401, detail="Unknown JWT signing key")
    if key_data.get("alg") and key_data.get("alg") != alg:
        raise HTTPException(status_code=401, detail="JWT algorithm does not match signing key metadata")
    if key_data.get("key_ops") and "verify" not in key_data.get("key_ops", []):
        raise HTTPException(status_code=401, detail="JWT signing key is not permitted for verification")
    try:
        pyjwk = jwt.PyJWK.from_dict(key_data)
        kwargs: dict[str, Any] = {
            "algorithms": [alg],
            "options": {"require": [cfg.jwt_subject_claim, "exp"]},
        }
        if cfg.jwt_issuer:
            kwargs["issuer"] = cfg.jwt_issuer
        if cfg.jwt_audience is not None:
            kwargs["audience"] = cfg.jwt_audience
        else:
            kwargs["options"] = {**kwargs["options"], "verify_aud": False}
        return jwt.decode(token, pyjwk.key, **kwargs)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid bearer token") from exc

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

idempotency_table = Table(
    "_forge_v3_idempotency", _internal_meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_slug", String(80), nullable=False, index=True),
    Column("operation_name", String(120), nullable=False, index=True),
    Column("key_hash", String(64), nullable=False),
    Column("state", String(16), nullable=False, default="pending", index=True),
    Column("response_json", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("project_slug", "operation_name", "key_hash", name="uq_forge_v3_idempotency"),
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
    if not raw_key and (project.security.allow_query_api_key or (getattr(request, "scope", {}).get("type") == "websocket" and project.security.allow_websocket_query_api_key)):
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
        cfg = project.security
        if cfg.jwt_provider == "jwks":
            payload = await _decode_jwks_token(token, project)
        else:
            try:
                payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", cfg.jwt_subject_claim]})
            except jwt.PyJWTError as exc:
                raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
        project_claim = _claim(payload, cfg.jwt_project_claim)
        if project_claim not in (None, project.slug):
            raise HTTPException(status_code=401, detail="Token is not valid for this project")
        roles = _claim_set(_claim(payload, cfg.jwt_roles_claim))
        direct = _claim_set(_claim(payload, cfg.jwt_permissions_claim))
        subject = _claim(payload, cfg.jwt_subject_claim)
        if subject is None:
            raise HTTPException(status_code=401, detail="Bearer token has no subject")
        tenant = _claim(payload, cfg.jwt_tenant_claim)
        return Principal(
            kind="jwt", subject=str(subject), roles=roles,
            permissions=direct | _expand_role_permissions(project, roles), tenant_id=str(tenant) if tenant is not None else None
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



async def list_api_keys(engine: AsyncEngine, project_slug: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(select(api_keys_table).where(
            api_keys_table.c.project_slug == project_slug
        ).order_by(api_keys_table.c.id.desc()))).mappings().all()
    return [{
        "id": row["id"], "name": row["name"], "prefix": row["prefix"],
        "roles": [x for x in row["roles"].split(",") if x],
        "permissions": [x for x in row["permissions"].split(",") if x],
        "tenant_id": row["tenant_id"], "enabled": row["enabled"],
        "rate_requests": row["rate_requests"], "rate_window_seconds": row["rate_window_seconds"],
        "rate_burst": row["rate_burst"], "expires_at": row["expires_at"], "created_at": row["created_at"],
    } for row in rows]


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
