# Architecture

## Pipeline

```
PERIODIC SOC DATA (>=2 distinct CSE profiles)
  -> INGESTION -> DATA RELIABILITY / ABSTAIN GATE
  -> SEMANTIC NORMALIZATION -> CANONICAL OBJECT MODEL
  -> OBJECT+EVENT+RELATIONSHIP RECONSTRUCTION -> OCEL 2.0 -> VALIDATE -> ROUND-TRIP
       |                                    |
       v                                    v
  OBSERVED WORLD (what happened)      OKF (what should happen)
       |____________________________________|
                       v
                    MOAT 1
                       v
         EVIDENCE FUSION -> ANOMALY -> FINDING -> CONCERN
                       v
                 EVIDENCE PACKAGE
                       v
         SAMPLING LAYER: budgeted, guaranteed, debiased
                       v
                 HUMAN EXAMINER VERDICT
                       v
         FEEDBACK: Beta-Binomial per bucket, debiased
                       v
     MOAT 2 -- only on TRUE_SUPERVISORY_FINDING
                       v
          [OPTIONAL, STRETCH] TEMPORAL AXIS
                       v
            IMMUTABLE AUDIT TRAIL, NEXT CYCLE
```

## Stack

- Language: Python 3.11 (system Python was 3.9; 3.11 installed via Homebrew
  specifically for this project — modern dependency support for the statistics/
  process-mining-adjacent libraries this build needs).
- Analytical storage: OCEL 2.0 canonical SQLite (own implementation — see
  `docs/assumptions.md` entry 001), constraint evaluation via DuckDB SQL.
- No web framework yet — UI deferred to Build Order Step 13.

## Repo layout

```
sat-sa/
  docs/                    product_contract, ontology, architecture, expected_authority,
                           assumptions, validation_plan, references
  src/satsa/
    ingestion/             raw CSV/JSON -> canonical object model
    generator/             synthetic CSE profile generator + hard negatives
    ocel/                  OCEL 2.0 model, json_io, sqlite_io, validate (own implementation)
      schema/              official ocel20-schema-json.json, fetched from ocel-standard.org
    okf/                   OKF rule schema, constraint compiler, authority tagging
    moat1/                 negative_space, structural, drift, secondary, fusion
    sampling/              cost_model, budget_split, submodular, feedback
    moat2/                 causal_model, sensitivity, decision
    temporal/              optional, built last
    evidence/              package, audit
    llm_explainer/         optional, strictly post-hoc NL explainer
    ui/                    examiner UI, built only after Moat 1/sampling/Moat 2 validated
  tests/                   one pytest module per gate
  data/dev/                dev-scale synthetic set (few hundred cases)
  data/scaled/             two full-scale CSE profiles
```

## Measured facts (Section 7.3 — recorded as measured, not assumed)

- OCEL 2.0 is the current standard; no 2.1/3.0 exists as of 2026-09-25
  (ocel-standard.org, arXiv:2403.01975).
- pm4py's installed version carries `License-Expression: AGPL-3.0-or-later`; ocpa
  transitively requires pm4py (GPL-3.0, version 2.2.32 observed). Neither is used in
  this build — see `docs/assumptions.md` entry 001.
- `jsonschema` (MIT) is used for OCEL 2.0 JSON validation against the official schema.
- Python 3.11.15 confirmed installed via Homebrew and used for the project virtualenv
  at `.venv/`.
- DuckDB's `sqlite` extension can `ATTACH` an OCEL 2.0 SQLite file directly and query
  its tables with ordinary SQL, confirmed locally before `src/satsa/okf/compiler.py`
  was built on top of it (Build Order Step 6).
- `scipy` (BSD-3-Clause-style; PyPI classifier shows the license text directly rather
  than an SPDX tag, but it's the well-known BSD scipy license) and `statsmodels`
  (BSD-3-Clause) added at Build Order Step 7 for the Poisson/NB negative-space
  regression Section 9.4 explicitly mandates — no copyleft concern, unlike entry 001.
