from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str = "development"
    apps_dir: Path = Path("app")
    bootstrap_admin_key: str = ""
    jwt_secret: str = ""
    operator_token: str = ""

    # The remote editor control plane is deliberately disabled by default. It
    # has an independent credential and network policy from application API
    # keys so an editor token cannot be used as an application credential.
    editor_api_enabled: bool = False
    editor_token: str = ""
    editor_require_https: bool = True
    editor_allowed_ips: str = "127.0.0.1/32,::1/128"
    editor_trusted_proxy_cidrs: str = ""
    editor_read_only: bool = False
    editor_allow_create_projects: bool = False
    editor_allow_hooks: bool = False
    editor_allow_graphs: bool = False
    editor_allowed_projects: str = ""
    editor_max_document_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=16 * 1024 * 1024)

    internal_database_url: str = "sqlite+aiosqlite:///./data/internal-v4.db"
    internal_pool_pre_ping: bool = True
    internal_pool_size: int = Field(default=10, ge=1)
    internal_max_overflow: int = Field(default=20, ge=0)
    internal_pool_timeout: int = Field(default=30, ge=1)
    internal_pool_recycle: int = Field(default=1800, ge=-1)
    internal_schema_mode: str = "create"

    primary_database_url: str = "sqlite+aiosqlite:///./data/app.db"
    mysql_database_url: str | None = None
    redis_url: str | None = None

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=Path.cwd() / ".env",
        extra="ignore",
        case_sensitive=False,
    )


def load_settings(*, root: Path | str | None = None, **overrides: Any) -> Settings:
    """Load process settings relative to a deployment root."""
    env_file = Path(root).resolve() / ".env" if root is not None else Path.cwd() / ".env"

    class RootSettings(Settings):
        model_config = SettingsConfigDict(env_file=env_file, extra="ignore", case_sensitive=False)

    return RootSettings(**overrides)


settings = load_settings()
