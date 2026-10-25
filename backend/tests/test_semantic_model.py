import re
import tomllib
from importlib.resources import files
from typing import Any

import pytest
from pydantic import ValidationError

from eaa.semantic.model import SemanticModel, load, parse

SQL_WORDS = {
    "sum", "avg", "count", "distinct", "nullif", "filter", "where", "case", "when",
    "then", "else", "end", "and", "or", "not", "is", "null",
}  # fmt: skip


def raw_model() -> dict[str, Any]:
    text = files("eaa.semantic").joinpath("model.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def test_the_model_loads() -> None:
    model = load()

    assert model.version >= 1
    assert len(model.views) == 10
    assert {m.name for m in model.metrics} >= {
        "net_revenue",
        "gross_margin",
        "gross_margin_rate",
        "average_order_value",
        "active_customers",
        "overdue_amount",
        "late_delivery_rate",
    }


def test_no_view_exposes_personal_data() -> None:
    model = load()

    assert all(c.classification != "pii" for v in model.views for c in v.columns)
    assert any(w.source == "sales.customer_contacts" for w in model.withheld)
    names = {c.name for v in model.views for c in v.columns}
    assert not names & {"email", "phone", "first_name", "last_name"}


def test_every_identifier_in_a_metric_is_a_column_of_its_view() -> None:
    model = load()
    for metric in model.metrics:
        expression = re.sub(r"'[^']*'", "", metric.expression)  # drop string literals
        identifiers = set(re.findall(r"[a-z_][a-z0-9_]*", expression.lower()))
        unknown = {
            i
            for i in identifiers - SQL_WORDS
            if model.view(metric.view).column(i) is None and not i.isdigit()
        }
        assert not unknown, f"{metric.name}: {unknown}"


def test_every_metric_states_its_rules() -> None:
    assert all(metric.rules for metric in load().metrics)


def test_a_pii_column_in_a_view_is_rejected() -> None:
    data = raw_model()
    data["views"][1]["columns"].append(
        {"name": "email", "type": "text", "classification": "pii", "description": "x"}
    )

    with pytest.raises(ValidationError, match="personal data"):
        SemanticModel.model_validate(data)


def test_a_metric_on_an_unknown_view_is_rejected() -> None:
    data = raw_model()
    data["metrics"][0]["view"] = "sales"

    with pytest.raises(ValidationError, match="unknown view"):
        SemanticModel.model_validate(data)


def test_duplicate_names_and_unknown_fields_are_rejected() -> None:
    data = raw_model()
    data["metrics"].append(data["metrics"][0])
    with pytest.raises(ValidationError, match="duplicate metric"):
        SemanticModel.model_validate(data)

    with pytest.raises(ValidationError, match="Extra inputs"):
        parse('version = 1\nreference_date = "x"\nviews = []\nwithheld = []\nmetrics = []\nx = 1')
