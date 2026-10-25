# Evaluation

The question is not "does the SQL run?" but "is the answer right?". The evaluation
answers it without trusting the model, and without an LLM judging numbers.

## The question set

[`backend/eval/questions.toml`](../backend/eval/questions.toml): 53 questions in French
and English, each with:

- **`expect = "answer"`** and a **reference SQL**, written by hand on the analytics views;
  or **`expect = "decline"`** and the reasons accepted (`personal_data`, `not_allowed`,
  `not_in_data`).
- a **category** (revenue, trend, ranking, payments, customers, stock, volumes,
  anomaly, multi-step, refusal, adversarial);
- a **split**: `dev` questions may guide a change, `test` questions only confirm it.
- for 8 of them, the **injected anomaly** the answer must be (A1 to A8). A database test
  checks that each of those reference answers *is* the anomaly, and that every
  reference SQL passes the validator and returns rows.

## Scoring

An answer is right when its rows match the rows of the reference SQL
([`eaa.evaluation.compare`](../backend/src/eaa/evaluation/compare.py)):

- tolerated: extra columns, other names and order of columns, a percentage for a ratio,
  rounding (a cent on amounts, 0.0005 on ratios), a midnight timestamp for a date;
- not tolerated: a missing reference column, a different number of rows, a wrong value;
- modes: `rows` (the same rows), `first` (for "which X": the reference row must be the
  first generated row), `contains` (the reference rows are among the generated ones).

A decline is right when the model called `cannot_answer` with an accepted reason.

## Metrics

Accuracy, execution accuracy (questions with an answer), correct refusals, false
refusals, valid SQL (answered at all), right on the first proposal, permission
violations (the database refusing a query that passed the validator: must be 0),
latency p50/p95, cost per question. Per category and per split.

## Discipline

- A change is decided on `dev`, with its acceptance rule written down before the `test`
  split runs; it is kept only if `test` does not regress.
- Every run is saved with its configuration, dataset identity (generator version, seed,
  scale), question-set and semantic-model versions, and commit.
- Runs call the LLM: they are run by hand (`-m live` tests and `python -m
  eaa.evaluation run`), never by the CI. The CI checks the references and the scoring.

## Results

See [`backend/eval/results/README.md`](../backend/eval/results/README.md). In short: one
real failure fixed (a prompt rule, confirmed on held-out questions), one performance bug
in a view found and fixed (31 s to 1.6 s), and a saturated set: three configurations at
100 %, so cost and latency decide.
