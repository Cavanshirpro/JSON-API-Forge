from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    config_dir: Path = Path("app/config")
    bootstrap_admin_key: str = ""
    jwt_secret: str = ""
    internal_database_url: str = "sqlite+aiosqlite:///./data/internal.db"
    primary_database_url: str = "sqlite+aiosqlite:///./data/app.db"
    mysql_database_url: str | None = None
    redis_url: str | None = None
    log_level: str = "INFO"
    trust_proxy_headers: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


settings = Settings()
