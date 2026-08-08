from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from framework.api_models import APIKeyCreate
from framework.audit import AuditWriter
from framework.config import OperationConfig, ProjectConfig, ResponseSpec, SQLStatementConfig
from framework.operations import _execute_on_connection, execute_operation, resolve_value
from framework.responses import render_response
from framework.security import (
    Principal,
    _claim,
    _claim_set,
    _expand_role_permissions,
    authenticate_request,
    hash_key,
    has_permission,
    issue_jwt,
    make_api_key,
    permission_matches,
)
from framework.services.http_client import ResilientHTTPClient
from framework.settings import settings


def _request(*, headers=None, query=b"", path_params=None):
    request = Request({
        "type": "http", "method": "POST", "path": "/op/7", "headers": headers or [],
        "query_string": query, "path_params": path_params or {"id": "7"},
        "server": ("test", 80), "client": ("127.0.0.1", 1), "scheme": "http",
    })
    request.state.request_id = "req-1"
    request.state.validated_parameters = {"page": 3}
    return request


def _project(**security):
    return ProjectConfig.model_validate({
        "slug": "p", "name": "P", "databases": {"primary": {"url": "sqlite+aiosqlite:///x.db"}},
        "security": {"jwt_enabled": True, "jwt_provider": "local_hs256", **security},
        "roles": {
            "reader": {"permissions": ["notes.read"]},
            "editor": {"permissions": ["notes.write"], "inherits": ["reader"]},
            "loop-a": {"permissions": ["a"], "inherits": ["loop-b"]},
            "loop-b": {"permissions": ["b"], "inherits": ["loop-a"]},
        },
    })


def test_security_claims_permissions_roles_and_local_jwt(monkeypatch):
    assert _claim({"a": {"b": 2}}, "a.b") == 2
    assert _claim({"a": {}}, "a.x", "d") == "d"
    assert _claim_set(None) == set()
    assert _claim_set("x") == {"x"}
    assert _claim_set(["x", None, 2]) == {"x", "2"}
    assert _claim_set(9) == {"9"}
    assert permission_matches("*", "x")
    assert permission_matches("notes.*", "notes.read")
    assert not permission_matches("notes.*", "users.read")
    principal = Principal(kind="api_key", subject="x", roles=set(), permissions={"notes.*"})
    assert has_permission(principal, "notes.write") and has_permission(principal, None)

    project = _project()
    assert _expand_role_permissions(project, {"editor"}) == {"notes.read", "notes.write"}
    assert _expand_role_permissions(project, {"loop-a"}) == {"a", "b"}

    monkeypatch.setattr(settings, "jwt_secret", "super-secret-" + "x" * 64)
    token = issue_jwt("user-1", "p", ["editor"], ["direct"], 5, "tenant-1")
    request = _request(headers=[(b"authorization", f"Bearer {token}".encode())])

    async def run():
        p = await authenticate_request(request, project, object())
        assert p.kind == "jwt" and p.subject == "user-1" and p.tenant_id == "tenant-1"
        assert {"direct", "notes.read", "notes.write"} <= p.permissions

        bad = jwt.encode({"sub": "u", "project": "other", "exp": datetime.now(timezone.utc).timestamp() + 60}, settings.jwt_secret, algorithm="HS256")
        with pytest.raises(HTTPException) as exc:
            await authenticate_request(_request(headers=[(b"authorization", f"Bearer {bad}".encode())]), project, object())
        assert exc.value.status_code == 401

        anonymous = await authenticate_request(_request(), project, object())
        assert anonymous.kind == "anonymous"
    asyncio.run(run())

    assert hash_key("abc") == hash_key("abc") and hash_key("abc") != hash_key("def")
    assert make_api_key().startswith("jf2_")



def test_project_scoped_local_jwt_secret_overrides_global(monkeypatch):
    project_secret = "P" * 64
    monkeypatch.setattr(settings, "jwt_secret", "G" * 64)
    project = _project(jwt_secret=project_secret)
    token = issue_jwt("user-project", "p", [], ["notes.read"], 5, secret=project_secret)
    request = _request(headers=[(b"authorization", f"Bearer {token}".encode())])

    async def run():
        principal = await authenticate_request(request, project, object())
        assert principal.subject == "user-project"
        wrong = issue_jwt("wrong", "p", [], [], 5)  # signed with global fallback
        with pytest.raises(HTTPException) as exc:
            await authenticate_request(
                _request(headers=[(b"authorization", f"Bearer {wrong}".encode())]), project, object()
            )
        assert exc.value.status_code == 401

    asyncio.run(run())


def test_operation_value_resolution_and_modes():
    principal = Principal(kind="api_key", subject="plugin", roles=set(), permissions=set(), tenant_id="t")
    request = _request(query=b"q=hello", headers=[(b"x-test", b"hdr")])
    body = {"user": {"id": 9}}
    assert resolve_value(4, body=body, request=request, principal=principal) == 4
    assert resolve_value("$$body.x", body=body, request=request, principal=principal) == "$body.x"
    assert resolve_value("$principal.subject", body=body, request=request, principal=principal) == "plugin"
    assert resolve_value("$principal.tenant_id", body=body, request=request, principal=principal) == "t"
    assert resolve_value("$principal.kind", body=body, request=request, principal=principal) == "api_key"
    assert resolve_value("$request.id", body=body, request=request, principal=principal) == "req-1"
    assert resolve_value("$body.user.id", body=body, request=request, principal=principal) == 9
    assert resolve_value("$param.page", body=body, request=request, principal=principal) == 3
    assert resolve_value("$query.q", body=body, request=request, principal=principal) == "hello"
    assert resolve_value("$path.id", body=body, request=request, principal=principal) == "7"
    assert resolve_value("$header.x-test", body=body, request=request, principal=principal) == "hdr"
    with pytest.raises(HTTPException): resolve_value("$body.missing", body=body, request=request, principal=principal)
    with pytest.raises(HTTPException): resolve_value("$query.nope", body=body, request=request, principal=principal)
    with pytest.raises(HTTPException): resolve_value("$unknown.x", body=body, request=request, principal=principal)

    class Mappings:
        def __init__(self, rows): self.rows = rows
        def first(self): return self.rows[0] if self.rows else None
        def fetchmany(self, n): return self.rows[:n]
    class Result:
        def __init__(self, *, rowcount=1, rows=None, scalar=None): self.rowcount=rowcount; self._rows=rows or []; self._scalar=scalar
        def mappings(self): return Mappings(self._rows)
        def scalar(self): return self._scalar
    class Conn:
        def __init__(self): self.i=0
        async def execute(self, statement, params):
            self.i += 1
            return [
                Result(rowcount=1),
                Result(rows=[{"x": datetime(2026, 1, 1, tzinfo=timezone.utc)}]),
                Result(rows=[{"x": 1}, {"x": 2}]),
                Result(scalar=7),
            ][self.i-1]

    op = OperationConfig.model_validate({
        "name": "all-modes", "permission": "op", "transaction": True,
        "statements": [
            {"sql":"UPDATE t SET x=:x", "mode":"execute", "params":{"x":"$body.user.id"}, "result_name":"exec"},
            {"sql":"SELECT x FROM t", "mode":"fetch_one", "result_name":"one"},
            {"sql":"SELECT x FROM t", "mode":"fetch_all", "max_rows":2, "result_name":"many"},
            {"sql":"SELECT 7", "mode":"scalar"},
        ],
    })
    output = asyncio.run(_execute_on_connection(Conn(), op, body=body, request=request, principal=principal))
    assert output["exec"] == {"rowcount":1}
    assert output["one"]["x"].startswith("2026-01-01")
    assert output["many"] == [{"x":1},{"x":2}]
    assert output["results"] == [7]


def test_operation_rowcount_and_max_rows_guards():
    principal = Principal(kind="x", subject="x", roles=set(), permissions=set())
    request = _request()
    class M:
        def __init__(self, rows): self.rows=rows
        def fetchmany(self, n): return self.rows[:n]
        def first(self): return None
    class R:
        def __init__(self, rc=0, rows=None): self.rowcount=rc; self.rows=rows or []
        def mappings(self): return M(self.rows)
        def scalar(self): return None
    class C:
        def __init__(self, result): self.result=result
        async def execute(self,*a,**k): return self.result

    low = OperationConfig(name="x", permission="x", transaction=True, statements=[SQLStatementConfig(sql="UPDATE x SET y=1", mode="execute", require_rowcount_min=1)])
    with pytest.raises(HTTPException) as exc: asyncio.run(_execute_on_connection(C(R(0)), low, body={}, request=request, principal=principal))
    assert exc.value.status_code == 409
    high = OperationConfig(name="x", permission="x", transaction=True, statements=[SQLStatementConfig(sql="UPDATE x SET y=1", mode="execute", require_rowcount_max=1)])
    with pytest.raises(HTTPException): asyncio.run(_execute_on_connection(C(R(2)), high, body={}, request=request, principal=principal))
    many = OperationConfig(name="x", permission="x", transaction=False, statements=[SQLStatementConfig(sql="SELECT x FROM t", mode="fetch_all", max_rows=1)])
    with pytest.raises(HTTPException) as exc: asyncio.run(_execute_on_connection(C(R(rows=[{"x":1},{"x":2}])), many, body={}, request=request, principal=principal))
    assert exc.value.status_code == 413


def test_response_rendering_all_kinds(tmp_path):
    cases = [
        (ResponseSpec(kind="json"), {"x":1}, 200),
        (ResponseSpec(kind="text", media_type="text/plain"), "hello", 200),
        (ResponseSpec(kind="html"), "<b>x</b>", 200),
        (ResponseSpec(kind="redirect"), {"url":"https://example.com"}, 307),
        (ResponseSpec(kind="empty"), None, 204),
    ]
    for spec, value, code in cases:
        assert render_response(spec, value).status_code == code
    stream = render_response(ResponseSpec(kind="stream"), iter([b"a"]))
    assert stream.status_code == 200
    path = tmp_path / "x.txt"; path.write_text("x")
    file_response = render_response(ResponseSpec(kind="file", filename="download.txt"), {"path":str(path)})
    assert Path(file_response.path) == path


def test_audit_writer_batch_and_overflow(caplog):
    class Conn:
        def __init__(self, engine): self.engine=engine
        async def execute(self, stmt, batch): self.engine.batches.append(list(batch))
    class Ctx:
        def __init__(self, engine): self.engine=engine
        async def __aenter__(self): return Conn(self.engine)
        async def __aexit__(self,*a): pass
    class Engine:
        def __init__(self): self.batches=[]
        def begin(self): return Ctx(self)

    async def run():
        engine=Engine(); writer=AuditWriter(engine,max_queue=1,batch_size=1,flush_interval=0.01)
        writer.submit(project_slug="p",request_id="1",principal_kind="x",principal_subject="x",method="GET",path="/",status_code=200,duration_ms=1)
        writer.submit(project_slug="p",request_id="2",principal_kind="x",principal_subject="x",method="GET",path="/",status_code=200,duration_ms=1)
        assert writer.dropped == 1
        await writer.start(); await asyncio.sleep(0.03); await writer.close()
        assert len(engine.batches)==1 and engine.batches[0][0]["request_id"]=="1"
    asyncio.run(run())
    assert "dropping audit event" in caplog.text


def test_resilient_http_client_retry_and_circuit(monkeypatch):
    async def run():
        client=ResilientHTTPClient(failure_threshold=2,reset_seconds=60)
        calls=0
        async def request(method,url,**kwargs):
            nonlocal calls; calls+=1
            req=httpx.Request(method,url)
            if calls < 2: raise httpx.ConnectError("boom", request=req)
            return httpx.Response(200,json={"ok":True},request=req)
        client._send_once=request
        # Avoid real retry delays in the unit test.
        async def no_sleep(_): return None
        monkeypatch.setattr(asyncio,"sleep",no_sleep)
        response=await client.request("GET","https://example.com",retries=1)
        assert response.json()=={"ok":True} and calls==2
        await client.close()

        failing=ResilientHTTPClient(failure_threshold=1,reset_seconds=60)
        async def fail(method,url,**kwargs):
            raise httpx.ConnectError("no",request=httpx.Request(method,url))
        failing._send_once=fail
        with pytest.raises(httpx.ConnectError): await failing.request("GET","https://bad.example",retries=0)
        with pytest.raises(RuntimeError): await failing.request("GET","https://bad.example",retries=0)
        await failing.close()
    asyncio.run(run())


def test_api_key_auth_create_list_revoke_and_bootstrap(monkeypatch):
    from framework.security import (
        api_keys_table, bootstrap_is_available, consume_bootstrap, create_api_key,
        list_api_keys, revoke_api_key,
    )

    class MappingView:
        def __init__(self, first=None, all_rows=None): self._first=first; self._all=all_rows or []
        def first(self): return self._first
        def all(self): return self._all
    class Result:
        def __init__(self, *, first=None, mapping_first=None, all_rows=None, rowcount=1, inserted=77):
            self._first=first; self._mapping_first=mapping_first; self._all=all_rows or []
            self.rowcount=rowcount; self.inserted_primary_key=[inserted]
        def first(self): return self._first
        def mappings(self): return MappingView(self._mapping_first, self._all)
    class Conn:
        def __init__(self, engine): self.engine=engine
        async def execute(self, stmt, params=None):
            text_repr=str(stmt)
            self.engine.statements.append(text_repr)
            if "_forge_v4_bootstrap_state.consumed_at" in text_repr:
                return Result(first=self.engine.bootstrap_row)
            if "_forge_v4_bootstrap_state.project_slug" in text_repr and text_repr.lstrip().startswith("SELECT"):
                return Result(first=("p",) if self.engine.bootstrap_row else None)
            if "_forge_v2_api_keys" in text_repr and text_repr.lstrip().startswith("SELECT"):
                if "ORDER BY" in text_repr:
                    return Result(all_rows=self.engine.list_rows)
                return Result(mapping_first=self.engine.auth_row)
            if text_repr.lstrip().startswith("UPDATE"):
                return Result(rowcount=1)
            if text_repr.lstrip().startswith("INSERT"):
                return Result(inserted=77)
            return Result()
        async def run_sync(self, fn): return None
    class Ctx:
        def __init__(self, engine): self.engine=engine
        async def __aenter__(self): return Conn(self.engine)
        async def __aexit__(self,*a): pass
    class Engine:
        def __init__(self):
            self.statements=[]; self.bootstrap_row=None; self.auth_row=None; self.list_rows=[]
        def connect(self): return Ctx(self)
        def begin(self): return Ctx(self)

    async def run():
        engine=Engine()
        assert await bootstrap_is_available(engine,"p")
        await consume_bootstrap(engine,"p")
        # Simulate state as consumed for the next availability check.
        engine.bootstrap_row=(datetime.now(timezone.utc),)
        assert not await bootstrap_is_available(engine,"p")

        created=await create_api_key(engine,project_slug="p",name="bot",roles=["editor"],permissions=["direct"],tenant_id="t")
        assert created["id"]==77 and created["api_key"].startswith("jf2_")
        engine.bootstrap_row=None
        engine.statements.clear()
        boot_created=await create_api_key(
            engine,project_slug="p",name="first-admin",roles=["admin"],permissions=["*"],consume_bootstrap_once=True
        )
        assert boot_created["id"]==77
        assert any("_forge_v4_bootstrap_state" in statement for statement in engine.statements)
        engine.list_rows=[{
            "id":77,"name":"bot","prefix":"jf2_prefix","roles":"editor","permissions":"direct",
            "tenant_id":"t","enabled":True,"rate_requests":10,"rate_window_seconds":60,"rate_burst":2,
            "expires_at":None,"created_at":datetime.now(timezone.utc),
        }]
        listed=await list_api_keys(engine,"p")
        assert listed[0]["roles"]==["editor"] and listed[0]["permissions"]==["direct"]
        assert await revoke_api_key(engine,"p",77)

        raw="jf2_test"
        engine.auth_row={
            "id":7,"name":"plugin","roles":"editor","permissions":"direct","tenant_id":"t","enabled":True,
            "rate_requests":12,"rate_window_seconds":60,"rate_burst":3,"expires_at":None,
        }
        project=_project(jwt_enabled=False)
        request=_request(headers=[(project.security.api_key_header.lower().encode(), raw.encode())])
        # `authenticate_request` builds a hash predicate; fake engine returns the configured row.
        p=await authenticate_request(request,project,engine)
        assert p.kind=="api_key" and "notes.read" in p.permissions and p.rate_requests==12

        # A successful API-key lookup is intentionally cached for a short TTL.
        cached = await authenticate_request(request, project, engine)
        assert cached.kind == "api_key"

        engine.auth_row = None
        from framework.security import clear_api_key_auth_cache
        clear_api_key_auth_cache("p")
        with pytest.raises(HTTPException) as exc:
            await authenticate_request(request,project,engine)
        assert exc.value.status_code==401

    asyncio.run(run())


def test_audit_writer_retries_transient_failure():
    class Conn:
        def __init__(self, engine): self.engine=engine
        async def execute(self, stmt, batch):
            self.engine.attempts += 1
            if self.engine.attempts == 1:
                raise RuntimeError("temporary")
            self.engine.saved.extend(batch)
    class Ctx:
        def __init__(self, engine): self.engine=engine
        async def __aenter__(self): return Conn(self.engine)
        async def __aexit__(self,*a): pass
    class Engine:
        def __init__(self): self.attempts=0; self.saved=[]
        def begin(self): return Ctx(self)

    async def run():
        engine=Engine()
        writer=AuditWriter(engine,max_queue=10,batch_size=1,flush_interval=0.01,write_retries=1,retry_backoff_seconds=0)
        await writer.start()
        writer.submit(project_slug="p",request_id="r",principal_kind="x",principal_subject="x",method="GET",path="/",status_code=200,duration_ms=1)
        await asyncio.sleep(0.03)
        await writer.close()
        assert engine.attempts == 2
        assert len(engine.saved) == 1
        assert writer.write_failures == 1
        assert writer.dropped == 0
    asyncio.run(run())


def test_resilient_http_client_does_not_retry_permanent_or_unsafe_requests(monkeypatch):
    async def run():
        async def no_sleep(_): return None
        monkeypatch.setattr(asyncio, "sleep", no_sleep)

        # A non-idempotent POST transport failure is attempted once unless the
        # declarative source explicitly opts into mutation retries.
        post_client = ResilientHTTPClient(failure_threshold=10)
        post_calls = 0
        async def fail_post(method, url, **kwargs):
            nonlocal post_calls
            post_calls += 1
            raise httpx.ConnectError("boom", request=httpx.Request(method, url))
        post_client._send_once = fail_post
        with pytest.raises(httpx.ConnectError):
            await post_client.request("POST", "https://example.com/mutate", retries=5)
        assert post_calls == 1
        await post_client.close()

        # Permanent 4xx responses are not retried and do not open the transient circuit.
        not_found = ResilientHTTPClient(failure_threshold=1)
        calls = 0
        async def return_404(method, url, **kwargs):
            nonlocal calls
            calls += 1
            req = httpx.Request(method, url)
            return httpx.Response(404, request=req)
        not_found._send_once = return_404
        with pytest.raises(httpx.HTTPStatusError):
            await not_found.request("GET", "https://example.com/missing", retries=3)
        assert calls == 1
        assert not_found.states["example.com"].opened_at is None
        await not_found.close()

        # Explicitly opting into POST retries is possible only when the caller owns
        # the upstream idempotency contract.
        opted = ResilientHTTPClient(failure_threshold=10)
        opted_calls = 0
        async def flaky_post(method, url, **kwargs):
            nonlocal opted_calls
            opted_calls += 1
            req = httpx.Request(method, url)
            if opted_calls == 1:
                return httpx.Response(503, request=req, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"ok": True}, request=req)
        opted._send_once = flaky_post
        response = await opted.request(
            "POST", "https://example.com/idempotent-provider", retries=1, retry_non_idempotent=True
        )
        assert response.json() == {"ok": True} and opted_calls == 2
        await opted.close()

    asyncio.run(run())


def test_observability_metrics_and_no_dependency_fallback(monkeypatch):
    import framework.observability as obs

    class Metric:
        def __init__(self):
            self.calls = []
        def labels(self, **kwargs):
            self.calls.append(("labels", kwargs)); return self
        def inc(self, value=1):
            self.calls.append(("inc", value))
        def observe(self, value):
            self.calls.append(("observe", value))
        def set(self, value):
            self.calls.append(("set", value))

    requests = Metric(); latency = Metric(); dropped = Metric(); failures = Metric(); queue = Metric()
    monkeypatch.setattr(obs, "_REQUESTS", requests)
    monkeypatch.setattr(obs, "_LATENCY", latency)
    monkeypatch.setattr(obs, "_AUDIT_DROPPED", dropped)
    monkeypatch.setattr(obs, "_AUDIT_WRITE_FAILURES", failures)
    monkeypatch.setattr(obs, "_AUDIT_QUEUE", queue)
    monkeypatch.setattr(obs, "generate_latest", lambda: b"metric 1\n")
    monkeypatch.setattr(obs, "CONTENT_TYPE_LATEST", "text/plain; version=0.0.4")

    obs.observe("app", "GET", 200, 0.25)
    obs.observe_audit_drop(2)
    obs.observe_audit_write_failure(3)
    obs.observe_audit_queue(4)
    payload, content_type = obs.metrics_payload()

    assert ("labels", {"project": "app", "method": "GET", "status": "200"}) in requests.calls
    assert ("observe", 0.25) in latency.calls
    assert ("inc", 2) in dropped.calls
    assert ("inc", 3) in failures.calls
    assert ("set", 4) in queue.calls
    assert payload == b"metric 1\n" and content_type == "text/plain; version=0.0.4"

    monkeypatch.setattr(obs, "_REQUESTS", None)
    monkeypatch.setattr(obs, "_AUDIT_DROPPED", None)
    monkeypatch.setattr(obs, "_AUDIT_WRITE_FAILURES", None)
    monkeypatch.setattr(obs, "_AUDIT_QUEUE", None)
    monkeypatch.setattr(obs, "generate_latest", None)
    obs.observe("app", "GET", 500, 1.0)
    obs.observe_audit_drop()
    obs.observe_audit_write_failure()
    obs.observe_audit_queue(0)
    assert obs.metrics_payload() == (b"prometheus-client is not installed\n", "text/plain")
