"""Load and validate the semantic model (model.toml).

TOML rather than YAML: Python reads it with the standard library, and the file is
written by people, not generated.
"""

import re
import tomllib
from functools import lru_cache
from importlib.resources import files
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

Classification = Literal["public", "internal", "confidential", "pii"]
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Column(_Strict):
    name: str
    type: str
    classification: Classification
    description: str


class View(_Strict):
    name: str
    description: str
    grain: str
    columns: tuple[Column, ...]

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


class Withheld(_Strict):
    source: str
    classification: Classification
    reason: str


class Metric(_Strict):
    name: str
    label: str
    unit: Literal["EUR", "ratio", "count", "days"]
    view: str
    expression: str
    time_column: str | None = None
    rules: tuple[str, ...]


class SemanticModel(_Strict):
    version: int
    reference_date: str
    views: tuple[View, ...]
    withheld: tuple[Withheld, ...]
    metrics: tuple[Metric, ...]

    def view(self, name: str) -> View:
        for view in self.views:
            if view.name == name:
                return view
        raise KeyError(name)

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        for kind, names in (
            ("view", [v.name for v in self.views]),
            ("metric", [m.name for m in self.metrics]),
        ):
            duplicates = {n for n in names if names.count(n) > 1}
            if duplicates:
                raise ValueError(f"duplicate {kind} names: {sorted(duplicates)}")
            invalid = [n for n in names if not _IDENTIFIER.fullmatch(n)]
            if invalid:
                raise ValueError(f"invalid {kind} names: {invalid}")
        view_names = {v.name for v in self.views}
        for view in self.views:
            columns = [c.name for c in view.columns]
            if len(set(columns)) != len(columns):
                raise ValueError(f"duplicate columns in view {view.name}")
            pii = [c.name for c in view.columns if c.classification == "pii"]
            if pii:
                raise ValueError(f"view {view.name} exposes personal data: {pii}")
        for metric in self.metrics:
            if metric.view not in view_names:
                raise ValueError(f"metric {metric.name} uses unknown view {metric.view}")
            view = self.view(metric.view)
            if metric.time_column is not None and view.column(metric.time_column) is None:
                raise ValueError(f"metric {metric.name}: no column {metric.time_column}")
        return self


def parse(text: str) -> SemanticModel:
    return SemanticModel.model_validate(tomllib.loads(text))


@lru_cache
def load() -> SemanticModel:
    return parse(files("eaa.semantic").joinpath("model.toml").read_text(encoding="utf-8"))
