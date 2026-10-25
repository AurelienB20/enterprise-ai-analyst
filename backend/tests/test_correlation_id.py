import json
import logging

import pytest
from fastapi.testclient import TestClient

from eaa.api.middleware import resolve_request_id
from eaa.observability.logs import CorrelationIdFilter, JsonFormatter, correlation_id_var


def test_a_request_id_is_generated_when_none_is_sent(client: TestClient) -> None:
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]

    assert len(first) == 32
    assert first != second


def test_a_well_formed_client_request_id_is_kept(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "front-42_abc"})

    assert response.headers["x-request-id"] == "front-42_abc"


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "a" * 65,
        "id with spaces",
        "fake\nERROR forged log line",
        "../../etc",
        "id;DROP TABLE customers",
    ],
)
def test_a_malformed_request_id_is_replaced(candidate: str) -> None:
    resolved = resolve_request_id(candidate)

    assert resolved != candidate
    assert len(resolved) == 32


def test_the_request_log_carries_the_id_but_not_the_query_string(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="eaa.api.middleware"):
        client.get("/health?question=secret-value", headers={"X-Request-ID": "req-1"})

    (record,) = [r for r in caplog.records if r.name == "eaa.api.middleware"]
    assert record.getMessage() == "GET /health -> 200"
    assert record.__dict__["correlation_id"] == "req-1"
    assert "secret-value" not in record.getMessage()


def test_the_correlation_id_is_reset_after_the_request(client: TestClient) -> None:
    client.get("/health", headers={"X-Request-ID": "req-2"})

    assert correlation_id_var.get() is None


def test_json_logs_hold_one_object_with_the_id_and_extra_fields() -> None:
    record = logging.makeLogRecord(
        {"name": "eaa.test", "levelname": "INFO", "msg": "done", "duration_ms": 12.5}
    )
    token = correlation_id_var.set("req-3")
    try:
        CorrelationIdFilter().filter(record)
    finally:
        correlation_id_var.reset(token)

    entry = json.loads(JsonFormatter().format(record))

    assert entry["message"] == "done"
    assert entry["correlation_id"] == "req-3"
    assert entry["duration_ms"] == 12.5
