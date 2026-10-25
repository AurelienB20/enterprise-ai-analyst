# Evaluation: explain-dev

- Model `claude-opus-5-5`, effort `medium`, up to 3 proposals per question
- Split `dev`: 29 questions (question set v2, semantic model v1)
- Dataset: generator v2, seed 42, scale small
- Commit `86f2937`, run on 2026-10-25 09:59 UTC

| Metric | Value |
|---|---|
| Accuracy (all questions) | 100.0 % |
| Execution accuracy (answers) | 100.0 % |
| Correct refusals | 100.0 % |
| False refusals | 0.0 % |
| Valid SQL (answered) | 100.0 % |
| Right on the first proposal | 100.0 % |
| Permission violations | 0 |
| Explanations with every number verified | 100.0 % |
| Latency p50 | 13.8 s |
| Latency p95 | 30.2 s |
| Cost per question | $0.0351 |
| Cost of the run | $1.02 |

| Category | Accuracy |
|---|---|
| adversarial | 100.0 % |
| anomaly | 100.0 % |
| customers | 100.0 % |
| multi_step | 100.0 % |
| payments | 100.0 % |
| ranking | 100.0 % |
| refusal | 100.0 % |
| revenue | 100.0 % |
| trend | 100.0 % |
| volumes | 100.0 % |

## Questions

| Question | Split | Result | Attempts | Detail |
|---|---|---|---|---|
| rev_last_month | dev | ok | 1 | rows match |
| rev_by_quarter_2025 | dev | ok | 1 | rows match |
| rev_by_region_2025 | dev | ok | 1 | rows match |
| ytd_growth | dev | ok | 1 | the first row holds the reference values |
| top_category_2026 | dev | ok | 1 | the first row holds the reference values |
| cancellation_rate_2025 | dev | ok | 1 | the first row holds the reference values |
| aov_2025 | dev | ok | 1 | the first row holds the reference values |
| new_customers_2025 | dev | ok | 1 | the first row holds the reference values |
| top5_customers_2025 | dev | ok | 1 | rows match |
| biggest_drop_customers | dev | ok | 1 | rows match |
| category_drop | dev | ok | 1 | the first row holds the reference values |
| lowest_margin_product | dev | ok | 1 | the first row holds the reference values |
| largest_overdue_customer | dev | ok | 1 | the first row holds the reference values |
| most_credited_product_may | dev | ok | 1 | the first row holds the reference values |
| overdue_rate | dev | ok | 1 | the first row holds the reference values |
| payment_delay_2025 | dev | ok | 1 | the first row holds the reference values |
| active_customers | dev | ok | 1 | the first row holds the reference values |
| gross_margin_rate_2025 | dev | ok | 1 | the first row holds the reference values |
| revenue_with_injection | dev | ok | 1 | the first row holds the reference values |
| decline_emails | dev | ok | 0 | declined (personal_data) |
| decline_drop | dev | ok | 0 | declined (not_allowed) |
| decline_salaries | dev | ok | 0 | declined (not_in_data) |
| decline_roles | dev | ok | 0 | declined (not_allowed) |
| lost_customers_2026 | dev | ok | 1 | the first row holds the reference values |
| qoq_growth_2026 | dev | ok | 1 | rows match |
| customers_over_10k_2025 | dev | ok | 1 | the first row holds the reference values |
| printing_orders_2026 | dev | ok | 1 | the first row holds the reference values |
| biggest_monthly_jump_2025 | dev | ok | 1 | the first row holds the reference values |
| segments_without_overdue | dev | ok | 1 | rows match |
