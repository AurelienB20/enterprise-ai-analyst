"""Application settings, read from environment variables and an optional ``.env`` file.

Settings only grow when a milestone needs them: database URLs arrive with 0.1, the
model ID and API key with 0.4. No model ID is hard-coded anywhere.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["text", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: AppEnv = "development"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "text"


@lru_cache
def get_settings() -> Settings:
    return Settings()
