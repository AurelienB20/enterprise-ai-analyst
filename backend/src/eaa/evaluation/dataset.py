"""The evaluation questions (backend/eval/questions.toml)."""

import tomllib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from eaa.evaluation.compare import MatchMode
from eaa.llm.sql_generator import DeclineReason

QUESTIONS_FILE = Path(__file__).resolve().parents[3] / "eval" / "questions.toml"

Split = Literal["dev", "test"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    split: Split
    category: str
    question: str
    expect: Literal["answer", "decline"]
    match: MatchMode = "rows"
    ordered: bool = False
    reference_sql: str | None = None
    accepted_reasons: tuple[DeclineReason, ...] = ()
    anomaly: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.expect == "answer" and not self.reference_sql:
            raise ValueError(f"{self.id}: an answer needs reference_sql")
        if self.expect == "decline" and not self.accepted_reasons:
            raise ValueError(f"{self.id}: a decline needs accepted_reasons")
        return self


class QuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    questions: tuple[Question, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [q.id for q in self.questions]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate question ids: {sorted(duplicates)}")
        return self

    def select(self, split: Split | Literal["all"]) -> tuple[Question, ...]:
        return tuple(q for q in self.questions if split == "all" or q.split == split)


def load_questions(path: Path = QUESTIONS_FILE) -> QuestionSet:
    return QuestionSet.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
