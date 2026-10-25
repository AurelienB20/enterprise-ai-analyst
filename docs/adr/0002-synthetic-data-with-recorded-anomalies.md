# ADR 0002: Synthetic data with injected, recorded anomalies

- Status: accepted
- Date: 2026-10-25

## Context

The project needs a company database to query. Real company data is out of the question
(confidentiality, and it would contain personal data). Public sample databases
(Northwind, AdventureWorks) are well known to LLMs, which may answer from memory
rather than from the data, and they have no known "interesting" answers to test against.

The evaluation (milestone 0.5) must check answers objectively: "the query ran" is not
enough, and an LLM judge cannot be trusted with numbers.

## Decision

- A home-made generator, pure Python standard library (`random.Random(seed)`), no Faker:
  the same seed and scale give the same rows byte for byte, checked by a digest.
- Realism through a few explicit mechanisms (seasonality, growth, heavy-tailed customers,
  price increases, discounts, cancellations, payment behaviours, supplier reliability),
  each a named parameter.
- Eight **anomalies injected on purpose**, each designed as the answer to a business
  question, recorded in `sales.dataset_anomalies` and checked by tests: the anomaly must
  be the *clear* answer, not merely present.
- A fixed **reference date** (2026-09-30) stored with the data, so relative periods
  ("this quarter") are reproducible.
- Personal data (`customer_contacts`) exists on purpose, to test the privacy layer.
- Contacts use reserved, unreachable values: `.example` emails (RFC 2606), 555-01xx phones.

## Consequences

- Building the generator took tuning: on the first version, three of the anomalies were
  drowned in noise. Testing them on 21 seeds made that visible; fewer, more even customers
  and stronger effects fixed it. Only seed 42 is guaranteed; that is documented.
- Some simplifications are visible (stock not reconciled with deliveries) and documented
  in docs/data-model.md rather than hidden.
- The evaluation gets questions with known answers, independent of any LLM.
