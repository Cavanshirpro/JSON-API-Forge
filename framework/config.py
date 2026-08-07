from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .settings import settings

_ENV_PATTERN = re.compile(r"^\$env:([A-Z0-9_]+)(?::-(.*))?$")


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value)
        if match:
            name, default = match.groups()
            return os.getenv(name, default)
        return value
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value


class DatabaseConfig(BaseModel):
    url: str
    echo: bool = False
    pool_pre_ping: bool = True


class RateLimitConfig(BaseModel):
    enabled: bool = True
    requests: int = 120
    window_seconds: int = 60
    backend: str = "memory"  # memory | redis


class SecurityConfig(BaseModel):
    api_key_header: str = "X-API-Key"
    bootstrap_admin_key: str | None = None
    jwt_enabled: bool = True
    jwt_exp_minutes: int = 60
    allow_query_api_key: bool = False


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
    soft_delete_field: str | None = None
    tenant_field: str | None = None


class CustomEndpointConfig(BaseModel):
    path: str
    method: str = "GET"
    permission: str | None = None
    handler: str
    summary: str | None = None


class AppConfig(BaseModel):
    name: str = "JSON API Forge"
    version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    docs_enabled: bool = True
    audit_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    databases: dict[str, DatabaseConfig]
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    roles: dict[str, RoleConfig] = Field(default_factory=dict)
    resources: list[ResourceConfig] = Field(default_factory=list)
    custom_endpoints: list[CustomEndpointConfig] = Field(default_factory=list)


def load_config(config_dir: Path | None = None) -> AppConfig:
    config_dir = Path(config_dir or settings.config_dir)
    main_file = config_dir / "app.json"
    if not main_file.exists():
        raise RuntimeError(f"Configuration file not found: {main_file}")
    try:
        raw = json.loads(main_file.read_text(encoding="utf-8"))
        raw = _resolve_env(raw)
        return AppConfig.model_validate(raw)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"Invalid configuration in {main_file}: {exc}") from exc
