"""Evaluate the pipeline on the question set. ``run`` calls the LLM: it costs money.

    uv run python -m eaa.evaluation run --label opus-medium --split all --database test
    uv run python -m eaa.evaluation run --label opus-low --split dev --effort low
    uv run python -m eaa.evaluation compare opus-medium opus-low

Reports go to backend/eval/results/<label>.json and .md. ``--database test`` reads
TEST_READER_DATABASE_URL (eaa_test, loaded by the database tests with seed 42).
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from eaa.config import Effort, Settings, get_settings
from eaa.evaluation.dataset import load_questions
from eaa.evaluation.markdown import render_comparison, render_report
from eaa.evaluation.runner import QuestionScore, report, run_questions
from eaa.semantic.model import load as load_model
from eaa.services import build_pipeline

RESULTS_DIR = Path(__file__).resolve().parents[3] / "eval" / "results"


class _TestDatabase(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    test_reader_database_url: SecretStr | None = None


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _settings(args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {}
    if args.database == "test":
        url = _TestDatabase().test_reader_database_url
        if url is None:
            raise SystemExit("TEST_READER_DATABASE_URL is not set")
        overrides["reader_database_url"] = url
    for option in (
        "model", "effort", "explain_effort", "max_attempts", "input_price", "output_price",
        "cache_price",
    ):  # fmt: skip
        value = getattr(args, option)
        if value is not None:
            key = {
                "model": "llm_model",
                "effort": "llm_effort",
                "explain_effort": "explain_effort",
                "max_attempts": "llm_max_attempts",
                "input_price": "llm_input_price_per_mtok",
                "output_price": "llm_output_price_per_mtok",
                "cache_price": "llm_cache_read_price_per_mtok",
            }[option]
            overrides[key] = value
    return get_settings().model_copy(update=overrides)


def run(args: argparse.Namespace) -> int:
    settings = _settings(args)
    pipeline = build_pipeline(settings)
    question_set = load_questions()
    questions = question_set.select(args.split)
    if args.only:
        questions = tuple(q for q in questions if q.id in args.only)

    def reference(sql: str) -> Any:
        return pipeline.executor.execute(pipeline.validator.validate(sql)).rows

    ((reference_date, _, generator_version, seed, scale),) = reference("SELECT * FROM dataset_info")
    print(f"{len(questions)} questions, {settings.llm_model} at {settings.llm_effort} effort")
    scores = run_questions(questions, pipeline.run, reference, workers=args.workers)
    config = {
        "label": args.label,
        "split": args.split,
        "model": settings.llm_model,
        "effort": settings.llm_effort,
        "explain_effort": settings.explain_effort if settings.explain_results else None,
        "max_attempts": settings.llm_max_attempts,
        "questions_version": question_set.version,
        "semantic_version": load_model().version,
        "dataset": {
            "generator_version": generator_version,
            "seed": seed,
            "scale": scale,
            "reference_date": str(reference_date),
        },
        "commit": _commit(),
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    }
    result = report(config, scores)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # newline="\n": the reports are committed, and Git keeps LF (.gitattributes).
    (RESULTS_DIR / f"{args.label}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown = render_report(result)
    (RESULTS_DIR / f"{args.label}.md").write_text(markdown, encoding="utf-8", newline="\n")
    print(markdown.split("\n## Questions")[0])
    return 0


def _load(label: str) -> dict[str, Any]:
    """One saved run, or several joined with "+" (the dev and test halves of a config)."""
    parts: list[dict[str, Any]] = [
        json.loads((RESULTS_DIR / f"{part}.json").read_text(encoding="utf-8"))
        for part in label.split("+")
    ]
    if len(parts) == 1:
        return parts[0]
    scores = [QuestionScore(**q) for part in parts for q in part["questions"]]
    return report({**parts[0]["config"], "label": label, "split": "all"}, scores)


def compare_runs(args: argparse.Namespace) -> int:
    print(render_comparison([_load(label) for label in args.labels]))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eaa.evaluation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run", help="run the questions (calls the LLM)")
    run_parser.add_argument("--label", required=True)
    run_parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    run_parser.add_argument("--only", nargs="*", help="question ids to run")
    run_parser.add_argument("--database", choices=["test", "dev"], default="test")
    run_parser.add_argument("--workers", type=int, default=4)
    run_parser.add_argument("--model")
    run_parser.add_argument("--effort", choices=get_args(Effort))
    run_parser.add_argument("--explain-effort", choices=get_args(Effort))
    run_parser.add_argument("--max-attempts", type=int)
    run_parser.add_argument("--input-price", type=float)
    run_parser.add_argument("--output-price", type=float)
    run_parser.add_argument("--cache-price", type=float)
    run_parser.set_defaults(handler=run)

    compare_parser = commands.add_parser("compare", help="compare saved runs")
    compare_parser.add_argument("labels", nargs="+", help='labels; "a+b" merges two runs')
    compare_parser.set_defaults(handler=compare_runs)

    args = parser.parse_args(argv)
    handler: Any = args.handler
    return int(handler(args))


if __name__ == "__main__":
    sys.exit(main())
