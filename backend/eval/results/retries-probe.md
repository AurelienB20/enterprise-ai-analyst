# Evaluation: retries-probe

- Model `claude-opus-5-5`, effort `medium`, up to 3 proposals per question
- Split `all`: 4 questions (question set v2, semantic model v1)
- Dataset: generator v2, seed 42, scale small
- Commit `176c9aa`, run on 2026-10-25 09:22 UTC

| Metric | Value |
|---|---|
| Accuracy (all questions) | 100.0 % |
| Execution accuracy (answers) | 100.0 % |
| Correct refusals | n/a |
| False refusals | 0.0 % |
| Valid SQL (answered) | 100.0 % |
| Right on the first proposal | 75.0 % |
| Permission violations | 0 |
| Latency p50 | 8.4 s |
| Latency p95 | 19.1 s |
| Cost per question | $0.0191 |
| Cost of the run | $0.08 |

| Category | Accuracy |
|---|---|
| multi_step | 100.0 % |
| trend | 100.0 % |

## Questions

| Question | Split | Result | Attempts | Detail |
|---|---|---|---|---|
| rev_by_month_apr_sep_2026 | test | ok | 1 | rows match |
| lost_customers_2026 | dev | ok | 1 | the first row holds the reference values |
| qoq_growth_2026 | dev | ok | 1 | rows match |
| segments_without_overdue | dev | ok | 2 | rows match |
