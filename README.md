# SAT-SA — Supervisory Analytics Tool for SOC Assessment

**Smart India Hackathon** — `[PS ID: verify on portal — previously observed SIH26157]` · `[Theme: verify on portal — previously observed Blockchain & Cybersecurity]` · PS Category: Software

A local, offline analytics tool that helps NCIIPC examiners prioritise scarce review
hours across Critical Sector Entity (CSE) SOCs — by surfacing **execution gaps**
(documented controls that the actual event trail contradicts) and **negative space**
(evidence that should exist and doesn't), instead of relying on manual sampling or
static KPI dashboards.

It is **not** a SIEM, not a SOC, not a live-monitoring platform, and has no cloud/SaaS
or externally hosted AI dependency anywhere in its analytical core — see
[Deployment](#deployment--offline-guarantee) below for how that's actually verified,
not just claimed.

---

## Links

| What | Where |
|---|---|
| Presentation deck (PDF) | [`presentation/SAT-SA_SIH_deck.pdf`](presentation/SAT-SA_SIH_deck.pdf) |
| Prototype / demo video | **`[placeholder — will be updated before 30 Sept 2026]`** |
| Live/offline demo instructions | See [Quick start](#quick-start) below — runs entirely on your own machine |
| Official SIH problem statement (portal) | **`[placeholder — verify exact PS ID/theme/team on the SIH portal, will be updated before 30 Sept 2026]`** |
| Team ID / Team Name | **`[placeholder — will be updated before 30 Sept 2026]`** |
| OCEL 2.0 specification (data model this project implements) | <https://www.ocel-standard.org/2.0/ocel20_specification.pdf> |
| Submodular selection theory (Sviridenko 2004; Badanidiyuru–Vondrák 2014) | <https://www.sciencedirect.com/science/article/pii/S0167637703000622> · <https://theory.stanford.edu/~jvondrak/data/submod-fast.pdf> |
| Causal sensitivity analysis (Cinelli & Hazlett 2020) | <https://doi.org/10.1111/rssb.12348> |

---

## Quick start

Requires Python **3.11+**.

```bash
git clone https://github.com/abhinav-mittal33/Supervisory-Analytics-Tool-for-SOC-Assessment-SAT-SA-.git
cd Supervisory-Analytics-Tool-for-SOC-Assessment-SAT-SA-

python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e .

# Run the examiner UI
streamlit run src/satsa/ui/app.py
# opens http://localhost:8501 — five synthetic demo CSEs load automatically

# Run the test suite (142 tests, no mocks — real generator, real OCEL I/O,
# real DuckDB queries, real statsmodels/pgmpy fits)
pytest -q
```

No API keys, no `.env` file, no external service of any kind is required — this
project is designed to run fully air-gapped (see below).

### Try it with your own data

Open **Import data** in the sidebar. Upload `cases.csv`/`case_events.csv` (CSV or
JSON — only these two tables are required; `alerts`/`assets`/`analysts`/`queues` are
optional enrichment) or a SQLite database export. Choose whether this is a new
entity or a new dated batch for an existing one. Ingestion runs in the background —
the rest of the app stays fully usable while it processes — and the new data appears
under **Companies** the moment it's done.

Five ready-made heterogeneous sample exports (CSV, JSON, and SQLite, each with
different column-naming conventions) already ship in [`data/samples/`](data/samples/)
if you want to see the ingestion path work on real files immediately without
preparing your own.

---

## What's actually implemented

Every claim below is backed by a real, runnable test in [`tests/`](tests/). Where
something is a known gap or a synthetic-only demonstration, it's labelled as such,
not glossed over.

### Pipeline

```
Periodic CSE data (CSV / JSON / SQLite export; generic REST API adapter exists in
code, not yet a Streamlit upload option)
        │
        ▼
Ingestion → field mapping → data-reliability / ABSTAIN quality gate
        │                                    (missing required tables → reject;
        ▼                                     unknown event values → skipped,
Canonical object model → OCEL 2.0 (own          evidence-quality downgraded, not guessed)
implementation, validated, round-tripped)
        │                     │
        ▼                     ▼
  Observed world        OKF — Operational Knowledge Framework
  (what happened)       (what SHOULD happen: NCIIPC criteria,
        │                approved SOPs, statistical peer baselines)
        └───────────┬────────────┘
                     ▼
              MOAT 1 — Evidence Discovery
   (object-centric structural detectors, declarative constraint
    compiler, exposure-adjusted negative space, drift detection)
                     ▼
        Anomaly → Finding → Concern → Evidence Package
                     ▼
   Budgeted, provably-bounded, self-improving sampling layer
                     ▼
              Human examiner verdict (+ free-text notes,
                 captured in the audit trail)
                     ▼
   Beta-Binomial feedback (debiased: risk-selected vs.
        random-calibration tracked separately)
                     ▼
   MOAT 2 — Supervisory Intervention Decision Engine
     (runs on confirmed findings; a real, computed
      preliminary entity-wide signal is also shown
      before confirmation)
                     ▼
   Cross-CSE peer comparison + entity risk indicator
                     ▼
   Two-cycle trend classification (Gate 5)
                     ▼
   Offline HTML reports, JSON evidence export,
        immutable-per-session audit trail
```

### The two moats

- **Moat 1 — Evidence Discovery.** *"Where is this SOC behaving in a way that
  warrants supervisory attention?"* Combines a declarative rule compiler (DuckDB SQL
  over OCEL-derived tables), object-centric structural detectors (reassignment
  loops, fast-close outliers, repeated-alert-no-remediation, low-telemetry critical
  assets, template-driven investigation patterns), and exposure-adjusted
  Poisson/Negative-Binomial negative-space detection with empirical-Bayes shrinkage
  for small peer groups.
- **Moat 2 — Intervention Decision Engine.** *"Given a confirmed weakness, does a
  proposed intervention plausibly help, and how confident should we be?"* Backdoor-
  criterion causal identification (`pgmpy`) + OLS estimation (`statsmodels`) + a
  closed-form Cinelli–Hazlett robustness value — gated so it never runs on an
  unconfirmed finding, but a real (labelled **preliminary**) entity-wide signal is
  computed the moment enough data exists, so the engine isn't silent while waiting
  for manual confirmation.

### Validation gates — real numbers, not projections

| Gate | What it proves | Status |
|---|---|---|
| 0 | OCEL 2.0 round-trips with zero data loss, at dev and full scale | **PASSED** |
| 1 | Recovers a planted reassignment loop, rejects its matched hard negative | **PASSED** (precision=recall=1.000) |
| 2 | Full pathology + hard-negative benchmark, including detector-suppression logic | **PASSED** |
| 3 | Causal honesty: correctly withholds a confident answer when confounded | **PASSED** |
| 4 | Budgeted coverage beats a naive top-score baseline under a tight budget | **PASSED** (baseline recovers **0%** of a ground-truth-backed finding type at every tested budget; the coverage sampler recovers 40–100%) |
| 5 | Two-cycle trend correctly distinguishes improvement / displacement / regression / insufficient evidence | **PASSED** |

**What is *not* yet validated, stated plainly:** no real NCIIPC expert-review data
exists in this environment, so nothing here has been checked against real expert
verdicts — only against this project's own planted synthetic ground truth. The
expert-agreement mechanism (`src/satsa/validation/expert_agreement.py`) computes a
real confirmation-rate metric the moment real verdicts exist; it has not been fed
real ones yet.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | |
| Storage | SQLite (OCEL 2.0, own implementation) | `pm4py`/`ocpa` carry AGPL/GPL license terms unsuitable for a government deliverable |
| Analytical SQL | DuckDB | attaches an OCEL SQLite file directly, queries it with plain SQL |
| Statistics | `scipy`, `statsmodels` | Poisson/NB regression, OLS, CUSUM/EWMA |
| Causal inference | `pgmpy` (not DoWhy) | DoWhy's own import chain unconditionally pulls in GPL-3.0 `cvxopt` |
| Sampling | hand-implemented budgeted submodular selection | no external solver dependency needed |
| UI | Streamlit | single-process, pure Python, no separate frontend build |
| Tests | `pytest`, 142 tests, no mocks | real generator, real OCEL I/O, real DuckDB, real statistical fits |

Full dependency list + exact versions: [`pyproject.toml`](pyproject.toml).

---

## Deployment — offline guarantee

Zero cloud, zero external API, zero LLM anywhere in the analytical core. This is
verified by an automated regression test
([`tests/test_offline_deployment.py`](tests/test_offline_deployment.py)) that
monkeypatches every `socket.connect`/`connect_ex` call to raise immediately, then
runs the **entire pipeline** end to end anyway. The one deliberate, documented
exception is the generic REST/JSON ingestion adapter, which makes a real HTTP call
**only** when an examiner explicitly configures it against their own CSE's internal
system — tested only against a local in-process server, never a real endpoint.

---

## Repository layout

```
src/satsa/
  ingestion/     CSV / JSON / SQLite-export / generic-API adapters → canonical model
  ocel/          OCEL 2.0 model, JSON/SQLite I/O, schema validation (own implementation)
  okf/           Operational Knowledge Framework: rule schema + DuckDB constraint compiler
  moat1/         structural detectors, negative-space, drift, fusion
  sampling/      cost model, budgeted submodular selection, Beta-Binomial feedback
  moat2/         causal model, sensitivity, ACT/INVESTIGATE_MORE decision, real-data estimand
  portfolio/     cross-CSE peer comparison, entity risk indicator, submission history
  temporal/      two-cycle trend classification
  evidence/      Evidence Package schema, examiner verdict ontology, JSON export
  reporting/     self-contained offline HTML reports (supervisory + intervention suggestions)
  ui/            Streamlit examiner console (Companies, Peer comparison, Findings,
                 Import data, Review plan, Audit & Reports) + background ingestion jobs
tests/           one module per validation gate + one per component, 142 tests total
data/samples/    5 heterogeneous demo CSE exports (CSV, JSON, SQLite) — committed fixtures
presentation/    SIH presentation deck (PDF + source HTML)
```
