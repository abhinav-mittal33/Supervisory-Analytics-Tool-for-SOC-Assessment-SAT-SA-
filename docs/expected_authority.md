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
| `REASSIGNMENT_LOOP` | Exact structural match (deterministic, not a statistical test): repeated Analyst object within a bounded-size analyst set across a case's REASSIGN trace, gated by absence of the `handover_reason=SHIFT_CHANGE` justification attribute. Confidence is binary (matched pattern / did not) rather than a continuous score — appropriate here since the pattern is a structural rule, not an estimated quantity. `src/satsa/moat1/structural.py::detect_reassignment_loops`. | Authority class: `EXPECTED` (deviation from the documented shift-change handover SOP). Gate 1: precision=recall=F1=1.000 on all three generated profiles. |
| `ESC-CRIT-001` (OKF Response) | Deterministic: ESCALATE event present in the case trace within 30 minutes of ASSIGN. Missing entirely, or present but late, are both violations — kept as one finding_type since both mean the same supervisory fact (escalation duty not met on time), not two. `src/satsa/okf/compiler.py::evaluate_response`. | Authority class: `MANDATORY` (`source_type=NCIIPC_CRITERIA`). Verified against an independent Python oracle in `tests/test_okf_compiler.py` — see `docs/assumptions.md` entry 004 for a real timing-model bug this caught. |
| `ENR-PREC-001` (OKF Precedence) | Deterministic: INVESTIGATE occurs without a prior ENRICH in the same case ("Missing Enrichment", Section 6.5's own example). `src/satsa/okf/compiler.py::evaluate_precedence`. | Authority class: `EXPECTED` (`source_type=APPROVED_SOP`). |
| `REASSIGN-CARD-001` (OKF Cardinality) | Deterministic: REASSIGN occurs more than twice in a case. Deliberately a weaker check than `REASSIGNMENT_LOOP` — see the docstring in `src/satsa/okf/rules.py` for why it's kept anyway (it demonstrates, not just claims, the Section 9.1 point about count-based rules misfiring on `REASSIGNMENT_CHAIN_NO_LOOP`). | Authority class: `OPTIONAL`. Never presented as a substitute for the structural detector. |
| Exposure-adjusted negative space (per peer group, e.g. Queue-level escalation-duty coverage) | Poisson GLM with a log-exposure offset (`statsmodels`), confidence interval on the pooled rate propagated into each group's expected-count bounds, empirical-Bayes (Poisson-Gamma) shrinkage for peer groups below `MIN_PEER_GROUP_SIZE=10`. `ABSTAIN` with `INSUFFICIENT_EVIDENCE`/`INSUFFICIENT_EXPOSURE` when the estimate can't be trusted. `src/satsa/moat1/negative_space.py::detect_negative_space`. | Authority class: `PEER_NORMAL` — always presented as "baseline for expected evidence," never a compliance rule. |
| Metric-gaming / displacement-within-a-cycle | CUSUM (two-sided, own-mean target) run in parallel on a KPI series and a linked invariant series, binned by week from each case's ASSIGN time. Output is always `POTENTIAL_DISPLACEMENT` / `POTENTIAL_EXECUTION_GAP`, never an assertion of intent. `src/satsa/moat1/drift.py::detect_displacement`. | No single authority class — this detects a *pattern across two other findings' authority-tagged series*, not a violation of one rule. See `docs/assumptions.md` entry 005 for the DISPLACEMENT vs EXECUTION_GAP labeling interpretation (the spec doesn't itself define the split) and the real statistical-power issue this surfaced at low duty-population density. |
| Moat 2 intervention opportunities (any confirmed finding) | Not a finding_type — Moat 2 runs strictly after a `TRUE_SUPERVISORY_FINDING` verdict, on the confirmed finding's controllable mechanism. Confidence expressed as the Cinelli-Hazlett Robustness Value (`src/satsa/moat2/sensitivity.py`), gating an explicit `ACT`/`INVESTIGATE_MORE` decision (`src/satsa/moat2/decision.py`) rather than a confidence score attached to a new finding. | See `docs/assumptions.md` entry 009 for what this number does and does not mean. |
| _(remaining Moat 1 finding_types populated at Build Order Step 8, Anomaly-\>Finding-\>Concern fusion)_ | | |

Confidence and evidence-quality are never blended into one number (see Evidence
Package schema in `docs/architecture.md`).
