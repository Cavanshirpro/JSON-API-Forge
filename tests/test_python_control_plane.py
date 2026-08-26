from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from json_api_forge import (
    AsyncEditorControlPlaneClient,
    EditorControlPlaneClient,
    ForgeHTTPError,
    ForgeResponse,
    ForgeSessionError,
)

SESSION = "jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN"
INVITATION = "jfi_" + "A" * 48
CALL_TICKET = "jfc_4qZ7bK2wM9sF6xR3nV8cD1hJ5pL0tY7uA2eG9mN6"


def test_sync_control_plane_session_scopes_files_and_redirect_policy(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/auth/login"):
            assert "authorization" not in request.headers
            return httpx.Response(
                200,
                json={"access_token": SESSION, "expires_in": 900, "profile": {"username": "worker"}},
                headers={"Set-Cookie": "ambient=must-not-return; Path=/"},
            )
        if path.endswith("/me"):
            assert request.headers["Authorization"] == f"Bearer {SESSION}"
            assert "cookie" not in request.headers
            assert request.headers["Cache-Control"] == "no-store"
            return httpx.Response(200, json={"username": "worker", "display_name": "Worker"})
        if path.endswith("/invitations"):
            assert request.method == "POST"
            return httpx.Response(201, json={"invitation": INVITATION})
        if "/documents/" in path:
            return httpx.Response(200, json={"path": path})
        if path.endswith("/areas/area-1/attachments") and request.method == "POST":
            assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
            assert b"signed plan" in request.content
            return httpx.Response(201, json={"id": "attachment-1", "original_name": "plan.txt"})
        if path.endswith("/areas/area-1/attachments"):
            return httpx.Response(200, json={"attachments": [{"id": "attachment-1"}]})
        if path.endswith("/attachments/attachment-1"):
            return httpx.Response(200, content=b"signed plan", headers={"Content-Type": "application/octet-stream"})
        if path.endswith("/calls/call-1/ticket"):
            return httpx.Response(
                200,
                json={
                    "ticket": CALL_TICKET,
                    "call_client_path": "/__forge/editor/v1/call-client/call-1",
                },
            )
        if path.endswith("/roles"):
            return httpx.Response(302, headers={"Location": "https://attacker.test/collect"})
        if path.endswith("/members"):
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json={"path": path})

    source = tmp_path / "plan.txt"
    source.write_bytes(b"signed plan")
    target = tmp_path / "downloaded-plan.txt"
    with EditorControlPlaneClient("https://forge.test/admin", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ForgeSessionError):
            client.profile()
        authenticated = client.login("worker", "correct horse battery staple")
        assert client.has_session
        assert "access_token" not in authenticated.data
        assert authenticated.data["profile"]["username"] == "worker"
        assert client.profile().data["display_name"] == "Worker"
        invitation = client.create_invitation([{"role_id": "developer", "project": "Project One"}])
        assert invitation.data["invitation"] == INVITATION

        document = client.document("Project One", "config/40-resources.json")
        assert document.data["path"].endswith("/projects/Project One/documents/config/40-resources.json")
        assert b"Project%20One" in seen[-1].url.raw_path

        uploaded = client.upload_attachment("area-1", source)
        assert uploaded.data["id"] == "attachment-1"
        assert client.attachments("area-1").data["attachments"][0]["id"] == "attachment-1"
        downloaded = client.download_attachment("attachment-1", target)
        assert downloaded.data == target
        assert target.read_bytes() == b"signed plan"

        ticket = client.call_ticket("call-1").data
        call_url = client.call_client_url(ticket["call_client_path"], ticket["ticket"])
        parsed = urlsplit(call_url)
        assert parsed.scheme == "https" and parsed.netloc == "forge.test"
        assert parsed.path == "/admin/__forge/editor/v1/call-client/call-1"
        assert parsed.query == ""
        assert parse_qs(parsed.fragment) == {"ticket": [CALL_TICKET]}
        with pytest.raises(ValueError, match="same-origin"):
            client.call_client_url("https://attacker.test/call", CALL_TICKET)
        with pytest.raises(ValueError, match="Forge call path"):
            client.call_client_url("/unrelated/call-client/call-1", CALL_TICKET)
        with pytest.raises(ValueError, match="Forge call path"):
            client.call_client_url("/__forge/editor/v1/call-client/call-1\n", CALL_TICKET)

        with pytest.raises(ForgeHTTPError, match="Redirects are disabled"):
            client.roles()
        assert client.has_session
        with pytest.raises(ForgeHTTPError) as unauthorized:
            client.members()
        assert unauthorized.value.status_code == 401
        assert not client.has_session

    assert not client.has_session
    assert sum(request.url.host == "attacker.test" for request in seen) == 0


def test_control_plane_rejects_unsafe_credentials_and_attachment_inputs(tmp_path: Path) -> None:
    client = EditorControlPlaneClient(
        "https://forge.test",
        max_attachment_bytes=1024,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    with pytest.raises(ValueError, match="format"):
        client.set_session_token("not-a-session-token" * 3)
    with pytest.raises(ValueError, match="invitation"):
        client.register("bad-token" * 8, "worker", "long enough password", "Worker")
    source = tmp_path / "large.bin"
    source.write_bytes(b"x" * 1025)
    client.set_session_token(SESSION)
    with pytest.raises(ValueError, match="max_attachment_bytes"):
        client.upload_attachment("area-1", source)
    with pytest.raises(ValueError, match="format"):
        client.call_client_url("/__forge/editor/v1/call-client/call-1", "jfc_short")
    client.close()


def test_attachment_paths_reject_source_symlinks_and_replace_destination_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"trusted source")
    source_link = tmp_path / "source-link.txt"
    victim = tmp_path / "victim.txt"
    target_link = tmp_path / "download.txt"
    victim.write_bytes(b"do not overwrite")
    try:
        source_link.symlink_to(source)
        target_link.symlink_to(victim)
    except OSError:
        pytest.skip("this platform does not permit unprivileged symlink creation")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, content=b"safe download")
        return httpx.Response(201, json={"id": "uploaded"})

    with EditorControlPlaneClient(
        "https://forge.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.set_session_token(SESSION)
        with pytest.raises(ValueError, match="non-symlink"):
            client.upload_attachment("area-1", source_link)
        saved = client.download_attachment("attachment-1", target_link)

    assert saved.data == target_link.resolve()
    assert not target_link.is_symlink()
    assert target_link.read_bytes() == b"safe download"
    assert victim.read_bytes() == b"do not overwrite"


def test_async_control_plane_uses_same_security_contract(tmp_path: Path) -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/auth/login"):
                return httpx.Response(200, json={"access_token": SESSION, "profile": {"username": "async-worker"}})
            if request.url.path.endswith("/areas/area-2/attachments"):
                assert b"async file" in request.content
                return httpx.Response(201, json={"id": "async-attachment"})
            if request.url.path.endswith("/attachments/async-attachment"):
                return httpx.Response(200, content=b"async file")
            return httpx.Response(201, json={"id": "message-1"})

        source = tmp_path / "async.txt"
        source.write_bytes(b"async file")
        target = tmp_path / "async-download.txt"
        async with AsyncEditorControlPlaneClient(
            "https://forge.test",
            transport=httpx.MockTransport(handler),
        ) as client:
            authenticated = await client.login("async-worker", "correct horse battery staple")
            assert "access_token" not in authenticated.data
            await client.post_message("area-2", "Hello from async")
            await client.upload_attachment("area-2", source)
            downloaded = await client.download_attachment("async-attachment", target)
            assert downloaded.data == target
            assert target.read_bytes() == b"async file"
            assert all(request.headers.get("Authorization") == f"Bearer {SESSION}" for request in requests[1:])
        assert not client.has_session

    asyncio.run(run())


def test_sync_control_plane_exposes_complete_v050_surface() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith(("/setup/founder", "/auth/register")):
            return httpx.Response(201, json={"access_token": SESSION, "profile": {"is_founder": True}})
        if request.url.path.endswith("/auth/logout") or (request.method == "PUT" and "/members/" in request.url.path):
            return httpx.Response(204)
        return httpx.Response(200, json={"ok": True})

    with EditorControlPlaneClient("https://forge.test", transport=httpx.MockTransport(handler)) as client:
        assert client.setup_status().data["ok"]
        client.setup_founder("S" * 32, "founder", "long secure password", " Founder ")
        client.register(INVITATION, "worker", "another secure password", " Worker ")
        assert client.capabilities().data["ok"]
        assert client.update_profile({"display_name": "Worker"}).data["ok"]
        assert client.projects().data["ok"]
        assert client.create_project("Billing", "billing").data["ok"]
        assert client.documents("Billing").data["ok"]
        assert client.save_document("Billing", "config/40-resources.json", "{}", "a" * 64).data["ok"]
        assert client.validate_project("Billing").data["ok"]
        assert client.roles().data["ok"]
        assert client.create_role({"name": "Reviewer", "rank": 30}).data["ok"]
        assert client.update_role("role-1", {"rank": 31}).data["ok"]
        assert client.members().data["ok"]
        assert client.update_member("user-1", [{"role_id": "role-1", "project": "Billing"}], active=False).status_code == 204
        assert client.create_invitation([{"role_id": "role-1", "project": "Billing"}], expires_hours=2).data["ok"]
        assert client.areas("Billing").data["ok"]
        assert client.create_area({"name": "Private", "visibility": "restricted"}).data["ok"]
        assert client.messages("area-1", limit=12).data["ok"]
        assert client.post_message("area-1", "Release ready", announcement=True).data["ok"]
        assert client.notes("Billing").data["ok"]
        assert client.create_note({"project": "Billing", "body": "Review"}).data["ok"]
        assert client.database_catalog("Billing").data["ok"]
        assert client.database_rows("Billing", "primary", "invoices", limit=12, offset=4).data["ok"]
        assert client.start_call("area-1", mode="audio").data["ok"]
        assert client.call_ticket("call-1").data["ok"]
        assert client.audit(project="Billing", limit=11).data["ok"]
        client.logout()

    assert not client.has_session
    assert any(request.url.params.get("project") == "Billing" for request in requests)
    assert any(b'"kind":"announcement"' in request.content for request in requests)


def test_async_control_plane_exposes_complete_v050_surface() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith(("/setup/founder", "/auth/register")):
                return httpx.Response(201, json={"access_token": SESSION, "profile": {"is_founder": True}})
            if request.url.path.endswith("/auth/logout") or (request.method == "PUT" and "/members/" in request.url.path):
                return httpx.Response(204)
            return httpx.Response(200, json={"ok": True})

        async with AsyncEditorControlPlaneClient("https://forge.test", transport=httpx.MockTransport(handler)) as client:
            assert (await client.setup_status()).data["ok"]
            await client.setup_founder("S" * 32, "founder", "long secure password", "Founder")
            await client.register(INVITATION, "worker", "another secure password", "Worker")
            assert (await client.capabilities()).data["ok"]
            assert (await client.profile()).data["ok"]
            assert (await client.update_profile({"display_name": "Worker"})).data["ok"]
            assert (await client.projects()).data["ok"]
            assert (await client.create_project("Billing", "billing")).data["ok"]
            assert (await client.documents("Billing")).data["ok"]
            assert (await client.document("Billing", "app.json")).data["ok"]
            assert (await client.save_document("Billing", "app.json", "{}", "a" * 64)).data["ok"]
            assert (await client.validate_project("Billing")).data["ok"]
            assert (await client.roles()).data["ok"]
            assert (await client.create_role({"name": "Reviewer"})).data["ok"]
            assert (await client.update_role("role-1", {"rank": 31})).data["ok"]
            assert (await client.members()).data["ok"]
            assert (await client.update_member("user-1", [], active=False)).status_code == 204
            assert (await client.create_invitation([], expires_hours=2)).data["ok"]
            assert (await client.areas("Billing")).data["ok"]
            assert (await client.create_area({"name": "Open"})).data["ok"]
            assert (await client.messages("area-1", limit=12)).data["ok"]
            assert (await client.post_message("area-1", "Hello", announcement=True)).data["ok"]
            assert (await client.notes("Billing")).data["ok"]
            assert (await client.create_note({"body": "Review"})).data["ok"]
            assert (await client.database_catalog("Billing")).data["ok"]
            assert (await client.database_rows("Billing", "primary", "invoices", limit=12, offset=4)).data["ok"]
            assert (await client.attachments("area-1", limit=12)).data["ok"]
            assert (await client.start_call("area-1", mode="audio")).data["ok"]
            assert (await client.call_ticket("call-1")).data["ok"]
            assert (await client.audit(project="Billing", limit=11)).data["ok"]
            await client.logout()

        assert not client.has_session
        assert any(request.url.params.get("offset") == "4" for request in requests)

    asyncio.run(run())


def test_control_plane_rejects_invalid_payloads_and_response_shapes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_attachment_bytes"):
        EditorControlPlaneClient("https://forge.test", max_attachment_bytes=1)

    client = EditorControlPlaneClient(
        "https://forge.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    with pytest.raises(ValueError, match="username"):
        client.login("", "password")
    with pytest.raises(ValueError, match="password"):
        client.login("worker", "bad\0password")
    with pytest.raises(ValueError, match="display_name"):
        client.setup_founder("S" * 32, "worker", "password", "   ")
    with pytest.raises(ValueError, match="ASCII"):
        client.set_session_token("jfe_session_" + "é" * 40)
    with pytest.raises(ForgeHTTPError, match="non-object"):
        client.setup_status()
    client.set_session_token(SESSION)
    client._request = lambda *_args, **_kwargs: ForgeResponse(data={}, status_code=200, request_id=None)  # type: ignore[method-assign]
    with pytest.raises(ForgeHTTPError, match="not binary"):
        client.download_attachment("attachment-1", tmp_path / "target.txt")
    with pytest.raises(ValueError, match="unavailable"):
        client.upload_attachment("area-1", tmp_path / "missing.txt")
    with pytest.raises(ValueError, match="regular"):
        client.upload_attachment("area-1", tmp_path)
    client.close()
