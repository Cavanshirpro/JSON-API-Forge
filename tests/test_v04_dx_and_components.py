from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request

from framework.cache import CacheManager, MemoryTTLCache, TieredCache
from framework.cli import main as cli_main
from framework.config import DataSourceConfig, MediaConfig, MongoResourceConfig, ProjectConfig
from framework.datasources import DataSourceManager
from framework.events import EventHub, build_event_hub
from framework.media import LocalMediaStore, _extension, _safe_name, build_media_store, make_signed_media_token, media_api_meta, save_media, verify_signed_media_token
from framework.mongo import MongoRegistry, _base_filter, _query_filter, _visible, _write_payload, count_documents, create_document, delete_document, get_document, list_documents, update_document
from framework.security import Principal
from framework.settings import settings


def _request(query: bytes = b"") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/x", "headers": [], "query_string": query,
        "server": ("test", 80), "client": ("127.0.0.1", 1), "scheme": "http",
    })


def _project(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig.model_validate({
        "slug": "demo",
        "name": "Demo",
        "databases": {"primary": {"url": "sqlite+aiosqlite:///demo.db"}},
        "security": {"jwt_enabled": False},
        "project_dir": str(tmp_path),
    })


def test_cli_init_new_schema_and_no_default_secrets(tmp_path: Path, capsys):
    root = tmp_path
    (root / "app").mkdir()
    (root / "schemas").mkdir()
    # Create a starter app, then generate secrets and schemas.
    cli_main(["--root", str(root), "new", "Bot", "--slug", "bot", "--preset", "discord-bot"])
    assert (root / "app/Bot/app.json").exists()
    security = json.loads((root / "app/Bot/config/20-security.json").read_text())
    assert security["security"]["bootstrap_admin_key"] == "$env:BOT_BOOTSTRAP_ADMIN_KEY"

    cli_main(["--root", str(root), "init"])
    env = (root / ".env").read_text()
    assert "BOT_BOOTSTRAP_ADMIN_KEY=" in env
    assert "JWT_SECRET=" not in env  # starter does not enable JWT, so no unused secret is generated
    assert "change-me" not in env.lower()
    secret = next(line.split("=", 1)[1] for line in env.splitlines() if line.startswith("BOT_BOOTSTRAP_ADMIN_KEY="))
    assert len(secret) >= 48
    if os.name != "nt":
        assert oct((root / ".env").stat().st_mode & 0o777) == "0o600"

    with pytest.raises(SystemExit):
        cli_main(["--root", str(root), "init"])

    cli_main(["--root", str(root), "schema"])
    assert json.loads((root / "schemas/project.schema.json").read_text())["$schema"].startswith("https://json-schema.org")
    assert json.loads((root / "schemas/fragment.schema.json").read_text())["type"] == "object"
    assert "Created" in capsys.readouterr().out


def test_datasources_file_read_query_and_mutations(tmp_path: Path):
    async def run():
        project = _project(tmp_path)
        manager = DataSourceManager(project)
        path = tmp_path / "items.json"
        path.write_text(json.dumps([{"id": 1, "name": "b", "kind": "x"}, {"id": 2, "name": "a", "kind": "x"}, {"id": 3, "name": "c", "kind": "y"}]))
        source = DataSourceConfig(
            name="items", type="json_file", file="items.json", public=True, public_write=True, writable=True, max_items=10,
            allowed_filters=["kind"], allowed_sort=["name"],
        )
        result = await manager.read(source, _request(b"kind=x&sort=name&limit=1"))
        assert result["total"] == 2
        assert result["items"][0]["name"] == "a"

        created = await manager.create(source, {"name": "d", "kind": "z"})
        assert created["id"] == 4
        with pytest.raises(HTTPException) as exc:
            await manager.update(source, "4", {"id": 999, "name": "e"})
        assert exc.value.status_code == 422
        updated = await manager.update(source, "4", {"name": "e"})
        assert updated["id"] == 4 and updated["name"] == "e"
        assert await manager.delete(source, "4") == {"deleted": True}

        with pytest.raises(HTTPException) as exc:
            await manager.update(source, "404", {"name": "none"})
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException):
            await manager.delete(source, "404")

        csv_path = tmp_path / "items.csv"
        csv_path.write_text("id,name\n1,one\n", encoding="utf-8")
        csv_source = DataSourceConfig(name="csv", type="csv_file", file="items.csv", public=True)
        csv = await manager.read(csv_source, _request())
        assert csv["items"][0]["name"] == "one"
        with pytest.raises(HTTPException) as exc:
            await manager.create(csv_source, {"name": "bad"})
        assert exc.value.status_code == 405

        static = DataSourceConfig(name="static", type="static", data={"ok": True}, public=True)
        assert await manager.read(static, _request()) == {"ok": True}
        with pytest.raises(HTTPException):
            manager._file_path(DataSourceConfig(name="escape", type="json_file", file="../escape.json", public=True))
        with pytest.raises(HTTPException) as exc:
            manager._query_collection([], source, _request(b"limit=nope"))
        assert exc.value.status_code == 400
        await manager.close()
    asyncio.run(run())


def test_cache_singleflight_stale_and_generation():
    async def run():
        backend = MemoryTTLCache(max_entries=2)
        cache = CacheManager(backend)
        assert await cache.make_key("n", {"x": 1}) == await cache.make_key("n", {"x": 1})
        calls = 0

        async def loader():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return {"v": calls}

        results = await asyncio.gather(*[cache.get_or_set_json("same", 2, loader) for _ in range(8)])
        assert calls == 1
        assert all(item[0] == {"v": 1} for item in results)
        assert sum(1 for _, hit in results if hit) == 7
        assert cache._locks == {}  # per-key stampede locks are ephemeral, not a cardinality leak

        await cache.set_json("stale", {"old": True}, ttl=1, stale_ttl=3)
        # Force the envelope into stale state without sleeping.
        raw = json.loads((await backend.get("stale")).decode())
        raw["fresh_until"] = time.time() - 1
        await backend.set("stale", json.dumps(raw).encode(), 3)
        value, hit = await cache.get_or_set_json("stale", 2, loader, stale_ttl=3)
        assert value == {"old": True} and hit is True
        await asyncio.sleep(0.04)
        assert (await cache.get_json("stale"))["v"] >= 2
        assert cache._locks == {}

        # A failed background refresh must not leak registry state or an unobserved task.
        await cache.set_json("stale-error", {"old": "safe"}, ttl=1, stale_ttl=3)
        raw_error = json.loads((await backend.get("stale-error")).decode())
        raw_error["fresh_until"] = time.time() - 1
        await backend.set("stale-error", json.dumps(raw_error).encode(), 3)
        async def failing_loader():
            raise RuntimeError("refresh failed")
        cached_error, error_hit = await cache.get_or_set_json("stale-error", 2, failing_loader, stale_ttl=3)
        assert cached_error == {"old": "safe"} and error_hit is True
        await asyncio.sleep(0.03)
        assert "stale-error" not in cache._refreshing
        assert cache._locks == {}

        assert await cache.invalidate_namespace("n") == 1
        assert ":g1:" in await cache.make_key("n", {"x": 1})
        await cache.close()
    asyncio.run(run())


def test_media_local_store_sanitization_streaming_and_signed_token(tmp_path: Path, monkeypatch):
    async def run():
        store = LocalMediaStore(str(tmp_path / "media"))
        assert _safe_name("../../hello world?.png") == "hello_world_.png"
        assert _extension("A.JPEG") == "jpeg"
        with pytest.raises(HTTPException):
            store.path_for("../escape")

        # Starlette UploadFile can stream from an in-memory SpooledTemporaryFile/file.
        import io
        upload = UploadFile(io.BytesIO(b"abc123"), filename="hello.txt", headers=Headers({"content-type": "text/plain"}))
        size, digest = await store.save_upload(upload, "demo/file.txt", 10)
        assert size == 6 and len(digest) == 64
        assert store.path_for("demo/file.txt").read_bytes() == b"abc123"
        store.delete("demo/file.txt")
        assert not store.path_for("demo/file.txt").exists()

        too_big = UploadFile(io.BytesIO(b"0123456789"), filename="x.bin")
        with pytest.raises(HTTPException) as exc:
            await store.save_upload(too_big, "demo/big.bin", 5)
        assert exc.value.status_code == 413
        assert not store.path_for("demo/big.bin").exists()

        assert isinstance(build_media_store(MediaConfig(enabled=True, backend="local", local_directory=str(tmp_path))), LocalMediaStore)
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            MediaConfig(enabled=True, backend="s3")

        safe = media_api_meta({
            "id":"m1","original_name":"a.txt","content_type":"text/plain","size":1,"sha256":"abc",
            "created_at":"now","owner_subject":"private-owner","storage_key":"internal/path"
        })
        assert safe["id"] == "m1" and "storage_key" not in safe and "owner_subject" not in safe
        assert media_api_meta({**safe,"owner_subject":"owner"}, include_owner=True)["owner_subject"] == "owner"

        class BadConn:
            async def execute(self, *args, **kwargs): raise RuntimeError("metadata database unavailable")
        class BadCtx:
            async def __aenter__(self): return BadConn()
            async def __aexit__(self, *args): return False
        class BadEngine:
            def begin(self): return BadCtx()
        failed_upload = UploadFile(io.BytesIO(b"orphan-check"), filename="orphan.txt", headers=Headers({"content-type":"text/plain"}))
        with pytest.raises(RuntimeError):
            await save_media(
                engine=BadEngine(), store=store, project_slug="demo",
                config=MediaConfig(enabled=True, allowed_mime_types=["text/plain"], deduplicate=False),
                upload=failed_upload, owner_subject="owner",
            )
        assert not any(path.name.endswith("orphan.txt") for path in (tmp_path / "media").rglob("*"))

    asyncio.run(run())
    secret = "s" * 64
    token = make_signed_media_token("demo", "id", 60, secret=secret)
    assert verify_signed_media_token("demo", "id", token, secret=secret)
    assert not verify_signed_media_token("demo", "other", token, secret=secret)
    assert not verify_signed_media_token("demo", "id", "bad", secret=secret)


class FakeCursor:
    def __init__(self, rows): self.rows = list(rows)
    def skip(self, n): self.rows = self.rows[n:]; return self
    def limit(self, n): self.rows = self.rows[:n]; return self
    def sort(self, field, direction=None):
        specs = field if isinstance(field, list) else [(field, direction)]
        for key, order in reversed(specs):
            self.rows.sort(key=lambda x: x.get(key), reverse=order < 0)
        return self
    async def to_list(self, length): return self.rows[:length]


class FakeCollection:
    def __init__(self, rows): self.rows = [dict(x) for x in rows]; self.next_id = 100
    @staticmethod
    def _match(row, filt):
        for key, expected in filt.items():
            actual = row.get(key)
            if isinstance(expected, dict):
                for op, value in expected.items():
                    if op == "$in" and actual not in value: return False
                    if op == "$ne" and actual == value: return False
                    if op == "$gt" and not str(actual) > str(value): return False
                    if op == "$gte" and not str(actual) >= str(value): return False
                    if op == "$lt" and not str(actual) < str(value): return False
                    if op == "$lte" and not str(actual) <= str(value): return False
            elif actual != expected:
                return False
        return True
    def find(self, filt): return FakeCursor([r for r in self.rows if self._match(r, filt)])
    async def count_documents(self, filt): return len([r for r in self.rows if self._match(r, filt)])
    async def find_one(self, filt): return next((dict(r) for r in self.rows if self._match(r, filt)), None)
    async def insert_one(self, data):
        self.next_id += 1; row = {"_id": str(self.next_id), **data}; self.rows.append(row); return SimpleNamespace(inserted_id=str(self.next_id))
    async def update_one(self, filt, update):
        for row in self.rows:
            if self._match(row, filt): row.update(update["$set"]); return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)
    async def delete_one(self, filt):
        for i, row in enumerate(self.rows):
            if self._match(row, filt): self.rows.pop(i); return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class FakeDatabase(dict):
    pass


def test_mongo_resource_logic_with_fake_async_database():
    async def run():
        resource = MongoResourceConfig.model_validate({
            "database": "main", "collection": "profiles", "path": "profiles",
            "tenant_field": "tenant_id", "soft_delete_field": "deleted_at",
            "allowed_filters": ["name"], "allowed_sort": ["name"],
            "filter_operators": ["eq", "in"], "writable_fields": ["name"],
        })
        principal = Principal(kind="api_key", subject="a", roles=set(), permissions=set(), tenant_id="t1")
        db = FakeDatabase(profiles=FakeCollection([
            {"_id": "1", "name": "b", "tenant_id": "t1", "deleted_at": None},
            {"_id": "2", "name": "a", "tenant_id": "t1", "deleted_at": None},
            {"_id": "3", "name": "z", "tenant_id": "t2", "deleted_at": None},
        ]))
        listed = await list_documents(_request(b"sort=name&name__in=a,b"), db, resource, principal)
        assert [x["name"] for x in listed["items"]] == ["a", "b"]
        assert (await count_documents(_request(), db, resource, principal))["count"] == 2
        assert (await get_document(db, resource, principal, "1"))["name"] == "b"
        created = await create_document(db, resource, principal, {"name": "c"})
        assert created["tenant_id"] == "t1"
        updated = await update_document(db, resource, principal, created["_id"], {"name": "d"})
        assert updated["name"] == "d"
        assert await delete_document(db, resource, principal, created["_id"]) == {"deleted": True}
        with pytest.raises(HTTPException):
            await get_document(db, resource, principal, created["_id"])
        with pytest.raises(HTTPException):
            _write_payload({"not_allowed": 1}, resource, None)
        with pytest.raises(HTTPException):
            _base_filter(resource, Principal(kind="anonymous", subject="x", roles=set(), permissions=set()))
        with pytest.raises(HTTPException):
            await list_documents(_request(b"sort=forbidden"), db, resource, principal)

        class Client:
            closed = False
            async def close(self): self.closed = True
        client = Client(); registry = MongoRegistry(clients={"x": client}, databases={})
        await registry.dispose(); assert client.closed
    asyncio.run(run())


def test_event_hub_drops_oldest_and_websocket_cleanup():
    class WS:
        def __init__(self, fail=False): self.fail = fail; self.accepted = False; self.sent = []
        async def accept(self): self.accepted = True
        async def send_json(self, event):
            if self.fail: raise RuntimeError("dead")
            self.sent.append(event)

    async def run():
        hub = EventHub()
        ws, dead = WS(), WS(fail=True)
        await hub.connect_ws("c", ws); await hub.connect_ws("c", dead)
        assert ws.accepted
        enqueued = await hub.publish("c", {"x": 1})
        assert enqueued == 2  # publish acknowledges queue admission, not network delivery
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert ws.sent == [{"x": 1}]
        assert all(client.websocket is not dead for client in hub._websockets["c"])
        await hub.disconnect_ws("c", ws)
        assert await hub.ping()
        assert isinstance(build_event_hub("memory", None, "forge", "p"), EventHub)
        with pytest.raises(RuntimeError): build_event_hub("redis", None, "forge", "p")
    asyncio.run(run())
