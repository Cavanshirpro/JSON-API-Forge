from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from .config import MongoResourceConfig, ProjectConfig
from .security import Principal
from .validation import validate_json_schema


@dataclass
class MongoRegistry:
    clients: dict[str, Any]
    databases: dict[str, Any]

    async def dispose(self) -> None:
        for client in self.clients.values():
            result = client.close()
            if hasattr(result, "__await__"):
                await result


async def build_mongo_registry(project: ProjectConfig) -> MongoRegistry | None:
    if not project.mongo_databases:
        return None
    try:
        from pymongo import AsyncMongoClient
    except ImportError as exc:
        raise RuntimeError("MongoDB is configured but pymongo with AsyncMongoClient is not installed") from exc
    clients, databases = {}, {}
    for alias, cfg in project.mongo_databases.items():
        client = AsyncMongoClient(
            cfg.uri,
            maxPoolSize=cfg.max_pool_size,
            minPoolSize=cfg.min_pool_size,
            serverSelectionTimeoutMS=cfg.server_selection_timeout_ms,
        )
        clients[alias] = client
        databases[alias] = client[cfg.database]
    return MongoRegistry(clients=clients, databases=databases)


def _visible(doc: dict[str, Any], resource: MongoResourceConfig) -> dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for field in resource.hidden_fields:
        out.pop(field, None)
    return out


def _write_payload(payload: dict[str, Any], resource: MongoResourceConfig, schema: dict[str, Any] | None) -> dict[str, Any]:
    validate_json_schema(payload, schema, label=f"mongo:{resource.path}")
    if resource.writable_fields is None:
        return {k: v for k, v in payload.items() if k != "_id"}
    unknown = set(payload) - set(resource.writable_fields)
    if unknown:
        raise HTTPException(status_code=422, detail={"forbidden_or_unknown_fields": sorted(unknown)})
    return {k: v for k, v in payload.items() if k in resource.writable_fields}


def _base_filter(resource: MongoResourceConfig, principal: Principal) -> dict[str, Any]:
    filt: dict[str, Any] = {}
    if resource.tenant_field:
        if not principal.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant-bound Mongo resource requires tenant_id")
        filt[resource.tenant_field] = principal.tenant_id
    if resource.soft_delete_field:
        filt[resource.soft_delete_field] = None
    return filt


def _id_filter(item_id: str) -> Any:
    try:
        from bson import ObjectId
        if ObjectId.is_valid(item_id):
            return ObjectId(item_id)
    except ImportError:
        pass
    return item_id


def _query_filter(request: Request, resource: MongoResourceConfig, principal: Principal) -> dict[str, Any]:
    filt = _base_filter(resource, principal)
    op_map = {"ne": "$ne", "gt": "$gt", "gte": "$gte", "lt": "$lt", "lte": "$lte", "in": "$in"}
    reserved = {"limit", "offset", "sort"}
    for key, value in request.query_params.items():
        if key in reserved:
            continue
        field, op = (key.rsplit("__", 1) if "__" in key else (key, "eq"))
        if field not in resource.allowed_filters or op not in resource.filter_operators:
            continue
        if op == "eq":
            filt[field] = value
        elif op == "in":
            filt[field] = {"$in": [x for x in value.split(",") if x]}
        else:
            existing = filt.get(field)
            if not isinstance(existing, dict): existing = {}
            existing[op_map[op]] = value
            filt[field] = existing
    return filt


async def list_documents(request: Request, database, resource: MongoResourceConfig, principal: Principal):
    try:
        limit = min(max(int(request.query_params.get("limit", resource.default_limit)), 1), resource.max_limit)
        offset = max(int(request.query_params.get("offset", 0)), 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="limit/offset must be integers") from exc
    cursor = database[resource.collection].find(_query_filter(request, resource, principal)).skip(offset).limit(limit)
    sort = request.query_params.get("sort")
    if sort:
        desc = sort.startswith("-"); field = sort[1:] if desc else sort
        if field not in resource.allowed_sort:
            raise HTTPException(status_code=400, detail="Sort field is not allowed")
        cursor = cursor.sort(field, -1 if desc else 1)
    rows = await cursor.to_list(length=limit)
    return {"items": [_visible(row, resource) for row in rows], "limit": limit, "offset": offset}


async def count_documents(request: Request, database, resource: MongoResourceConfig, principal: Principal):
    count = await database[resource.collection].count_documents(_query_filter(request, resource, principal))
    return {"count": int(count)}


async def get_document(database, resource: MongoResourceConfig, principal: Principal, item_id: str):
    filt = {"_id": _id_filter(item_id), **_base_filter(resource, principal)}
    row = await database[resource.collection].find_one(filt)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return _visible(row, resource)


async def create_document(database, resource: MongoResourceConfig, principal: Principal, payload: dict[str, Any]):
    data = _write_payload(payload, resource, resource.create_schema)
    if resource.tenant_field:
        if not principal.tenant_id: raise HTTPException(status_code=403, detail="Tenant-bound Mongo resource requires tenant_id")
        data[resource.tenant_field] = principal.tenant_id
    result = await database[resource.collection].insert_one(data)
    return await get_document(database, resource, principal, str(result.inserted_id))


async def update_document(database, resource: MongoResourceConfig, principal: Principal, item_id: str, payload: dict[str, Any]):
    data = _write_payload(payload, resource, resource.update_schema)
    if not data: raise HTTPException(status_code=422, detail="No writable fields supplied")
    filt = {"_id": _id_filter(item_id), **_base_filter(resource, principal)}
    result = await database[resource.collection].update_one(filt, {"$set": data})
    if not result.matched_count: raise HTTPException(status_code=404, detail="Not found")
    return await get_document(database, resource, principal, item_id)


async def delete_document(database, resource: MongoResourceConfig, principal: Principal, item_id: str):
    filt = {"_id": _id_filter(item_id), **_base_filter(resource, principal)}
    if resource.soft_delete_field:
        result = await database[resource.collection].update_one(filt, {"$set": {resource.soft_delete_field: datetime.now(timezone.utc)}})
        count = result.matched_count
    else:
        result = await database[resource.collection].delete_one(filt)
        count = result.deleted_count
    if not count: raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}
