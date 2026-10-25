import json
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from eaa.api.analyses import StatsOut
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
        self.explained: list[uuid.UUID] = []

    def run(self, question: str) -> Analysis:
        analysis = self.answer(question)
        self.explain(analysis)
        return analysis

    def explain(self, analysis: Analysis) -> None:
        from eaa.analysis.explainer import Insight

        self.explained.append(analysis.id)
        analysis.insight = Insight(status="verified", summary="Western Europe leads.")

    def answer(self, question: str) -> Analysis:
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
        self.spent = Decimal(0)

    def spent_today(self) -> Decimal:
        return self.spent

    def stats(self, days: int) -> dict[str, Any]:
        row: dict[str, Any] = dict.fromkeys(StatsOut.model_fields, 0)
        del row["days"]
        return {**row, "analyses": len(self.rows), "latency_p50_ms": None}

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
    assert "not ready" in response.json()["detail"]


def parse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_the_stream_sends_the_answer_then_the_explanation(
    client: TestClient, stub: StubPipeline, store: MemoryStore
) -> None:
    response = client.post("/analyses/stream", json={"question": "Customers by region?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert [name for name, _ in events] == ["answer", "done"]
    answer, done = events[0][1], events[1][1]
    assert answer["insight"] is None and answer["result"]["row_count"] == 2
    assert done["insight"]["summary"] == "Western Europe leads."
    assert uuid.UUID(done["id"]) in store.rows


def test_a_failure_in_the_stream_is_an_error_event(client: TestClient, stub: StubPipeline) -> None:
    def broken(question: str) -> Analysis:
        raise RuntimeError("boom")

    stub.answer = broken  # type: ignore[method-assign]

    events = parse_events(client.post("/analyses/stream", json={"question": "q?x"}).text)

    assert events == [("error", {"detail": "The analysis failed."})]


def test_each_client_gets_a_limited_number_of_analyses(
    stub: StubPipeline, store: MemoryStore
) -> None:
    with make_client(stub, store, analyses_per_client_per_hour=2) as client:
        statuses = [
            client.post("/analyses", json={"question": "Revenue?"}).status_code for _ in range(3)
        ]
        stream = client.post("/analyses/stream", json={"question": "Revenue?"})

    assert statuses == [200, 200, 429]
    assert stream.status_code == 429 and int(stream.headers["retry-after"]) > 0


def test_the_daily_budget_stops_new_analyses(stub: StubPipeline, store: MemoryStore) -> None:
    store.spent = Decimal("5.01")
    with make_client(stub, store, daily_budget_usd=5) as client:
        response = client.post("/analyses", json={"question": "Revenue?"})

    assert response.status_code == 429
    assert "budget" in response.json()["detail"]
    assert stub.questions == []


def test_slots_are_released_after_each_analysis(stub: StubPipeline, store: MemoryStore) -> None:
    with make_client(stub, store, max_concurrent_analyses=1) as client:
        for _ in range(3):
            assert client.post("/analyses/stream", json={"question": "Revenue?"}).status_code == 200
            assert client.post("/analyses", json={"question": "Revenue?"}).status_code == 200


def test_stats_are_served_and_bounded(client: TestClient) -> None:
    client.post("/analyses", json={"question": "Revenue?"})

    response = client.get("/analyses/stats", params={"days": 30})

    assert response.status_code == 200
    assert response.json()["analyses"] == 1 and response.json()["days"] == 30
    assert client.get("/analyses/stats", params={"days": 365}).status_code == 422
