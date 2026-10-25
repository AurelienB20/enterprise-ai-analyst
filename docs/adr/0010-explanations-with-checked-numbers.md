# ADR 0010: Explanations in which every number is checked

- Status: accepted
- Date: 2026-10-25

## Context

After the SQL ran, the user should get a short written reading of the result. The risk
is the one that ruins trust in an "AI analyst": a fluent sentence with a wrong figure
("revenue fell by 12 %" when it fell by 17 %), or a cause the data does not show.
Prompting the model to be careful reduces the risk; it does not remove it.

## Decision

- **Code computes, the model writes.** Totals, averages, extremes, shares of total and
  first-to-last changes are computed by `eaa.analysis.facts` and given to the model as
  named facts, next to the (pseudonymised, at most 50 rows) result.
- **Every number in the text is checked** (`eaa.analysis.numbers`) against the result
  values and the facts, at the precision it is written with, in French and English
  formats ("1 234,56 €", "4.2 M€", "43 %"). Years, dates, quarter labels, pseudonyms and
  integers from the question or the SQL are not checked.
- **One correction, then withholding.** Unverified numbers go back to the model once, as
  an error tool result. If any remain, the explanation is replaced by a deterministic
  sentence that says so: no unchecked figure is ever shown. The status (`verified`,
  `fallback`, `failed`) is returned and stored in the audit trail; the text is not
  stored, since it quotes the data.
- **No causal claims**: the prompt says to describe, not explain why, and to say when the
  data does not tell why.
- **Pseudonyms are revealed in the backend**, after checking, so the provider never sees
  company names (ADR 0009).

## Measurements (dev split, 29 questions, Claude Opus 5.5)

- Explanation effort `medium`: 25 of 25 explanations verified, some after one correction.
- Effort `low`, on 8 of them: 7 of 8 verified (one withheld), more corrections, and no
  faster. The default stays `medium`; the setting is `EXPLAIN_EFFORT`.
- The cost: median latency from 5 s to 14 s, cost per question from $0.015 to $0.035.

## Consequences

- The check catches invented and miscomputed figures, not wrong words around right ones
  ("rose" for a drop of the same size is caught only through the sign of facts, which
  the check compares loosely). Wording is not evaluated automatically yet.
- Latency is now the main weakness: the explanation should not block the result. Done
  in ADR 0011 (streamed result first), which also bounds the explanation's cost.
