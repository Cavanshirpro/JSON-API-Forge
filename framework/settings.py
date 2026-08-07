from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str = "development"
    apps_dir: Path = Path("app")
    bootstrap_admin_key: str = ""
    jwt_secret: str = ""
    internal_database_url: str = "sqlite+aiosqlite:///./data/internal-v2.db"
    primary_database_url: str = "sqlite+aiosqlite:///./data/app.db"
    mysql_database_url: str | None = None
    redis_url: str | None = None
    log_level: str = "INFO"
    trust_proxy_headers: bool = False

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore", case_sensitive=False)


settings = Settings()
