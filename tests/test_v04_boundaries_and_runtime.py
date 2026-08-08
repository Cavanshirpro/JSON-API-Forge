from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from framework.config import ForgeConfig, MongoResourceConfig, ProjectConfig
from framework.security import Principal


def _request(*, method="GET", path="/", headers=None, query=b"", client="10.0.0.10", scheme="http"):
    return Request({
        "type": "http", "method": method, "path": path, "headers": headers or [],
        "query_string": query, "server": ("test", 80), "client": (client, 1234), "scheme": scheme,
    })


def _project(**overrides) -> ProjectConfig:
    data = {
        "slug": "p", "name": "P", "databases": {"primary": {"url": "sqlite+aiosqlite:///:memory:"}},
        "security": {"jwt_enabled": False},
        "roles": {"reader": {"permissions": ["notes.read"]}, "child": {"inherits": ["reader"], "permissions": ["notes.list"]}},
        "rate_limit": {"requests": 100, "window_seconds": 60, "burst": 20},
    }
    for key, value in overrides.items():
        if key == "security": data["security"] = {**data["security"], **value}
        else: data[key] = value
    return ProjectConfig.model_validate(data)


def test_proxy_trust_ip_host_and_https_boundaries():
    from framework.protection import client_ip, direct_peer, host_allowed, ip_allowed, request_is_https

    assert direct_peer(SimpleNamespace(client=None)) == "0.0.0.0"
    untrusted = _request(headers=[(b"x-forwarded-for", b"203.0.113.9")], client="198.51.100.10")
    assert client_ip(untrusted, ["10.0.0.0/8"]) == "198.51.100.10"

    trusted = _request(
        headers=[(b"x-forwarded-for", b"203.0.113.9, 10.1.1.2"), (b"x-forwarded-proto", b"https")],
        client="10.1.1.1",
    )
    assert client_ip(trusted, ["10.0.0.0/8"]) == "203.0.113.9"
    assert request_is_https(trusted, ["10.0.0.0/8"]) is True
    assert request_is_https(untrusted, ["10.0.0.0/8"]) is False
    assert request_is_https(_request(scheme="https"), []) is True

    all_trusted = _request(headers=[(b"x-forwarded-for", b"10.2.2.2, invalid, 10.3.3.3")], client="10.1.1.1")
    assert client_ip(all_trusted, ["10.0.0.0/8"]) == "10.2.2.2"

    assert ip_allowed(trusted, ["203.0.113.0/24"], [], ["10.0.0.0/8"])
    assert not ip_allowed(trusted, [], ["203.0.113.9"], ["10.0.0.0/8"])
    assert not ip_allowed(_request(client="bad-ip"), ["10.0.0.0/8"], [])
    assert ip_allowed(_request(client="bad-ip"), [], [])

    assert host_allowed("api.example.com:443", ["api.example.com"])
    assert host_allowed("a.example.com", ["*.example.com"])
    assert not host_allowed("example.com", ["*.example.com"])
    assert not host_allowed(None, ["example.com"])
    assert host_allowed("whatever", ["*"])


def test_request_body_limit_asgi_paths():
    from framework.protection import RequestBodyLimitMiddleware

    async def run_case(scope, incoming, *, limit=5, app_reads=True):
        sent = []
        queue = list(incoming)
        async def receive(): return queue.pop(0)
        async def send(message): sent.append(message)
        async def app(scope, receive, send):
            if app_reads:
                while True:
                    msg = await receive()
                    if not msg.get("more_body"): break
            await send({"type":"http.response.start","status":200,"headers":[]})
            await send({"type":"http.response.body","body":b"ok","more_body":False})
        mw = RequestBodyLimitMiddleware(app, lambda path: limit if path == "/limited" else None)
        await mw(scope, receive, send)
        return sent

    async def run():
        base = {"type":"http","method":"POST","path":"/limited","headers":[]}
        sent = await run_case(base, [{"type":"http.request","body":b"123456","more_body":False}])
        assert sent[0]["status"] == 413
        sent = await run_case({**base,"headers":[(b"content-length",b"99")]}, [{"type":"http.request","body":b"","more_body":False}])
        assert sent[0]["status"] == 413
        sent = await run_case({**base,"headers":[(b"content-length",b"wat")]}, [{"type":"http.request","body":b"","more_body":False}])
        assert sent[0]["status"] == 400
        sent = await run_case({**base,"path":"/free"}, [{"type":"http.request","body":b"123456","more_body":False}])
        assert sent[0]["status"] == 200
        # Non-HTTP scopes bypass the HTTP body policy.
        sent=[]
        async def app(scope, receive, send): sent.append(scope["type"])
        mw=RequestBodyLimitMiddleware(app, lambda _: 1)
        await mw({"type":"websocket","path":"/limited"}, lambda: None, lambda _: None)
        assert sent == ["websocket"]
    asyncio.run(run())


def test_security_claims_roles_local_jwt_and_delegation(monkeypatch):
    import framework.security as sec

    assert sec._claim({"a":{"b":1}}, "a.b") == 1
    assert sec._claim({"a":{}}, "a.b", "x") == "x"
    assert sec._claim_set(None) == set()
    assert sec._claim_set("x") == {"x"}
    assert sec._claim_set(["x", 2, None]) == {"x", "2"}
    assert sec.permission_matches("notes.*", "notes.read") and not sec.permission_matches("notes.*", "users.read")

    project = _project(security={"jwt_enabled":True,"jwt_secret":"s"*64,"jwt_require_project_claim":True})
    assert sec._expand_role_permissions(project, {"child"}) == {"notes.read","notes.list"}

    token = sec.issue_jwt("user-1", "p", ["child"], ["direct.x"], 5, tenant_id="t1", secret="s"*64)
    async def auth():
        req = _request(headers=[(b"authorization", f"Bearer {token}".encode())])
        principal = await sec.authenticate_request(req, project, engine=object())
        assert principal.kind == "jwt" and principal.subject == "user-1"
        assert {"notes.read","notes.list","direct.x"}.issubset(principal.permissions)
        assert principal.tenant_id == "t1"
        bad = sec.issue_jwt("user-1", "other", [], [], 5, secret="s"*64)
        with pytest.raises(HTTPException) as exc:
            await sec.authenticate_request(_request(headers=[(b"authorization", f"Bearer {bad}".encode())]), project, object())
        assert exc.value.status_code == 401
        with pytest.raises(HTTPException):
            await sec.authenticate_request(_request(headers=[(b"authorization", b"Bearer "+b"x"*9000)]), project, object())
        anon = await sec.authenticate_request(_request(), project, object())
        assert anon.kind == "anonymous"
    asyncio.run(auth())

    parent = Principal(
        kind="api_key", subject="api-key:1:parent", roles={"child"},
        permissions={"notes.read","notes.list","direct.x","admin.jwt.issue"}, tenant_id="t1",
        rate_requests=50, rate_window_seconds=60, rate_burst=10,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=10),
    )
    sec.ensure_credential_delegation(
        project, parent, roles=["child"], permissions=["direct.x"], tenant_id="t1",
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=5),
        rate_requests=40, rate_window_seconds=60, rate_burst=8, subject=parent.subject,
    )
    for kwargs in (
        dict(roles=["reader"], permissions=[], tenant_id="t1"),
        dict(roles=["child"], permissions=["admin.*"], tenant_id="t1"),
        dict(roles=["child"], permissions=[], tenant_id="other"),
        dict(roles=["child"], permissions=[], tenant_id="t1", rate_requests=51),
        dict(roles=["child"], permissions=[], tenant_id="t1", rate_burst=11),
        dict(roles=["child"], permissions=[], tenant_id="t1", subject="other"),
    ):
        with pytest.raises(HTTPException): sec.ensure_credential_delegation(project, parent, **kwargs)
    with pytest.raises(HTTPException):
        sec.ensure_credential_delegation(project, parent, roles=["child"], permissions=[], tenant_id="t1", expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    # An expiring caller may not mint an effectively immortal child credential.
    with pytest.raises(HTTPException):
        sec.ensure_credential_delegation(project, parent, roles=["child"], permissions=[], tenant_id="t1", expires_at=None)

    god = Principal(kind="api_key", subject="god", roles=set(), permissions={"admin.credentials.delegate_any"})
    sec.ensure_credential_delegation(project, god, roles=["whatever"], permissions=["*"], tenant_id="x", subject="other")


def test_bootstrap_and_api_key_authentication_boundaries():
    import framework.security as sec

    class Mapping:
        def __init__(self, row): self.row=row
        def first(self): return self.row
    class Result:
        def __init__(self, row=None, maprow=None): self.row=row; self.maprow=maprow
        def first(self): return self.row
        def mappings(self): return Mapping(self.maprow)
    class Conn:
        def __init__(self, engine): self.engine=engine
        async def execute(self, stmt):
            text=str(stmt)
            if "_forge_v4_bootstrap_state" in text: return Result(row=self.engine.bootstrap)
            return Result(maprow=self.engine.keyrow)
    class Ctx:
        def __init__(self,e): self.e=e
        async def __aenter__(self): return Conn(self.e)
        async def __aexit__(self,*a): return False
    class Engine:
        def __init__(self): self.bootstrap=None; self.keyrow=None
        def connect(self): return Ctx(self)

    project=_project(security={"bootstrap_enabled":True,"bootstrap_admin_key":"B"*40,"bootstrap_one_time":True})
    engine=Engine()
    async def run():
        p=await sec.authenticate_request(_request(headers=[(b"x-api-key", b"B"*40)]),project,engine)
        assert p.kind=="bootstrap" and p.permissions=={"admin.keys.create","admin.credentials.delegate_any"}
        engine.bootstrap=(datetime.now(timezone.utc),)
        with pytest.raises(HTTPException): await sec.authenticate_request(_request(headers=[(b"x-api-key", b"B"*40)]),project,engine)
        with pytest.raises(HTTPException): await sec.authenticate_request(_request(headers=[(b"x-api-key", b"x"*513)]),project,engine)
        engine.bootstrap=None
        engine.keyrow={
            "id":9,"name":"bot","roles":"child","permissions":"direct.x","tenant_id":"t1","enabled":True,
            "rate_requests":10,"rate_window_seconds":30,"rate_burst":2,"expires_at":None,
        }
        p=await sec.authenticate_request(_request(headers=[(b"x-api-key", b"not-bootstrap")]),project,engine)
        assert p.subject=="api-key:9:bot" and "notes.read" in p.permissions
        engine.keyrow={**engine.keyrow,"enabled":False}
        with pytest.raises(HTTPException): await sec.authenticate_request(_request(headers=[(b"x-api-key", b"bad")]),project,engine)
        engine.keyrow={**engine.keyrow,"enabled":True,"expires_at":datetime.now(timezone.utc)-timedelta(seconds=1)}
        with pytest.raises(HTTPException): await sec.authenticate_request(_request(headers=[(b"x-api-key", b"old")]),project,engine)
    asyncio.run(run())


def test_http_client_stream_limits_retry_and_circuit(monkeypatch):
    from framework.services.http_client import ResilientHTTPClient, ResponseTooLarge

    async def run():
        async def handler(request: httpx.Request):
            if request.url.path == "/large": return httpx.Response(200, content=b"123456", request=request)
            return httpx.Response(200, json={"ok":True}, request=request)
        client=ResilientHTTPClient()
        await client.client.aclose()
        client.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert (await client._send_once("GET","https://x.test/ok",max_response_bytes=20)).json()=={"ok":True}
        with pytest.raises(ResponseTooLarge): await client._send_once("GET","https://x.test/large",max_response_bytes=5)
        await client.close()

        retry=ResilientHTTPClient(failure_threshold=2,reset_seconds=0.1)
        attempts=[]
        async def send(method,url,**kwargs):
            attempts.append(url)
            req=httpx.Request(method,url)
            if len(attempts)<2: raise httpx.ConnectError("boom",request=req)
            return httpx.Response(200,json={"ok":True},request=req)
        retry._send_once=send
        async def no_sleep(_): return None
        monkeypatch.setattr(asyncio,"sleep",no_sleep)
        assert (await retry.request("GET","https://retry.test",retries=1)).status_code==200
        assert len(attempts)==2
        await retry.close()

        circuit=ResilientHTTPClient(failure_threshold=1,reset_seconds=60)
        async def fail(method,url,**kwargs): raise httpx.ConnectError("down",request=httpx.Request(method,url))
        circuit._send_once=fail
        with pytest.raises(httpx.ConnectError): await circuit.request("GET","https://down.test",retries=0)
        with pytest.raises(RuntimeError, match="Circuit open"): await circuit.request("GET","https://down.test",retries=0)
        await circuit.close()
    asyncio.run(run())


def test_mongo_owner_tenant_replace_and_delete_paths():
    from framework.mongo import _base_filter, _positive_int, _query_filter, create_document, delete_document, get_document, update_document

    resource=MongoResourceConfig.model_validate({
        "database":"main","collection":"items","path":"items","tenant_field":"tenant_id","owner_field":"owner_id",
        "owner_actions":["list","read","update","delete"],"owner_bypass_permission":"items.owner_bypass",
        "soft_delete_field":"deleted_at","writable_fields":["name"],"allowed_filters":["name"],
        "filter_operators":["eq","ne","in"],"allowed_sort":["name"],
    })
    principal=Principal(kind="api_key",subject="u1",roles=set(),permissions=set(),tenant_id="t1")
    assert _base_filter(resource,principal)=={"tenant_id":"t1","owner_id":"u1","deleted_at":None}
    bypass=Principal(kind="api_key",subject="admin",roles=set(),permissions={"items.owner_bypass"},tenant_id="t1")
    assert "owner_id" not in _base_filter(resource,bypass)
    with pytest.raises(HTTPException): _base_filter(resource,Principal(kind="anonymous",subject="x",roles=set(),permissions=set(),tenant_id="t1"))
    req=_request(query=b"name__in=a,b&ignored=x")
    filt=_query_filter(req,resource,principal)
    assert filt["name"]=={"$in":["a","b"]} and "ignored" not in filt
    with pytest.raises(HTTPException): _positive_int(_request(query=b"limit=no"),"limit",10,minimum=1)
    with pytest.raises(HTTPException): _positive_int(_request(query=b"limit=0"),"limit",10,minimum=1)

    class Collection:
        def __init__(self):
            self.rows={"1":{"_id":"1","name":"old","tenant_id":"t1","owner_id":"u1","deleted_at":None}}
            self.last_replace=None
        async def find_one(self,filt):
            row=self.rows.get(str(filt.get("_id")))
            if not row: return None
            return dict(row) if all(row.get(k)==v for k,v in filt.items() if k!="_id") else None
        async def insert_one(self,data): self.rows["2"]={"_id":"2",**data}; return SimpleNamespace(inserted_id="2")
        async def update_one(self,filt,update):
            row=await self.find_one(filt)
            if not row: return SimpleNamespace(matched_count=0)
            self.rows[str(filt["_id"])].update(update["$set"]); return SimpleNamespace(matched_count=1)
        async def replace_one(self,filt,replacement):
            if not await self.find_one(filt): return SimpleNamespace(matched_count=0)
            self.last_replace=dict(replacement); self.rows[str(filt["_id"])]=dict(replacement); return SimpleNamespace(matched_count=1)
        async def delete_one(self,filt): return SimpleNamespace(deleted_count=0)
    col=Collection(); db={"items":col}
    async def run():
        created=await create_document(db,resource,principal,{"name":"new"})
        assert created["tenant_id"]=="t1" and created["owner_id"]=="u1"
        replaced=await update_document(db,resource,principal,"1",{"name":"replaced"},replace=True)
        assert replaced["name"]=="replaced" and col.last_replace["owner_id"]=="u1"
        assert await delete_document(db,resource,principal,"1") == {"deleted":True}
        with pytest.raises(HTTPException): await get_document(db,resource,principal,"missing")
    asyncio.run(run())


def test_runtime_manager_transactional_start_and_cleanup(monkeypatch):
    import framework.runtime as rt

    projects=[_project(slug="a",name="A",api_prefix="/a"),_project(slug="b",name="B",api_prefix="/b")]
    forge=ForgeConfig(projects=projects)
    created=[]
    class Service:
        def __init__(self,name,fail_close=False): self.name=name; self.closed=False; self.fail_close=fail_close
        async def close(self): self.closed=True; 
        async def dispose(self): self.closed=True
        async def ping(self): return True
    class Registry(Service): pass
    async def registry(cfg):
        if cfg.slug=="b" and getattr(registry,"fail",False): raise RuntimeError("boom")
        value=Registry("db-"+cfg.slug); created.append(value); return value
    async def mongo(cfg): value=Service("mongo-"+cfg.slug); created.append(value); return value
    monkeypatch.setattr(rt,"build_registry",registry); monkeypatch.setattr(rt,"build_mongo_registry",mongo)
    monkeypatch.setattr(rt,"build_cache",lambda *a,**k: Service("cache"))
    monkeypatch.setattr(rt,"DataSourceManager",lambda cfg: Service("data"))
    monkeypatch.setattr(rt,"build_event_hub",lambda *a,**k: Service("events"))
    monkeypatch.setattr(rt,"MemoryRateLimiter",lambda **k: Service("limiter"))

    async def run():
        manager=rt.RuntimeManager(forge)
        assert manager.for_path("/a/x").config.slug=="a" and manager.for_path("/none") is None
        assert manager.body_limit_for_path("/none") is None
        await manager.start(); assert manager._started
        await manager.close(); assert not manager._started
        assert all(s.closed for s in created)

        created.clear(); registry.fail=True
        manager=rt.RuntimeManager(forge)
        with pytest.raises(RuntimeError): await manager.start()
        assert all(s.closed for s in created)
    asyncio.run(run())


def test_mongo_registry_validation_failure_cleanup_and_extra_paths(monkeypatch):
    import sys, types
    import framework.mongo as m

    clients=[]
    class Client:
        def __init__(self, uri, **kwargs): self.uri=uri; self.kwargs=kwargs; self.closed=False; clients.append(self)
        def __getitem__(self,name): return {"name":name}
        async def close(self): self.closed=True
    mod=types.ModuleType("pymongo"); mod.AsyncMongoClient=Client; monkeypatch.setitem(sys.modules,"pymongo",mod)

    project=_project(
        mongo_databases={"m":{"uri":"mongodb://db","database":"app","max_pool_size":5,"min_pool_size":1}},
        mongo_resources=[{"database":"m","collection":"x","path":"x","writable_fields":["name"]}],
    )
    async def run():
        reg=await m.build_mongo_registry(project)
        assert reg.databases["m"]=={"name":"app"}
        await reg.dispose(); assert clients[-1].closed

        bad=_project(
            mongo_databases={"m":{"uri":"mongodb://db","database":"app"}},
            mongo_resources=[{"database":"missing","collection":"x","path":"x"}],
        )
        with pytest.raises(RuntimeError,match="Unknown Mongo database alias"): await m.build_mongo_registry(bad)
        assert clients[-1].closed

        bad_write=_project(
            mongo_databases={"m":{"uri":"mongodb://db","database":"app"}},
            mongo_resources=[{"database":"m","collection":"x","path":"x","tenant_field":"tenant_id","writable_fields":["tenant_id"]}],
        )
        with pytest.raises(RuntimeError,match="policy fields"): await m.build_mongo_registry(bad_write)

        bad_owner=_project(
            mongo_databases={"m":{"uri":"mongodb://db","database":"app"}},
            mongo_resources=[{"database":"m","collection":"x","path":"x","owner_actions":["read"]}],
        )
        with pytest.raises(RuntimeError,match="owner_actions"): await m.build_mongo_registry(bad_owner)
    asyncio.run(run())


def test_mongo_query_operators_anonymous_create_and_hard_delete():
    import framework.mongo as m
    resource=MongoResourceConfig.model_validate({
        "database":"m","collection":"x","path":"x","writable_fields":["name"],
        "allowed_filters":["name"],"filter_operators":["eq","ne","gt","gte","lt","lte","in"],"allowed_sort":["name"],
    })
    principal=Principal(kind="api_key",subject="u",roles=set(),permissions=set())
    f=m._query_filter(_request(query=b"name__ne=a&name__gt=0"),resource,principal)
    assert f["name"]=={"$ne":"a","$gt":"0"}
    assert m._visible({"_id":123,"secret":1},MongoResourceConfig(database="m",collection="x",path="x",hidden_fields=["secret"]))=={"_id":"123"}

    owner=MongoResourceConfig(database="m",collection="x",path="x",owner_field="user_id",writable_fields=["name"])
    class Col:
        async def insert_one(self,data): return SimpleNamespace(inserted_id="1")
        async def find_one(self,filt): return {"_id":"1","name":"x","user_id":"u"}
        async def delete_one(self,filt): return SimpleNamespace(deleted_count=1)
        async def update_one(self,filt,update): return SimpleNamespace(matched_count=0)
    db={"x":Col()}
    async def run():
        with pytest.raises(HTTPException) as exc:
            await m.create_document(db,owner,Principal(kind="anonymous",subject="anonymous",roles=set(),permissions=set()),{"name":"x"})
        assert exc.value.status_code==401
        plain=MongoResourceConfig(database="m",collection="x",path="x",writable_fields=["name"])
        assert await m.delete_document(db,plain,principal,"1") == {"deleted":True}
        with pytest.raises(HTTPException): await m.update_document(db,plain,principal,"1",{})
    asyncio.run(run())


def test_api_key_auth_cache_is_bounded_short_lived_and_explicitly_invalidatable():
    import framework.security as sec

    class Mapping:
        def __init__(self, row): self.row = row
        def first(self): return self.row
    class Result:
        def __init__(self, row): self.row = row
        def mappings(self): return Mapping(self.row)
    class Conn:
        def __init__(self, engine): self.engine = engine
        async def execute(self, stmt):
            self.engine.lookups += 1
            return Result(self.engine.row)
    class Ctx:
        def __init__(self, engine): self.engine = engine
        async def __aenter__(self): return Conn(self.engine)
        async def __aexit__(self, *args): return False
    class Engine:
        def __init__(self):
            self.lookups = 0
            self.row = {
                "id": 11, "name": "cached", "roles": "", "permissions": "notes.read",
                "tenant_id": None, "enabled": True, "rate_requests": None,
                "rate_window_seconds": None, "rate_burst": None, "expires_at": None,
            }
        def connect(self): return Ctx(self)

    project = _project(security={"api_key_cache_ttl_seconds": 5.0, "api_key_cache_max_entries": 100})
    engine = Engine()
    sec.clear_api_key_auth_cache()

    async def run():
        request = _request(headers=[(b"x-api-key", b"cache-me")])
        first = await sec.authenticate_request(request, project, engine)
        second = await sec.authenticate_request(request, project, engine)
        assert first.subject == second.subject == "api-key:11:cached"
        assert engine.lookups == 1
        sec.clear_api_key_auth_cache(project.slug)
        await sec.authenticate_request(request, project, engine)
        assert engine.lookups == 2

    asyncio.run(run())
    sec.clear_api_key_auth_cache()
