from __future__ import annotations

from typing import Any
from fastapi import HTTPException, Request
from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.sql.schema import Table

from .config import ResourceConfig
from .security import Principal


def _visible(row: dict[str, Any], resource: ResourceConfig) -> dict[str, Any]:
    data = dict(row)
    for f in resource.hidden_fields:
        data.pop(f, None)
    if resource.readable_fields is not None:
        data = {k: v for k, v in data.items() if k in resource.readable_fields}
    return data


def _write_payload(payload: dict[str, Any], resource: ResourceConfig, table: Table) -> dict[str, Any]:
    allowed = set(table.c.keys())
    if resource.writable_fields is not None:
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
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"Invalid value for field {column.name}")


def _tenant_clause(resource: ResourceConfig, table: Table, principal: Principal):
    if not resource.tenant_field:
        return None
    if not principal.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant-bound resource requires tenant_id")
    return table.c[resource.tenant_field] == principal.tenant_id


async def list_rows(request: Request, engine, table: Table, resource: ResourceConfig, principal: Principal):
    limit = min(int(request.query_params.get("limit", resource.default_limit)), resource.max_limit)
    offset = max(int(request.query_params.get("offset", 0)), 0)
    stmt = select(table)
    clauses = []
    tenant_clause = _tenant_clause(resource, table, principal)
    if tenant_clause is not None:
        clauses.append(tenant_clause)
    if resource.soft_delete_field and resource.soft_delete_field in table.c:
        clauses.append(table.c[resource.soft_delete_field].is_(None))
    for field in resource.allowed_filters:
        if field in request.query_params and field in table.c:
            clauses.append(table.c[field] == _coerce_for_column(table.c[field], request.query_params[field]))
    if clauses:
        stmt = stmt.where(and_(*clauses))
    sort = request.query_params.get("sort")
    if sort:
        desc = sort.startswith("-")
        name = sort[1:] if desc else sort
        if name not in resource.allowed_sort or name not in table.c:
            raise HTTPException(status_code=400, detail="Sort field is not allowed")
        stmt = stmt.order_by(table.c[name].desc() if desc else table.c[name].asc())
    stmt = stmt.offset(offset).limit(limit)
    async with engine.connect() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return {"items": [_visible(dict(r), resource) for r in rows], "limit": limit, "offset": offset}


async def get_row(engine, table: Table, resource: ResourceConfig, principal: Principal, item_id: Any):
    pk = table.c[resource.primary_key]
    clauses = [pk == _coerce_for_column(pk, item_id)]
    tenant_clause = _tenant_clause(resource, table, principal)
    if tenant_clause is not None: clauses.append(tenant_clause)
    async with engine.connect() as conn:
        row = (await conn.execute(select(table).where(and_(*clauses)))).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _visible(dict(row), resource)


async def create_row(engine, table: Table, resource: ResourceConfig, principal: Principal, payload: dict[str, Any]):
    data = _write_payload(payload, resource, table)
    if resource.tenant_field:
        if not principal.tenant_id: raise HTTPException(status_code=403, detail="Tenant-bound resource requires tenant_id")
        data[resource.tenant_field] = principal.tenant_id
    async with engine.begin() as conn:
        result = await conn.execute(insert(table).values(**data))
        pk_val = result.inserted_primary_key[0] if result.inserted_primary_key else None
    if pk_val is not None:
        return await get_row(engine, table, resource, principal, pk_val)
    return {"created": True}


async def update_row(engine, table: Table, resource: ResourceConfig, principal: Principal, item_id: Any, payload: dict[str, Any]):
    data = _write_payload(payload, resource, table)
    pk = table.c[resource.primary_key]
    clauses = [pk == _coerce_for_column(pk, item_id)]
    tenant_clause = _tenant_clause(resource, table, principal)
    if tenant_clause is not None: clauses.append(tenant_clause)
    async with engine.begin() as conn:
        result = await conn.execute(update(table).where(and_(*clauses)).values(**data))
    if not result.rowcount: raise HTTPException(status_code=404, detail="Not found")
    return await get_row(engine, table, resource, principal, item_id)


async def delete_row(engine, table: Table, resource: ResourceConfig, principal: Principal, item_id: Any):
    pk = table.c[resource.primary_key]
    clauses = [pk == _coerce_for_column(pk, item_id)]
    tenant_clause = _tenant_clause(resource, table, principal)
    if tenant_clause is not None: clauses.append(tenant_clause)
    async with engine.begin() as conn:
        if resource.soft_delete_field:
            from datetime import datetime, timezone
            result = await conn.execute(update(table).where(and_(*clauses)).values({resource.soft_delete_field: datetime.now(timezone.utc)}))
        else:
            result = await conn.execute(delete(table).where(and_(*clauses)))
    if not result.rowcount: raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}
