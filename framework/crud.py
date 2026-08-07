from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.sql.schema import Table

from .config import ResourceConfig
from .security import Principal
from .validation import validate_json_schema


def _visible(row: dict[str, Any], resource: ResourceConfig) -> dict[str, Any]:
    data = dict(row)
    for field in resource.hidden_fields:
        data.pop(field, None)
    if resource.readable_fields is not None:
        data = {k: v for k, v in data.items() if k in resource.readable_fields}
    return data


def _write_payload(payload: dict[str, Any], resource: ResourceConfig, table: Table, *, schema=None) -> dict[str, Any]:
    validate_json_schema(payload, schema, label=f"resource:{resource.path}")
    allowed = set(table.c.keys())
    if resource.writable_fields is None:
        allowed.discard(resource.primary_key)
    else:
        allowed &= set(resource.writable_fields)
    data = {k: v for k, v in payload.items() if k in allowed}
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail={"forbidden_or_unknown_fields": sorted(unknown)})
    return data


def _coerce_for_column(column, value: Any):
    if value is None:
        return None
    try:
        pytype = column.type.python_type
    except (NotImplementedError, AttributeError):
        return value
    if pytype is bool and isinstance(value, str):
        low = value.lower()
        if low in {"1", "true", "yes", "on"}: return True
        if low in {"0", "false", "no", "off"}: return False
    try:
        return pytype(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid value for field {column.name}") from exc


def _tenant_clause(resource: ResourceConfig, table: Table, principal: Principal):
    if not resource.tenant_field:
        return None
    if resource.tenant_field not in table.c:
        raise RuntimeError(f"tenant_field {resource.tenant_field!r} is missing from table {table.name!r}")
    if not principal.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant-bound resource requires tenant_id")
    return table.c[resource.tenant_field] == principal.tenant_id


def _base_clauses(resource: ResourceConfig, table: Table, principal: Principal) -> list[Any]:
    clauses: list[Any] = []
    tenant_clause = _tenant_clause(resource, table, principal)
    if tenant_clause is not None:
        clauses.append(tenant_clause)
    if resource.soft_delete_field:
        if resource.soft_delete_field not in table.c:
            raise RuntimeError(f"soft_delete_field {resource.soft_delete_field!r} missing from {table.name!r}")
        clauses.append(table.c[resource.soft_delete_field].is_(None))
    return clauses


def _parse_int(value: str | None, default: int, *, minimum: int = 0) -> int:
    if value is None: return default
    try: parsed = int(value)
    except ValueError as exc: raise HTTPException(status_code=400, detail="Pagination values must be integers") from exc
    return max(parsed, minimum)


def _filter_clause(column, op: str, raw: str):
    if op == "isnull":
        return column.is_(None) if raw.lower() in {"1", "true", "yes"} else column.is_not(None)
    if op == "in":
        values = [_coerce_for_column(column, x) for x in raw.split(",") if x != ""]
        return column.in_(values)
    value = _coerce_for_column(column, raw)
    if op == "eq": return column == value
    if op == "ne": return column != value
    if op == "gt": return column > value
    if op == "gte": return column >= value
    if op == "lt": return column < value
    if op == "lte": return column <= value
    if op == "like": return column.like(str(raw))
    if op == "ilike": return column.ilike(str(raw))
    raise HTTPException(status_code=400, detail=f"Unsupported filter operator: {op}")


def build_filter_clauses(request: Request, table: Table, resource: ResourceConfig) -> list[Any]:
    clauses: list[Any] = []
    allowed = set(resource.allowed_filters)
    ops = set(resource.filter_operators)
    reserved = {"limit", "offset", "cursor", "sort", "q"}
    for key, raw in request.query_params.items():
        if key in reserved: continue
        if "__" in key:
            field, op = key.rsplit("__", 1)
        else:
            field, op = key, "eq"
        if field not in allowed or field not in table.c or op not in ops:
            continue
        clauses.append(_filter_clause(table.c[field], op, raw))
    q = request.query_params.get("q")
    if q and resource.search_fields:
        searchable = [table.c[name].ilike(f"%{q}%") for name in resource.search_fields if name in table.c]
        if searchable:
            clauses.append(or_(*searchable))
    return clauses


async def list_rows(request: Request, engine, table: Table, resource: ResourceConfig, principal: Principal):
    limit = min(_parse_int(request.query_params.get("limit"), resource.default_limit, minimum=1), resource.max_limit)
    offset = _parse_int(request.query_params.get("offset"), 0, minimum=0)
    clauses = [*_base_clauses(resource, table, principal), *build_filter_clauses(request, table, resource)]
    stmt = select(table)
    if clauses: stmt = stmt.where(and_(*clauses))

    if resource.pagination_mode == "cursor":
        cursor_name = resource.cursor_field or resource.primary_key
        if cursor_name not in table.c: raise RuntimeError(f"cursor_field {cursor_name!r} missing from {table.name!r}")
        cursor = request.query_params.get("cursor")
        if cursor is not None:
            stmt = stmt.where(table.c[cursor_name] > _coerce_for_column(table.c[cursor_name], cursor))
        stmt = stmt.order_by(table.c[cursor_name].asc()).limit(limit + 1)
        async with engine.connect() as conn: raw_rows = (await conn.execute(stmt)).mappings().all()
        has_more = len(raw_rows) > limit
        rows = raw_rows[:limit]
        next_cursor = rows[-1][cursor_name] if has_more and rows else None
        return {"items": [_visible(dict(row), resource) for row in rows], "limit": limit, "next_cursor": next_cursor, "has_more": has_more}

    sort = request.query_params.get("sort")
    if sort:
        descending = sort.startswith("-")
        name = sort[1:] if descending else sort
        if name not in resource.allowed_sort or name not in table.c: raise HTTPException(status_code=400, detail="Sort field is not allowed")
        stmt = stmt.order_by(table.c[name].desc() if descending else table.c[name].asc())
    stmt = stmt.offset(offset).limit(limit)
    async with engine.connect() as conn: rows = (await conn.execute(stmt)).mappings().all()
    return {"items": [_visible(dict(row), resource) for row in rows], "limit": limit, "offset": offset}


async def count_rows(request: Request, engine, table: Table, resource: ResourceConfig, principal: Principal):
    clauses = [*_base_clauses(resource, table, principal), *build_filter_clauses(request, table, resource)]
    stmt = select(func.count()).select_from(table)
    if clauses: stmt = stmt.where(and_(*clauses))
    async with engine.connect() as conn: total = (await conn.execute(stmt)).scalar_one()
    return {"count": int(total)}


async def get_row(engine, table: Table, resource: ResourceConfig, principal: Principal, item_id: Any):
    pk = table.c[resource.primary_key]
    clauses = [pk == _coerce_for_column(pk, item_id), *_base_clauses(resource, table, principal)]
    async with engine.connect() as conn: row = (await conn.execute(select(table).where(and_(*clauses)))).mappings().first()
    if not row: raise HTTPException(status_code=404, detail="Not found")
    return _visible(dict(row), resource)


async def create_row(engine, table: Table, resource: ResourceConfig, principal: Principal, payload: dict[str, Any]):
    data = _write_payload(payload, resource, table, schema=resource.create_schema)
    if resource.tenant_field:
        if not principal.tenant_id: raise HTTPException(status_code=403, detail="Tenant-bound resource requires tenant_id")
        data[resource.tenant_field] = principal.tenant_id
    async with engine.begin() as conn:
        result = await conn.execute(insert(table).values(**data))
        pk_val = result.inserted_primary_key[0] if result.inserted_primary_key else None
    if pk_val is not None: return await get_row(engine, table, resource, principal, pk_val)
    return {"created": True}


async def batch_create_rows(engine, table: Table, resource: ResourceConfig, principal: Principal, payloads: list[dict[str, Any]]):
    if not resource.batch_enabled: raise HTTPException(status_code=405, detail="Batch API disabled for this resource")
    if not payloads or len(payloads) > resource.max_batch_size: raise HTTPException(status_code=422, detail=f"Batch size must be 1..{resource.max_batch_size}")
    values = []
    for payload in payloads:
        data = _write_payload(payload, resource, table, schema=resource.create_schema)
        if resource.tenant_field:
            if not principal.tenant_id: raise HTTPException(status_code=403, detail="Tenant-bound resource requires tenant_id")
            data[resource.tenant_field] = principal.tenant_id
        values.append(data)
    async with engine.begin() as conn:
        result = await conn.execute(insert(table), values)
    return {"created": len(values), "rowcount": max(result.rowcount or len(values), 0)}


async def update_row(engine, table: Table, resource: ResourceConfig, principal: Principal, item_id: Any, payload: dict[str, Any]):
    data = _write_payload(payload, resource, table, schema=resource.update_schema)
    if not data: raise HTTPException(status_code=422, detail="No writable fields supplied")
    pk = table.c[resource.primary_key]
    clauses = [pk == _coerce_for_column(pk, item_id), *_base_clauses(resource, table, principal)]
    async with engine.begin() as conn: result = await conn.execute(update(table).where(and_(*clauses)).values(**data))
    if not result.rowcount: raise HTTPException(status_code=404, detail="Not found")
    return await get_row(engine, table, resource, principal, item_id)


async def delete_row(engine, table: Table, resource: ResourceConfig, principal: Principal, item_id: Any):
    pk = table.c[resource.primary_key]
    clauses = [pk == _coerce_for_column(pk, item_id), *_base_clauses(resource, table, principal)]
    async with engine.begin() as conn:
        if resource.soft_delete_field:
            from datetime import datetime, timezone
            result = await conn.execute(update(table).where(and_(*clauses)).values({resource.soft_delete_field: datetime.now(timezone.utc)}))
        else:
            result = await conn.execute(delete(table).where(and_(*clauses)))
    if not result.rowcount: raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}
