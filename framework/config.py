from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from dotenv import dotenv_values

from .settings import settings

_ENV_PATTERN = re.compile(r"^\$env:([A-Z0-9_]+)(?::-(.*))?$")
_DOTENV_VALUES = dotenv_values(Path(__file__).resolve().parents[1] / ".env")


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value)
        if match:
            name, default = match.groups()
            value = os.getenv(name)
            if value is None:
                value = _DOTENV_VALUES.get(name)
            return value if value is not None else default
        return value
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value


def _deep_merge(base: Any, extra: Any) -> Any:
    """Merge config fragments. Dicts merge recursively, lists append, scalars override."""
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for key, value in extra.items():
            out[key] = _deep_merge(out[key], value) if key in out else value
        return out
    if isinstance(base, list) and isinstance(extra, list):
        return [*base, *extra]
    return extra


class DatabaseConfig(BaseModel):
    url: str
    echo: bool = False
    pool_pre_ping: bool = True
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 1800


class CacheConfig(BaseModel):
    enabled: bool = True
    backend: Literal["memory", "redis", "tiered"] = "memory"
    default_ttl_seconds: int = 30
    stale_ttl_seconds: int = 0
    max_entries: int = 10_000
    key_prefix: str = "forge"
    cache_lists: bool = True
    cache_reads: bool = True


class ResourceCacheConfig(BaseModel):
    enabled: bool | None = None
    ttl_seconds: int | None = None
    list_ttl_seconds: int | None = None
    read_ttl_seconds: int | None = None


class RateLimitConfig(BaseModel):
    enabled: bool = True
    requests: int = 120
    window_seconds: int = 60
    backend: Literal["memory", "redis"] = "memory"
    burst: int | None = None


class ProtectionConfig(BaseModel):
    max_request_body_bytes: int = 8 * 1024 * 1024
    max_concurrent_requests: int = 1000
    request_timeout_seconds: float = 30.0
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])
    gzip_minimum_size: int = 1024
    reject_when_saturated: bool = True
    max_queue_wait_seconds: float = 1.0


class SecurityConfig(BaseModel):
    api_key_header: str = "X-API-Key"
    bootstrap_admin_key: str | None = None
    jwt_enabled: bool = True
    jwt_exp_minutes: int = 60
    allow_query_api_key: bool = False
    require_https: bool = False
    allowed_ips: list[str] = Field(default_factory=list)
    denied_ips: list[str] = Field(default_factory=list)


class RoleConfig(BaseModel):
    permissions: list[str] = Field(default_factory=list)
    inherits: list[str] = Field(default_factory=list)


class ColumnConfig(BaseModel):
    type: str = "string"
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    index: bool = False
    default: Any = None
    max_length: int | None = None


class ResourceConfig(BaseModel):
    database: str = "primary"
    table: str
    path: str
    enabled: bool = True
    auto_create: bool = False
    columns: dict[str, ColumnConfig] = Field(default_factory=dict)
    primary_key: str = "id"
    allowed_actions: list[str] = Field(default_factory=lambda: ["list", "read", "create", "update", "delete"])
    permissions: dict[str, str] = Field(default_factory=dict)
    readable_fields: list[str] | None = None
    writable_fields: list[str] | None = None
    hidden_fields: list[str] = Field(default_factory=list)
    default_limit: int = 50
    max_limit: int = 200
    allowed_filters: list[str] = Field(default_factory=list)
    allowed_sort: list[str] = Field(default_factory=list)
    pagination_mode: Literal["offset", "cursor"] = "offset"
    cursor_field: str | None = None
    soft_delete_field: str | None = None
    tenant_field: str | None = None
    cache: ResourceCacheConfig = Field(default_factory=ResourceCacheConfig)


class CustomEndpointConfig(BaseModel):
    path: str
    method: str = "GET"
    permission: str | None = None
    handler: str
    summary: str | None = None


class MediaConfig(BaseModel):
    enabled: bool = False
    backend: Literal["local", "s3"] = "local"
    local_directory: str = "./data/media"
    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_mime_types: list[str] = Field(default_factory=lambda: [
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "video/mp4", "audio/mpeg", "audio/ogg", "application/pdf",
    ])
    public: bool = False
    upload_permission: str = "media.upload"
    read_permission: str = "media.read"
    delete_permission: str = "media.delete"
    deduplicate: bool = True


class MessagingPackConfig(BaseModel):
    enabled: bool = False
    table_prefix: str = "msg_"
    database: str = "primary"
    tenant_field: str | None = None


class SocialPackConfig(BaseModel):
    enabled: bool = False
    table_prefix: str = "social_"
    database: str = "primary"
    tenant_field: str | None = None


class GamingPackConfig(BaseModel):
    enabled: bool = False
    table_prefix: str = "game_"
    database: str = "primary"
    tenant_field: str | None = None


class FeaturePacksConfig(BaseModel):
    messaging: MessagingPackConfig = Field(default_factory=MessagingPackConfig)
    social: SocialPackConfig = Field(default_factory=SocialPackConfig)
    gaming: GamingPackConfig = Field(default_factory=GamingPackConfig)


class ProjectConfig(BaseModel):
    slug: str
    name: str
    version: str = "0.2.0"
    enabled: bool = True
    api_prefix: str | None = None
    docs_enabled: bool = True
    audit_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    databases: dict[str, DatabaseConfig]
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    protection: ProtectionConfig = Field(default_factory=ProtectionConfig)
    roles: dict[str, RoleConfig] = Field(default_factory=dict)
    resources: list[ResourceConfig] = Field(default_factory=list)
    custom_endpoints: list[CustomEndpointConfig] = Field(default_factory=list)
    media: MediaConfig = Field(default_factory=MediaConfig)
    features: FeaturePacksConfig = Field(default_factory=FeaturePacksConfig)

    @model_validator(mode="after")
    def finalize_prefix(self):
        if self.api_prefix is None:
            self.api_prefix = f"/api/{self.slug}/v1"
        if not self.api_prefix.startswith("/"):
            self.api_prefix = "/" + self.api_prefix
        return self


class ForgeConfig(BaseModel):
    name: str = "JSON API Forge"
    version: str = "0.2.0"
    projects: list[ProjectConfig]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def _load_project_dir(project_dir: Path) -> ProjectConfig:
    manifest = project_dir / "app.json"
    if not manifest.exists():
        manifest = project_dir / "manifest.json"
    if not manifest.exists():
        raise RuntimeError(f"Project {project_dir.name!r} has no app.json or manifest.json")

    raw: dict[str, Any] = _load_json(manifest)
    config_dir = project_dir / "config"
    if config_dir.exists():
        for fragment in sorted(config_dir.glob("*.json")):
            raw = _deep_merge(raw, _load_json(fragment))

    raw.setdefault("slug", project_dir.name.lower())
    raw.setdefault("name", project_dir.name)
    raw = _resolve_env(raw)
    try:
        return ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid project configuration in {project_dir}: {exc}") from exc


def load_config(apps_dir: Path | None = None) -> ForgeConfig:
    apps_dir = Path(apps_dir or settings.apps_dir)
    if not apps_dir.exists():
        raise RuntimeError(f"Applications directory not found: {apps_dir}")

    projects: list[ProjectConfig] = []
    for project_dir in sorted(p for p in apps_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        if not ((project_dir / "app.json").exists() or (project_dir / "manifest.json").exists()):
            continue
        project = _load_project_dir(project_dir)
        if project.enabled:
            projects.append(project)

    if not projects:
        raise RuntimeError(f"No enabled projects found under {apps_dir}")

    slugs = [p.slug for p in projects]
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("Project slugs must be unique")
    prefixes = [p.api_prefix for p in projects]
    if len(prefixes) != len(set(prefixes)):
        raise RuntimeError("Project api_prefix values must be unique")

    return ForgeConfig(projects=projects)
