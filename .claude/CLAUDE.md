# Project CLAUDE.md
# Personal overrides (MCP servers, local paths): .claude/local.md (gitignored)

## Project

**Name**: SAT-SA — Supervisory Analytics Tool for SOC Assessment (SIH26157, NCIIPC/NTRO)
**Purpose**: Prioritize scarce NCIIPC examiner review hours across Critical Sector Entity (CSE) SOCs by surfacing execution gaps and negative space, without becoming a SIEM/SOAR/monitor.
**MVP scope**: See `docs/product_contract.md` and the full build spec conversation history. In: object-centric evidence discovery (Moat 1), budgeted submodular sampling, causal intervention decision engine (Moat 2), examiner UI. Out: real-time monitoring, LLM-in-the-analytical-core (anywhere), cloud/SaaS dependency, the temporal axis (optional, cut first).
**Status**: Active development — all 5 required validation gates pass (Gate 0-4); Gate 5 (temporal axis) optional and deferred.

## Stack

- **Language + version**: Python 3.11.15 (installed via Homebrew specifically for this project — system Python was 3.9)
- **Backend framework**: none (analytical pipeline, not a served API)
- **Database**: OCEL 2.0 canonical storage as SQLite (own implementation, not pm4py/ocpa — see `docs/assumptions.md` entry 001); DuckDB for OKF constraint SQL over the OCEL tables
- **Frontend**: Streamlit (examiner UI, `src/satsa/ui/app.py`)
- **Package manager**: pip + `pyproject.toml`, editable install (`pip install -e .`)
- **Test runner**: pytest
- **Key libraries**: duckdb, jsonschema, scipy, statsmodels, dowhy, streamlit — every one's license checked before use (`docs/architecture.md` "Measured facts")
- **Deployment target**: fully air-gapped, offline (Section 18) — no cloud, no external API calls anywhere, ever

## Folder Structure

```
sat-sa/
  docs/                    SAT-SA build-spec docs: product_contract, ontology, architecture,
                           expected_authority, assumptions (loophole log), validation_plan, references
  src/satsa/
    ingestion/             raw CSV/JSON -> canonical object model (not yet built)
    generator/             synthetic CSE profile generator + hard negatives + calibration
    ocel/                  OCEL 2.0 model, json_io, sqlite_io, validate (own implementation)
      schema/              official ocel20-schema-json.json, fetched from ocel-standard.org
    okf/                   OKF rule schema, DuckDB constraint compiler, worked rules
    moat1/                 structural (reassignment loop), negative_space, drift, fusion
    sampling/              cost_model, budget_split, submodular, feedback, baselines, allocation_explanation
    moat2/                 synthetic_causal_data, causal_model, sensitivity, decision, intervention
    temporal/               optional, not built (Section 13, cut first under time pressure)
    evidence/               package (Evidence Package schema), verdict (examiner verdict ontology)
    llm_explainer/          optional, not built — system works without it either way
    ui/                     app.py — Streamlit examiner console (Section 17 minimum set)
  tests/                    one or more pytest modules per gate + per module
  data/dev/                 dev-scale synthetic set (gitignored, regenerate via scripts/build_dev_dataset.py)
  data/scaled/               two full-scale CSE profiles (gitignored, scripts/build_scaled_datasets.py)
  .streamlit/config.toml     disables Streamlit's usage-telemetry ping (air-gapped requirement)
```

## Commands

```bash
# Install (from repo root, venv at .venv/)
source .venv/bin/activate && pip install -e .

# Dev server (examiner UI)
streamlit run src/satsa/ui/app.py

# Run all tests
pytest -q

# Run a single gate's tests
pytest tests/test_gate0_ocel.py -v

# Regenerate on-disk demo datasets
python scripts/build_dev_dataset.py
python scripts/build_scaled_datasets.py

# Lint / format
(not yet set up — no linter/formatter configured)

# Build / export
(no build step — pure Python; SBOM/offline packaging is Build Order Step 14, not yet done)
```

## Architecture Summary

See `docs/architecture.md` for the full pipeline diagram. In short: a synthetic CSE
generator produces an OCEL 2.0 log (objects: Alert/Case/Analyst/Queue/Asset). Moat 1
(structural detector + OKF DuckDB constraint compiler + Poisson/NB negative-space +
CUSUM/EWMA drift) fuses Anomaly->Finding->Concern into Evidence Packages. The sampling
layer (submodular selection + triple-sample budget split) turns those Concerns into a
budget-constrained review plan with a (1-1/e-epsilon) guarantee. Examiner verdicts feed
a debiased Beta-Binomial feedback loop. Moat 2 (DoWhy identification + closed-form
Cinelli-Hazlett robustness value) runs only on `TRUE_SUPERVISORY_FINDING` verdicts,
producing an explicit ACT/INVESTIGATE_MORE intervention recommendation. The Streamlit
UI wires all of the above together for an examiner: allocation explanation, finding
detail with authority/confidence/evidence-quality, object/process trace, verdict entry,
and an audit trail.

## Key Decisions & Why

See `docs/assumptions.md` for the full, dated log (9 entries as of this writing) — every
non-obvious decision is there with its reasoning, not just the outcome. Highlights:

| Decision | Choice | Reason |
|----------|--------|--------|
| OCEL 2.0 implementation | From scratch, not pm4py/ocpa | Both carry a copyleft (AGPL/GPL) dependency unsuitable for a government deliverable — entry 001 |
| Causal sensitivity analysis | Closed-form Cinelli-Hazlett Robustness Value, not DoWhy's own refuter | DoWhy's simulation-based refuter didn't discriminate confounded from unconfounded scenarios in this build's hands — entry 009 |
| Gate 4 metric | Per-finding-type recall, not aggregate | Aggregate recall was dominated by one numerous finding_type and actively favored the wrong baseline — entry 008 |
| UI framework | Streamlit | Internal examiner tool, pure Python, no separate frontend build, matches global CLAUDE.md's stack preference and the air-gapped requirement (telemetry disabled via `.streamlit/config.toml`) |

## Project-Specific Rules

- Every non-obvious decision or loophole gets logged in `docs/assumptions.md` BEFORE
  implementing the workaround (Section 1 of the build spec) — this is not optional
  process theater, it's how this project stays auditable.
- A gate is not "passed" until its pytest module is green. Weakening a test to make a
  gate pass is a regression, not a fix.
- No LLM anywhere in the analytical core. Every detector/statistic/causal
  estimate/finding/sampling decision is deterministic, statistical, or rule-based.
- Regenerate `data/dev/` and `data/scaled/` (via the two `scripts/build_*.py`) after
  any generator change — they're gitignored, not committed, always derived.

## Testing Approach

- **Test location**: `tests/`, one file per gate (`test_gate0_ocel.py` ... ) plus one
  per module for non-gate infrastructure (OKF compiler, negative space, drift, etc.)
- **Naming convention**: `test_<what_is_being_verified>` — descriptive enough to read
  as a sentence explaining the requirement, not just `test_1`/`test_2`
- **How to run a single test**: `pytest tests/test_gate1_reassignment.py -v`
- **How to run all tests**: `pytest -q`
- **CI command**: none set up yet (no CI configured for this repo)
- **Coverage target**: none formal — every gate's STOP condition must be a literal
  assertion, that's the real bar
- **Mock policy**: no mocks — every test runs the real generator, real OCEL
  read/write, real DuckDB queries, real statsmodels/dowhy fits. Where a theoretical
  guarantee is cited (submodular selection, robustness value), it's checked against a
  brute-force or closed-form reference, not trusted from the citation alone.
- **Fixture / seed strategy**: every `CSEProfile` has a fixed `seed` — generation is
  fully deterministic and reproducible
- **Async test strategy**: n/a, no async code in this project

## Env Vars Required

None. Fully local/offline — no API keys, no external services, no `.env` file needed.

## Context Files — Read On Demand

| File | Read when... |
|------|-------------|
| `docs/architecture.md` | System design, new modules, major refactors |
| `docs/ontology.md` | The verdict taxonomy, Anomaly->Finding->Concern, ABSTAIN reasons |
| `docs/expected_authority.md` | OKF authority classes, per-finding-type confidence sourcing |
| `docs/assumptions.md` | **Read this first** — every loophole, every real bug found during a gate, every design decision with its reasoning |
| `docs/validation_plan.md` | Which gates have passed, with the actual numbers |
| `docs/references.md` | Every external citation/dataset/library, with license and exact quote |

## Self-Improvement

After correcting Claude's behavior, say:
**"Update CLAUDE.md so you don't make that mistake again."**

*Generated by Claude on: 2026-09-25 | Updated as project evolves*
