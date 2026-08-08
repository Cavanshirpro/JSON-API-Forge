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
    """Load process settings relative to a deployment root.

    Installed wheels must not accidentally search for `.env` beside site-packages.
    The default root is the current working directory; CLI commands may pass an
    explicit project root.
    """

    env_file = Path(root).resolve() / ".env" if root is not None else Path.cwd() / ".env"
    class RootSettings(Settings):
        model_config = SettingsConfigDict(env_file=env_file, extra="ignore", case_sensitive=False)
    return RootSettings(**overrides)


settings = load_settings()
