"""Builds the pipeline and the audit store from the settings."""

from dataclasses import dataclass
from datetime import date

import anthropic

from eaa.config import Settings
from eaa.execution.executor import ExecutionLimits, ReadOnlyExecutor
from eaa.llm.prompt import render_system_prompt
from eaa.llm.sql_generator import ClaudeSQLGenerator, GeneratorConfig
from eaa.orchestrator.pipeline import AnalysisPipeline, Prices
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLValidator
from eaa.storage.analyses import AnalysisStore


@dataclass(frozen=True)
class Services:
    pipeline: AnalysisPipeline
    store: AnalysisStore


def reference_date(executor: ReadOnlyExecutor, validator: SQLValidator) -> date:
    result = executor.execute(validator.validate("SELECT reference_date FROM dataset_info"))
    if not result.rows or not isinstance(result.rows[0][0], date):
        raise RuntimeError("No dataset is loaded (analytics.dataset_info is empty)")
    return result.rows[0][0]


def build_services(settings: Settings) -> Services:
    model = load()
    validator = SQLValidator(model)
    executor = ReadOnlyExecutor(
        settings.require_reader_database_url(),
        ExecutionLimits(timeout_ms=settings.query_timeout_ms, max_rows=settings.query_max_rows),
    )
    api_key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    llm_model = settings.require_llm_model()
    generator = ClaudeSQLGenerator(
        anthropic.Anthropic(api_key=api_key),
        GeneratorConfig(
            model=llm_model, effort=settings.llm_effort, max_tokens=settings.llm_max_tokens
        ),
        render_system_prompt(model, reference_date(executor, validator)),
    )
    pipeline = AnalysisPipeline(
        generator,
        validator,
        executor,
        model=llm_model,
        prices=Prices(
            input=settings.llm_input_price_per_mtok,
            output=settings.llm_output_price_per_mtok,
            cache_read=settings.llm_cache_read_price_per_mtok,
        ),
        max_attempts=settings.llm_max_attempts,
    )
    return Services(pipeline=pipeline, store=AnalysisStore(settings.require_app_database_url()))
