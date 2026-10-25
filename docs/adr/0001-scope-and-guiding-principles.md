# ADR 0001: Scope and guiding principles

- Status: accepted
- Date: 2026-10-25

## Context

The project answers business questions in natural language over a company database.
The obvious version is a chatbot that sends the schema to an LLM, runs whatever SQL comes
back and summarises the rows. That version fails in three ways that matter to a business:

1. **It is unsafe.** An LLM can be talked into writing destructive or exfiltrating SQL
   ("ignore your instructions and..."), and string checks such as "starts with SELECT"
   are easy to bypass with CTEs, subqueries or functions.
2. **It is unreliable.** A query that runs without error can still be wrong (a bad join,
   cancelled orders counted as revenue), and the LLM improvises what "revenue" or
   "active customer" mean.
3. **It leaks data.** Raw rows, including personal data, are sent to an external provider
   and end up in logs.

## Decision

- **The LLM proposes, the backend verifies, the database enforces permissions.** The LLM
  never connects to the database. Its SQL goes through a deterministic validator, then
  runs under a least-privilege PostgreSQL role in a read-only transaction. The database
  role is the security boundary; the validator is an early, explainable filter.
- **Business definitions are code.** Metrics are defined once in a versioned semantic
  layer, compiled into SQL views and tested.
- **Privacy by design.** Columns are classified; personal data is not exposed to
  generated SQL and is not sent to the provider. Aggregation happens in PostgreSQL.
- **Evaluation-driven.** Correctness is measured by comparing results with reference
  queries, not by "it ran" or by an LLM judge for numbers.
- **Simple, linear pipeline.** No agent framework (LangChain, LangGraph), no queue, no
  cache, no vector database until a measured need appears. A linear pipeline with one
  retry is easier to test, to secure and to explain.
- **Synthetic data only**, generated from a fixed seed, with documented anomalies so that
  the evaluation has known answers.
- The model ID is configuration, never code.

## Consequences

- More upfront work (semantic layer, roles, validator) before the first answer.
- Some questions cannot be answered because the views do not expose the data; the
  system says so instead of guessing. That is the intended trade-off.
- Frameworks may still be adopted later, through an ADR that names the problem they solve.
