from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import ColumnConfig, ProjectConfig, ResourceConfig


@dataclass
class DatabaseRegistry:
    engines: dict[str, AsyncEngine]
    metadata: dict[str, MetaData]
    tables: dict[tuple[str, str], Table]

    async def dispose(self) -> None:
        for engine in self.engines.values():
            await engine.dispose()


def _column_type(spec: ColumnConfig):
    t = spec.type.lower()
    if t in {"int", "integer", "bigint"}: return Integer
    if t in {"float", "number", "double"}: return Float
    if t in {"bool", "boolean"}: return Boolean
    if t in {"text"}: return Text
    if t in {"datetime", "timestamp"}: return DateTime(timezone=True)
    if t in {"json", "object", "array"}: return JSON
    return String(spec.max_length or 255)


def _ensure_sqlite_dir(url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def _engine_kwargs(db) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": db.echo, "pool_pre_ping": db.pool_pre_ping}
    if db.isolation_level:
        kwargs["isolation_level"] = db.isolation_level
    if not db.url.startswith("sqlite"):
        kwargs.update(
            pool_size=db.pool_size,
            max_overflow=db.max_overflow,
            pool_timeout=db.pool_timeout,
            pool_recycle=db.pool_recycle,
        )
    return kwargs


def build_declared_table(metadata: MetaData, resource: ResourceConfig) -> Table:
    cols: list[Column[Any]] = []
    for name, spec in resource.columns.items():
        kwargs: dict[str, Any] = {
            "nullable": spec.nullable,
            "primary_key": spec.primary_key,
            "unique": spec.unique,
            "index": spec.index,
        }
        if spec.default is not None:
            kwargs["default"] = spec.default
        if spec.primary_key and spec.type.lower() in {"int", "integer", "bigint"}:
            kwargs["autoincrement"] = True
        cols.append(Column(name, _column_type(spec), **kwargs))
    if not cols:
        raise RuntimeError(f"Resource {resource.path!r} uses auto_create but has no columns")
    return Table(resource.table, metadata, *cols, extend_existing=True)


async def _reflect_table(engine: AsyncEngine, metadata: MetaData, table_name: str) -> Table:
    def sync_reflect(conn):
        metadata.reflect(bind=conn, only=[table_name])
    async with engine.begin() as conn:
        await conn.run_sync(sync_reflect)
    return metadata.tables[table_name]


async def build_registry(project: ProjectConfig) -> DatabaseRegistry:
    engines: dict[str, AsyncEngine] = {}
    metadata_map: dict[str, MetaData] = {}
    tables: dict[tuple[str, str], Table] = {}

    for alias, db in project.databases.items():
        _ensure_sqlite_dir(db.url)
        engines[alias] = create_async_engine(db.url, **_engine_kwargs(db))
        metadata_map[alias] = MetaData()

    for resource in project.resources:
        if not resource.enabled:
            continue
        if resource.database not in engines:
            raise RuntimeError(f"Unknown database alias {resource.database!r} in resource {resource.path!r}")
        engine = engines[resource.database]
        metadata = metadata_map[resource.database]
        if resource.auto_create:
            table = build_declared_table(metadata, resource)
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
        else:
            table = await _reflect_table(engine, metadata, resource.table)
        tables[(resource.database, resource.table)] = table

    return DatabaseRegistry(engines=engines, metadata=metadata_map, tables=tables)
