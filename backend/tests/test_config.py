import pytest
from pydantic import ValidationError

from eaa.config import Settings
from eaa.db import sqlalchemy_url


def test_defaults_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"


def test_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("API_KEY", "a-long-random-key")

    settings = Settings(_env_file=None)

    assert settings.app_env == "production"
    assert settings.log_format == "json"


def test_an_unknown_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_an_api_key() -> None:
    with pytest.raises(ValidationError, match="API_KEY is required"):
        Settings(_env_file=None, app_env="production")


def test_a_missing_llm_model_fails_clearly() -> None:
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        Settings(_env_file=None).require_llm_model()


def test_a_missing_database_url_fails_clearly() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings(_env_file=None).require_database_url()


def test_the_database_url_is_hidden_in_reprs() -> None:
    settings = Settings(_env_file=None, database_url="postgresql://u:secret@h/db")

    assert "secret" not in repr(settings)
    assert settings.require_database_url() == "postgresql://u:secret@h/db"


@pytest.mark.parametrize("url", ["postgresql://u:p@h:5432/db", "postgres://u:p@h:5432/db"])
def test_libpq_urls_become_sqlalchemy_urls(url: str) -> None:
    assert sqlalchemy_url(url) == "postgresql+psycopg://u:p@h:5432/db"


@pytest.mark.parametrize("url", ["mysql://u:p@h/db", "u:p@h/db"])
def test_other_urls_are_refused(url: str) -> None:
    with pytest.raises(ValueError, match=r"postgresql://"):
        sqlalchemy_url(url)
