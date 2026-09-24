# Expected Authority (OKF)

## What OKF is / is not

Answers "what should happen, why, for whom, what evidence should exist, under what
authority." Versioned, structured, deterministic. Not an LLM knowledge base, not RAG,
not a vector database, not embedded documents, not a chatbot (see Section 8 of the
build spec for the absolute prohibition).

## Authority classes

| Class | Meaning | Violation treatment |
|---|---|---|
| `MANDATORY` | NCIIPC/regulation | Violation is a finding candidate |
| `EXPECTED` | Approved SOP/playbook | Deviation is a finding candidate after checking for justification |
| `PEER_NORMAL` | Statistically derived from peer CSEs | Never a compliance rule — surfaces only as "baseline for negative-space estimation" |
| `OPTIONAL` | Best practice | Informational only |
| `UNKNOWN` | No defensible basis | Descriptive only, never normative |

Every output derived from a peer baseline states explicitly: "this is a baseline for
estimating expected evidence, not a requirement."

## OKF rule schema

See Section 6.3 of the build spec for the full JSON example. This build implements
the complete schema including `version` and `effective_from`/`effective_to`, but sets
every rule to `version: "1.0"` with a single effective period for the demo dataset —
no multi-version conflict-resolution logic (explicitly out of scope, per the spec's
own instruction not to build unscoped production machinery).

## Declarative constraint templates (Section 6.5)

Each OKF rule compiles into exactly one of these, evaluated as SQL over OCEL-derived
tables (DuckDB):

- **Response** — if A occurs, B must eventually occur in the same case/object trace.
- **Precedence** — B can only occur if A occurred earlier.
- **Cardinality/Absence** — activity occurs at most/exactly/at least N times.
- **Not-Co-Existence** — A and B should never both occur in the same case.

Each constraint instantiation carries exactly one authority tag, one capability
mapping, and produces its own violation count.

## Confidence, per finding_type — filled in as each detector is built

| finding_type | Statistical test producing confidence | Notes |
|---|---|---|
| _(populated at Build Order Step 7-8 as negative-space / drift / structural detectors are implemented)_ | | |

Confidence and evidence-quality are never blended into one number (see Evidence
Package schema in `docs/architecture.md`).
