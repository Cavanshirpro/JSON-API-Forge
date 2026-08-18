from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from dotenv import dotenv_values
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from .config import _load_project_dir
from .doctor import is_weak_secret
from .protection import ip_allowed, request_is_https
from .settings import Settings

log = logging.getLogger("json_api_forge.editor")

EDITOR_PREFIX = "/__forge/editor/v1"
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 ._-]{0,62}[A-Za-z0-9])?$")
_PROJECT_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_RESERVED = frozenset({"config", "data", "hooks", "plugins", "schemas"})


class EditorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentWrite(EditorModel):
    content: str
    expected_sha256: str = Field(min_length=3, max_length=64)


class ProjectCreate(EditorModel):
    name: str
    slug: str


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _allowed_project(settings: Settings, name: str) -> bool:
    configured = set(_csv(settings.editor_allowed_projects))
    return not configured or name in configured


def _project_name(name: str) -> str:
    if not _PROJECT_NAME.fullmatch(name) or name.casefold() in _RESERVED or name in {".", ".."}:
        raise HTTPException(status_code=404, detail="Project not found")
    return name


def _document_path(project_dir: Path, raw: str, *, allow_hooks: bool) -> tuple[Path, str]:
    if not raw or "\\" in raw or "\0" in raw:
        raise HTTPException(status_code=400, detail="Invalid document path")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise HTTPException(status_code=400, detail="Invalid document path")
    normalized = relative.as_posix()
    allowed = normalized == "app.json" or (len(relative.parts) == 2 and relative.parts[0] == "config" and relative.suffix == ".json")
    if allow_hooks:
        allowed = allowed or (
            len(relative.parts) == 2 and relative.parts[0] == "hooks" and relative.suffix == ".py" and not relative.name.startswith(".")
        )
    if not allowed:
        raise HTTPException(status_code=403, detail="Document type is not allowed by the editor policy")
    target = project_dir.joinpath(*relative.parts)
    try:
        target.resolve(strict=False).relative_to(project_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid document path") from exc
    return target, normalized


class EditorControlPlane:
    def __init__(self, apps_dir: Path, settings: Settings):
        self.apps_dir = apps_dir.resolve()
        self.settings = settings
        self._write_lock = asyncio.Lock()

    def _project_dir(self, name: str, *, must_exist: bool = True) -> Path:
        name = _project_name(name)
        if not _allowed_project(self.settings, name):
            raise HTTPException(status_code=404, detail="Project not found")
        project = self.apps_dir / name
        if must_exist and (not project.is_dir() or project.is_symlink()):
            raise HTTPException(status_code=404, detail="Project not found")
        try:
            project.resolve(strict=False).relative_to(self.apps_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return project

    async def authorize(self, request: Request) -> None:
        trusted = _csv(self.settings.editor_trusted_proxy_cidrs)
        if self.settings.editor_require_https and not request_is_https(request, trusted):
            raise HTTPException(status_code=400, detail="HTTPS is required for the editor API")
        if not ip_allowed(request, _csv(self.settings.editor_allowed_ips), [], trusted):
            raise HTTPException(status_code=403, detail="Client IP is not allowed for the editor API")
        supplied = request.headers.get("X-Forge-Editor-Token", "")
        if not supplied or len(supplied) > 512 or not hmac.compare_digest(supplied, self.settings.editor_token):
            raise HTTPException(status_code=401, detail="Editor authentication required")

    def list_projects(self) -> list[dict]:
        if not self.apps_dir.exists():
            return []
        projects = []
        for path in sorted(self.apps_dir.iterdir(), key=lambda value: value.name.casefold()):
            if not path.is_dir() or path.is_symlink() or not _allowed_project(self.settings, path.name):
                continue
            if path.name.casefold() in _RESERVED or path.name.startswith((".", "_")):
                continue
            manifest = path / "app.json"
            if not manifest.is_file():
                continue
            try:
                raw = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            projects.append({"directory": path.name, "name": raw.get("name", path.name), "slug": raw.get("slug", "")})
        return projects

    def list_documents(self, project_name: str) -> list[dict]:
        project = self._project_dir(project_name)
        candidates = [project / "app.json", *sorted((project / "config").glob("*.json"))]
        if self.settings.editor_allow_hooks:
            candidates.extend(sorted((project / "hooks").glob("*.py")))
        documents = []
        for path in candidates:
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            documents.append(
                {
                    "path": path.relative_to(project).as_posix(),
                    "size": len(data),
                    "sha256": _digest(data),
                    "editable": not self.settings.editor_read_only,
                }
            )
        return documents

    def read_document(self, project_name: str, raw_path: str) -> tuple[str, str]:
        project = self._project_dir(project_name)
        path, _ = _document_path(project, raw_path, allow_hooks=self.settings.editor_allow_hooks)
        if not path.is_file() or path.is_symlink():
            raise HTTPException(status_code=404, detail="Document not found")
        data = path.read_bytes()
        if len(data) > self.settings.editor_max_document_bytes:
            raise HTTPException(status_code=413, detail="Document exceeds the editor policy limit")
        try:
            return data.decode("utf-8"), _digest(data)
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=415, detail="Editor documents must be UTF-8 text") from exc

    def validate_project(self, project_name: str) -> dict:
        project = self._project_dir(project_name)
        configured = _load_project_dir(project, dotenv=dotenv_values(self.apps_dir.parent / ".env"))
        return {
            "valid": True,
            "slug": configured.slug,
            "resources": len(configured.resources),
            "operations": len(configured.operations),
            "data_sources": len(configured.data_sources),
        }

    async def write_document(self, project_name: str, raw_path: str, payload: DocumentWrite) -> str:
        if self.settings.editor_read_only:
            raise HTTPException(status_code=403, detail="Editor API is read-only")
        data = payload.content.encode("utf-8")
        if len(data) > self.settings.editor_max_document_bytes:
            raise HTTPException(status_code=413, detail="Document exceeds the editor policy limit")
        project = self._project_dir(project_name)
        target, normalized = _document_path(project, raw_path, allow_hooks=self.settings.editor_allow_hooks)
        if normalized.endswith(".json"):
            try:
                parsed = json.loads(payload.content)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}") from exc
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=422, detail="JSON document root must be an object")

        async with self._write_lock:
            exists = target.is_file() and not target.is_symlink()
            if exists:
                current = target.read_bytes()
                if payload.expected_sha256 != _digest(current):
                    raise HTTPException(status_code=409, detail="Document changed on the server; reload before saving")
            elif payload.expected_sha256 != "new":
                raise HTTPException(status_code=409, detail="Document no longer exists; reload before saving")
            elif target.exists():
                raise HTTPException(status_code=409, detail="Document target is not a regular file")

            with tempfile.TemporaryDirectory(prefix="forge-editor-") as temp_root:
                staged = Path(temp_root) / project.name
                shutil.copytree(project, staged, symlinks=False)
                staged_target, _ = _document_path(staged, normalized, allow_hooks=self.settings.editor_allow_hooks)
                staged_target.parent.mkdir(parents=True, exist_ok=True)
                staged_target.write_bytes(data)
                try:
                    _load_project_dir(staged, dotenv=dotenv_values(self.apps_dir.parent / ".env"))
                except RuntimeError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc

            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        digest = _digest(data)
        log.info("editor write project=%s document=%s client_policy=authorized sha256=%s", project.name, normalized, digest[:12])
        return digest

    async def create_project(self, payload: ProjectCreate) -> dict:
        if self.settings.editor_read_only or not self.settings.editor_allow_create_projects:
            raise HTTPException(status_code=403, detail="Project creation is disabled by the editor policy")
        if not _PROJECT_NAME.fullmatch(payload.name) or payload.name.casefold() in _RESERVED:
            raise HTTPException(status_code=422, detail="Invalid project directory name")
        if not _PROJECT_SLUG.fullmatch(payload.slug):
            raise HTTPException(status_code=422, detail="Invalid project slug")
        if not _allowed_project(self.settings, payload.name):
            raise HTTPException(status_code=403, detail="Project is outside the editor allowlist")
        target = self._project_dir(payload.name, must_exist=False)
        async with self._write_lock:
            if target.exists():
                raise HTTPException(status_code=409, detail="Project already exists")
            self.apps_dir.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=f".{payload.name}.", dir=self.apps_dir))
            try:
                (temporary / "config").mkdir()
                (temporary / "hooks").mkdir()
                (temporary / "app.json").write_text(
                    json.dumps(
                        {
                            "$schema": "../../schemas/manifest.schema.json",
                            "slug": payload.slug,
                            "name": payload.name,
                            "version": "1.0.0",
                            "api_prefix": f"/api/{payload.slug}/v1",
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (temporary / "config" / "10-databases.json").write_text(
                    json.dumps(
                        {
                            "$schema": "../../../schemas/fragment.schema.json",
                            "databases": {
                                "primary": {
                                    "url": f"$env:{payload.slug.upper().replace('-', '_')}_DATABASE_URL:-sqlite+aiosqlite:///./data/{payload.slug}.db"
                                }
                            },
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                _load_project_dir(temporary, dotenv=dotenv_values(self.apps_dir.parent / ".env"))
                os.replace(temporary, target)
            except BaseException:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        log.info("editor project created project=%s slug=%s", payload.name, payload.slug)
        return {"directory": payload.name, "name": payload.name, "slug": payload.slug}


def register_editor_api(app: FastAPI, *, apps_dir: Path, settings: Settings) -> None:
    if not settings.editor_api_enabled:
        return
    if is_weak_secret(settings.editor_token, minimum_length=32):
        raise RuntimeError("EDITOR_API_ENABLED=true requires a strong, independent EDITOR_TOKEN of at least 32 characters")
    if settings.app_env.casefold() == "production" and not settings.editor_require_https:
        raise RuntimeError("Production editor API requires EDITOR_REQUIRE_HTTPS=true")

    control = EditorControlPlane(apps_dir, settings)
    router = APIRouter(prefix=EDITOR_PREFIX, dependencies=[])

    async def authorized(request: Request) -> None:
        await control.authorize(request)

    @router.get("/capabilities")
    async def capabilities(request: Request):
        await authorized(request)
        return {
            "api_version": 1,
            "read_only": settings.editor_read_only,
            "allow_create_projects": settings.editor_allow_create_projects,
            "allow_hooks": settings.editor_allow_hooks,
            "max_document_bytes": settings.editor_max_document_bytes,
            "authentication": "X-Forge-Editor-Token",
            "optimistic_concurrency": "sha256",
        }

    @router.get("/projects")
    async def projects(request: Request):
        await authorized(request)
        return {"projects": control.list_projects()}

    @router.post("/projects", status_code=status.HTTP_201_CREATED)
    async def create_project(payload: ProjectCreate, request: Request):
        await authorized(request)
        return await control.create_project(payload)

    @router.get("/projects/{project_name}/documents")
    async def documents(project_name: str, request: Request):
        await authorized(request)
        return {"documents": control.list_documents(project_name)}

    @router.get("/projects/{project_name}/documents/{document_path:path}")
    async def read_document(project_name: str, document_path: str, request: Request, response: Response):
        await authorized(request)
        content, digest = control.read_document(project_name, document_path)
        response.headers["ETag"] = f'"{digest}"'
        return {"path": document_path, "content": content, "sha256": digest}

    @router.put("/projects/{project_name}/documents/{document_path:path}")
    async def write_document(project_name: str, document_path: str, payload: DocumentWrite, request: Request, response: Response):
        await authorized(request)
        digest = await control.write_document(project_name, document_path, payload)
        response.headers["ETag"] = f'"{digest}"'
        return {"path": document_path, "sha256": digest, "valid": True}

    @router.post("/projects/{project_name}/validate")
    async def validate_project(project_name: str, request: Request):
        await authorized(request)
        try:
            return control.validate_project(project_name)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    app.include_router(router)
    log.warning(
        "Remote editor API enabled prefix=%s allowed_ips=%s read_only=%s hooks=%s",
        EDITOR_PREFIX,
        settings.editor_allowed_ips,
        settings.editor_read_only,
        settings.editor_allow_hooks,
    )
