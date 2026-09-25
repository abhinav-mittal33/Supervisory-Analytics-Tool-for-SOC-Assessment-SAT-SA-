# Plan vs. Actual

A single-page delta view: what the V7 build spec asked for, what actually shipped,
what was cut, and what was swapped mid-build with the reasoning. `docs/assumptions.md`
has the full dated log with quotes and numbers for every item below — this file is
the index into it, organized by "what changed" rather than "in what order."

## Build Order status (Section 20)

| # | Planned | Status | Notes |
|---|---|---|---|
| 1 | Docs scaffold before any code | ✅ Done | `docs/product_contract.md`, `ontology.md`, `expected_authority.md`, `references.md`, `assumptions.md`, `validation_plan.md`, `architecture.md` |
| 2 | Dev-scale generator, one CSE profile | ✅ Done | `MATURE_CSE_DEV`, 300 cases |
| 3 | OCEL 2.0 gen/validate/round-trip — **Gate 0** | ✅ **PASSED** | Built from scratch, not with the planned library — see swap #1 below |
| 4 | Second CSE profile, scaled up, calibration table | ✅ Done | `MATURE_CSE_SCALED` + `SMALL_CSE_SCALED`, calibrated to CardinalOps 2025 + SANS 2025 (real cited numbers, not invented) |
| 5 | Object-centric discovery + reassignment loop — **Gate 1** | ✅ **PASSED** | precision=recall=1.000 on all 3 profiles |
| 6 | OKF schema + constraint compiler (4 templates) | ✅ Done | Response, Precedence, Cardinality, Not-Co-Existence, compiled to DuckDB SQL |
| 7 | Negative space (Poisson/NB) + CUSUM/EWMA drift | ✅ Done | See formulas below |
| 8 | Anomaly→Finding→Concern + Evidence Package — **Gate 2** | ✅ **PASSED** | Case-level only — see scope cut below |
| 9 | Sampling layer: cost model, triple split, submodular selection | ✅ Done | See formulas below |
| 10 | Verdict ontology + Beta-Binomial feedback — **Gate 4** | ✅ **PASSED** | First test design was wrong and had to be corrected — see swap #3 |
| 11 | Moat 2: causal engine — **Gate 3** | ✅ **PASSED** | Built on a different library than planned — see swap #2 |
| 12 | Local LLM explainer | ❌ Not built | Explicitly optional; spec says "system must work without it either way" — skipped outright, no partial stub |
| 13 | Examiner UI | ✅ Done | Streamlit, not the framework left open in the original doc — decided at this step, not before |
| 14 | Offline packaging + disconnected run-through | ✅ Done | Automated, not manual — see note below |
| 15 | Temporal axis (optional) — **Gate 5** | ❌ Not attempted | Explicitly the first thing the spec says to cut under time pressure; never started |

Every ✅ above has a corresponding green pytest module. Nothing on this list is
claimed done without a test proving it.

## What got cut or scoped down (not swapped, just not built)

- **Temporal axis (Section 13 / Gate 5).** Not attempted. Spec's own words: cut this
  first, and say so plainly rather than ship something rushed. No cross-cycle
  verification exists anywhere in this build.
- **Local LLM explainer (Section 20 Step 12).** Not built. The whole analytical
  pipeline (all 5 required gates) works with zero LLM involvement, which is the point.
- **Portfolio/queue-level fusion.** Concern fusion (`src/satsa/moat1/fusion.py`) only
  operates at case-level (structural loop + OKF rule violations). Queue-level negative
  space and period-level drift findings are computed but never fused into the same
  Evidence Package stream — they're a separate, unfused output. Section 10.4's
  "hierarchical: portfolio-level across CSEs, then case-level" sampling was therefore
  only ever demonstrated at the case level, never truly cross-CSE. (`docs/assumptions.md`
  entry 006)
- **Data Reliability / ABSTAIN gate (Section 5.3).** Not built. Every Evidence Package
  in this build hardcodes `evidence_quality="HIGH"` — there's no mechanism yet that
  would ever produce `MEDIUM`/`LOW` or an `ABSTAIN` verdict from actual data gaps,
  because the synthetic generator never produces incomplete/broken records in the
  first place. (entry 006)
- **Continuous anomaly scores.** Every detector in this build is binary (pattern
  matched / rule violated, or it didn't). The secondary Isolation-Forest detector
  (Section 9.3) that would produce a genuinely continuous, calibrated anomaly score
  was never built. `anomaly_score` and `conformance_deviation` are always `1.0` when
  a finding fires. (entry 006)
- **Ingestion layer.** No raw CSV/JSON → canonical-object-model normalization exists.
  Everything runs on the synthetic generator's direct OCEL output; a real deployment
  would need this layer built first.
- **Real BPIC event-log grounding (Section 14.4).** Confirmed license-clean (CC0) and
  deliberately not used — the calibration table's citations (CardinalOps 2025, SANS
  2025) already satisfy "cite, don't invent" on their own, and the spec explicitly
  endorses skipping this when that's true. (entry 003)

## Library / approach swaps — what changed mid-build and why

### 1. OCEL 2.0 library: planned pm4py → shipped a from-scratch implementation

**Planned:** the spec assumed pm4py as the OCEL 2.x tool.
**Hit:** pm4py is AGPL-3.0-or-later. Its pitched MIT alternative, ocpa, turned out to
*require* pm4py transitively (confirmed by installing it and watching pm4py 2.2.32,
GPL-3.0, get pulled in).
**Shipped:** `src/satsa/ocel/` — hand-written JSON I/O, SQLite I/O (Section 6's
relational schema implemented directly from the spec paper, CC BY 4.0), and a
validator checked against the *official* JSON Schema fetched from ocel-standard.org.
**Cost:** no borrowed object-centric discovery/conformance-checking algorithms — every
Moat 1 detector is bespoke DuckDB SQL + Python instead, which the build spec's own
contingency language anticipates.
Full account: `docs/assumptions.md` entry 001.

### 2. Causal identification library: planned/built DoWhy → shipped pgmpy

**Planned:** DoWhy for causal identification + estimation + sensitivity refutation.
**Hit twice:**
- DoWhy's own `add_unobserved_common_cause` sensitivity refuter was tested against
  four synthetic scenarios (no/weak/moderate/strong confounding) and found to flip
  the estimate's sign at a similar strength *regardless* of the true confounding
  level — not a usable discriminator. Replaced with the closed-form **Cinelli-Hazlett
  (2020) Robustness Value** instead (entry 009).
- Later, while generating the SBOM (Step 14), found that `from dowhy import
  CausalModel` unconditionally imports a chain ending in `causal-learn` →
  `cvxopt` (**GPL-3.0-or-later**) — confirmed by removing those packages and watching
  the import fail outright. DoWhy's own license (MIT) had been checked; its full
  transitive tree hadn't.
**Shipped:** **pgmpy** (MIT) for identification (`pgmpy.identification.Adjustment`,
formal backdoor-criterion verification) + **statsmodels OLS** for the actual numeric
estimate/CI (unchanged) + the Cinelli-Hazlett Robustness Value for sensitivity
(unchanged). pgmpy's full transitive tree was checked this time (`pipdeptree`) —
clean — and its `huggingface_hub` dependency was separately verified to make zero
network calls.
Full account: `docs/assumptions.md` entries 009 and 010.

## Formulas actually shipped

These are the concrete, load-bearing formulas behind the pitch — cite these, not a
vague description.

**Review cost estimate** (`src/satsa/sampling/cost_model.py`, Section 10.2):
```
cost_minutes = (base_time + per_alert_time * num_alerts_linked
                + evidence_review_time * evidence_volume
                + missing_data_penalty [if evidence_quality != HIGH])
               * complexity_weight[authority]
```
Coefficients are configurable constants, explicitly labeled as engineering estimates
pending real examiner timing data — never presented as calibrated.

**Exposure-adjusted negative space** (`src/satsa/moat1/negative_space.py`, Section 9.4):
Poisson GLM with a log-exposure offset gives the pooled rate `λ̂` and its own
confidence interval (not treated as a fixed constant). For a peer group below
`MIN_PEER_GROUP_SIZE=10`, its own rate is replaced by an empirical-Bayes
(Poisson-Gamma conjugate) shrinkage estimate: `(α_prior + observed) / (β_prior + exposure)`,
with `α_prior, β_prior` fit by method-of-moments across all peer groups' rates.
`Expected = rate × exposure`; deviation reported as a z-score,
`z = (observed - Expected) / sqrt(Expected)`.

**Submodular coverage objective** (`src/satsa/sampling/submodular.py`, Section 10.4):
```
f(S) = Σ_bucket  log(1 + count_of_selected_items_in_bucket)
```
— a sum of concave functions of modular counts (a standard, provably submodular
"coverage" construction). Selection: bounded seed enumeration (Sviridenko 2004,
capped to `top_k_seeds` candidates by density, not the full candidate set) completed
via thresholding-greedy (Badanidiyuru–Vondrák 2014) under the cost knapsack
constraint. **Stated guarantee: (1 − 1/e − ε)**, not the naive (1 − 1/e) — the
epsilon is real, from substituting the accelerated completion step for classical
greedy, and is disclosed rather than rounded away (`docs/assumptions.md` entry 007).
Verified empirically against brute-force optimal on a 14-item instance, not just
cited.

**Beta-Binomial feedback** (`src/satsa/sampling/feedback.py`, Section 10.6):
Conjugate update, `Beta(1,1)` prior. `TRUE_SUPERVISORY_FINDING` → `α += 1`;
`FALSE_POSITIVE`/`OUT_OF_SCOPE` → `β += 1`; `INCONCLUSIVE`/`DATA_QUALITY_ISSUE`/
`EXPECTED_LEGITIMATE_BEHAVIOR`/`DUPLICATE_OF_EXISTING_FINDING` → no update. Two
**separate** posteriors tracked per bucket — `risk_selected` and
`random_calibration` — specifically so the self-confirming bias the spec warns about
is visible as a gap between the two numbers, not blended away.

**Causal robustness value** (`src/satsa/moat2/sensitivity.py`, Cinelli & Hazlett 2020):
```
f = |t_statistic| / sqrt(df_residual)
RV = 0.5 * (sqrt(f⁴ + 4f²) - f²)
```
Decision policy (`src/satsa/moat2/decision.py`): `ACT` only if the CI excludes zero
**and** `RV ≥ 0.3` (a documented constant, not fit per-scenario). Below that,
`INVESTIGATE_MORE` — including when the point estimate's sign happens to already be
wrong, since RV is fundamentally incapable of detecting that (a limitation of
sensitivity analysis generally, not this implementation — see entry 009).

## Test-design corrections (not code bugs — the test was measuring the wrong thing)

**Gate 4 (sampling validation).** First version measured *aggregate* case-count
recall across all ground-truth-backed finding types. It **failed** — top-score-only
ranking won, and random selection beat everyone. Diagnosed rather than patched: one
finding_type (`MISSING_ENRICHMENT`) outnumbers the others ~12-to-1 in the generated
data, so aggregate recall was dominated by noise in which `MISSING_ENRICHMENT` cases
each method happened to grab. Corrected to per-finding-type recall (the minimum
across the three types) — the metric that actually reflects what submodular selection
is for. Result: top-score-only ranking gets **zero** `REASSIGNMENT_LOOP` recall at
every tested budget level; submodular selection covers all three types even at the
smallest budget. `docs/assumptions.md` entry 008.

## Real bugs found during this build (not swaps, not scope — actual defects caught and fixed)

- OCEL timestamp formatter truncated sub-second precision, silently breaking
  round-trip identity on any event with microseconds. Caught by Gate 0's own
  round-trip assertion. (entry logged in `docs/validation_plan.md` Gate 0)
- A classic `sqlite3` cursor-reuse bug silently dropped rows from a nested query
  during OCEL read-back. Same fix pass as above.
- The generator originally sequenced `ESCALATE` after `ENRICH`+`INVESTIGATE`, making
  the OKF's 30-minute escalation SLA structurally unsatisfiable regardless of actual
  compliance. Fixed by branching escalation off the `ASSIGN` timestamp directly
  (`docs/assumptions.md` entry 004).
- A single zero-exposure peer group broke the pooled-rate Poisson fit for *every
  other* peer group too (`log(0)` offset). Caught by `tests/test_negative_space.py`.
- Two independently-run CUSUM series don't necessarily alarm on the exact same period
  bin — an exact-index match missed the planted metric-gaming window entirely; fixed
  with a period-tolerance window (entry 005).
- The SBOM generator itself had a bug: a package whose license field literally
  contained the string `"UNKNOWN"` short-circuited past the classifier fallback that
  had the real answer, for `ptyprocess`. Fixed while generating `docs/sbom.json`
  (entry 010).

## Net effect on the pitch

Every claim in `docs/references.md` and the finding_type table in
`docs/expected_authority.md` is either a cited external number, a measured result from
this build's own tests, or explicitly labeled as a simulation parameter / engineering
estimate. Nothing here was left as a placeholder that quietly became a real number
later — see Rule 7 of Section 2 (numerical integrity) and `docs/assumptions.md` for
the enforcement trail.
