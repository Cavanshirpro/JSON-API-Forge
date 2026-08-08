from __future__ import annotations

import hashlib
import hmac
import secrets
import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, Text, UniqueConstraint, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.exc import IntegrityError

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
    if key_data.get("use") and key_data.get("use") != "sig":
        raise HTTPException(status_code=401, detail="JWT key is not designated for signatures")
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

bootstrap_state_table = Table(
    "_forge_v4_bootstrap_state", _internal_meta,
    Column("project_slug", String(80), primary_key=True),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
)


media_usage_table = Table(
    "_forge_v4_media_usage", _internal_meta,
    Column("project_slug", String(80), primary_key=True),
    Column("owner_subject", String(160), primary_key=True),
    Column("used_bytes", Integer, nullable=False, default=0),
    Column("updated_at", DateTime(timezone=True), nullable=False),
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
    expires_at: datetime | None = None


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_api_key() -> str:
    return "jf2_" + secrets.token_urlsafe(36)


async def init_security(engine: AsyncEngine, *, mode: str = "create") -> None:
    if mode not in {"create", "validate"}:
        raise RuntimeError(f"Unsupported internal schema mode: {mode}")
    if mode == "create":
        async with engine.begin() as conn:
            await conn.run_sync(_internal_meta.create_all)
        return

    async with engine.connect() as conn:
        def missing(sync_conn):
            from sqlalchemy import inspect
            inspector = inspect(sync_conn)
            return sorted(name for name in _internal_meta.tables if not inspector.has_table(name))
        missing_tables = await conn.run_sync(missing)
    if missing_tables:
        raise RuntimeError(
            "Forge internal support schema is missing tables: " + ", ".join(missing_tables) +
            ". Run `forge migrate`."
        )


async def bootstrap_is_available(engine: AsyncEngine, project_slug: str) -> bool:
    """Return False after a one-time bootstrap credential has been consumed."""
    async with engine.connect() as conn:
        row = (await conn.execute(select(bootstrap_state_table.c.consumed_at).where(
            bootstrap_state_table.c.project_slug == project_slug
        ))).first()
    return not row or row[0] is None


async def consume_bootstrap(engine: AsyncEngine, project_slug: str) -> None:
    """Permanently consume this project's bootstrap credential in the internal DB."""
    now = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        row = (await conn.execute(select(bootstrap_state_table.c.project_slug).where(
            bootstrap_state_table.c.project_slug == project_slug
        ))).first()
        if row:
            await conn.execute(update(bootstrap_state_table).where(
                bootstrap_state_table.c.project_slug == project_slug
            ).values(consumed_at=now))
        else:
            await conn.execute(insert(bootstrap_state_table).values(project_slug=project_slug, consumed_at=now))


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


# Successful API-key lookups are cached briefly per worker to keep authentication from
# turning the internal metadata database into the first high-RPS bottleneck. The cache
# is deliberately short-lived and bounded: revocation in this process is invalidated
# immediately; other workers may retain a successful row only until the configured TTL.
_api_key_auth_cache: "OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]]" = OrderedDict()

def clear_api_key_auth_cache(project_slug: str | None = None) -> None:
    if project_slug is None:
        _api_key_auth_cache.clear()
        return
    for key in [key for key in _api_key_auth_cache if key[0] == project_slug]:
        _api_key_auth_cache.pop(key, None)

def _cached_api_key_row(project: ProjectConfig, key_hash: str) -> dict[str, Any] | None:
    if project.security.api_key_cache_ttl_seconds <= 0:
        return None
    cache_key = (project.slug, key_hash)
    item = _api_key_auth_cache.get(cache_key)
    if item is None:
        return None
    expires, row = item
    if expires <= time.monotonic():
        _api_key_auth_cache.pop(cache_key, None)
        return None
    _api_key_auth_cache.move_to_end(cache_key)
    return dict(row)

def _store_api_key_row(project: ProjectConfig, key_hash: str, row: dict[str, Any]) -> None:
    ttl = project.security.api_key_cache_ttl_seconds
    if ttl <= 0:
        return
    cache_key = (project.slug, key_hash)
    _api_key_auth_cache[cache_key] = (time.monotonic() + ttl, dict(row))
    _api_key_auth_cache.move_to_end(cache_key)
    while len(_api_key_auth_cache) > project.security.api_key_cache_max_entries:
        _api_key_auth_cache.popitem(last=False)


async def authenticate_request(request: Request, project: ProjectConfig, engine: AsyncEngine) -> Principal:
    raw_key = request.headers.get(project.security.api_key_header)
    if not raw_key and (project.security.allow_query_api_key or (getattr(request, "scope", {}).get("type") == "websocket" and project.security.allow_websocket_query_api_key)):
        raw_key = request.query_params.get("api_key")
    if raw_key is not None and (not raw_key or len(raw_key) > 512):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    bootstrap = (project.security.bootstrap_admin_key or settings.bootstrap_admin_key) if project.security.bootstrap_enabled else None
    if raw_key and bootstrap and hmac.compare_digest(raw_key, bootstrap):
        if project.security.bootstrap_one_time and not await bootstrap_is_available(engine, project.slug):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bootstrap credential has already been consumed")
        return Principal(
            kind="bootstrap",
            subject=f"bootstrap:{project.slug}",
            roles=set(),
            permissions={"admin.keys.create", "admin.credentials.delegate_any"},
        )

    if raw_key:
        key_hash = hash_key(raw_key)
        row = _cached_api_key_row(project, key_hash)
        if row is None:
            async with engine.connect() as conn:
                loaded = (await conn.execute(select(api_keys_table).where(
                    (api_keys_table.c.key_hash == key_hash) & (api_keys_table.c.project_slug == project.slug)
                ))).mappings().first()
            row = dict(loaded) if loaded else None
            if row and row["enabled"]:
                _store_api_key_row(project, key_hash, row)
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
            kind="api_key", subject=f"api-key:{row['id']}:{row['name']}", roles=roles,
            permissions=direct | _expand_role_permissions(project, roles), key_id=row["id"],
            tenant_id=row["tenant_id"], rate_requests=row["rate_requests"],
            rate_window_seconds=row["rate_window_seconds"], rate_burst=row["rate_burst"],
            expires_at=expires_at,
        )

    auth = request.headers.get("Authorization", "")
    if project.security.jwt_enabled and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        if not token or len(token) > 8192:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
        cfg = project.security
        if cfg.jwt_provider == "jwks":
            payload = await _decode_jwks_token(token, project)
        else:
            try:
                secret = cfg.jwt_secret or settings.jwt_secret
                if not secret:
                    raise HTTPException(status_code=503, detail="Local JWT verification is not configured")
                payload = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", cfg.jwt_subject_claim]})
            except jwt.PyJWTError as exc:
                raise HTTPException(status_code=401, detail="Invalid bearer token") from exc
        project_claim = _claim(payload, cfg.jwt_project_claim)
        if cfg.jwt_require_project_claim and project_claim != project.slug:
            raise HTTPException(status_code=401, detail="Bearer token is missing the required project claim")
        if project_claim not in (None, project.slug):
            raise HTTPException(status_code=401, detail="Token is not valid for this project")
        if cfg.jwt_provider == "jwks":
            roles = _claim_set(_claim(payload, cfg.jwt_roles_claim)) if cfg.jwt_trust_roles_claim else set()
            direct = _claim_set(_claim(payload, cfg.jwt_permissions_claim)) if cfg.jwt_trust_permissions_claim else set()
        else:
            roles = _claim_set(_claim(payload, cfg.jwt_roles_claim))
            direct = _claim_set(_claim(payload, cfg.jwt_permissions_claim))
        subject = _claim(payload, cfg.jwt_subject_claim)
        if subject is None:
            raise HTTPException(status_code=401, detail="Bearer token has no subject")
        tenant = _claim(payload, cfg.jwt_tenant_claim)
        if cfg.jwt_provider == "jwks" and not cfg.jwt_trust_tenant_claim:
            tenant = None
        return Principal(
            kind="jwt", subject=str(subject), roles=roles,
            permissions=direct | _expand_role_permissions(project, roles), tenant_id=str(tenant) if tenant is not None else None
        )

    return Principal(kind="anonymous", subject="anonymous", roles=set(), permissions=set())


async def _consume_bootstrap_in_transaction(conn, project_slug: str) -> None:
    """Atomically consume a bootstrap credential inside an existing DB transaction.

    `SELECT .. FOR UPDATE` serializes the normal existing-row path. For the first
    ever use, concurrent inserts race on the primary key; the losing transaction
    receives an IntegrityError and rolls back its API-key insert as well.
    """

    now = datetime.now(timezone.utc)
    row = (await conn.execute(
        select(bootstrap_state_table.c.consumed_at)
        .where(bootstrap_state_table.c.project_slug == project_slug)
        .with_for_update()
    )).first()
    if row:
        if row[0] is not None:
            raise HTTPException(status_code=401, detail="Bootstrap credential has already been consumed")
        await conn.execute(
            update(bootstrap_state_table)
            .where(
                (bootstrap_state_table.c.project_slug == project_slug)
                & (bootstrap_state_table.c.consumed_at.is_(None))
            )
            .values(consumed_at=now)
        )
    else:
        await conn.execute(insert(bootstrap_state_table).values(project_slug=project_slug, consumed_at=now))


def _permission_is_delegable(parent: Principal, requested: str) -> bool:
    return any(permission_matches(granted, requested) for granted in parent.permissions)


def ensure_credential_delegation(
    project: ProjectConfig,
    parent: Principal,
    *,
    roles: list[str],
    permissions: list[str],
    tenant_id: str | None,
    expires_at: datetime | None = None,
    rate_requests: int | None = None,
    rate_window_seconds: int | None = None,
    rate_burst: int | None = None,
    subject: str | None = None,
) -> None:
    """Prevent delegated credentials from exceeding the caller's authority.

    `admin.credentials.delegate_any` is intentionally explicit. Ordinary delegated
    admins may only reproduce a subset of their own roles/permissions/tenant and
    cannot mint a longer-lived or higher-budget credential.
    """
    if has_permission(parent, "admin.credentials.delegate_any"):
        return
    requested_roles = set(roles)
    if not requested_roles.issubset(parent.roles):
        raise HTTPException(status_code=403, detail="Cannot delegate roles not held by the caller")
    effective = set(permissions) | _expand_role_permissions(project, requested_roles)
    if any(not _permission_is_delegable(parent, permission) for permission in effective):
        raise HTTPException(status_code=403, detail="Cannot delegate permissions beyond the caller")
    if tenant_id != parent.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot delegate a different tenant")
    if parent.expires_at:
        if expires_at is None:
            raise HTTPException(status_code=403, detail="Cannot delegate a non-expiring credential from an expiring caller")
        parent_exp = parent.expires_at if parent.expires_at.tzinfo else parent.expires_at.replace(tzinfo=timezone.utc)
        child_exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if child_exp > parent_exp:
            raise HTTPException(status_code=403, detail="Cannot delegate a credential that outlives the caller")
    parent_requests = parent.rate_requests or project.rate_limit.requests
    parent_window = parent.rate_window_seconds or project.rate_limit.window_seconds
    parent_burst = parent.rate_burst or project.rate_limit.burst or parent_requests
    child_requests = rate_requests or project.rate_limit.requests
    child_window = rate_window_seconds or project.rate_limit.window_seconds
    child_burst = rate_burst or project.rate_limit.burst or child_requests
    if child_requests > parent_requests:
        raise HTTPException(status_code=403, detail="Cannot delegate a larger rate_requests budget")
    if child_burst > parent_burst:
        raise HTTPException(status_code=403, detail="Cannot delegate a larger rate_burst budget")
    # A shorter window with the same request count is a larger sustained budget.
    if child_window < parent_window and child_requests >= parent_requests:
        raise HTTPException(status_code=403, detail="Cannot delegate a more permissive rate window")
    if subject is not None and subject != parent.subject and not has_permission(parent, "admin.credentials.impersonate"):
        raise HTTPException(status_code=403, detail="Cannot issue a credential for another subject")


async def create_api_key(
    engine: AsyncEngine, *, project_slug: str, name: str, roles: list[str], permissions: list[str],
    expires_at: datetime | None = None, tenant_id: str | None = None,
    rate_requests: int | None = None, rate_window_seconds: int | None = None,
    rate_burst: int | None = None, consume_bootstrap_once: bool = False,
) -> dict[str, Any]:
    """Create an API key, optionally consuming one-time bootstrap atomically.

    When `consume_bootstrap_once=True`, bootstrap state and the durable API key are
    committed in the same internal-database transaction. Two concurrent first-admin
    requests therefore cannot both mint keys successfully.
    """

    raw = make_api_key()
    values = dict(
        project_slug=project_slug, name=name, prefix=raw[:12], key_hash=hash_key(raw), roles=",".join(sorted(set(roles))),
        permissions=",".join(sorted(set(permissions))), tenant_id=tenant_id, rate_requests=rate_requests,
        rate_window_seconds=rate_window_seconds, rate_burst=rate_burst, enabled=True, expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    try:
        async with engine.begin() as conn:
            if consume_bootstrap_once:
                await _consume_bootstrap_in_transaction(conn, project_slug)
            result = await conn.execute(insert(api_keys_table).values(**values))
            key_id = result.inserted_primary_key[0]
    except IntegrityError as exc:
        if consume_bootstrap_once:
            raise HTTPException(status_code=401, detail="Bootstrap credential has already been consumed") from exc
        raise
    clear_api_key_auth_cache(project_slug)
    return {
        "id": key_id, "api_key": raw, "project": project_slug, "name": name, "roles": roles,
        "permissions": permissions, "tenant_id": tenant_id, "rate_requests": rate_requests,
        "rate_window_seconds": rate_window_seconds, "rate_burst": rate_burst, "expires_at": expires_at,
    }


def _api_key_metadata(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "prefix": row["prefix"],
        "roles": [x for x in row["roles"].split(",") if x],
        "permissions": [x for x in row["permissions"].split(",") if x],
        "tenant_id": row["tenant_id"], "enabled": row["enabled"],
        "rate_requests": row["rate_requests"], "rate_window_seconds": row["rate_window_seconds"],
        "rate_burst": row["rate_burst"], "expires_at": row["expires_at"], "created_at": row["created_at"],
    }


async def get_api_key_metadata(engine: AsyncEngine, project_slug: str, key_id: int) -> dict[str, Any] | None:
    async with engine.connect() as conn:
        row = (await conn.execute(select(api_keys_table).where(
            (api_keys_table.c.id == key_id) & (api_keys_table.c.project_slug == project_slug)
        ))).mappings().first()
    return _api_key_metadata(row) if row else None


async def revoke_api_key(engine: AsyncEngine, project_slug: str, key_id: int) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(update(api_keys_table).where(
            (api_keys_table.c.id == key_id) & (api_keys_table.c.project_slug == project_slug)
        ).values(enabled=False))
    if result.rowcount:
        clear_api_key_auth_cache(project_slug)
    return bool(result.rowcount)



async def list_api_keys(engine: AsyncEngine, project_slug: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(select(api_keys_table).where(
            api_keys_table.c.project_slug == project_slug
        ).order_by(api_keys_table.c.id.desc()))).mappings().all()
    return [_api_key_metadata(row) for row in rows]


def issue_jwt(
    subject: str, project_slug: str, roles: list[str], permissions: list[str], exp_minutes: int,
    tenant_id: str | None = None, *, secret: str | None = None,
) -> str:
    signing_secret = secret or settings.jwt_secret
    if not signing_secret:
        raise RuntimeError("Local JWT signing secret is not configured")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject, "project": project_slug, "roles": roles, "permissions": permissions,
        "iat": now, "exp": now + timedelta(minutes=exp_minutes),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, signing_secret, algorithm="HS256")
