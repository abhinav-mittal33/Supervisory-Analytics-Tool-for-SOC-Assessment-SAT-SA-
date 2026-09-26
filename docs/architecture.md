# Architecture

## Pipeline

```
PERIODIC SOC DATA (>=2 distinct CSEs; CSV / JSON / SQLite export / generic REST API)
  -> INGESTION (adapters -> field mapping) -> DATA RELIABILITY / ABSTAIN GATE
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
                 EVIDENCE PACKAGE (per CSE)
                       v
         SAMPLING LAYER: budgeted, guaranteed, debiased
                       v
                 HUMAN EXAMINER VERDICT
                       v
         FEEDBACK: Beta-Binomial per bucket, debiased
       -- also feeds validation/expert_agreement.py (PS Sec 8 mechanism) --
                       v
     MOAT 2 -- only on TRUE_SUPERVISORY_FINDING
                       v
     PORTFOLIO: cross-CSE peer comparison + entity risk (PS req 8/9)
                       v
     TEMPORAL AXIS: two-cycle trend classification (Gate 5, PS req 16)
                       v
     REPORTING: self-contained offline HTML report (PS req 15-17)
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
    ingestion/             CSV/JSON/SQLite-export/generic-REST-API -> canonical
                           object model (adapters/, mapping/, normalization/,
                           quality/) — see "Measured facts" below
    generator/             synthetic CSE profile generator + hard negatives
    ocel/                  OCEL 2.0 model, json_io, sqlite_io, validate (own implementation)
      schema/              official ocel20-schema-json.json, fetched from ocel-standard.org
    okf/                   OKF rule schema, constraint compiler, authority tagging
    moat1/                 negative_space, structural, drift, secondary, fusion
    sampling/              cost_model, budget_split, submodular, feedback
    moat2/                 causal_model, sensitivity, decision
    portfolio/             cross-CSE peer comparison + entity risk indicator (PS req
                           8/9) — supporting functionality on Moat 1, not a third moat
    temporal/              two-cycle trend classification (Gate 5, PS req 16)
    reporting/             self-contained offline HTML report generator (PS req 15-17)
    validation/            expert-agreement mechanism (PS Section 8 — see
                           assumptions.md entry 015: mechanism only, no real NCIIPC
                           expert data exists to validate against)
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
- `dowhy` 0.14, used at Build Order Step 11 for formal causal identification,
  **dropped at Step 14**: its own license is MIT, but its package `__init__` chain
  unconditionally imports `causal-learn`, which requires `cvxopt`
  (GPL-3.0-or-later) — confirmed by removing those packages and watching
  `from dowhy import CausalModel` fail outright, not something avoidable while still
  using DoWhy at all (docs/assumptions.md entry 010). Replaced with **pgmpy** 1.1.2
  (MIT, full transitive tree checked via `pipdeptree` — zero copyleft, see
  docs/sbom.json) for the identification step. The numeric estimate/CI and the
  sensitivity analysis itself remain statsmodels OLS + the closed-form
  Cinelli-Hazlett Robustness Value (docs/assumptions.md entry 009), unaffected by the
  swap.
- `pgmpy`'s dependency on `huggingface_hub` was specifically checked for outbound
  network calls (a Section 18 concern, not a licensing one) by monkeypatching every
  `socket.connect` to raise while running pgmpy's causal-inference classes — zero
  network calls attempted. Covered permanently by `tests/test_offline_deployment.py`.
- `docs/sbom.json` (`scripts/generate_sbom.py`) — a full software bill of materials
  generated from the actual installed virtualenv (`importlib.metadata`, not
  hand-maintained), added at Build Order Step 14 specifically because the DoWhy/cvxopt
  discovery showed a single package's own license page isn't enough — the full
  transitive tree needs checking. 124 packages as of last generation, zero
  GPL/AGPL/LGPL.
- `scripts/benchmark_pipeline.py` (stdlib `tracemalloc`/`time`, zero new dependency)
  measured real wall-clock/memory across all profiles — full numbers and a genuine,
  unresolved submodular-selection scaling finding (57s at 1,011 concerns) are in
  `docs/deployment_requirements.md` and `docs/assumptions.md` entry 016, not smoothed
  over.
- `streamlit` 1.64 confirmed Apache-2.0-licensed, added at Build Order Step 13 for the
  examiner UI. Verified it makes no external network calls by disabling its
  usage-telemetry ping (`.streamlit/config.toml`, `gatherUsageStats = false`) — a real
  requirement given Section 18's air-gapped deployment constraint, not a cosmetic
  setting. The full UI (all three tabs, verdict submission with conditional required
  fields, cost override, review timer, audit trail) was launched and driven with a
  real browser (Playwright) before being reported as working — not just unit-tested.
- `src/satsa/ingestion/` (previously the one known, scoped gap — see
  `docs/plan_vs_actual.md`) built against the official PS's actual Functional
  Requirements 1-2, not an arbitrary-format parser: CSV, JSON, SQLite database
  export, and a generic REST/JSON API adapter, all behind one `SourceAdapter`
  interface, feeding a field-mapping step (auto-suggested, always overridable) and a
  data-reliability/ABSTAIN quality gate before OCEL construction — see
  `docs/assumptions.md` entry 011 for the full design and the one real judgment call
  it required (the API adapter's network call vs. the Section 18 offline mandate).
  `normalization/canonical.py` deliberately reuses `generator/generate.py`'s exact
  object/event vocabulary, so no downstream detector (Moat 1, OKF, sampling, Moat 2)
  needed to change. Proven end to end, not just unit-tested: three CSE fixtures with
  three different real-world column-naming conventions (`data/samples/`) all
  normalize into one canonical model, and the existing reassignment-loop detector
  recovers a planted loop from the CSV fixture unmodified
  (`tests/test_ingestion_pipeline_end_to_end.py`).
