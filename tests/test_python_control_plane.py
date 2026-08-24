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
    ForgeSessionError,
)
from tests.test_v050_editor_collaboration import SETUP_TOKEN, _account_app

SESSION = "jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN"


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
            return httpx.Response(201, json={"invitation": "jfi_one_time_invitation"})
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
                    "ticket": "jfc_one_time_ticket",
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
        assert invitation.data["invitation"] == "jfi_one_time_invitation"

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
        assert parse_qs(parsed.fragment) == {"ticket": ["jfc_one_time_ticket"]}
        with pytest.raises(ValueError, match="same-origin"):
            client.call_client_url("https://attacker.test/call", "jfc_one_time_ticket")

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
    with pytest.raises(ValueError, match="prefix"):
        client.set_session_token("not-a-session-token" * 3)
    with pytest.raises(ValueError, match="invitation"):
        client.register("bad-token" * 8, "worker", "long enough password", "Worker")
    source = tmp_path / "large.bin"
    source.write_bytes(b"x" * 1025)
    client.set_session_token(SESSION)
    with pytest.raises(ValueError, match="max_attachment_bytes"):
        client.upload_attachment("area-1", source)
    client.close()


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


def test_async_control_plane_against_real_forge_app(tmp_path: Path) -> None:
    async def run() -> None:
        app, _settings = _account_app(tmp_path)
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 43000))
        async with app.router.lifespan_context(app):
            async with AsyncEditorControlPlaneClient(
                "http://localhost",
                allow_insecure_http=True,
                transport=transport,
            ) as control:
                setup = await control.setup_founder(
                    SETUP_TOKEN,
                    "sdk-founder",
                    "Granite river orbits seven moons 42!",
                    "SDK Founder",
                )
                assert setup.data["profile"]["is_founder"] is True
                assert "roles.manage" in (await control.capabilities()).data["permission_catalog"]
                area = await control.create_area({"project": "Notes", "name": "SDK project area", "visibility": "open"})
                message = await control.post_message(area.data["id"], "Control-plane integration is online")
                assert message.status_code == 201
                source = tmp_path / "real-upload.txt"
                source.write_text("real app attachment", encoding="utf-8")
                uploaded = await control.upload_attachment(area.data["id"], source)
                listed = await control.attachments(area.data["id"])
                assert listed.data["attachments"][0]["id"] == uploaded.data["id"]
                target = tmp_path / "real-download.txt"
                await control.download_attachment(uploaded.data["id"], target)
                assert target.read_text(encoding="utf-8") == "real app attachment"
                await control.logout()
                assert not control.has_session

    asyncio.run(run())
