# Privacy by design

The data is synthetic, but the system is built as if it were not: the same controls
would apply to a real company database.

## Data flows

| Flow | What leaves the backend | What never does |
|---|---|---|
| Question -> LLM provider | The question, with emails, phone numbers, IBANs, card numbers and French social security numbers masked (`[EMAIL]`...) | The original identifiers |
| System prompt -> LLM provider | Rules, the reference date, descriptions of the analytics views and metrics | Any data row |
| Rejection feedback -> LLM provider | Validator messages (they name constructs); database messages, except data exceptions (SQLSTATE 22), which can quote a value and are replaced by a generic text | Values from the views |
| Result -> LLM provider (explanation) | At most 50 rows, `confidential` values pseudonymised (`CUSTOMER_001`), `pii` columns dropped | Company names, the pseudonym mapping |
| Result -> user | The rows, with the classification and the source view columns of every column | |
| Audit trail (`app.analyses`) | Masked question, every proposed SQL and its outcome, the SQL that ran, row count, timings, tokens, cost | Result rows, pseudonym mappings |
| Logs | Request IDs, statuses, counts, durations, costs | Questions, SQL values, results, secrets |

Before connecting real data, review the provider's data retention and usage terms for
the API, and decide how long the audit trail is kept (milestone 0.9).

## Classification first, detection second

Every column of every view is classified in the semantic model
(`backend/src/eaa/semantic/model.toml`):

| Class | Meaning | Treatment |
|---|---|---|
| `public` | Identifies nobody (region, category) | Sent as is |
| `internal` | Business data (amounts, dates, technical ids) | Sent as is, aggregated |
| `confidential` | Names a business entity (customer company) | Pseudonymised before the provider |
| `pii` | Personal data | Never in a view; dropped if it ever appeared |

Personal data (`sales.customer_contacts`: names, emails, phone numbers of people) is in
no view: generated SQL cannot read it, the role cannot read it, the model is told it is
not available, and the evaluation checks that such questions are declined.

A result column inherits the most sensitive class of the view columns it is computed
from, found by column lineage through CTEs and subqueries (`eaa.privacy.lineage`):
`UPPER(customer_name)` is confidential, `SUM(net_revenue)` internal. If lineage cannot be
computed, every column is treated as confidential.

Classification is deterministic and complete because the schema is ours. Detection
(next section) only covers what classification cannot: free text typed by users.

## Masking, pseudonymisation, anonymisation

They are not the same, and the system never calls one by the other's name.

- **Masking** replaces a value by a placeholder that carries no link back: the question
  "orders of jean.dupont@acme.example" becomes "orders of [EMAIL]". Irreversible here.
- **Pseudonymisation** replaces a value by a token that the backend can map back:
  `CUSTOMER_001` stands for one company within one analysis. The mapping lives in memory
  for that analysis only, so the user sees real names in the answer. Pseudonymised data
  is still personal data in the sense of the GDPR (recital 26): whoever holds the mapping,
  or enough context, can re-identify.
- **Anonymisation** means re-identification is no longer reasonably possible, by anyone.
  Nothing in this system produces anonymous data, and nothing claims to.

## Re-identification risks, stated plainly

- **Context.** "CUSTOMER_001, Enterprise segment, Southern Europe, 4.2 M EUR of revenue"
  may be enough to recognise a company for someone who knows the market. Pseudonyms hide
  names from the provider, not identities from an informed reader.
- **Small groups.** An average over a group of one is that one value. The views expose
  companies, not people, and no person-level metric exists (no salaries), so no
  minimum-group rule is applied today. With person-level data, a minimum group size
  (for example 5) would be required, and it would still not be enough on its own.
- **Differencing.** Two allowed aggregates can isolate one entity: total revenue, minus
  total revenue excluding one customer. Per-query rules cannot see that; it needs
  tracking of what each user has already asked, which this system does not do.
- **Detection gaps.** Names of people, postal addresses and identifiers without a fixed
  format are not detected in questions. A user who types them sends them.

## Why not Presidio (yet)

Microsoft Presidio adds statistical recognisers (people, places) on top of patterns. It
was considered and not adopted for now:

- it needs spaCy and a language model of several hundred megabytes, for French and
  English, on a development machine with 8 GB of RAM;
- the business questions are full of company names, which a person-name recogniser
  confuses with people: false positives would mask the very entities being asked about;
- the views already contain no personal data, so detection only protects free text.

It becomes worth it if free-text fields (notes, emails) enter the views, or if users are
expected to type names of people. The masking function is the place to plug it in.

## Tests

- `tests/test_privacy.py`: masking (identifiers caught, business text left alone, the
  known gap on names), lineage, pseudonymisation and the provider payload.
- `tests/test_pipeline.py`: the model receives the masked question; the audit trail
  stores it masked.
- `tests/db/test_privacy_payload.py`: for every legitimate query of the corpus, on the
  real data, no company name reaches the provider payload.
- The evaluation: questions asking for emails and phone numbers are declined.
