from __future__ import annotations

import asyncio
import sys
import types
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import MetaData, Table, Column, Integer

from framework.audit import AuditWriter
from framework.config import ProjectConfig
from framework.events import EventHub, RedisEventHub, build_event_hub, sse_encode


def test_event_hub_queue_overwrite_cleanup_and_dead_websocket():
    class WS:
        def __init__(self, *, fail: bool = False):
            self.fail = fail
            self.accepted = False
            self.sent = []

        async def accept(self):
            self.accepted = True

        async def send_json(self, payload):
            if self.fail:
                raise RuntimeError("closed")
            self.sent.append(payload)

    async def run():
        hub = EventHub()
        live = WS()
        dead = WS(fail=True)
        await hub.connect_ws("updates", live)
        await hub.connect_ws("updates", dead)

        subscription = hub.subscribe("updates", 1)
        first_waiter = asyncio.create_task(anext(subscription))
        await asyncio.sleep(0)
        assert await hub.publish("updates", {"n": 1}) == 3  # SSE queue + two socket queues
        assert await first_waiter == {"n": 1}
        await asyncio.sleep(0); await asyncio.sleep(0)

        # A full best-effort queue drops the new event rather than blocking the publisher.
        await hub.publish("updates", {"n": 2})
        assert await hub.publish("updates", {"n": 3}) >= 1
        assert await anext(subscription) == {"n": 2}
        await asyncio.sleep(0); await asyncio.sleep(0)
        assert all(client.websocket is not dead for client in hub._websockets["updates"])
        assert live.sent[-1] in ({"n": 2}, {"n": 3})

        await subscription.aclose()
        assert not hub._subscribers["updates"]
        await hub.disconnect_ws("updates", live)
        assert not hub._websockets["updates"]
        assert await hub.ping() is True
        assert await hub.close() is None

    asyncio.run(run())
    assert sse_encode({"when": object()}).startswith(b"data: ")


def test_redis_event_hub_listener_ready_publish_decode_and_close(monkeypatch):
    published: list[tuple[str, str]] = []

    class FakePubSub:
        def __init__(self):
            self.subscribed = []
            self.unsubscribed = []
            self.closed = False
            self.messages = asyncio.Queue()

        async def subscribe(self, channel):
            self.subscribed.append(channel)

        async def unsubscribe(self, channel):
            self.unsubscribed.append(channel)

        async def aclose(self):
            self.closed = True

        async def listen(self):
            while True:
                yield await self.messages.get()

    class FakeRedis:
        def __init__(self):
            self.pubsub_instance = FakePubSub()
            self.closed = False

        def pubsub(self):
            return self.pubsub_instance

        async def publish(self, channel, payload):
            published.append((channel, payload))
            return 4

        async def ping(self):
            return True

        async def aclose(self):
            self.closed = True

    fake_redis = FakeRedis()
    redis_asyncio = types.ModuleType("redis.asyncio")
    redis_asyncio.from_url = lambda *a, **k: fake_redis
    redis_pkg = types.ModuleType("redis")
    redis_pkg.asyncio = redis_asyncio
    monkeypatch.setitem(sys.modules, "redis", redis_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    async def run():
        hub = RedisEventHub("redis://fake", "forge", "app")
        assert hub._redis_channel("updates") == "forge:app:updates"

        subscription = hub.subscribe("updates", 4)
        first = asyncio.create_task(anext(subscription))
        for _ in range(20):
            if hub._subscribers["updates"]:
                break
            await asyncio.sleep(0)
        await fake_redis.pubsub_instance.messages.put({"type": "message", "data": '{"ok":true}'})
        assert await asyncio.wait_for(first, 1) == {"ok": True}
        second = asyncio.create_task(anext(subscription))
        await fake_redis.pubsub_instance.messages.put({"type": "message", "data": "not-json"})
        assert await asyncio.wait_for(second, 1) == {"event": "not-json"}

        assert await hub.publish("updates", {"x": 1}) == 4
        assert published == [("forge:app:updates", '{"x":1}')]
        assert await hub.ping() is True
        await subscription.aclose()
        await hub.close()
        assert fake_redis.closed is True
        assert fake_redis.pubsub_instance.closed is True
        assert hub._listeners == {}
        assert hub._listener_ready == {}

    asyncio.run(run())


def test_redis_event_hub_ready_timeout_surfaces_listener_failure(monkeypatch):
    class BrokenPubSub:
        async def subscribe(self, channel):
            raise RuntimeError("redis subscribe failed")

        async def unsubscribe(self, channel):
            return None

        async def aclose(self):
            return None

    class BrokenRedis:
        def pubsub(self):
            return BrokenPubSub()

        async def aclose(self):
            return None

    redis_asyncio = types.ModuleType("redis.asyncio")
    redis_asyncio.from_url = lambda *a, **k: BrokenRedis()
    redis_pkg = types.ModuleType("redis")
    redis_pkg.asyncio = redis_asyncio
    monkeypatch.setitem(sys.modules, "redis", redis_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    async def run():
        hub = RedisEventHub("redis://fake", "forge", "app")
        # The listener task fails immediately. _ensure_listener should surface
        # that concrete failure rather than silently claiming readiness.
        with pytest.raises(RuntimeError, match="redis subscribe failed"):
            await hub._ensure_listener("broken")
        await hub.close()

    asyncio.run(run())


def test_build_event_hub_requires_redis_url():
    assert isinstance(build_event_hub("memory", None, "forge", "app"), EventHub)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        build_event_hub("redis", None, "forge", "app")


def test_database_registry_builds_autocreate_reflect_and_idempotency(monkeypatch, tmp_path):
    import framework.db as dbmod

    calls = {"idempotency": [], "disposed": [], "created": 0, "reflected": []}

    class FakeConn:
        async def run_sync(self, fn):
            # metadata.create_all is a bound callable in the auto-create path.
            calls["created"] += 1
            return None

    class FakeBegin:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            return None

    class FakeEngine:
        def __init__(self, url):
            self.url = url

        def begin(self):
            return FakeBegin()

        async def dispose(self):
            calls["disposed"].append(self.url)

    def fake_engine(url, **kwargs):
        return FakeEngine(url)

    async def fake_init(engine, mode="create"):
        calls["idempotency"].append(engine.url)

    async def fake_reflect(engine, metadata, table_name):
        calls["reflected"].append((engine.url, table_name))
        return Table(table_name, metadata, Column("id", Integer, primary_key=True), extend_existing=True)

    monkeypatch.setattr(dbmod, "create_async_engine", fake_engine)
    monkeypatch.setattr(dbmod, "init_operation_idempotency", fake_init)
    monkeypatch.setattr(dbmod, "_reflect_table", fake_reflect)

    sqlite_path = tmp_path / "nested" / "forge.db"
    project = ProjectConfig.model_validate({
        "slug": "p", "name": "P",
        "databases": {
            "primary": {"url": f"sqlite+aiosqlite:///{sqlite_path}"},
            "archive": {"url": "postgresql+asyncpg://u:p@db/archive"},
        },
        "resources": [
            {
                "database": "primary", "table": "items", "path": "items", "auto_create": True,
                "columns": {"id": {"type": "integer", "primary_key": True, "nullable": False}},
            },
            {"database": "archive", "table": "history", "path": "history", "auto_create": False},
        ],
        "operations": [{
            "name": "write", "path": "rpc/write", "database": "primary", "permission": "write",
            "transaction": True, "idempotency": True,
            "statements": [{"sql": "UPDATE items SET id=id WHERE id=:id", "params": {"id": "$body.id"}}],
        }],
        "security": {"jwt_enabled": False},
    })

    async def run():
        registry = await dbmod.build_registry(project)
        assert set(registry.engines) == {"primary", "archive"}
        assert ("primary", "items") in registry.tables
        assert ("archive", "history") in registry.tables
        assert calls["idempotency"] == [f"sqlite+aiosqlite:///{sqlite_path}"]
        assert calls["created"] == 1
        assert calls["reflected"] == [("postgresql+asyncpg://u:p@db/archive", "history")]
        assert sqlite_path.parent.exists()
        await registry.dispose()
        assert set(calls["disposed"]) == {f"sqlite+aiosqlite:///{sqlite_path}", "postgresql+asyncpg://u:p@db/archive"}

    asyncio.run(run())


def test_database_registry_rejects_unknown_aliases(monkeypatch):
    import framework.db as dbmod

    class FakeEngine:
        async def dispose(self):
            return None

    monkeypatch.setattr(dbmod, "create_async_engine", lambda *a, **k: FakeEngine())

    bad_resource = ProjectConfig.model_validate({
        "slug": "p", "name": "P", "databases": {"primary": {"url": "sqlite+aiosqlite:///:memory:"}},
        "resources": [{"database": "missing", "table": "x", "path": "x"}],
        "security": {"jwt_enabled": False},
    })
    with pytest.raises(RuntimeError, match="Unknown database alias"):
        asyncio.run(dbmod.build_registry(bad_resource))

    bad_operation = ProjectConfig.model_validate({
        "slug": "p", "name": "P", "databases": {"primary": {"url": "sqlite+aiosqlite:///:memory:"}},
        "operations": [{
            "name": "op", "path": "rpc/op", "database": "missing", "permission": "op",
            "transaction": True, "idempotency": True,
            "statements": [{"sql": "UPDATE x SET y=1"}],
        }],
        "security": {"jwt_enabled": False},
    })
    with pytest.raises(RuntimeError, match="Unknown database alias"):
        asyncio.run(dbmod.build_registry(bad_operation))


def test_audit_writer_permanent_failure_is_visible(caplog):
    class Conn:
        async def execute(self, stmt, batch):
            raise RuntimeError("db unavailable")

    class Ctx:
        async def __aenter__(self):
            return Conn()

        async def __aexit__(self, *args):
            return None

    class Engine:
        def begin(self):
            return Ctx()

    async def run():
        writer = AuditWriter(Engine(), max_queue=4, batch_size=2, flush_interval=0.01, write_retries=1, retry_backoff_seconds=0)
        await writer.start()
        writer.submit(project_slug="p", request_id="r", principal_kind="api_key", principal_subject="k", method="POST", path="/x", status_code=500, duration_ms=1)
        await asyncio.sleep(0.04)
        await writer.close()
        assert writer.write_failures == 2
        assert writer.dropped == 1

    asyncio.run(run())
    assert "permanently dropped" in caplog.text


def test_cache_backends_eviction_tiered_and_failure_policy(monkeypatch):
    import framework.cache as cachemod

    class FakeLock:
        def __init__(self):
            self.acquired = False
            self.released = False
        async def acquire(self):
            self.acquired = True
            return True
        async def release(self):
            self.released = True

    class FakeRedis:
        def __init__(self):
            self.data = {}
            self.locks = []
            self.closed = False
        async def get(self, key): return self.data.get(key)
        async def set(self, key, value, ex=None): self.data[key] = value
        async def delete(self, key): self.data.pop(key, None)
        async def incr(self, key):
            self.data[key] = int(self.data.get(key, 0)) + 1
            return self.data[key]
        def lock(self, key, **kwargs):
            lock = FakeLock(); self.locks.append((key, kwargs, lock)); return lock
        async def ping(self): return True
        async def aclose(self): self.closed = True

    fake_redis = FakeRedis()
    redis_asyncio = types.ModuleType("redis.asyncio")
    redis_asyncio.from_url = lambda *a, **k: fake_redis
    redis_pkg = types.ModuleType("redis"); redis_pkg.asyncio = redis_asyncio
    monkeypatch.setitem(sys.modules, "redis", redis_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", redis_asyncio)

    async def run():
        memory = cachemod.MemoryTTLCache(max_entries=2)
        await memory.set("a", b"1", 30)
        await memory.set("b", b"2", 30)
        assert await memory.get("a") == b"1"
        await memory.set("c", b"3", 30)
        # Accessing a moved it to MRU, so b is evicted.
        assert await memory.get("b") is None
        assert await memory.get("c") == b"3"
        await memory.delete("c")
        assert await memory.get("c") is None
        assert await memory.bump_generation("n") == 1
        assert await memory.generation("n") == 1
        assert await memory.ping() is True

        redis = cachemod.RedisTTLCache("redis://fake", "p")
        await redis.set("x", b"redis", 0)
        assert await redis.get("x") == b"redis"
        assert await redis.generation("n") == 0
        assert await redis.bump_generation("n") == 1
        lock = redis.distributed_lock("same", timeout=9, blocking_timeout=2)
        assert await lock.acquire() is True
        await lock.release()
        assert fake_redis.locks and fake_redis.locks[0][1]["timeout"] == 9
        assert await redis.ping() is True

        tiered = cachemod.TieredCache(cachemod.MemoryTTLCache(10), redis)
        # Force L2 hit and warm L1.
        await redis.set("l2", b"value", 10)
        assert await tiered.get("l2") == b"value"
        fake_redis.data.pop(redis._key("l2"), None)
        assert await tiered.get("l2") == b"value"
        await tiered.set("both", b"v", 20)
        assert await tiered.get("both") == b"v"
        assert await tiered.bump_generation("tier") == 1
        assert await tiered.generation("tier") == 1
        assert await tiered.ping() is True
        await tiered.delete("both")

        class BrokenBackend:
            async def generation(self, namespace): raise RuntimeError("down")
            async def get(self, key): raise RuntimeError("down")
            async def set(self, key, value, ttl): raise RuntimeError("down")
            async def bump_generation(self, namespace): raise RuntimeError("down")
            async def close(self): return None
        open_manager = cachemod.CacheManager(BrokenBackend(), fail_open=True)
        assert await open_manager.generation("x") is None
        assert await open_manager.get_json("x") is None
        await open_manager.set_json("x", {"ignored": True}, 1)
        assert await open_manager.invalidate_namespace("x") == -1
        assert await open_manager.ping() is True  # no ping method = healthy/no-op dependency
        await open_manager.close()

        closed_manager = cachemod.CacheManager(BrokenBackend(), fail_open=False)
        with pytest.raises(RuntimeError): await closed_manager.generation("x")
        with pytest.raises(RuntimeError): await closed_manager.get_json("x")
        with pytest.raises(RuntimeError): await closed_manager.set_json("x", {}, 1)
        with pytest.raises(RuntimeError): await closed_manager.invalidate_namespace("x")
        await closed_manager.close()

        await tiered.close()
        assert fake_redis.closed is True

    asyncio.run(run())


def test_build_cache_modes_and_redis_requirement(monkeypatch):
    import framework.cache as cachemod
    from framework.config import CacheConfig

    class DummyRedisCache:
        def __init__(self, url, prefix): self.url=url; self.prefix=prefix
        async def generation(self, n): return 0
        async def get(self, k): return None
        async def set(self, k, v, ttl): return None
        async def bump_generation(self, n): return 1
        async def close(self): return None
        async def ping(self): return True
    monkeypatch.setattr(cachemod, "RedisTTLCache", DummyRedisCache)

    assert cachemod.build_cache(CacheConfig(enabled=False), None) is None
    assert isinstance(cachemod.build_cache(CacheConfig(backend="memory"), None), cachemod.CacheManager)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        cachemod.build_cache(CacheConfig(backend="redis"), None)
    redis_manager = cachemod.build_cache(CacheConfig(backend="redis"), "redis://x")
    assert isinstance(redis_manager.backend, DummyRedisCache)
    tiered_manager = cachemod.build_cache(CacheConfig(backend="tiered"), "redis://x")
    assert isinstance(tiered_manager.backend, cachemod.TieredCache)


def test_media_policy_quota_dedup_delete_and_signed_url_edges(tmp_path, monkeypatch):
    import io
    from datetime import datetime, timezone
    from fastapi import UploadFile, HTTPException
    from starlette.datastructures import Headers
    import framework.media as mediamod
    from framework.config import MediaConfig
    from framework.settings import settings

    class MappingResult:
        def __init__(self, row=None, scalar=0, rowcount=1): self.row=row; self.scalar_value=scalar; self.rowcount=rowcount
        def mappings(self): return self
        def first(self): return self.row
        def scalar_one(self): return self.scalar_value

    class ScriptedConn:
        def __init__(self, engine): self.engine=engine
        async def execute(self, stmt, *args, **kwargs):
            text = str(stmt)
            if "sum(" in text.lower():
                value = self.engine.sums.pop(0) if self.engine.sums else 0
                return MappingResult(scalar=value)
            if text.lstrip().startswith("SELECT"):
                return MappingResult(row=self.engine.select_row)
            if text.lstrip().startswith("DELETE"):
                self.engine.deleted += 1
                return MappingResult(rowcount=1)
            if text.lstrip().startswith("INSERT"):
                self.engine.inserted += 1
                return MappingResult(rowcount=1)
            if text.lstrip().startswith("UPDATE"):
                # Quota reservation can be scripted with reserve_rowcounts; otherwise succeeds.
                rc = self.engine.reserve_rowcounts.pop(0) if self.engine.reserve_rowcounts else 1
                return MappingResult(rowcount=rc)
            return MappingResult(rowcount=1)

    class Ctx:
        def __init__(self, engine): self.engine=engine
        async def __aenter__(self): return ScriptedConn(self.engine)
        async def __aexit__(self, *args): return None

    class Engine:
        def __init__(self, *, sums=None, row=None, reserve_rowcounts=None):
            self.sums=list(sums or []); self.select_row=row; self.inserted=0; self.deleted=0; self.reserve_rowcounts=list(reserve_rowcounts or [])
        def connect(self): return Ctx(self)
        def begin(self): return Ctx(self)

    def upload(data=b"abc", name="x.txt", content_type="text/plain"):
        return UploadFile(io.BytesIO(data), filename=name, headers=Headers({"content-type": content_type}))

    async def run():
        store = mediamod.LocalMediaStore(str(tmp_path / "media"))
        # MIME and extension policy are separate guardrails.
        cfg = MediaConfig(enabled=True, allowed_mime_types=["image/png"], allowed_extensions=["png"])
        with pytest.raises(HTTPException) as exc:
            await mediamod.save_media(engine=Engine(), store=store, project_slug="p", config=cfg, upload=upload(content_type="text/plain"), owner_subject="u")
        assert exc.value.status_code == 415
        with pytest.raises(HTTPException) as exc:
            await mediamod.save_media(engine=Engine(), store=store, project_slug="p", config=cfg, upload=upload(name="x.jpg", content_type="image/png"), owner_subject="u")
        assert exc.value.status_code == 415

        # Owner quota is enforced by an atomic usage-ledger UPDATE inside the metadata transaction.
        quota = MediaConfig(enabled=True, max_owner_bytes=10, allowed_mime_types=["text/plain"])
        with pytest.raises(HTTPException) as exc:
            await mediamod.save_media(engine=Engine(reserve_rowcounts=[0]), store=store, project_slug="p", config=quota, upload=upload(), owner_subject="u")
        assert exc.value.status_code == 413

        existing = {
            "id":"existing", "project_slug":"p", "storage_key":"p/a", "original_name":"old.txt",
            "content_type":"text/plain", "size":3, "sha256":"x", "owner_subject":"u",
            "created_at":datetime.now(timezone.utc),
        }
        # Compute real digest so dedup query can represent an existing identical row.
        import hashlib
        existing["sha256"] = hashlib.sha256(b"abc").hexdigest()
        dedup_engine = Engine(row=existing)
        dedup_cfg = MediaConfig(enabled=True, deduplicate=True, deduplicate_scope="owner", allowed_mime_types=["text/plain"])
        result = await mediamod.save_media(engine=dedup_engine, store=store, project_slug="p", config=dedup_cfg, upload=upload(), owner_subject="u")
        assert result["id"] == "existing" and dedup_engine.inserted == 0

        # Normal persistence + retrieval + deletion use the internal storage key but API callers do not.
        create_engine = Engine(row=None)
        created = await mediamod.save_media(engine=create_engine, store=store, project_slug="p", config=MediaConfig(enabled=True, deduplicate=False, allowed_mime_types=["text/plain"]), upload=upload(b"delete-me"), owner_subject="u")
        assert create_engine.inserted == 1
        create_engine.select_row = created
        meta = await mediamod.get_media_meta(create_engine, "p", created["id"])
        assert meta["storage_key"] == created["storage_key"]
        assert store.path_for(created["storage_key"]).exists()
        assert await mediamod.delete_media(create_engine, store, "p", created["id"]) is True
        assert create_engine.deleted == 1
        assert not store.path_for(created["storage_key"]).exists()
        create_engine.select_row = None
        with pytest.raises(HTTPException) as exc:
            await mediamod.get_media_meta(create_engine, "p", "missing")
        assert exc.value.status_code == 404

    asyncio.run(run())

    with pytest.raises(RuntimeError, match="signing secret"):
        mediamod.make_signed_media_token("p", "m", 5, secret="")
    assert mediamod.verify_signed_media_token("p", "m", None, secret="s" * 64) is False
    # A token with a negative TTL is immediately expired.
    expired = mediamod.make_signed_media_token("p", "m", -1, secret="s" * 64)
    assert mediamod.verify_signed_media_token("p", "m", expired, secret="s" * 64) is False


def test_mongo_registry_build_and_object_id_paths(monkeypatch):
    import framework.mongo as mongomod

    class FakeClient:
        def __init__(self, uri, **kwargs):
            self.uri=uri; self.kwargs=kwargs; self.closed=False
        def __getitem__(self, name): return {"database": name, "uri": self.uri}
        async def close(self): self.closed=True

    pymongo = types.ModuleType("pymongo")
    pymongo.AsyncMongoClient = FakeClient
    monkeypatch.setitem(sys.modules, "pymongo", pymongo)

    project = ProjectConfig.model_validate({
        "slug":"p", "name":"P", "security":{"jwt_enabled":False},
        "databases":{"primary":{"url":"sqlite+aiosqlite:///:memory:"}},
        "mongo_databases": {
            "main": {"uri":"mongodb://localhost:27017", "database":"forge", "max_pool_size":25, "min_pool_size":2, "server_selection_timeout_ms":1234}
        }
    })

    async def run():
        registry = await mongomod.build_mongo_registry(project)
        assert registry is not None
        client = registry.clients["main"]
        assert client.kwargs == {"maxPoolSize":25,"minPoolSize":2,"serverSelectionTimeoutMS":1234}
        assert registry.databases["main"]["database"] == "forge"
        await registry.dispose()
        assert client.closed is True
        empty = ProjectConfig.model_validate({"slug":"empty","name":"Empty","security":{"jwt_enabled":False},"databases":{"primary":{"url":"sqlite+aiosqlite:///:memory:"}}})
        assert await mongomod.build_mongo_registry(empty) is None
    asyncio.run(run())

    class ObjectId:
        @staticmethod
        def is_valid(value): return value == "valid"
        def __init__(self, value): self.value=value
    bson = types.ModuleType("bson"); bson.ObjectId=ObjectId
    monkeypatch.setitem(sys.modules, "bson", bson)
    converted = mongomod._id_filter("valid")
    assert isinstance(converted, ObjectId) and converted.value == "valid"
    assert mongomod._id_filter("plain") == "plain"


def test_idempotent_operation_success_replay_conflict_and_inflight():
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    from starlette.requests import Request
    from framework.config import OperationConfig
    from framework.operations import execute_idempotent_operation, request_fingerprint
    from framework.security import Principal

    principal = Principal(kind="api_key", subject="bot", roles=set(), permissions={"op"})
    request = Request({
        "type":"http", "method":"POST", "path":"/rpc/op", "headers":[], "query_string":b"",
        "path_params":{"account_id":"1"}, "server":("test",80), "client":("127.0.0.1",1), "scheme":"http",
    })
    request.state.validated_parameters = {"mode":"safe"}
    operation = OperationConfig.model_validate({
        "name":"op", "path":"rpc/op", "permission":"op", "transaction":True, "idempotency":True,
        "input_schema":{"type":"object","required":["amount"],"properties":{"amount":{"type":"integer","minimum":1}}},
        "statements":[{"sql":"UPDATE wallet SET balance=balance+:amount", "mode":"execute", "params":{"amount":"$body.amount"}, "result_name":"write"}],
    })

    class Result:
        def __init__(self, *, rowcount=1, row=None, rows=None): self.rowcount=rowcount; self.row=row; self.rows=rows or []
        def mappings(self): return self
        def first(self): return self.row
        def scalars(self): return self
        def all(self): return list(self.rows)

    class Conn:
        def __init__(self, engine, phase): self.engine=engine; self.phase=phase
        async def execute(self, statement, params=None):
            text = str(statement)
            if self.phase == "begin" and text.lstrip().startswith("INSERT") and self.engine.raise_insert:
                raise IntegrityError("insert", {}, RuntimeError("duplicate"))
            if self.phase == "connect" and text.lstrip().startswith("SELECT"):
                return Result(row=self.engine.replay_row)
            if text.lstrip().startswith("UPDATE") and "_forge_v4_operation_idempotency" not in text:
                self.engine.business_calls += 1
                return Result(rowcount=1)
            return Result(rowcount=1)

    class Ctx:
        def __init__(self, engine, phase): self.engine=engine; self.phase=phase
        async def __aenter__(self): return Conn(self.engine,self.phase)
        async def __aexit__(self, *args): return False

    class Engine:
        def __init__(self): self.raise_insert=False; self.replay_row=None; self.business_calls=0
        def begin(self): return Ctx(self,"begin")
        def connect(self): return Ctx(self,"connect")

    async def run():
        engine=Engine()
        result,replayed = await execute_idempotent_operation(
            engine, project_slug="p", operation=operation, principal=principal, raw_key="k", body={"amount":5}, request=request
        )
        assert replayed is False and result["write"] == {"rowcount":1} and engine.business_calls == 1

        fp = request_fingerprint(body={"amount":5}, request=request, principal=principal, operation=operation)
        engine.raise_insert=True
        engine.replay_row={"request_hash":fp,"state":"complete","response_json":'{"write":{"rowcount":1}}'}
        replay,replayed = await execute_idempotent_operation(
            engine, project_slug="p", operation=operation, principal=principal, raw_key="k", body={"amount":5}, request=request
        )
        assert replayed is True and replay["write"]["rowcount"] == 1 and engine.business_calls == 1

        engine.replay_row={"request_hash":"different","state":"complete","response_json":"{}"}
        with pytest.raises(HTTPException) as exc:
            await execute_idempotent_operation(engine,project_slug="p",operation=operation,principal=principal,raw_key="k",body={"amount":5},request=request)
        assert exc.value.status_code == 409 and "different request" in str(exc.value.detail)

        engine.replay_row={"request_hash":fp,"state":"pending","response_json":None}
        with pytest.raises(HTTPException) as exc:
            await execute_idempotent_operation(engine,project_slug="p",operation=operation,principal=principal,raw_key="k",body={"amount":5},request=request)
        assert exc.value.status_code == 409 and exc.value.headers["Retry-After"] == "1"

        engine.replay_row=None
        with pytest.raises(IntegrityError):
            await execute_idempotent_operation(engine,project_slug="p",operation=operation,principal=principal,raw_key="k",body={"amount":5},request=request)

        with pytest.raises(Exception):
            await execute_idempotent_operation(engine,project_slug="p",operation=operation,principal=principal,raw_key="another",body={"amount":0},request=request)

    asyncio.run(run())


def test_protection_invalid_ip_wait_timeout_and_body_limit_edges():
    from fastapi import HTTPException
    from starlette.requests import Request
    from framework.protection import ConcurrencyGate, RequestBodyLimitMiddleware, ip_allowed

    def request_for(ip):
        return Request({"type":"http","method":"GET","path":"/","headers":[],"query_string":b"","server":("x",80),"client":(ip,1),"scheme":"http"})

    assert ip_allowed(request_for("not-an-ip"), [], []) is True
    assert ip_allowed(request_for("not-an-ip"), ["10.0.0.0/8"], []) is False
    assert ip_allowed(request_for("127.0.0.1"), [], ["127.0.0.1"]) is False
    assert ip_allowed(request_for("127.0.0.1"), ["127.0.0.1"], []) is True
    assert ip_allowed(request_for("127.0.0.1"), ["10.0.0.0/8"], []) is False

    async def run_gate():
        gate = ConcurrencyGate(1, 0.01, reject_when_saturated=False)
        await gate.__aenter__()
        assert gate.active == 1
        with pytest.raises(HTTPException) as exc:
            await gate.__aenter__()
        assert exc.value.status_code == 503
        await gate.__aexit__(None,None,None)
        assert gate.active == 0
    asyncio.run(run_gate())

    async def run_middleware():
        calls=[]
        async def app(scope, receive, send):
            calls.append(scope["type"])
            if scope["type"] == "http":
                # Start a response, then consume a too-large chunk. Middleware must
                # close the already-started body rather than attempting a second start.
                await send({"type":"http.response.start","status":200,"headers":[]})
                await receive()
        mw = RequestBodyLimitMiddleware(app, lambda path: None if path == "/unlimited" else 3)

        sent=[]
        async def recv_ws(): return {"type":"websocket.receive"}
        await mw({"type":"websocket","path":"/ws"}, recv_ws, lambda m: asyncio.sleep(0, result=sent.append(m)))
        assert calls[-1] == "websocket"

        sent.clear()
        async def recv_unlimited(): return {"type":"http.request","body":b"large","more_body":False}
        await mw({"type":"http","path":"/unlimited","headers":[]}, recv_unlimited, lambda m: asyncio.sleep(0, result=sent.append(m)))
        assert sent[0]["status"] == 200

        sent.clear()
        async def recv_large(): return {"type":"http.request","body":b"1234","more_body":False}
        await mw({"type":"http","path":"/limited","headers":[]}, recv_large, lambda m: asyncio.sleep(0, result=sent.append(m)))
        assert sent[0]["status"] == 200 and sent[-1]["type"] == "http.response.body"

        sent.clear()
        await mw({"type":"http","path":"/limited","headers":[(b"content-length",b"wat")]}, recv_large, lambda m: asyncio.sleep(0, result=sent.append(m)))
        assert sent[0]["status"] == 400
    asyncio.run(run_middleware())


def test_rate_limiter_cleanup_redis_and_lifecycle(monkeypatch):
    import framework.rate_limit as rl
    from fastapi import HTTPException

    async def run_memory():
        limiter = rl.MemoryRateLimiter(max_buckets=100, idle_ttl_seconds=10, cleanup_interval_seconds=1)
        assert await limiter.ping() is True
        now = 1000.0
        limiter._buckets = {
            "stale": rl.Bucket(tokens=1, updated=now-20, last_seen=now-20),
            **{f"k{i}": rl.Bucket(tokens=1, updated=now, last_seen=now+i/1000) for i in range(105)},
        }
        limiter._next_cleanup = 0
        limiter._cleanup_locked(now)
        assert "stale" not in limiter._buckets and len(limiter._buckets) <= 100
        await limiter.close()
        assert limiter._buckets == {}
    asyncio.run(run_memory())

    class FakeRedis:
        def __init__(self): self.allowed=1; self.tokens=2.0; self.calls=[]; self.closed=False
        async def eval(self,*args): self.calls.append(args); return [self.allowed,self.tokens]
        async def ping(self): return True
        async def aclose(self): self.closed=True
    fake=FakeRedis()
    redis_asyncio=types.ModuleType("redis.asyncio"); redis_asyncio.from_url=lambda *a,**k: fake
    redis_pkg=types.ModuleType("redis"); redis_pkg.asyncio=redis_asyncio
    monkeypatch.setitem(sys.modules,"redis",redis_pkg); monkeypatch.setitem(sys.modules,"redis.asyncio",redis_asyncio)

    async def run_redis():
        limiter=rl.RedisRateLimiter("redis://fake",prefix="p:")
        await limiter.check("identity",10,60,burst=3)
        assert fake.calls and ":" in fake.calls[0][2]
        fake.allowed=0; fake.tokens=0.2
        with pytest.raises(HTTPException) as exc:
            await limiter.check("identity",10,60,burst=3)
        assert exc.value.status_code==429
        assert await limiter.ping() is True
        await limiter.close(); assert fake.closed is True
    asyncio.run(run_redis())


def test_crud_runtime_paths_without_database_driver():
    from fastapi import HTTPException
    from sqlalchemy import MetaData, Table, Column, Integer, String
    from starlette.requests import Request
    from framework.config import ResourceConfig
    from framework.crud import list_rows, count_rows, get_row, create_row, batch_create_rows, update_row, delete_row
    from framework.security import Principal

    table = Table(
        "items", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("tenant_id", String),
        Column("deleted_at", String),
    )
    principal = Principal(kind="api_key", subject="k", roles=set(), permissions={"*"}, tenant_id="t1")

    def resource(**overrides):
        base = {
            "database":"primary", "table":"items", "path":"items", "primary_key":"id",
            "permissions":{"list":"i.list","read":"i.read","create":"i.create","update":"i.update","delete":"i.delete"},
            "allowed_filters":["id","name"], "allowed_sort":["id","name"], "search_fields":["name"],
            "writable_fields":["name"], "tenant_field":"tenant_id", "soft_delete_field":"deleted_at",
            "batch_enabled":True, "max_batch_size":3,
        }
        base.update(overrides)
        return ResourceConfig.model_validate(base)

    def request(query=b""):
        return Request({"type":"http","method":"GET","path":"/items","headers":[],"query_string":query,"server":("x",80),"client":("127.0.0.1",1),"scheme":"http"})

    class Mappings:
        def __init__(self, rows): self.rows=rows
        def all(self): return self.rows
        def first(self): return self.rows[0] if self.rows else None
    class Result:
        def __init__(self, *, rows=None, scalar=0, inserted=None, rowcount=1):
            self.rows=rows or []; self.scalar=scalar; self.inserted_primary_key=[] if inserted is None else [inserted]; self.rowcount=rowcount
        def mappings(self): return Mappings(self.rows)
        def scalar_one(self): return self.scalar
    class Conn:
        def __init__(self, engine): self.engine=engine
        async def execute(self,*args,**kwargs): return self.engine.results.pop(0)
    class Ctx:
        def __init__(self, engine): self.engine=engine
        async def __aenter__(self): return Conn(self.engine)
        async def __aexit__(self,*args): return None
    class Engine:
        def __init__(self,*results): self.results=list(results)
        def connect(self): return Ctx(self)
        def begin(self): return Ctx(self)

    async def run():
        r = resource()
        offset = await list_rows(request(b"limit=2&offset=1&sort=-name&q=a"), Engine(Result(rows=[{"id":1,"name":"A","tenant_id":"t1","deleted_at":None}])), table, r, principal)
        assert offset["items"] == [{"id":1,"name":"A","tenant_id":"t1","deleted_at":None}] and offset["offset"] == 1
        with pytest.raises(HTTPException):
            await list_rows(request(b"sort=forbidden"), Engine(), table, r, principal)

        cursor_r = resource(pagination_mode="cursor", cursor_field="id", default_limit=2, max_limit=5)
        first_page = await list_rows(request(b"limit=2"), Engine(Result(rows=[{"id":1,"name":"A"},{"id":2,"name":"B"},{"id":3,"name":"C"}])), table, cursor_r, principal)
        assert first_page["has_more"] is True and first_page["next_cursor"] and len(first_page["items"]) == 2
        cursor_page = await list_rows(request(("limit=2&cursor=" + first_page["next_cursor"]).encode()), Engine(Result(rows=[{"id":3,"name":"C"}])), table, cursor_r, principal)
        assert len(cursor_page["items"]) == 1
        bad_cursor_r = resource(pagination_mode="cursor", cursor_field="missing")
        with pytest.raises(RuntimeError):
            await list_rows(request(), Engine(), table, bad_cursor_r, principal)

        counted = await count_rows(request(b"name=A"), Engine(Result(scalar=7)), table, r, principal)
        assert counted == {"count":7}
        found = await get_row(Engine(Result(rows=[{"id":4,"name":"D","tenant_id":"t1","deleted_at":None}])), table, r, principal, "4")
        assert found["id"] == 4
        with pytest.raises(HTTPException) as exc:
            await get_row(Engine(Result(rows=[])), table, r, principal, "404")
        assert exc.value.status_code == 404

        created = await create_row(
            Engine(Result(inserted=9), Result(rows=[{"id":9,"name":"N","tenant_id":"t1","deleted_at":None}])),
            table, r, principal, {"name":"N"},
        )
        assert created["id"] == 9
        created_without_pk = await create_row(Engine(Result(inserted=None)), table, resource(tenant_field=None,soft_delete_field=None), principal, {"name":"N"})
        assert created_without_pk == {"created":True}
        with pytest.raises(HTTPException):
            await create_row(Engine(), table, r, Principal(kind="x",subject="x",roles=set(),permissions=set()), {"name":"N"})

        batch = await batch_create_rows(Engine(Result(rowcount=0)), table, r, principal, [{"name":"A"},{"name":"B"}])
        assert batch == {"created":2,"rowcount":2}
        with pytest.raises(HTTPException):
            await batch_create_rows(Engine(), table, resource(batch_enabled=False), principal, [{"name":"A"}])
        with pytest.raises(HTTPException):
            await batch_create_rows(Engine(), table, r, principal, [])
        with pytest.raises(HTTPException):
            await batch_create_rows(Engine(), table, r, Principal(kind="x",subject="x",roles=set(),permissions=set()), [{"name":"A"}])

        updated = await update_row(
            Engine(Result(rowcount=1), Result(rows=[{"id":1,"name":"Changed","tenant_id":"t1","deleted_at":None}])),
            table, r, principal, 1, {"name":"Changed"},
        )
        assert updated["name"] == "Changed"
        with pytest.raises(HTTPException):
            await update_row(Engine(Result(rowcount=0)), table, r, principal, 1, {"name":"X"})
        with pytest.raises(HTTPException):
            await update_row(Engine(), table, r, principal, 1, {})

        assert await delete_row(Engine(Result(rowcount=1)), table, r, principal, 1) == {"deleted":True}
        hard = resource(soft_delete_field=None)
        assert await delete_row(Engine(Result(rowcount=1)), table, hard, principal, 1) == {"deleted":True}
        with pytest.raises(HTTPException):
            await delete_row(Engine(Result(rowcount=0)), table, hard, principal, 1)

    asyncio.run(run())


def test_security_jwks_cache_validation_and_authentication_edges(monkeypatch):
    import httpx
    import jwt
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from starlette.requests import Request
    import framework.security as sec

    sec._jwks_cache.clear(); sec._jwks_locks.clear()

    class FakeResponse:
        def __init__(self, data=None, error=None): self.data=data; self.error=error
        def raise_for_status(self):
            if self.error: raise self.error
        def json(self): return self.data
    class FakeClient:
        calls=0; response=FakeResponse({"keys":[{"kid":"k"}]})
        def __init__(self,*a,**k): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): return None
        async def get(self,*a,**k):
            FakeClient.calls += 1
            return FakeClient.response
    monkeypatch.setattr(sec.httpx,"AsyncClient",FakeClient)

    async def jwks_flow():
        first=await sec._get_jwks("https://issuer/jwks",ttl=60,timeout=1)
        second=await sec._get_jwks("https://issuer/jwks",ttl=60,timeout=1)
        assert first==second and FakeClient.calls==1
        sec._jwks_cache.clear(); FakeClient.response=FakeResponse({"bad":[]})
        with pytest.raises(HTTPException) as exc:
            await sec._get_jwks("https://issuer/invalid",ttl=60,timeout=1)
        assert exc.value.status_code==503
        sec._jwks_cache.clear(); FakeClient.response=FakeResponse(error=httpx.ConnectError("down",request=httpx.Request("GET","https://issuer/down")))
        with pytest.raises(HTTPException) as exc:
            await sec._get_jwks("https://issuer/down",ttl=60,timeout=1)
        assert exc.value.status_code==503
    asyncio.run(jwks_flow())

    project = ProjectConfig.model_validate({
        "slug":"p","name":"P","databases":{"primary":{"url":"sqlite+aiosqlite:///:memory:"}},
        "security":{"jwt_enabled":True,"jwt_provider":"jwks","jwt_jwks_url":"https://issuer/jwks","jwt_algorithms":["RS256"],"jwt_issuer":"iss","jwt_audience":"aud"},
    })
    monkeypatch.setattr(sec.jwt,"get_unverified_header",lambda token:{"kid":"kid1","alg":"RS256"})
    async def fake_get(url,**kwargs): return {"keys":[{"kid":"kid1","alg":"RS256","key_ops":["verify"],"kty":"RSA","n":"x","e":"AQAB"}]}
    monkeypatch.setattr(sec,"_get_jwks",fake_get)
    class PyJWK: key="public"
    monkeypatch.setattr(sec.jwt.PyJWK,"from_dict",lambda data:PyJWK())
    decoded_kwargs={}
    def fake_decode(token,key,**kwargs): decoded_kwargs.update(kwargs); return {"sub":"u","exp":9999999999}
    monkeypatch.setattr(sec.jwt,"decode",fake_decode)
    payload=asyncio.run(sec._decode_jwks_token("t",project))
    assert payload["sub"]=="u" and decoded_kwargs["issuer"]=="iss" and decoded_kwargs["audience"]=="aud"

    monkeypatch.setattr(sec.jwt,"get_unverified_header",lambda token:{"kid":"kid1","alg":"HS256"})
    with pytest.raises(HTTPException): asyncio.run(sec._decode_jwks_token("t",project))
    monkeypatch.setattr(sec.jwt,"get_unverified_header",lambda token:{"kid":"kid1","alg":"RS256"})
    async def alg_mismatch(url,**kwargs): return {"keys":[{"kid":"kid1","alg":"ES256"}]}
    monkeypatch.setattr(sec,"_get_jwks",alg_mismatch)
    with pytest.raises(HTTPException): asyncio.run(sec._decode_jwks_token("t",project))
    async def no_verify(url,**kwargs): return {"keys":[{"kid":"kid1","alg":"RS256","key_ops":["sign"]}]}
    monkeypatch.setattr(sec,"_get_jwks",no_verify)
    with pytest.raises(HTTPException): asyncio.run(sec._decode_jwks_token("t",project))


def test_security_helpers_bootstrap_query_key_expiry_and_local_jwt(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from starlette.requests import Request
    import framework.security as sec

    assert sec._claim({"a":{"b":2}},"a.b")==2
    assert sec._claim({"a":1},"a.b","d")=="d"
    assert sec._claim_set(None)==set() and sec._claim_set("x")=={"x"} and sec._claim_set(["x",None,2])=={"x","2"}
    assert sec.permission_matches("*","a") and sec.permission_matches("notes.*","notes.read") and not sec.permission_matches("notes.*","users.read")
    assert sec.has_permission(sec.Principal("x","x",set(),{"notes.read"}),"notes.read")
    assert sec.has_permission(sec.Principal("x","x",set(),set()),None)
    assert sec.hash_key("x")==sec.hash_key("x") and sec.make_api_key().startswith("jf2_")

    project = ProjectConfig.model_validate({
        "slug":"p","name":"P","databases":{"primary":{"url":"sqlite+aiosqlite:///:memory:"}},
        "roles":{"reader":{"permissions":["notes.read"]},"editor":{"permissions":["notes.write"],"inherits":["reader"]}},
        "security":{"jwt_enabled":False,"allow_query_api_key":True,"bootstrap_enabled":True,"bootstrap_admin_key":"B"*48,"bootstrap_one_time":False},
    })
    assert sec._expand_role_permissions(project,{"editor","missing"})=={"notes.read","notes.write"}

    class Map:
        def __init__(self,row=None,rows=None): self.row=row; self.rows=rows or []
        def first(self): return self.row
        def all(self): return self.rows
    class Result:
        def __init__(self,*,row=None,rows=None,first=None,rowcount=1,inserted=1): self.row=row;self.rows=rows or [];self.first_row=first;self.rowcount=rowcount;self.inserted_primary_key=[inserted]
        def mappings(self): return Map(self.row,self.rows)
        def first(self): return self.first_row
    class Conn:
        def __init__(self,engine): self.engine=engine
        async def run_sync(self,fn): self.engine.init_called=True
        async def execute(self,stmt,*a,**k):
            text=str(stmt)
            if "_forge_v4_bootstrap_state" in text:
                if text.lstrip().startswith("SELECT"): return Result(first=self.engine.bootstrap_first)
                self.engine.bootstrap_writes += 1; return Result()
            if "_forge_v2_api_keys" in text and text.lstrip().startswith("SELECT"):
                return Result(row=self.engine.key_row)
            return Result()
    class Ctx:
        def __init__(self,e): self.e=e
        async def __aenter__(self): return Conn(self.e)
        async def __aexit__(self,*a): return None
    class Engine:
        def __init__(self): self.bootstrap_first=None; self.bootstrap_writes=0; self.key_row=None; self.init_called=False
        def connect(self): return Ctx(self)
        def begin(self): return Ctx(self)

    def req(*,query=b"",headers=None,scope_type="http"):
        return Request({"type":scope_type,"method":"GET","path":"/","headers":headers or [],"query_string":query,"server":("x",80),"client":("127.0.0.1",1),"scheme":"http"})

    async def run():
        e=Engine(); await sec.init_security(e); assert e.init_called
        assert await sec.bootstrap_is_available(e,"p") is True
        await sec.consume_bootstrap(e,"p"); assert e.bootstrap_writes==1
        e.bootstrap_first=("p",); await sec.consume_bootstrap(e,"p"); assert e.bootstrap_writes==2

        # Query API key path can authenticate the bootstrap credential.
        p=await sec.authenticate_request(req(query=("api_key="+"B"*48).encode()),project,e)
        assert p.kind=="bootstrap"

        # Disabled and expired durable keys fail closed.
        project.security.bootstrap_admin_key=None
        project.security.bootstrap_enabled=False
        e.key_row={"id":1,"name":"k","roles":"editor","permissions":"direct","tenant_id":None,"enabled":False,"rate_requests":None,"rate_window_seconds":None,"rate_burst":None,"expires_at":None}
        with pytest.raises(HTTPException): await sec.authenticate_request(req(query=b"api_key=bad"),project,e)
        e.key_row={**e.key_row,"enabled":True,"expires_at":datetime.now()-timedelta(seconds=1)}
        with pytest.raises(HTTPException): await sec.authenticate_request(req(query=b"api_key=bad"),project,e)
        e.key_row={**e.key_row,"expires_at":datetime.now(timezone.utc)-timedelta(seconds=1)}
        with pytest.raises(HTTPException): await sec.authenticate_request(req(query=b"api_key=bad"),project,e)

        # Anonymous fallback when no credential is present.
        assert (await sec.authenticate_request(req(),project,e)).kind=="anonymous"

        local = ProjectConfig.model_validate({
            "slug":"p","name":"P","databases":{"primary":{"url":"sqlite+aiosqlite:///:memory:"}},
            "security":{"jwt_enabled":True,"jwt_provider":"local_hs256","jwt_secret":"S"*64},
        })
        good = sec.issue_jwt("u","p",["reader"],["notes.read"],5,secret="S"*64)
        jwt_p=await sec.authenticate_request(req(headers=[(b"authorization",f"Bearer {good}".encode())]),local,e)
        assert jwt_p.kind=="jwt" and jwt_p.subject=="u"
        wrong_project=sec.issue_jwt("u","other",[],[],5,secret="S"*64)
        with pytest.raises(HTTPException): await sec.authenticate_request(req(headers=[(b"authorization",f"Bearer {wrong_project}".encode())]),local,e)
        token_without_subject=sec.jwt.encode({"project":"p","exp":datetime.now(timezone.utc)+timedelta(minutes=5)},"S"*64,algorithm="HS256")
        with pytest.raises(HTTPException): await sec.authenticate_request(req(headers=[(b"authorization",f"Bearer {token_without_subject}".encode())]),local,e)

    asyncio.run(run())
    monkeypatch.setattr(sec.settings,"jwt_secret",None)
    with pytest.raises(RuntimeError): sec.issue_jwt("u","p",[],[],1)


def test_datasource_yaml_http_and_mutation_validation(tmp_path):
    import httpx
    from fastapi import HTTPException
    from starlette.requests import Request
    from framework.config import DataSourceConfig, ProjectConfig
    from framework.datasources import DataSourceManager

    project = ProjectConfig.model_validate({
        "slug":"p","name":"P","project_dir":str(tmp_path),
        "databases":{"primary":{"url":"sqlite+aiosqlite:///:memory:"}},
        "security":{"jwt_enabled":False},
    })
    manager=DataSourceManager(project)
    req=Request({"type":"http","method":"POST","path":"/","headers":[],"query_string":b"q=x&q=y","server":("x",80),"client":("127.0.0.1",1),"scheme":"http"})

    async def run():
        yaml_path=tmp_path/"items.yaml"
        yaml_path.write_text("- id: 1\n  name: one\n",encoding="utf-8")
        source=DataSourceConfig(name="yaml",type="yaml_file",file="items.yaml",public=True,public_write=True,writable=True)
        plain_req=Request({"type":"http","method":"GET","path":"/","headers":[],"query_string":b"","server":("x",80),"client":("127.0.0.1",1),"scheme":"http"})
        assert (await manager.read(source,plain_req))["items"][0]["name"]=="one"
        created=await manager.create(source,{"name":"two"}); assert created["id"]==2
        with pytest.raises(HTTPException): await manager.create(source,"not-object")
        with pytest.raises(HTTPException): await manager.create(source,{"id":2,"name":"dup"})
        with pytest.raises(HTTPException): await manager.update(source,"1","not-object")

        missing=DataSourceConfig(name="missing",type="json_file",file="missing.json",public=True)
        with pytest.raises(HTTPException) as exc: await manager.read(missing,req)
        assert exc.value.status_code==404

        calls=[]
        async def fake_request(method,url,**kwargs):
            calls.append((method,url,kwargs))
            request=httpx.Request(method,url)
            return httpx.Response(200,json={"ok":True},headers={"content-type":"application/json"},request=request)
        manager.http.request=fake_request
        http=DataSourceConfig(
            name="http",type="http",url="https://upstream.example/api",method="POST",public=True,
            forward_query=True,forward_body=True,retries=4,retry_non_idempotent=True,headers={"X-Upstream":"yes"},
            allow_private_networks=True
        )
        assert await manager.read(http,req,payload={"x":1})=={"ok":True}
        assert calls[0][2]["retry_non_idempotent"] is True and calls[0][2]["json"]=={"x":1} and len(calls[0][2]["params"])==2

        async def text_request(method,url,**kwargs):
            request=httpx.Request(method,url)
            return httpx.Response(502,text="bad gateway",headers={"content-type":"text/plain"},request=request)
        manager.http.request=text_request
        text_result=await manager.read(http,req,payload=None)
        assert text_result=={"status_code":502,"text":"bad gateway"}
        await manager.close()
    asyncio.run(run())
