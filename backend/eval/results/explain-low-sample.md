# Evaluation: explain-low-sample

- Model `claude-opus-5-5`, effort `medium`, up to 3 proposals per question
- Split `all`: 8 questions (question set v2, semantic model v1)
- Dataset: generator v2, seed 42, scale small
- Commit `86f2937`, run on 2026-10-25 10:00 UTC

| Metric | Value |
|---|---|
| Accuracy (all questions) | 100.0 % |
| Execution accuracy (answers) | 100.0 % |
| Correct refusals | n/a |
| False refusals | 0.0 % |
| Valid SQL (answered) | 100.0 % |
| Right on the first proposal | 87.5 % |
| Permission violations | 0 |
| Explanations with every number verified | 87.5 % |
| Latency p50 | 19.8 s |
| Latency p95 | 25.7 s |
| Cost per question | $0.0407 |
| Cost of the run | $0.33 |

| Category | Accuracy |
|---|---|
| anomaly | 100.0 % |
| multi_step | 100.0 % |
| ranking | 100.0 % |
| revenue | 100.0 % |
| trend | 100.0 % |

## Questions

| Question | Split | Result | Attempts | Detail |
|---|---|---|---|---|
| rev_by_quarter_2025 | dev | ok | 1 | rows match |
| rev_by_region_2025 | dev | ok | 1 | rows match |
| ytd_growth | dev | ok | 1 | the first row holds the reference values |
| top5_customers_2025 | dev | ok | 1 | rows match |
| category_drop | dev | ok | 1 | the first row holds the reference values |
| lowest_margin_product | dev | ok | 1 | the first row holds the reference values |
| largest_overdue_customer | dev | ok | 1 | the first row holds the reference values |
| qoq_growth_2026 | dev | ok | 2 | rows match |
