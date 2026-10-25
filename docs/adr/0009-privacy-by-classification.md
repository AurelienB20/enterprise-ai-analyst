# ADR 0009: Privacy by classification, pattern masking, ephemeral pseudonyms

- Status: accepted
- Date: 2026-10-25

## Context

Three things could carry personal or confidential data to the LLM provider: the
question typed by the user, the data the model needs to explain a result (milestone
0.7), and error messages. The usual tool for this is PII detection (Presidio and the
like), applied to whatever text is about to be sent.

## Decision

- **Classification over detection for the data.** Every view column is classified in
  the semantic model; personal data is in no view. Result columns inherit the class of
  their source columns through SQLGlot column lineage; unknown lineage means
  confidential. This is complete and deterministic, which detection on values never is.
- **Pattern masking for free text.** The question is masked for identifiers that have a
  format (email, phone number, IBAN with a valid checksum, card number with a valid Luhn
  checksum, French social security number) before it reaches the model or the audit
  trail. Names of people are not detected, and that is documented.
- **Ephemeral pseudonyms for confidential values.** Company names become `CUSTOMER_001`
  in anything sent to the provider; the mapping lives in memory for one analysis and is
  never sent, logged or stored. It is called pseudonymisation, never anonymisation.
- **No Presidio for now**: a heavy dependency, false positives on company names, and
  little to protect once the views hold no personal data. Revisit if free-text fields or
  person-level data enter the views.
- **No minimum group size for now**: the views describe companies and hold no
  person-level metric. Documented as required before any person-level data is added,
  together with its limit (differencing attacks).

## Consequences

- The privacy guarantees are as good as the classification in `model.toml`, which is
  reviewed like code and checked against the database by tests.
- A user can still type the name of a person into a question; it would reach the
  provider. The README and docs/privacy.md say so.
- Milestone 0.7 builds explanations on `ProviderPayload`, never on raw rows.
