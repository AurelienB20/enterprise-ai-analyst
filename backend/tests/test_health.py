from fastapi.testclient import TestClient

from eaa import __version__
from eaa.config import Settings
from eaa.main import create_app


def test_health_reports_ok_and_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_docs_are_served_outside_production(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_are_hidden_in_production() -> None:
    settings = Settings(_env_file=None, app_env="production", api_key="k")
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200
