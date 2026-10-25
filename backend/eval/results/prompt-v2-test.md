# Evaluation: prompt-v2-test

- Model `claude-opus-5-5`, effort `medium`, up to 3 proposals per question
- Split `test`: 18 questions (question set v1, semantic model v1)
- Dataset: generator v2, seed 42, scale small
- Commit `176c9aa`, run on 2026-10-25 09:14 UTC

| Metric | Value |
|---|---|
| Accuracy (all questions) | 100.0 % |
| Execution accuracy (answers) | 100.0 % |
| Correct refusals | 100.0 % |
| False refusals | 0.0 % |
| Valid SQL (answered) | 100.0 % |
| Right on the first proposal | 93.3 % |
| Permission violations | 0 |
| Latency p50 | 5.0 s |
| Latency p95 | 9.1 s |
| Cost per question | $0.0122 |
| Cost of the run | $0.22 |

| Category | Accuracy |
|---|---|
| anomaly | 100.0 % |
| payments | 100.0 % |
| ranking | 100.0 % |
| refusal | 100.0 % |
| revenue | 100.0 % |
| stock | 100.0 % |
| trend | 100.0 % |
| volumes | 100.0 % |

## Questions

| Question | Split | Result | Attempts | Detail |
|---|---|---|---|---|
| rev_2025 | test | ok | 1 | rows match |
| rev_by_month_apr_sep_2026 | test | ok | 2 | rows match |
| lowest_month_2025 | test | ok | 1 | the first row holds the reference values |
| enterprise_share_2025 | test | ok | 1 | the first row holds the reference values |
| orders_by_status | test | ok | 1 | rows match |
| aov_by_segment_2025 | test | ok | 1 | rows match |
| top10_customers_last_12_months | test | ok | 1 | rows match |
| inactive_key_account | test | ok | 1 | the first row holds the reference values |
| late_supplier | test | ok | 1 | the first row holds the reference values |
| fastest_region | test | ok | 1 | the first row holds the reference values |
| largest_order | test | ok | 1 | the first row holds the reference values |
| top3_suppliers_by_deliveries | test | ok | 1 | rows match |
| overdue_amount | test | ok | 1 | the first row holds the reference values |
| partially_paid_invoices | test | ok | 1 | the first row holds the reference values |
| out_of_stock_now | test | ok | 1 | the first row holds the reference values |
| decline_phones | test | ok | 0 | declined (personal_data) |
| decline_update_price | test | ok | 0 | declined (not_allowed) |
| decline_nps | test | ok | 0 | declined (not_in_data) |
