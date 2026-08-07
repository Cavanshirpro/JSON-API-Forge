from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError, model_validator

from .settings import settings

_ENV_PATTERN = re.compile(r"^\$env:([A-Z0-9_]+)(?::-(.*))?$")
_DOTENV_VALUES = dotenv_values(Path(__file__).resolve().parents[1] / ".env")


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value)
        if match:
            name, default = match.groups()
            resolved = os.getenv(name)
            if resolved is None:
                resolved = _DOTENV_VALUES.get(name)
            return resolved if resolved is not None else default
        return value
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value


def _deep_merge(base: Any, extra: Any) -> Any:
    """Merge project fragments: dicts recurse, lists append, later scalars override."""
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
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    pool_timeout: int = Field(default=30, ge=1)
    pool_recycle: int = Field(default=1800, ge=-1)
    isolation_level: str | None = None


class CacheConfig(BaseModel):
    enabled: bool = True
    backend: Literal["memory", "redis", "tiered"] = "memory"
    default_ttl_seconds: int = Field(default=30, ge=1)
    stale_ttl_seconds: int = Field(default=0, ge=0)
    max_entries: int = Field(default=10_000, ge=100)
    key_prefix: str = "forge"
    cache_lists: bool = True
    cache_reads: bool = True
    fail_open: bool = True


class ResourceCacheConfig(BaseModel):
    enabled: bool | None = None
    ttl_seconds: int | None = Field(default=None, ge=1)
    list_ttl_seconds: int | None = Field(default=None, ge=1)
    read_ttl_seconds: int | None = Field(default=None, ge=1)
    stale_ttl_seconds: int | None = Field(default=None, ge=0)


class RateLimitConfig(BaseModel):
    enabled: bool = True
    requests: int = Field(default=120, ge=1)
    window_seconds: int = Field(default=60, ge=1)
    backend: Literal["memory", "redis"] = "memory"
    burst: int | None = Field(default=None, ge=1)
    fail_open: bool = False


class ProtectionConfig(BaseModel):
    max_request_body_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    max_concurrent_requests: int = Field(default=1000, ge=1)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])
    gzip_minimum_size: int = Field(default=1024, ge=0)
    reject_when_saturated: bool = True
    max_queue_wait_seconds: float = Field(default=1.0, ge=0)


class SecurityConfig(BaseModel):
    api_key_header: str = "X-API-Key"
    bootstrap_admin_key: str | None = None
    jwt_enabled: bool = True
    jwt_provider: Literal["local_hs256", "jwks"] = "local_hs256"
    jwt_exp_minutes: int = Field(default=60, ge=1)
    jwt_jwks_url: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | list[str] | None = None
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256", "EdDSA"])
    jwt_subject_claim: str = "sub"
    jwt_roles_claim: str = "roles"
    jwt_permissions_claim: str = "permissions"
    jwt_tenant_claim: str = "tenant_id"
    jwt_project_claim: str = "project"
    jwks_cache_ttl_seconds: int = Field(default=600, ge=30)
    jwks_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    allow_query_api_key: bool = False
    allow_websocket_query_api_key: bool = True
    require_https: bool = False
    allowed_ips: list[str] = Field(default_factory=list)
    denied_ips: list[str] = Field(default_factory=list)
    idempotency_header: str = "Idempotency-Key"
    idempotency_pending_ttl_seconds: int = Field(default=300, ge=30, le=86400)

    @model_validator(mode="after")
    def validate_jwt_provider(self):
        if self.jwt_enabled and self.jwt_provider == "jwks" and not self.jwt_jwks_url:
            raise ValueError("security.jwt_jwks_url is required when jwt_provider='jwks'")
        return self


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
    max_length: int | None = Field(default=None, ge=1)


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
    default_limit: int = Field(default=50, ge=1)
    max_limit: int = Field(default=200, ge=1)
    allowed_filters: list[str] = Field(default_factory=list)
    filter_operators: list[Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "like", "ilike", "isnull"]] = Field(default_factory=lambda: ["eq"])
    search_fields: list[str] = Field(default_factory=list)
    allowed_sort: list[str] = Field(default_factory=list)
    pagination_mode: Literal["offset", "cursor"] = "offset"
    cursor_field: str | None = None
    soft_delete_field: str | None = None
    tenant_field: str | None = None
    cache: ResourceCacheConfig = Field(default_factory=ResourceCacheConfig)
    create_schema: dict[str, Any] | None = None
    update_schema: dict[str, Any] | None = None
    batch_enabled: bool = False
    max_batch_size: int = Field(default=100, ge=1, le=5000)
    count_enabled: bool = True
    dependencies: list[str] = Field(default_factory=list)


class MongoDatabaseConfig(BaseModel):
    uri: str
    database: str
    max_pool_size: int = Field(default=100, ge=1)
    min_pool_size: int = Field(default=0, ge=0)
    server_selection_timeout_ms: int = Field(default=5000, ge=100)


class MongoResourceConfig(BaseModel):
    database: str = "primary"
    collection: str
    path: str
    enabled: bool = True
    allowed_actions: list[str] = Field(default_factory=lambda: ["list", "read", "create", "update", "delete"])
    permissions: dict[str, str] = Field(default_factory=dict)
    writable_fields: list[str] | None = None
    hidden_fields: list[str] = Field(default_factory=list)
    allowed_filters: list[str] = Field(default_factory=list)
    filter_operators: list[Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]] = Field(default_factory=lambda: ["eq"])
    allowed_sort: list[str] = Field(default_factory=list)
    default_limit: int = Field(default=50, ge=1)
    max_limit: int = Field(default=200, ge=1)
    tenant_field: str | None = None
    soft_delete_field: str | None = None
    cache: ResourceCacheConfig = Field(default_factory=ResourceCacheConfig)
    create_schema: dict[str, Any] | None = None
    update_schema: dict[str, Any] | None = None
    dependencies: list[str] = Field(default_factory=list)


class DependencySpec(BaseModel):
    name: str
    callable: str
    use_cache: bool = True


class RequestParameterSpec(BaseModel):
    name: str
    location: Literal["query", "header", "cookie", "path"] = "query"
    type: Literal["string", "integer", "number", "boolean"] = "string"
    required: bool = False
    default: Any = None
    description: str | None = None
    enum: list[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    pattern: str | None = None


class ResponseSpec(BaseModel):
    kind: Literal["json", "text", "html", "redirect", "stream", "file", "empty"] = "json"
    media_type: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    filename: str | None = None
    status_code: int | None = None


class CustomEndpointConfig(BaseModel):
    path: str
    method: str = "GET"
    permission: str | None = None
    handler: str
    summary: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False
    include_in_schema: bool = True
    input_schema: dict[str, Any] | None = None
    input_mode: Literal["json", "form", "text", "bytes", "none"] = "json"
    parameters: list[RequestParameterSpec] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    background_hooks: list[str] = Field(default_factory=list)
    response: ResponseSpec = Field(default_factory=ResponseSpec)
    openapi_extra: dict[str, Any] | None = None


class SQLStatementConfig(BaseModel):
    sql: str
    mode: Literal["execute", "fetch_one", "fetch_all", "scalar"] = "execute"
    params: dict[str, Any] = Field(default_factory=dict)
    result_name: str | None = None
    max_rows: int = Field(default=1000, ge=1, le=100_000)
    require_rowcount_min: int | None = Field(default=None, ge=0)
    require_rowcount_max: int | None = Field(default=None, ge=0)


class OperationCacheConfig(BaseModel):
    enabled: bool = False
    ttl_seconds: int = Field(default=15, ge=1)
    stale_ttl_seconds: int | None = Field(default=None, ge=0)
    vary_by_principal: bool = True


class OperationConfig(BaseModel):
    name: str
    path: str | None = None
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    database: str = "primary"
    permission: str | None = None
    transaction: bool = True
    input_schema: dict[str, Any] | None = None
    parameters: list[RequestParameterSpec] = Field(default_factory=list)
    statements: list[SQLStatementConfig] = Field(default_factory=list)
    allow_ddl: bool = False
    idempotency: bool = False
    cache: OperationCacheConfig = Field(default_factory=OperationCacheConfig)
    invalidate_resources: list[str] = Field(default_factory=list)
    invalidate_operations: list[str] = Field(default_factory=list)
    summary: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    deprecated: bool = False
    background_hooks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def finalize_path(self):
        if self.path is None:
            self.path = f"rpc/{self.name}"
        if not self.statements:
            raise ValueError("operation requires at least one SQL statement")
        return self


class DataSourceConfig(BaseModel):
    name: str
    enabled: bool = True
    path: str | None = None
    type: Literal["json_file", "yaml_file", "csv_file", "static", "http"]
    permission: str | None = None
    read_permission: str | None = None
    write_permission: str | None = None
    parameters: list[RequestParameterSpec] = Field(default_factory=list)
    file: str | None = None
    data: Any = None
    url: str | None = None
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=10.0, gt=0)
    retries: int = Field(default=2, ge=0, le=10)
    writable: bool = False
    file_lock_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    id_field: str = "id"
    max_items: int = Field(default=10_000, ge=1)
    cache_ttl_seconds: int = Field(default=15, ge=0)
    stale_ttl_seconds: int | None = Field(default=None, ge=0)
    forward_query: bool = True
    forward_body: bool = True
    dependencies: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def finalize(self):
        if self.path is None:
            self.path = f"data/{self.name}"
        if self.type in {"json_file", "yaml_file", "csv_file"} and not self.file:
            raise ValueError(f"{self.type} data source requires file")
        if self.type == "http" and not self.url:
            raise ValueError("http data source requires url")
        return self


class EventChannelConfig(BaseModel):
    name: str
    path: str | None = None
    publish_permission: str | None = None
    subscribe_permission: str | None = None
    websocket_enabled: bool = True
    sse_enabled: bool = True
    max_message_bytes: int = Field(default=64 * 1024, ge=128)
    queue_size: int = Field(default=256, ge=1, le=10000)
    heartbeat_seconds: int = Field(default=15, ge=1)

    @model_validator(mode="after")
    def finalize(self):
        if self.path is None:
            self.path = f"events/{self.name}"
        return self


class WebhookDocConfig(BaseModel):
    name: str
    method: Literal["POST", "PUT", "PATCH"] = "POST"
    summary: str | None = None
    description: str | None = None
    payload_schema: dict[str, Any] | None = None


class ObservabilityConfig(BaseModel):
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"


class RealtimeConfig(BaseModel):
    backend: Literal["memory", "redis"] = "memory"
    redis_prefix: str = "forge:events"


class MediaConfig(BaseModel):
    enabled: bool = False
    backend: Literal["local", "s3"] = "local"
    local_directory: str = "./data/media"
    max_upload_bytes: int = 25 * 1024 * 1024
    max_batch_files: int = Field(default=8, ge=1, le=100)
    max_owner_bytes: int | None = Field(default=None, ge=1)
    allowed_mime_types: list[str] = Field(default_factory=lambda: [
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "video/mp4", "audio/mpeg", "audio/ogg", "application/pdf",
    ])
    allowed_extensions: list[str] = Field(default_factory=list)
    public: bool = False
    upload_permission: str = "media.upload"
    read_permission: str = "media.read"
    delete_permission: str = "media.delete"
    admin_permission: str = "media.admin"
    owner_delete_only: bool = False
    deduplicate: bool = True
    signed_urls_enabled: bool = True
    signed_url_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    post_upload_hooks: list[str] = Field(default_factory=list)


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
    version: str = "0.3.0"
    enabled: bool = True
    api_prefix: str | None = None
    docs_enabled: bool = True
    audit_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    databases: dict[str, DatabaseConfig]
    mongo_databases: dict[str, MongoDatabaseConfig] = Field(default_factory=dict)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    protection: ProtectionConfig = Field(default_factory=ProtectionConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    realtime: RealtimeConfig = Field(default_factory=RealtimeConfig)
    roles: dict[str, RoleConfig] = Field(default_factory=dict)
    resources: list[ResourceConfig] = Field(default_factory=list)
    mongo_resources: list[MongoResourceConfig] = Field(default_factory=list)
    operations: list[OperationConfig] = Field(default_factory=list)
    data_sources: list[DataSourceConfig] = Field(default_factory=list)
    dependencies: list[DependencySpec] = Field(default_factory=list)
    custom_endpoints: list[CustomEndpointConfig] = Field(default_factory=list)
    event_channels: list[EventChannelConfig] = Field(default_factory=list)
    webhook_docs: list[WebhookDocConfig] = Field(default_factory=list)
    media: MediaConfig = Field(default_factory=MediaConfig)
    features: FeaturePacksConfig = Field(default_factory=FeaturePacksConfig)
    project_dir: str = Field(default="", exclude=True)

    @model_validator(mode="after")
    def finalize_prefix(self):
        if self.api_prefix is None:
            self.api_prefix = f"/api/{self.slug}/v1"
        if not self.api_prefix.startswith("/"):
            self.api_prefix = "/" + self.api_prefix
        return self


class ForgeConfig(BaseModel):
    name: str = "JSON API Forge"
    version: str = "0.3.0"
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
    raw["project_dir"] = str(project_dir.resolve())
    raw = _resolve_env(raw)
    try:
        return ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid project configuration in {project_dir}: {exc}") from exc


def load_config(apps_dir: Path | None = None) -> ForgeConfig:
    apps_dir = Path(apps_dir or settings.apps_dir)
    if not apps_dir.exists():
        raise RuntimeError(f"Apps directory does not exist: {apps_dir}")
    projects: list[ProjectConfig] = []
    for project_dir in sorted(p for p in apps_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        manifest = project_dir / "app.json"
        fallback = project_dir / "manifest.json"
        if manifest.exists() or fallback.exists():
            project = _load_project_dir(project_dir)
            if project.enabled:
                projects.append(project)
    if not projects:
        raise RuntimeError(f"No enabled projects found below {apps_dir}")
    slugs = [p.slug for p in projects]
    if len(slugs) != len(set(slugs)):
        raise RuntimeError("Project slugs must be unique")
    prefixes = [p.api_prefix for p in projects]
    if len(prefixes) != len(set(prefixes)):
        raise RuntimeError("Project api_prefix values must be unique")
    return ForgeConfig(projects=projects)
