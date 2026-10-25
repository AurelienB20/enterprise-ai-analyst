"""Application settings, read from environment variables and an optional ``.env`` file.

Settings only grow when a milestone needs them: the model ID and API key arrive with
0.4. No model ID is hard-coded anywhere.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["text", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: AppEnv = "development"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "text"

    # libpq form (postgresql://user:password@host:port/db) of the owner role, which runs
    # migrations and loads the synthetic data. Never used to run generated SQL.
    database_url: SecretStr | None = None
    # The eaa_reader role: the only one that runs generated SQL.
    reader_database_url: SecretStr | None = None
    query_timeout_ms: int = Field(default=5_000, gt=0, le=60_000)
    query_max_rows: int = Field(default=1_000, gt=0, le=100_000)

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
        return self.database_url.get_secret_value()

    def require_reader_database_url(self) -> str:
        if self.reader_database_url is None:
            raise RuntimeError("READER_DATABASE_URL is not set (see backend/.env.example)")
        return self.reader_database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
