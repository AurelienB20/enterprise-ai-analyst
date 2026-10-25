from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from eaa.config import Settings
from eaa.main import create_app


@pytest.fixture
def settings() -> Settings:
    # Explicit values, so a developer's .env never changes what the tests see.
    return Settings(_env_file=None, app_env="test", log_level="INFO", log_format="text")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
