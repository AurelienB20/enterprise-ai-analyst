# ADR 0007: Text-to-SQL by tool calling, in a bounded loop, without data in the prompt

- Status: accepted
- Date: 2026-10-25

## Context

Milestone 0.4 turns a question into SQL with Claude. Choices to make: how the model
returns its proposal, what it is told, how errors are handled, and what it sees.

## Decision

- **Two strict tools**, `submit_query` (SQL, views used, explanation, assumptions,
  ambiguities) and `cannot_answer` (a reason code: `personal_data`, `not_allowed`,
  `not_in_data`, `unclear`, and a message). `strict: true` guarantees the arguments match
  the schema. Declining is a first-class answer, not a failure: "I cannot answer this"
  with a reason is what a trustworthy analyst says.
  Forced tool choice is not available on current models, so `tool_choice` is `auto`, the
  prompt says to always call a tool, and a reply without a tool call is handled.
- **A bounded loop in the pipeline, not an agent framework.** At most `LLM_MAX_ATTEMPTS`
  (3) proposals. A validator rejection or a database error goes back as an error
  `tool_result` in the same conversation; the model corrects itself. A permission error
  is never retried: the validator should have caught it, so it is treated as a signal.
- **No data in the prompt.** The model sees the rules, the reference date, and the
  semantic model (views, columns, metric definitions). It never sees a result row in this
  milestone. Database errors whose text can quote a value (SQLSTATE class 22, such as
  `invalid input syntax for type integer: "<value>"`) are replaced by a generic message
  before they go back to the model.
- **Context selection: the whole semantic model.** Ten views and eleven metrics make
  5,356 tokens with the tools. That is small, stable and cached (prompt caching on the
  system prompt): a schema retrieval step would add a failure mode and save little.
  Revisit when the model grows past a few dozen views.
- **Model and effort are configuration** (`LLM_MODEL`, `LLM_EFFORT`), as are the prices
  used for the cost estimate. Default: Claude Opus 5.5 at `medium` effort; the evaluation
  (0.5) will compare effort levels and models on the same questions.
- **Server-side fallbacks** are on (`fallbacks: "default"`): if a safety classifier
  declines a legitimate business question, the API re-runs it on Anthropic's recommended
  fallback model instead of failing.
- **Audit trail** in `app.analyses`, written by `eaa_app`, a role that can only insert and
  read there: every proposal and its outcome, the SQL that ran, timings, tokens, cost.
  Never the result rows.

## Consequences

- First live run (6 questions, eaa_test, Opus 5.5 at medium effort): every answer right
  on the first proposal, checked against reference SQL or the recorded anomalies; the
  injection and the personal-data questions declined; 3 to 12 s per question; about
  $0.10 in total.
- The question itself is stored in the audit trail as typed: a user may type personal
  data into it. Retention and masking are decided with the privacy milestone (0.6).
- Results reach the user as rows; turning them into an explanation is milestone 0.7,
  where what may be sent to the model is decided with the privacy controls in place.
