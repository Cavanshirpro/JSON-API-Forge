from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from .config import OperationConfig, SQLStatementConfig
from .security import Principal, idempotency_table
from .validation import validate_json_schema

_DANGEROUS = re.compile(r"\b(DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|ATTACH|DETACH|VACUUM|PRAGMA|DO)\b", re.I)
_FIRST_WORD = re.compile(r"^\s*([A-Za-z]+)")


def _safe_sql(stmt: SQLStatementConfig, allow_ddl: bool) -> None:
    sql = stmt.sql.strip()
    if not sql:
        raise RuntimeError("Empty SQL statement")
    # A trailing semicolon is harmless; embedded semicolons/multi-statements are not accepted.
    body = sql[:-1] if sql.endswith(";") else sql
    if ";" in body or "--" in body or "/*" in body or "*/" in body:
        raise RuntimeError("SQL operations must contain one parameterized statement and no SQL comments")
    if not allow_ddl and _DANGEROUS.search(body):
        raise RuntimeError("DDL/administrative SQL is disabled for declarative operations")
    match = _FIRST_WORD.search(body)
    verb = match.group(1).upper() if match else ""
    if stmt.mode in {"fetch_one", "fetch_all", "scalar"} and verb not in {"SELECT", "WITH", "SHOW", "EXPLAIN"}:
        # RETURNING writes are deliberately configured as execute in this framework.
        raise RuntimeError(f"mode={stmt.mode} only accepts read statements; got {verb or 'unknown'}")
    if stmt.mode == "execute" and verb in {"DROP", "ALTER", "TRUNCATE", "GRANT", "REVOKE"} and not allow_ddl:
        raise RuntimeError(f"Administrative SQL verb {verb} is disabled")


def _dig(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise HTTPException(status_code=422, detail=f"Parameter source not found: {path}")
    return current


def resolve_value(spec: Any, *, body: Any, request: Request, principal: Principal) -> Any:
    if not isinstance(spec, str) or not spec.startswith("$"):
        return spec
    if spec.startswith("$$"):
        return spec[1:]
    if spec == "$principal.subject":
        return principal.subject
    if spec == "$principal.tenant_id":
        return principal.tenant_id
    if spec == "$principal.kind":
        return principal.kind
    if spec == "$request.id":
        return getattr(request.state, "request_id", None)
    source, _, path = spec[1:].partition(".")
    if source == "body":
        return _dig(body, path)
    if source == "param":
        values = getattr(request.state, "validated_parameters", {})
        if path not in values:
            raise HTTPException(status_code=422, detail=f"Validated parameter not found: {path}")
        return values[path]
    if source == "query":
        if path not in request.query_params:
            raise HTTPException(status_code=422, detail=f"Missing query parameter: {path}")
        return request.query_params[path]
    if source == "path":
        if path not in request.path_params:
            raise HTTPException(status_code=422, detail=f"Missing path parameter: {path}")
        return request.path_params[path]
    if source == "header":
        value = request.headers.get(path)
        if value is None:
            raise HTTPException(status_code=422, detail=f"Missing header: {path}")
        return value
    raise HTTPException(status_code=422, detail=f"Unknown parameter source: {spec}")


def _params(stmt: SQLStatementConfig, *, body: Any, request: Request, principal: Principal) -> dict[str, Any]:
    return {name: resolve_value(source, body=body, request=request, principal=principal) for name, source in stmt.params.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def _execute_on_connection(conn, operation: OperationConfig, *, body: Any, request: Request, principal: Principal) -> dict[str, Any]:
    output: dict[str, Any] = {}
    unnamed: list[Any] = []
    for statement in operation.statements:
        _safe_sql(statement, operation.allow_ddl)
        result = await conn.execute(text(statement.sql), _params(statement, body=body, request=request, principal=principal))
        if statement.mode == "execute":
            rowcount = max(result.rowcount or 0, 0)
            if statement.require_rowcount_min is not None and rowcount < statement.require_rowcount_min:
                raise HTTPException(status_code=409, detail={"operation": operation.name, "reason": "rowcount_below_minimum", "minimum": statement.require_rowcount_min, "actual": rowcount})
            if statement.require_rowcount_max is not None and rowcount > statement.require_rowcount_max:
                raise HTTPException(status_code=409, detail={"operation": operation.name, "reason": "rowcount_above_maximum", "maximum": statement.require_rowcount_max, "actual": rowcount})
            value: Any = {"rowcount": rowcount}
        elif statement.mode == "fetch_one":
            row = result.mappings().first()
            value = _jsonable(dict(row)) if row else None
        elif statement.mode == "fetch_all":
            rows = result.mappings().fetchmany(statement.max_rows + 1)
            if len(rows) > statement.max_rows:
                raise HTTPException(status_code=413, detail=f"Operation result exceeds max_rows={statement.max_rows}")
            value = [_jsonable(dict(row)) for row in rows]
        else:
            value = _jsonable(result.scalar())
        if statement.result_name:
            output[statement.result_name] = value
        else:
            unnamed.append(value)
    if unnamed:
        output["results"] = unnamed
    return output


async def execute_operation(engine, operation: OperationConfig, *, body: Any, request: Request, principal: Principal) -> dict[str, Any]:
    validate_json_schema(body, operation.input_schema, label=f"operation:{operation.name}")
    if operation.transaction:
        async with engine.begin() as conn:
            return await _execute_on_connection(conn, operation, body=body, request=request, principal=principal)
    async with engine.connect() as conn:
        return await _execute_on_connection(conn, operation, body=body, request=request, principal=principal)


def idempotency_digest(project_slug: str, operation_name: str, principal: Principal, raw_key: str) -> str:
    raw = f"{project_slug}\x00{operation_name}\x00{principal.subject}\x00{raw_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def claim_idempotency(engine, project_slug: str, operation_name: str, digest: str, *, pending_ttl_seconds: int = 300) -> tuple[str, Any | None]:
    """Atomically reserve an idempotency key before side effects.

    Returns ("claimed", None), ("complete", response), or ("pending", None).
    The unique constraint makes this safe across multiple workers sharing the internal DB.
    """
    now = datetime.now(timezone.utc)
    try:
        async with engine.begin() as conn:
            await conn.execute(insert(idempotency_table).values(
                project_slug=project_slug, operation_name=operation_name, key_hash=digest, state="pending",
                response_json=None, created_at=now, updated_at=now,
            ))
        return "claimed", None
    except IntegrityError:
        pass

    async with engine.connect() as conn:
        row = (await conn.execute(select(idempotency_table).where(
            (idempotency_table.c.project_slug == project_slug)
            & (idempotency_table.c.operation_name == operation_name)
            & (idempotency_table.c.key_hash == digest)
        ))).mappings().first()
    if not row:
        # A failing claimant may have released the row between our conflict and read. Retry once.
        return await claim_idempotency(engine, project_slug, operation_name, digest, pending_ttl_seconds=pending_ttl_seconds)
    if row["state"] == "complete" and row["response_json"] is not None:
        return "complete", json.loads(row["response_json"])

    created = row["created_at"]
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if (now - created).total_seconds() > pending_ttl_seconds:
        # Crash recovery: delete only this still-pending stale reservation, then attempt to claim again.
        async with engine.begin() as conn:
            await conn.execute(delete(idempotency_table).where(
                (idempotency_table.c.id == row["id"]) & (idempotency_table.c.state == "pending")
            ))
        return await claim_idempotency(engine, project_slug, operation_name, digest, pending_ttl_seconds=pending_ttl_seconds)
    return "pending", None


async def complete_idempotency(engine, project_slug: str, operation_name: str, digest: str, response: Any) -> None:
    payload = json.dumps(response, separators=(",", ":"), default=str)
    now = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        result = await conn.execute(update(idempotency_table).where(
            (idempotency_table.c.project_slug == project_slug)
            & (idempotency_table.c.operation_name == operation_name)
            & (idempotency_table.c.key_hash == digest)
            & (idempotency_table.c.state == "pending")
        ).values(state="complete", response_json=payload, updated_at=now))
    if not result.rowcount:
        raise RuntimeError("Idempotency reservation disappeared before completion")


async def release_idempotency(engine, project_slug: str, operation_name: str, digest: str) -> None:
    """Release a pending reservation after a failed operation so a later retry can execute."""
    async with engine.begin() as conn:
        await conn.execute(delete(idempotency_table).where(
            (idempotency_table.c.project_slug == project_slug)
            & (idempotency_table.c.operation_name == operation_name)
            & (idempotency_table.c.key_hash == digest)
            & (idempotency_table.c.state == "pending")
        ))
