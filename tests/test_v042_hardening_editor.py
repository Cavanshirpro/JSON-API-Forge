import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from framework.cli import cmd_new
from framework.config import load_config
from framework.editor_api import DocumentWrite, EditorControlPlane, ProjectCreate, register_editor_api
from framework.security import Principal, ensure_credential_delegation
from framework.settings import Settings

EDITOR_TOKEN = "ForgeEditor_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB"


def _write_project(apps: Path, name: str = "Notes") -> Path:
    project = apps / name
    (project / "config").mkdir(parents=True)
    (project / "hooks").mkdir()
    (project / "app.json").write_text(
        json.dumps(
            {
                "slug": "notes",
                "name": "Notes",
                "databases": {"primary": {"url": "sqlite+aiosqlite:///./data/notes.db"}},
                "roles": {"reader": {"permissions": ["notes.read"]}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (project / "config" / "40-resources.json").write_text('{"resources": []}\n', encoding="utf-8")
    return project


def _editor_settings(**values) -> Settings:
    defaults = dict(
        _env_file=None,
        editor_api_enabled=True,
        editor_token=EDITOR_TOKEN,
        editor_require_https=False,
        editor_allowed_ips="",
    )
    defaults.update(values)
    return Settings(**defaults)


def test_legacy_root_folders_are_not_treated_as_projects(tmp_path):
    apps = tmp_path / "app"
    _write_project(apps)
    legacy = apps / "config"
    legacy.mkdir()
    (legacy / "app.json").write_text('{"bootstrap_enabled": false}', encoding="utf-8")
    assert [project.slug for project in load_config(apps).projects] == ["notes"]


def test_cli_new_rejects_path_traversal(tmp_path):
    args = type("Args", (), {"root": str(tmp_path), "name": "../outside", "slug": "safe", "preset": "minimal"})()
    with pytest.raises(SystemExit):
        cmd_new(args)
    assert not (tmp_path.parent / "outside").exists()


def test_delegation_compares_sustained_rate_not_only_request_count(tmp_path):
    project = load_config(_write_project(tmp_path / "app").parent).projects[0]
    parent = Principal(
        kind="api_key",
        subject="parent",
        roles={"reader"},
        permissions={"notes.read"},
        tenant_id=None,
        rate_requests=100,
        rate_window_seconds=60,
        rate_burst=100,
    )
    with pytest.raises(HTTPException, match="sustained"):
        ensure_credential_delegation(
            project,
            parent,
            roles=["reader"],
            permissions=[],
            tenant_id=None,
            rate_requests=99,
            rate_window_seconds=1,
            rate_burst=99,
        )


def test_editor_control_plane_validates_conflicts_and_rolls_back(tmp_path):
    apps = tmp_path / "app"
    project = _write_project(apps)
    control = EditorControlPlane(apps, _editor_settings())
    documents = control.list_documents("Notes")
    assert {item["path"] for item in documents} == {"app.json", "config/40-resources.json"}

    target = project / "config" / "40-resources.json"
    before = target.read_text(encoding="utf-8")
    digest = hashlib.sha256(before.encode()).hexdigest()

    async def run():
        with pytest.raises(HTTPException) as invalid:
            await control.write_document(
                "Notes",
                "config/40-resources.json",
                DocumentWrite(content='{"resources": "not-a-list"}\n', expected_sha256=digest),
            )
        assert invalid.value.status_code == 422
        assert target.read_text(encoding="utf-8") == before

        saved = await control.write_document(
            "Notes",
            "config/40-resources.json",
            DocumentWrite(content='{\n  "resources": []\n}\n', expected_sha256=digest),
        )
        assert saved == hashlib.sha256(b'{\n  "resources": []\n}\n').hexdigest()

        with pytest.raises(HTTPException) as conflict:
            await control.write_document(
                "Notes",
                "config/40-resources.json",
                DocumentWrite(content='{"resources": []}\n', expected_sha256=digest),
            )
        assert conflict.value.status_code == 409

        with pytest.raises(HTTPException):
            await control.write_document("Notes", "../.env", DocumentWrite(content="x", expected_sha256="new"))

    asyncio.run(run())


def test_editor_api_uses_independent_token_and_reports_policy(tmp_path):
    apps = tmp_path / "app"
    _write_project(apps)
    app = FastAPI()
    settings = _editor_settings()
    register_editor_api(app, apps_dir=apps, settings=settings)
    with TestClient(app) as client:
        assert client.get("/__forge/editor/v1/capabilities").status_code == 401
        response = client.get("/__forge/editor/v1/capabilities", headers={"X-Forge-Editor-Token": EDITOR_TOKEN})
        assert response.status_code == 200
        assert response.json()["optimistic_concurrency"] == "sha256"
        assert (
            client.get("/__forge/editor/v1/projects", headers={"X-Forge-Editor-Token": EDITOR_TOKEN}).json()["projects"][0]["slug"]
            == "notes"
        )


def test_editor_project_creation_is_policy_gated(tmp_path):
    apps = tmp_path / "app"
    apps.mkdir()

    async def run():
        blocked = EditorControlPlane(apps, _editor_settings())
        with pytest.raises(HTTPException) as denied:
            await blocked.create_project(ProjectCreate(name="New Project", slug="new-project"))
        assert denied.value.status_code == 403

        enabled = EditorControlPlane(apps, _editor_settings(editor_allow_create_projects=True))
        created = await enabled.create_project(ProjectCreate(name="New Project", slug="new-project"))
        assert created["slug"] == "new-project"
        assert enabled.validate_project("New Project")["valid"] is True

    asyncio.run(run())


def test_editor_rejects_weak_token(tmp_path):
    app = FastAPI()
    with pytest.raises(RuntimeError, match="strong"):
        register_editor_api(app, apps_dir=tmp_path, settings=_editor_settings(editor_token="short"))
