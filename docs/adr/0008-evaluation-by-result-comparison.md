# ADR 0008: Evaluation by result comparison, with a held-out split

- Status: accepted
- Date: 2026-10-25

## Context

A generated query that runs can still be wrong. Common Text-to-SQL metrics are either
too weak ("valid SQL rate", "it executed") or too strict (exact match of the SQL text,
exact equality of result sets). An LLM judge is cheap to set up but unreliable on
numbers, and it shares blind spots with the model it judges.

## Decision

- **Execution accuracy against hand-written reference SQL**, compared on results, not on
  SQL text: tolerant to presentation (extra columns, names, order, percentages, rounding),
  strict on substance (a missing column, a wrong value, a different row count).
- **Three comparison modes** chosen per question (`rows`, `first`, `contains`), because
  "which category dropped the most?" is correctly answered by a ranked list whose first
  row is the right one.
- **Anomaly questions** whose answer is an injected, recorded fact: ground truth that
  does not depend on the reference SQL being right.
- **Refusals are scored too**: declining with the right reason is a correct answer.
- **A dev/test split**: changes are tuned on dev and confirmed on test, with the rule
  written before the test run.
- No LLM judge for numbers. If explanations are evaluated later (milestone 0.7), a judge
  may grade wording, never figures.

## Consequences

- Reference SQL is work, and it can be wrong: a database test runs every reference and
  checks the anomaly answers against the recorded ground truth.
- The first set saturated quickly (three configurations at 100 %). The method is sound;
  the questions need to get harder, which is planned rather than hidden.
