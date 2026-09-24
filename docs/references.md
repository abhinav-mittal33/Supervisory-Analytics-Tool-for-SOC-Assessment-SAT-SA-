# References & Calibration Traceability

## Standards implemented directly against

| Artifact | Source | License | Used for |
|---|---|---|---|
| OCEL 2.0 JSON Schema | `https://www.ocel-standard.org/2.0/ocel20-schema-json.json` | Published standard artifact (validator input, no library redistribution) | `src/satsa/ocel/validate.py` JSON validation |
| OCEL 2.0 Specification | Berti et al., *OCEL (Object-Centric Event Log) 2.0 Specification*, arXiv:2403.01975, Oct 2023 | CC BY 4.0 | Section 6 (relational SQLite format) implemented by hand in `src/satsa/ocel/sqlite_io.py` |

See `docs/assumptions.md` entry 001 for why this is implemented directly rather than
through pm4py/ocpa (both carry a copyleft dependency unsuitable for this deliverable).

## Public event-log grounding (Section 14.4) — pending, Build Order Step 4

| Dataset | Source | License | Status |
|---|---|---|---|
| BPI Challenge 2013 (Volvo IT incidents) | 4TU.ResearchData | To verify at download | Not yet used |
| BPI Challenge 2014 (Rabobank ITSM) | 4TU.ResearchData / tf-pm.org | To verify at download | Not yet used |

## Synthetic generator parameter calibration table (Section 14.3) — populated as the generator is built

| Parameter | Value used | Cited source |
|---|---|---|
| _(filled in at Build Order Steps 2 and 4)_ | | |

## Causal engine (Section 12 / Moat 2) — pending, Build Order Step 11

| Library | License | Role |
|---|---|---|
| DoWhy | MIT (to re-verify at install time) | Graphical causal model, potential-outcomes estimation, refutation/sensitivity API |
