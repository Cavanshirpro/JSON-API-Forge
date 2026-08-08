"""Live dependency smoke tests used by the GitHub integration job.

These tests intentionally skip in a lightweight local checkout. CI supplies real
PostgreSQL, Redis and MongoDB service containers and installs all optional drivers.
"""
from __future__ import annotations

import os

import pytest


@pytest.mark.asyncio
async def test_postgres_service_container():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not configured")
    asyncpg = pytest.importorskip("asyncpg")
    conn = await asyncpg.connect(url)
    try:
        assert await conn.fetchval("SELECT 1") == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_redis_service_container():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not configured")
    redis_asyncio = pytest.importorskip("redis.asyncio")
    client = redis_asyncio.from_url(url, decode_responses=True)
    try:
        assert await client.ping() is True
        await client.set("forge-ci", "ok", ex=10)
        assert await client.get("forge-ci") == "ok"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_mongo_service_container():
    url = os.getenv("TEST_MONGO_URL")
    if not url:
        pytest.skip("TEST_MONGO_URL not configured")
    pymongo = pytest.importorskip("pymongo")
    if not hasattr(pymongo, "AsyncMongoClient"):
        pytest.fail("Installed PyMongo does not expose AsyncMongoClient")
    client = pymongo.AsyncMongoClient(url, serverSelectionTimeoutMS=5000)
    try:
        result = await client.admin.command("ping")
        assert result.get("ok") == 1.0
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_postgres_forge_idempotent_transaction():
    """Exercise the v0.4 idempotency ledger and business writes in one real PG transaction."""
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not configured")
    pytest.importorskip("asyncpg")
    from uuid import uuid4
    from fastapi import HTTPException
    from starlette.requests import Request
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from framework.config import OperationConfig
    from framework.operations import execute_idempotent_operation, init_operation_idempotency
    from framework.security import Principal

    async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, pool_pre_ping=True)
    suffix = uuid4().hex[:12]
    table = f"forge_ci_accounts_{suffix}"
    operation_name = f"transfer-{suffix}"
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY, balance INTEGER NOT NULL)'))
            await conn.execute(text(f'INSERT INTO "{table}" (id,balance) VALUES (\'a\',100),(\'b\',0)'))
        await init_operation_idempotency(engine)
        operation = OperationConfig.model_validate({
            "name": operation_name,
            "permission": "economy.transfer",
            "transaction": True,
            "idempotency": True,
            "statements": [
                {
                    "sql": f'UPDATE "{table}" SET balance=balance-:amount WHERE id=:sender AND balance>=:amount',
                    "mode": "execute", "require_rowcount_min": 1,
                    "params": {"amount": "$body.amount", "sender": "$body.sender"},
                    "result_name": "debit",
                },
                {
                    "sql": f'UPDATE "{table}" SET balance=balance+:amount WHERE id=:receiver',
                    "mode": "execute", "require_rowcount_min": 1,
                    "params": {"amount": "$body.amount", "receiver": "$body.receiver"},
                    "result_name": "credit",
                },
            ],
        })
        principal = Principal(kind="api_key", subject="ci-bot", roles=set(), permissions={"economy.transfer"})
        request = Request({
            "type":"http","method":"POST","path":"/rpc/transfer","headers":[],"query_string":b"",
            "path_params":{},"server":("test",80),"client":("127.0.0.1",1),"scheme":"http",
        })
        request.state.validated_parameters = {}
        body = {"sender":"a","receiver":"b","amount":25}
        first, replay = await execute_idempotent_operation(
            engine, project_slug="ci", operation=operation, principal=principal,
            raw_key="interaction-1", body=body, request=request,
        )
        assert replay is False and first["debit"]["rowcount"] == 1
        second, replay = await execute_idempotent_operation(
            engine, project_slug="ci", operation=operation, principal=principal,
            raw_key="interaction-1", body=body, request=request,
        )
        assert replay is True and second == first
        with pytest.raises(HTTPException) as conflict:
            await execute_idempotent_operation(
                engine, project_slug="ci", operation=operation, principal=principal,
                raw_key="interaction-1", body={**body,"amount":30}, request=request,
            )
        assert conflict.value.status_code == 409
        async with engine.connect() as conn:
            balances = dict((await conn.execute(text(f'SELECT id,balance FROM "{table}" ORDER BY id'))).all())
        assert balances == {"a":75,"b":25}

        with pytest.raises(HTTPException):
            await execute_idempotent_operation(
                engine, project_slug="ci", operation=operation, principal=principal,
                raw_key="interaction-insufficient", body={**body,"amount":999}, request=request,
            )
        async with engine.connect() as conn:
            balances_after = dict((await conn.execute(text(f'SELECT id,balance FROM "{table}" ORDER BY id'))).all())
        assert balances_after == balances  # failed debit rolls back the whole operation
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
        await engine.dispose()


@pytest.mark.asyncio
async def test_redis_forge_rate_limiter_is_distributed():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not configured")
    pytest.importorskip("redis.asyncio")
    from uuid import uuid4
    from fastapi import HTTPException
    from framework.rate_limit import RedisRateLimiter

    prefix = f"forge-ci-rate:{uuid4().hex}"
    first = RedisRateLimiter(url, prefix=prefix)
    second = RedisRateLimiter(url, prefix=prefix)
    try:
        await first.check("same-principal", 2, 60, 2)
        await second.check("same-principal", 2, 60, 2)
        with pytest.raises(HTTPException) as exc:
            await first.check("same-principal", 2, 60, 2)
        assert exc.value.status_code == 429
    finally:
        await first.close(); await second.close()


@pytest.mark.asyncio
async def test_mongo_forge_crud_with_tenant_isolation():
    url = os.getenv("TEST_MONGO_URL")
    if not url:
        pytest.skip("TEST_MONGO_URL not configured")
    pymongo = pytest.importorskip("pymongo")
    from uuid import uuid4
    from starlette.requests import Request
    from framework.config import MongoResourceConfig
    from framework.mongo import create_document, delete_document, get_document, list_documents
    from framework.security import Principal

    client = pymongo.AsyncMongoClient(url, serverSelectionTimeoutMS=5000)
    db = client["forge_test"]
    collection = f"profiles_{uuid4().hex[:12]}"
    resource = MongoResourceConfig.model_validate({
        "database":"main","collection":collection,"path":"profiles",
        "tenant_field":"tenant_id","allowed_filters":["name"],"allowed_sort":["name"],
        "writable_fields":["name"]
    })
    t1 = Principal(kind="api_key",subject="one",roles=set(),permissions=set(),tenant_id="t1")
    t2 = Principal(kind="api_key",subject="two",roles=set(),permissions=set(),tenant_id="t2")
    try:
        one = await create_document(db, resource, t1, {"name":"Alice"})
        await create_document(db, resource, t2, {"name":"Bob"})
        request = Request({
            "type":"http","method":"GET","path":"/profiles","headers":[],"query_string":b"",
            "server":("test",80),"client":("127.0.0.1",1),"scheme":"http",
        })
        listed = await list_documents(request, db, resource, t1)
        assert [row["name"] for row in listed["items"]] == ["Alice"]
        assert (await get_document(db, resource, t1, one["_id"]))["name"] == "Alice"
        await delete_document(db, resource, t1, one["_id"])
    finally:
        await db[collection].drop()
        await client.close()


@pytest.mark.asyncio
async def test_redis_event_hub_cross_instance_delivery():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not configured")
    pytest.importorskip("redis.asyncio")
    import asyncio
    from uuid import uuid4
    from framework.events import RedisEventHub

    suffix = uuid4().hex
    publisher = RedisEventHub(url, f"forge-ci-events:{suffix}", "project")
    subscriber = RedisEventHub(url, f"forge-ci-events:{suffix}", "project")

    async def receive_one():
        stream = subscriber.subscribe("notifications", 8)
        try:
            return await asyncio.wait_for(anext(stream), timeout=5)
        finally:
            await stream.aclose()

    task = asyncio.create_task(receive_one())
    try:
        # Ensure the subscriber listener is registered before publishing.
        await subscriber._ensure_listener("notifications")
        delivered = await publisher.publish("notifications", {"kind": "ready", "n": 1})
        assert delivered >= 1
        assert await task == {"kind": "ready", "n": 1}
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await publisher.close()
        await subscriber.close()


@pytest.mark.asyncio
async def test_postgres_one_time_bootstrap_is_atomic_under_concurrency():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not configured")
    pytest.importorskip("asyncpg")
    import asyncio
    from uuid import uuid4
    from fastapi import HTTPException
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import create_async_engine
    from framework.security import (
        api_keys_table, bootstrap_state_table, create_api_key, init_security,
    )

    async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, pool_pre_ping=True)
    project = f"bootstrap-{uuid4().hex[:12]}"
    try:
        await init_security(engine)

        async def mint(name: str):
            try:
                key = await create_api_key(
                    engine, project_slug=project, name=name, roles=["admin"], permissions=["*"],
                    consume_bootstrap_once=True,
                )
                return ("ok", key["id"])
            except HTTPException as exc:
                return ("denied", exc.status_code)

        results = await asyncio.gather(mint("first-a"), mint("first-b"))
        assert sorted(status for status, _ in results) == ["denied", "ok"]
        assert next(value for status, value in results if status == "denied") == 401
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(api_keys_table).where(api_keys_table.c.project_slug == project))
            await conn.execute(delete(bootstrap_state_table).where(bootstrap_state_table.c.project_slug == project))
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_media_owner_quota_is_atomic_under_concurrency(tmp_path):
    """Two workers must not both reserve beyond one owner's byte quota."""
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not configured")
    pytest.importorskip("asyncpg")
    import asyncio
    from io import BytesIO
    from uuid import uuid4

    from fastapi import HTTPException, UploadFile
    from starlette.datastructures import Headers
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import create_async_engine

    from framework.config import MediaConfig
    from framework.media import LocalMediaStore, save_media
    from framework.security import init_security, media_table, media_usage_table

    async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(async_url, pool_pre_ping=True)
    project = f"media-quota-{uuid4().hex[:12]}"
    owner = "api-key:quota:test"
    store = LocalMediaStore(str(tmp_path / project))
    config = MediaConfig.model_validate({
        "enabled": True,
        "backend": "local",
        "local_directory": str(tmp_path / project),
        "max_upload_bytes": 100,
        "max_owner_bytes": 10,
        "allowed_mime_types": ["application/octet-stream"],
        "deduplicate": False,
    })

    def upload(name: str) -> UploadFile:
        return UploadFile(
            file=BytesIO(b"1234567"),
            filename=name,
            headers=Headers({"content-type": "application/octet-stream"}),
        )

    async def save(name: str):
        try:
            value = await save_media(
                engine=engine,
                store=store,
                project_slug=project,
                config=config,
                upload=upload(name),
                owner_subject=owner,
            )
            return ("ok", value["size"])
        except HTTPException as exc:
            return ("denied", exc.status_code)

    try:
        await init_security(engine)
        results = await asyncio.gather(save("a.bin"), save("b.bin"))
        assert sorted(status for status, _ in results) == ["denied", "ok"]
        assert next(value for status, value in results if status == "denied") == 413
        async with engine.connect() as conn:
            used = (await conn.execute(select(media_usage_table.c.used_bytes).where(
                (media_usage_table.c.project_slug == project)
                & (media_usage_table.c.owner_subject == owner)
            ))).scalar_one()
            stored = (await conn.execute(select(media_table.c.id).where(
                media_table.c.project_slug == project
            ))).all()
        assert used == 7
        assert len(stored) == 1
    finally:
        async with engine.begin() as conn:
            await conn.execute(delete(media_table).where(media_table.c.project_slug == project))
            await conn.execute(delete(media_usage_table).where(media_usage_table.c.project_slug == project))
        await engine.dispose()


def test_postgres_forge_migrate_then_validate_mode(tmp_path, monkeypatch):
    """The explicit migration command must prepare a validate-only runtime."""
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not configured")
    asyncpg = pytest.importorskip("asyncpg")
    import asyncio
    import json
    from uuid import uuid4

    from framework.cli import main as forge_main
    from framework.config import load_config
    from framework.db import build_registry
    from framework.settings import settings

    async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    suffix = uuid4().hex[:12]
    table = f"forge_ci_migrate_{suffix}"
    root = tmp_path / "forge-migrate"
    project = root / "app" / "MigrationApp"
    project.mkdir(parents=True)
    (root / ".env").write_text(
        f"INTERNAL_DATABASE_URL={async_url}\nINTERNAL_SCHEMA_MODE=validate\n",
        encoding="utf-8",
    )
    config = {
        "slug": "migration-ci",
        "name": "Migration CI",
        "docs_enabled": False,
        "databases": {
            "primary": {
                "url": async_url,
                "support_schema_mode": "validate",
            }
        },
        "resources": [{
            "database": "primary",
            "table": table,
            "path": "items",
            "auto_create": True,
            "columns": {
                "id": {"type": "integer", "primary_key": True, "nullable": False},
                "name": {"type": "string", "nullable": False},
            },
            "permissions": {
                "list": "items.list", "read": "items.read", "create": "items.create",
                "update": "items.update", "delete": "items.delete",
            },
        }],
    }
    (project / "app.json").write_text(json.dumps(config), encoding="utf-8")

    original_settings = {name: getattr(settings, name) for name in settings.__class__.model_fields}
    forge_main(["--root", str(root), "migrate"])

    async def verify():
        conn = await asyncpg.connect(url)
        try:
            assert await conn.fetchval("SELECT to_regclass($1)", table) == table
            assert await conn.fetchval("SELECT to_regclass('_forge_v4_operation_idempotency')") == "_forge_v4_operation_idempotency"
        finally:
            await conn.close()

        cfg = load_config(root / "app")
        registry = await build_registry(cfg.projects[0])
        await registry.dispose()

    try:
        asyncio.run(verify())
    finally:
        async def cleanup():
            conn = await asyncpg.connect(url)
            try:
                await conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            finally:
                await conn.close()
        asyncio.run(cleanup())
        for name, value in original_settings.items():
            setattr(settings, name, value)
