# Evaluation: hard-opus-low

- Model `claude-opus-5-5`, effort `low`, up to 3 proposals per question
- Split `all`: 12 questions (question set v2, semantic model v1)
- Dataset: generator v2, seed 42, scale small
- Commit `176c9aa`, run on 2026-10-25 09:20 UTC

| Metric | Value |
|---|---|
| Accuracy (all questions) | 100.0 % |
| Execution accuracy (answers) | 100.0 % |
| Correct refusals | n/a |
| False refusals | 0.0 % |
| Valid SQL (answered) | 100.0 % |
| Right on the first proposal | 91.7 % |
| Permission violations | 0 |
| Latency p50 | 6.2 s |
| Latency p95 | 9.5 s |
| Cost per question | $0.0135 |
| Cost of the run | $0.16 |

| Category | Accuracy |
|---|---|
| multi_step | 100.0 % |

## Questions

| Question | Split | Result | Attempts | Detail |
|---|---|---|---|---|
| lost_customers_2026 | dev | ok | 1 | the first row holds the reference values |
| best_customer_per_region_2025 | test | ok | 1 | rows match |
| qoq_growth_2026 | dev | ok | 2 | rows match |
| top20_share_2025 | test | ok | 1 | the first row holds the reference values |
| customers_over_10k_2025 | dev | ok | 1 | the first row holds the reference values |
| never_sold_products | test | ok | 1 | the first row holds the reference values |
| printing_orders_2026 | dev | ok | 1 | the first row holds the reference values |
| avg_revenue_active_customer | test | ok | 1 | the first row holds the reference values |
| biggest_monthly_jump_2025 | dev | ok | 1 | the first row holds the reference values |
| discounts_2025 | test | ok | 1 | the first row holds the reference values |
| segments_without_overdue | dev | ok | 1 | rows match |
| payment_delay_by_segment_2026 | test | ok | 1 | rows match |
