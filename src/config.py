from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    open_library_base_url: str = Field(default="https://openlibrary.org")
    api_timeout_seconds: float = Field(default=10.0)
    database_path: Path = Field(default=Path("data/library.db"))
    cache_ttl_seconds: int = Field(default=86400)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @field_validator("database_path", mode="before")
    @classmethod
    def parse_path(cls, value: str | Path) -> Path:
        path = Path(value)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
