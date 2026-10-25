import pytest
from pydantic import ValidationError

from eaa.config import Settings


def test_defaults_are_safe_for_local_development() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"


def test_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_FORMAT", "json")

    settings = Settings(_env_file=None)

    assert settings.app_env == "production"
    assert settings.log_format == "json"


def test_an_unknown_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
