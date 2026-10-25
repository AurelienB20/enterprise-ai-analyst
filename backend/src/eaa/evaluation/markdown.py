"""Human-readable reports and comparisons of evaluation runs."""

from typing import Any


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f} %"


SUMMARY_ROWS = (
    ("Accuracy (all questions)", "accuracy", _pct),
    ("Execution accuracy (answers)", "execution_accuracy", _pct),
    ("Correct refusals", "correct_refusal_rate", _pct),
    ("False refusals", "false_refusal_rate", _pct),
    ("Valid SQL (answered)", "valid_sql_rate", _pct),
    ("Right on the first proposal", "first_try_rate", _pct),
    ("Permission violations", "permission_violations", str),
    ("Latency p50", "latency_p50_ms", lambda v: f"{v / 1000:.1f} s"),
    ("Latency p95", "latency_p95_ms", lambda v: f"{v / 1000:.1f} s"),
    ("Cost per question", "cost_mean_usd", lambda v: f"${v:.4f}"),
    ("Cost of the run", "cost_total_usd", lambda v: f"${v:.2f}"),
)


def render_report(report: dict[str, Any]) -> str:
    config, summary = report["config"], report["summary"]
    lines = [
        f"# Evaluation: {config['label']}",
        "",
        f"- Model `{config['model']}`, effort `{config['effort']}`, "
        f"up to {config['max_attempts']} proposals per question",
        f"- Split `{config['split']}`: {summary['questions']} questions (question set "
        f"v{config['questions_version']}, semantic model v{config['semantic_version']})",
        f"- Dataset: generator v{config['dataset']['generator_version']}, seed "
        f"{config['dataset']['seed']}, scale {config['dataset']['scale']}",
        f"- Commit `{config['commit']}`, run on {config['date']}",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    lines += [f"| {label} | {fmt(summary[key])} |" for label, key, fmt in SUMMARY_ROWS]
    lines += ["", "| Category | Accuracy |", "|---|---|"]
    lines += [f"| {k} | {_pct(v)} |" for k, v in summary["by_category"].items()]
    lines += [
        "",
        "## Questions",
        "",
        "| Question | Split | Result | Attempts | Detail |",
        "|---|---|---|---|---|",
    ]
    for q in report["questions"]:
        mark = "ok" if q["correct"] else "**wrong**"
        lines.append(f"| {q['id']} | {q['split']} | {mark} | {q['attempts']} | {q['detail']} |")
    failures = [q for q in report["questions"] if not q["correct"]]
    if failures:
        lines += ["", "## Failures", ""]
        for q in failures:
            lines += [f"### {q['id']} ({q['status']})", "", q["detail"]]
            if q["error"]:
                lines += ["", f"Message: {q['error']}"]
            if q["executed_sql"]:
                lines += ["", "```sql", q["executed_sql"], "```"]
            lines.append("")
    return "\n".join(lines) + "\n"


def render_comparison(reports: list[dict[str, Any]]) -> str:
    labels = [r["config"]["label"] for r in reports]
    lines = ["| Metric | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for label, key, fmt in SUMMARY_ROWS:
        lines.append(f"| {label} | " + " | ".join(fmt(r["summary"][key]) for r in reports) + " |")
    by_id = [{q["id"]: q for q in r["questions"]} for r in reports]
    common = [i for i in by_id[0] if all(i in b for b in by_id[1:])]
    changed = [i for i in common if len({b[i]["correct"] for b in by_id}) > 1]
    if changed:
        lines += [
            "",
            "| Question that changed | " + " | ".join(labels) + " |",
            "|---|" + "---|" * len(labels),
        ]
        for i in changed:
            lines.append(
                f"| {i} | " + " | ".join("ok" if b[i]["correct"] else "wrong" for b in by_id) + " |"
            )
    return "\n".join(lines) + "\n"
