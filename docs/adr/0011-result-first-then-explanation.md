# ADR 0011: The result first, the explanation after, with a bounded cost

- Status: accepted
- Date: 2026-10-25

## Context

With the checked explanation (ADR 0010), a user waited for everything at once: 14 s at
the median, 30 s at the 95th percentile, for figures that were ready after about 5 to
9 s. The explanation is the slow part, and it is the optional part: the table, the chart
and the SQL already answer the question.

A live check then showed a second problem. On "Net revenue by region in 2025", the
explanation's correction round (after a figure failed the check) ran to the 16,000-token
ceiling: 107 s, $0.34, and an unusable, truncated answer.

## Decision

1. **`POST /analyses/stream`**, server-sent events: `answer` as soon as the query has run
   (result, SQL, trace, no explanation), then `done` (the same with the explanation,
   final timings and cost), or `error`. One request, so result rows are still never
   stored to be explained later. `POST /analyses` keeps the one-shot behaviour.
2. The pipeline is split into `answer()` and `explain()`; `run()` is both.
3. The interface reads the stream (fetch and a small parser, since EventSource cannot
   POST) and shows the result on `answer`, with a "checking every figure" indicator
   until `done`. The Next.js proxy passes events through unbuffered.
4. **The explanation has its own token ceiling** (`EXPLAIN_MAX_TOKENS`, 4,000, thinking
   included), and a cut-off explanation fails at once instead of going to a correction
   round. A failed explanation is shown as a short note, never as the summary.

## Consequences

- Measured through the proxy: the result arrives after 8.6 s instead of 22 s for the same
  question; the explanation follows.
- The worst case of an explanation is now about $0.08 per call (4,000 output tokens at
  Opus prices) instead of $0.32.
- An explanation that would have needed more than 4,000 tokens is now withheld. On the
  dev split, the explanations measured so far (ADR 0010) were well under it; the
  evaluation should confirm it with the new ceiling.
