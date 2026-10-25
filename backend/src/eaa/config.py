"""Application settings, read from environment variables and an optional ``.env`` file.

Settings only grow when a milestone needs them. No model ID is hard-coded in the code:
LLM_MODEL must be set (backend/.env.example proposes one).
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["text", "json"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: AppEnv = "development"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "text"

    # When set, every route but /health needs it in the X-API-Key header. Required in
    # production: an open /analyses would let anyone spend the LLM budget.
    api_key: SecretStr | None = None

    # libpq form (postgresql://user:password@host:port/db) of the owner role, which runs
    # migrations and loads the synthetic data. Never used to run generated SQL.
    database_url: SecretStr | None = None
    # The eaa_reader role: the only one that runs generated SQL.
    reader_database_url: SecretStr | None = None
    # The eaa_app role: the API's audit trail (schema app), nothing else.
    app_database_url: SecretStr | None = None
    query_timeout_ms: int = Field(default=5_000, gt=0, le=60_000)
    query_max_rows: int = Field(default=1_000, gt=0, le=100_000)

    # The SDK also reads ANTHROPIC_API_KEY from the process environment; this field lets
    # it come from backend/.env too.
    anthropic_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_effort: Effort = "medium"
    llm_max_tokens: int = Field(default=16_000, gt=0, le=128_000)
    # Proposals the model may make for one question when the validator or the database
    # rejects the previous one.
    llm_max_attempts: int = Field(default=3, ge=1, le=5)
    # USD per million tokens, for the cost estimate of each analysis. Set them to the
    # prices of LLM_MODEL.
    llm_input_price_per_mtok: float = Field(default=4.0, ge=0)
    llm_output_price_per_mtok: float = Field(default=20.0, ge=0)
    llm_cache_read_price_per_mtok: float = Field(default=0.2, ge=0)

    @model_validator(mode="after")
    def _production_needs_an_api_key(self) -> Self:
        if self.app_env == "production" and self.api_key is None:
            raise ValueError("API_KEY is required in production")
        return self

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
        return self.database_url.get_secret_value()

    def require_reader_database_url(self) -> str:
        if self.reader_database_url is None:
            raise RuntimeError("READER_DATABASE_URL is not set (see backend/.env.example)")
        return self.reader_database_url.get_secret_value()

    def require_app_database_url(self) -> str:
        if self.app_database_url is None:
            raise RuntimeError("APP_DATABASE_URL is not set (see backend/.env.example)")
        return self.app_database_url.get_secret_value()

    def require_llm_model(self) -> str:
        if not self.llm_model:
            raise RuntimeError("LLM_MODEL is not set (see backend/.env.example)")
        return self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
