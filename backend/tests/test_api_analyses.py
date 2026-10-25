import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from eaa.config import Settings
from eaa.execution.executor import QueryResult, ResultColumn
from eaa.llm.sql_generator import QueryProposal
from eaa.main import create_app
from eaa.orchestrator.pipeline import Analysis, AnalysisPipeline, Attempt
from eaa.services import Services
from eaa.sql_security.validator import ValidatedQuery
from eaa.storage.analyses import AnalysisStore


class StubPipeline:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def run(self, question: str) -> Analysis:
        self.questions.append(question)
        analysis = Analysis(question=question, model="test-model", status="answered")
        analysis.proposal = QueryProposal(
            "SELECT region, created_at FROM customers", ("customers",), "Lists.", ("a",), ("b",)
        )
        analysis.executed = ValidatedQuery(
            "SELECT region, created_at FROM customers", frozenset({"customers"}), frozenset()
        )
        analysis.result = QueryResult(
            columns=(ResultColumn("region", "text"), ResultColumn("amount", "numeric")),
            rows=(("Western Europe", Decimal("10.10")), (None, date(2026, 9, 30))),
            truncated=True,
            duration_ms=1.0,
        )
        analysis.attempts = [Attempt(analysis.executed.sql, "accepted")]
        return analysis


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, dict[str, Any]] = {}

    def record(self, analysis: Analysis, correlation_id: str | None) -> None:
        self.rows[analysis.id] = {"id": analysis.id, "status": analysis.status, "cost_usd": 0}

    def get(self, analysis_id: uuid.UUID) -> dict[str, Any] | None:
        return self.rows.get(analysis_id)


@pytest.fixture
def stub() -> StubPipeline:
    return StubPipeline()


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def make_client(stub: StubPipeline, store: MemoryStore, **settings: Any) -> TestClient:
    services = Services(pipeline=cast(AnalysisPipeline, stub), store=cast(AnalysisStore, store))
    return TestClient(create_app(Settings(_env_file=None, **settings), services))


@pytest.fixture
def client(stub: StubPipeline, store: MemoryStore) -> Iterator[TestClient]:
    with make_client(stub, store) as test_client:
        yield test_client


def test_an_analysis_returns_sql_result_and_trace(
    client: TestClient, stub: StubPipeline, store: MemoryStore
) -> None:
    response = client.post("/analyses", json={"question": "  Customers by region?  "})

    assert response.status_code == 200
    body = response.json()
    assert stub.questions == ["Customers by region?"]
    assert body["status"] == "answered"
    assert body["executed_sql"] == "SELECT region, created_at FROM customers"
    assert body["views"] == ["customers"]
    assert body["assumptions"] == ["a"] and body["ambiguities"] == ["b"]
    # Exact decimals travel as strings, dates as ISO strings.
    assert body["result"]["rows"] == [["Western Europe", "10.10"], [None, "2026-09-30"]]
    assert body["result"]["truncated"] is True
    assert body["attempts"] == [
        {"sql": "SELECT region, created_at FROM customers", "outcome": "accepted", "message": None}
    ]
    assert uuid.UUID(body["id"]) in store.rows


def test_the_trace_can_be_read_back(client: TestClient) -> None:
    analysis_id = client.post("/analyses", json={"question": "Revenue?"}).json()["id"]

    assert client.get(f"/analyses/{analysis_id}").json()["status"] == "answered"
    assert client.get(f"/analyses/{uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize("question", ["", "  ", "ab", "x" * 501])
def test_questions_are_bounded(client: TestClient, question: str) -> None:
    assert client.post("/analyses", json={"question": question}).status_code == 422


def test_the_api_key_is_enforced_when_set(stub: StubPipeline, store: MemoryStore) -> None:
    with make_client(stub, store, api_key="secret-key") as client:
        assert client.post("/analyses", json={"question": "Revenue?"}).status_code == 401
        wrong = client.post(
            "/analyses", json={"question": "Revenue?"}, headers={"X-API-Key": "nope"}
        )
        assert wrong.status_code == 401
        ok = client.post(
            "/analyses", json={"question": "Revenue?"}, headers={"X-API-Key": "secret-key"}
        )
        assert ok.status_code == 200
        assert client.get("/health").status_code == 200


def test_an_unconfigured_service_says_so() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/analyses", json={"question": "Revenue?"})

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
