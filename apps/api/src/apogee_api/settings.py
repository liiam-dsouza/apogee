from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from APOGEE_* environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_prefix="APOGEE_", env_file=".env", extra="ignore")

    data_dir: Path = Path(".data")
    redis_url: str = "redis://localhost:6379"
    git_sha: str = "dev"
    field_mode: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
