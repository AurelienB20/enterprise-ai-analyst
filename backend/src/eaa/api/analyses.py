"""POST /analyses runs a question through the pipeline; GET /analyses/{id} returns its
audit trace (without result rows, which are never stored)."""

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StringConstraints

from eaa.observability.logs import correlation_id_var
from eaa.orchestrator.pipeline import Analysis, Outcome, Status
from eaa.services import Services

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AnalysisRequest(BaseModel):
    question: Question


class AttemptOut(BaseModel):
    sql: str
    outcome: Outcome
    message: str | None


class ColumnOut(BaseModel):
    name: str
    type: str
    classification: str | None = Field(
        None, description="public, internal, confidential: from the view columns it uses."
    )
    sources: list[str] = Field(default_factory=list, description="view.column it comes from")


class ResultOut(BaseModel):
    columns: list[ColumnOut]
    # Numbers come as strings when they are exact decimals: no float rounding.
    rows: list[list[Any]]
    row_count: int
    truncated: bool


class UsageOut(BaseModel):
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float


class TimingsOut(BaseModel):
    generation_ms: float
    execution_ms: float
    explanation_ms: float
    total_ms: float


class InsightOut(BaseModel):
    status: str = Field(
        description="verified: every number checked; fallback: commentary withheld; failed."
    )
    summary: str
    key_points: list[str]
    caveats: list[str]
    numbers_checked: int


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    status: Status
    question: str
    model: str
    explanation: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    proposed_sql: str | None = Field(None, description="The SQL the model wrote last.")
    executed_sql: str | None = Field(None, description="The SQL that actually ran.")
    views: list[str] = Field(default_factory=list)
    result: ResultOut | None = None
    insight: InsightOut | None = None
    attempts: list[AttemptOut]
    masked_personal_data: list[str] = Field(
        default_factory=list, description="Kinds of personal data masked in the question."
    )
    declined_reason: str | None = None
    error: str | None = None
    timings: TimingsOut
    usage: UsageOut


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _columns(analysis: Analysis) -> list[ColumnOut]:
    if analysis.result is None:
        return []
    lineage = analysis.lineage if len(analysis.lineage) == len(analysis.result.columns) else ()
    return [
        ColumnOut(
            name=column.name,
            type=column.type_name,
            classification=lineage[i].classification if lineage else None,
            sources=list(lineage[i].sources) if lineage else [],
        )
        for i, column in enumerate(analysis.result.columns)
    ]


def to_response(analysis: Analysis) -> AnalysisResponse:
    proposal, result = analysis.proposal, analysis.result
    return AnalysisResponse(
        id=analysis.id,
        status=analysis.status,
        question=analysis.question,
        model=analysis.model,
        explanation=proposal.explanation if proposal else None,
        assumptions=list(proposal.assumptions) if proposal else [],
        ambiguities=list(proposal.ambiguities) if proposal else [],
        proposed_sql=proposal.sql if proposal else None,
        executed_sql=analysis.executed.sql if analysis.executed else None,
        views=sorted(analysis.executed.views) if analysis.executed else [],
        result=ResultOut(
            columns=_columns(analysis),
            rows=[[json_value(v) for v in row] for row in result.rows],
            row_count=len(result.rows),
            truncated=result.truncated,
        )
        if result
        else None,
        attempts=[
            AttemptOut(sql=a.sql, outcome=a.outcome, message=a.message) for a in analysis.attempts
        ],
        insight=InsightOut(
            status=analysis.insight.status,
            summary=analysis.insight.summary,
            key_points=analysis.insight.key_points,
            caveats=analysis.insight.caveats,
            numbers_checked=analysis.insight.numbers_checked,
        )
        if analysis.insight
        else None,
        masked_personal_data=list(analysis.masked_personal_data),
        declined_reason=analysis.declined.reason if analysis.declined else None,
        error=analysis.declined.message if analysis.declined else analysis.error_message,
        timings=TimingsOut(
            generation_ms=analysis.generation_ms,
            execution_ms=analysis.execution_ms,
            explanation_ms=analysis.explanation_ms,
            total_ms=analysis.total_ms,
        ),
        usage=UsageOut(
            llm_calls=analysis.usage.calls,
            input_tokens=analysis.usage.input_tokens,
            output_tokens=analysis.usage.output_tokens,
            cache_read_tokens=analysis.usage.cache_read_tokens,
            cost_usd=analysis.cost_usd,
        ),
    )


def get_services(request: Request) -> Services:
    services: Services | None = getattr(request.app.state, "services", None)
    if services is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The analysis service is not configured (database URLs, LLM_MODEL).",
        )
    return services


@router.post("")
async def create_analysis(
    body: AnalysisRequest, services: Annotated[Services, Depends(get_services)]
) -> AnalysisResponse:
    analysis = await run_in_threadpool(services.pipeline.run, body.question)
    try:
        await run_in_threadpool(services.store.record, analysis, correlation_id_var.get())
    except Exception:
        # The answer is still valid; a missing audit row is logged loudly, not hidden.
        logger.exception("Could not record analysis %s", analysis.id)
    return to_response(analysis)


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: uuid.UUID, services: Annotated[Services, Depends(get_services)]
) -> dict[str, Any]:
    row = await run_in_threadpool(services.store.get, analysis_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown analysis.")
    return {key: json_value(value) for key, value in row.items()}
