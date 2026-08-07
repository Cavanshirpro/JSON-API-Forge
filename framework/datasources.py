from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, Request

from .config import DataSourceConfig, ProjectConfig
from .services.http_client import ResilientHTTPClient


class DataSourceManager:
    def __init__(self, project: ProjectConfig):
        self.project = project
        self.root = Path(project.project_dir).resolve()
        self._locks: dict[str, asyncio.Lock] = {}
        self.http = ResilientHTTPClient()

    def _lock(self, name: str) -> asyncio.Lock:
        return self._locks.setdefault(name, asyncio.Lock())

    def _file_path(self, source: DataSourceConfig) -> Path:
        path = (self.root / (source.file or "")).resolve()
        if self.root not in path.parents and path != self.root:
            raise HTTPException(status_code=400, detail="Data source path escapes project directory")
        return path

    def _read_file_sync(self, source: DataSourceConfig) -> Any:
        path = self._file_path(source)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Data source file not found: {source.file}")
        if source.type == "json_file":
            return json.loads(path.read_text(encoding="utf-8"))
        if source.type == "yaml_file":
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        if source.type == "csv_file":
            with path.open("r", encoding="utf-8", newline="") as fh:
                return list(csv.DictReader(fh))
        raise RuntimeError("Unsupported file source")

    def _write_file_sync(self, source: DataSourceConfig, value: Any) -> None:
        path = self._file_path(source)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        if source.type == "json_file":
            tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        elif source.type == "yaml_file":
            tmp.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
        else:
            raise HTTPException(status_code=405, detail="CSV data sources are read-only")
        tmp.replace(path)

    async def read(self, source: DataSourceConfig, request: Request, payload: Any = None) -> Any:
        if source.type == "static":
            data = source.data
        elif source.type in {"json_file", "yaml_file", "csv_file"}:
            data = await asyncio.to_thread(self._read_file_sync, source)
        elif source.type == "http":
            kwargs: dict[str, Any] = {"headers": source.headers, "retries": source.retries, "timeout": source.timeout_seconds}
            if source.forward_query:
                kwargs["params"] = list(request.query_params.multi_items())
            if source.forward_body and payload is not None:
                kwargs["json"] = payload
            response = await self.http.request(source.method, source.url or "", **kwargs)
            ctype = response.headers.get("content-type", "")
            return response.json() if "json" in ctype else {"status_code": response.status_code, "text": response.text}
        else:
            raise RuntimeError(f"Unsupported data source type {source.type}")
        return self._query_collection(data, source, request)

    def _query_collection(self, data: Any, source: DataSourceConfig, request: Request) -> Any:
        if not isinstance(data, list):
            return data
        rows = data[: source.max_items]
        reserved = {"limit", "offset", "sort"}
        for key, value in request.query_params.items():
            if key in reserved:
                continue
            rows = [row for row in rows if isinstance(row, dict) and str(row.get(key)) == value]
        sort = request.query_params.get("sort")
        if sort:
            reverse = sort.startswith("-")
            field = sort[1:] if reverse else sort
            rows = sorted(rows, key=lambda r: (r.get(field) is None, r.get(field)) if isinstance(r, dict) else (True, None), reverse=reverse)
        try:
            limit = min(max(int(request.query_params.get("limit", "100")), 1), source.max_items)
            offset = max(int(request.query_params.get("offset", "0")), 0)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="limit/offset must be integers") from exc
        return {"items": rows[offset:offset + limit], "limit": limit, "offset": offset, "total": len(rows)}

    def _mutate_file_sync(self, source: DataSourceConfig, action: str, *, payload: Any = None, item_id: str | None = None) -> Any:
        from filelock import FileLock, Timeout
        path = self._file_path(source)
        lock = FileLock(str(path) + ".forge.lock", timeout=source.file_lock_timeout_seconds)
        try:
            with lock:
                data = self._read_file_sync(source)
                if not isinstance(data, list):
                    raise HTTPException(status_code=422, detail="Writable file data source must contain a list of objects")
                if action == "create":
                    if not isinstance(payload, dict):
                        raise HTTPException(status_code=422, detail="Writable file create payload must be an object")
                    item = dict(payload)
                    if source.id_field not in item:
                        numeric = [x.get(source.id_field) for x in data if isinstance(x, dict) and isinstance(x.get(source.id_field), int)]
                        item[source.id_field] = (max(numeric) + 1) if numeric else 1
                    if any(isinstance(x, dict) and str(x.get(source.id_field)) == str(item[source.id_field]) for x in data):
                        raise HTTPException(status_code=409, detail="Duplicate data-source id")
                    data.append(item); self._write_file_sync(source, data); return item
                if action == "update":
                    if not isinstance(payload, dict):
                        raise HTTPException(status_code=422, detail="Writable file update payload must be an object")
                    for idx, row in enumerate(data):
                        if isinstance(row, dict) and str(row.get(source.id_field)) == str(item_id):
                            immutable_id = row.get(source.id_field)
                            updated = {**row, **payload, source.id_field: immutable_id}
                            data[idx] = updated; self._write_file_sync(source, data); return updated
                    raise HTTPException(status_code=404, detail="Data source item not found")
                if action == "delete":
                    new_data = [row for row in data if not (isinstance(row, dict) and str(row.get(source.id_field)) == str(item_id))]
                    if len(new_data) == len(data):
                        raise HTTPException(status_code=404, detail="Data source item not found")
                    self._write_file_sync(source, new_data); return {"deleted": True}
                raise RuntimeError(f"Unknown file mutation action: {action}")
        except Timeout as exc:
            raise HTTPException(status_code=503, detail="Data source file is busy", headers={"Retry-After": "1"}) from exc

    async def create(self, source: DataSourceConfig, payload: Any) -> Any:
        if not source.writable or source.type not in {"json_file", "yaml_file"}:
            raise HTTPException(status_code=405, detail="Data source is read-only")
        async with self._lock(source.name):
            return await asyncio.to_thread(self._mutate_file_sync, source, "create", payload=payload)

    async def update(self, source: DataSourceConfig, item_id: str, payload: dict[str, Any]) -> Any:
        if not source.writable or source.type not in {"json_file", "yaml_file"}:
            raise HTTPException(status_code=405, detail="Data source is read-only")
        async with self._lock(source.name):
            return await asyncio.to_thread(self._mutate_file_sync, source, "update", payload=payload, item_id=item_id)

    async def delete(self, source: DataSourceConfig, item_id: str) -> dict[str, bool]:
        if not source.writable or source.type not in {"json_file", "yaml_file"}:
            raise HTTPException(status_code=405, detail="Data source is read-only")
        async with self._lock(source.name):
            return await asyncio.to_thread(self._mutate_file_sync, source, "delete", item_id=item_id)

    async def close(self) -> None:
        await self.http.close()
