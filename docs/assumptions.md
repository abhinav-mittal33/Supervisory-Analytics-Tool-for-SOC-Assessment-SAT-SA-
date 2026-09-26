# Assumptions & Loophole Log

Per the build spec's Section 1 protocol: every gap the spec doesn't fully resolve is
logged here — what was hit, why it's unresolved, the options considered, and what was
decided — before implementation, not after.

---

## 001 — OCEL library licensing (resolved 2026-09-25)

**Hit:** The spec names pm4py as the presumed OCEL 2.x tool. `pip show pm4py` on the
actually-installed package confirms `License-Expression: AGPL-3.0-or-later`. `ocpa`
(pitched as an MIT-licensed alternative) was checked next — its own METADATA says
`License: MIT`, but `pip show ocpa` lists `Requires: jsonschema, pm4py, setuptools`,
and installing it pulled down `pm4py==2.2.32` transitively, licensed **GPL-3.0** (not
even AGPL). So there is no path through either library that avoids a copyleft
dependency landing in the shipped application.

**Why unresolved by the spec:** Section 7.3 says "verify tooling before relying on
it" for *capability*, but says nothing about license fitness for a government
deliverable — a real gap given this product's audience (NCIIPC) and the reject-list's
implicit expectation of a clean, deployable artifact.

**Options considered:**
1. Use pm4py directly, document the AGPL obligation as a known tradeoff.
2. Zero third-party OCEL library — implement OCEL 2.0 read/write/validate directly
   against the public standard's own published schema files.

**Decision:** Option 2, chosen by the user. Implemented against the *actual* published
artifacts, fetched directly from the standard body (not reconstructed from memory or
copied from a GPL-licensed reference implementation's schema files):
- JSON validation schema: `https://www.ocel-standard.org/2.0/ocel20-schema-json.json`
  (draft-07 JSON Schema, no license header found on the file itself — treated as a
  published standard artifact, not software, and used only as validator input data,
  never redistributed as part of any code path that executes it as a library).
- Relational (SQLite) implementation: derived from Section 6 of the OCEL 2.0
  Specification paper (Berti et al., arXiv:2403.01975, **CC BY 4.0** — explicit
  attribution given in `docs/references.md`), table structure implemented by hand:
  `event_map_type`, `object_map_type`, `event`, `object`, one `event_<type>` table
  per event type, one `object_<type>` table per object type (with the
  `ocel_changed_field` attribute-history pattern), `event_object` (E2O), `object_object`
  (O2O).
- Validation is implemented as our own code (`src/satsa/ocel/validate.py`): JSON
  Schema check via `jsonschema` (MIT-licensed, standalone, no pm4py dependency) for
  the JSON format, and direct SQLite structural/FK/PK checks (via `sqlite_master`,
  `PRAGMA foreign_key_list`, `PRAGMA table_info`) for the relational format, since no
  license-clean off-the-shelf OCEL 2.0 validator was found.

**Cost of this decision:** Section 7.3's "native object-centric pattern-query
capability" and "object-centric discovery/conformance-checking" library support are
foregone. Per the spec's own contingency language ("otherwise implement a documented,
tested fallback and never claim query-tool-backed results when the implementation is
actually the fallback"), Moat 1's structural/statistical detectors (Section 9) are
built as bespoke DuckDB SQL + Python, which was already the plan for the OKF
constraint layer (Section 6.5) regardless of this decision — so the marginal cost is
limited to discovery/conformance-checking convenience, not core detector capability.

---

## 002 — Process-native causal library gap (open, revisit at Step 11)

**Hit:** No mature, license-clean, off-the-shelf Python library performs causal
estimation natively over object-centric event-log control-flow structure (verified via
research: this is active academic territory — decision-point extraction, ARE
algorithm, etc. — not a packaged tool).

**Decision (updated at Step 11, see entry 009 for what actually shipped):** DoWhy
confirmed installed, MIT-licensed (`pip show dowhy` -> `License: MIT`, version 0.14).
Used for formal causal identification (`CausalModel.identify_effect`) — its actual
strength. Its own simulation-based sensitivity refuter (`add_unobserved_common_cause`)
was tried, found unsuitable for this build's data, and replaced with a closed-form
method instead. Full account in entry 009.

---

## 003 — BPIC dataset license check (resolved 2026-09-25)

**Hit:** Section 14.4 asks for a real, public, structurally-adjacent event log (BPIC
2013/2014 incident/ITSM logs) to anchor the generic case-lifecycle skeleton's timing
and branching statistics.

**Resolved:** Checked the BPIC 2013 dataset page directly on 4TU.ResearchData — it
carries no dataset-specific license override, so it falls under 4TU's General Terms
of Use, which is **CC0** (public domain dedication) for any dataset "where no other
licence is given." No licensing blocker. Recorded in `docs/references.md`.

**Decision:** Deferred anyway, not because of licensing but because Section 14.4 itself
frames the BPIC pull as an optional additional grounding layer and explicitly endorses
proceeding on calibrated-synthetic parameters alone (Section 14.2-14.3) when that's
sufficient. The calibration table populated at Build Order Step 4
(`docs/references.md`) anchors every generator rate to a cited, directly-quoted public
benchmark (CardinalOps 2025 State of SIEM Detection Risk report; SANS SOC Survey
2025), which meets the spec's actual requirement — "don't invent numbers" — without
needing the BPIC logs. Revisit only if a future step needs real timing/branching
statistics for the case-lifecycle skeleton specifically, which the hand-modeled
lifecycle hasn't needed so far.

---

## 004 — ESC-CRIT-001 time_constraint reference point (resolved 2026-09-25)

**Hit:** The build spec's own worked OKF example (Section 6.3) gives ESC-CRIT-001 a
`time_constraint` of "<=30 minutes" but doesn't specify what that 30 minutes is
measured *from* — the triggering condition becoming true has no single unambiguous
event in an object-centric model (case creation? alert raised? assignment?).

**Decision:** Implemented the RESPONSE template's time_constraint as measured from the
case's earliest case-linked event (in this generator's lifecycle, that's ASSIGN) to
the expected event's (ESCALATE) timestamp. Chose this over "case open" or "alert
raised" because those aren't case-linked events in the `case_events` view
(`src/satsa/okf/compiler.py`) — ALERT_RAISED relates to an Asset, OPEN_CASE relates to
an Alert, neither carries a `*_for_case` E2O qualifier to the Case object itself.

**A real bug this surfaced:** the generator originally emitted ESCALATE *after*
ENRICH+INVESTIGATE, which alone can take 25-180 minutes — meaning every case, compliant
or not, would violate a 30-minute SLA measured from any reasonable reference point.
Fixed by moving the escalation branch to fire off the ASSIGN timestamp directly,
independent of the enrich/investigate timeline — which also happens to be more
realistic SOC practice (a CRITICAL alert on a high-value asset gets escalated in
parallel with, not strictly after, deeper investigation). Caught by inspecting the
generator's own timing arithmetic while implementing the RESPONSE template, before any
test was run against it — fixed in the generator first, then verified via an
independent Python oracle for each OKF template asserted to agree with the
DuckDB-compiled result (`tests/test_okf_compiler.py`).

---

## 005 — Metric-gaming/displacement labeling and a real statistical-power finding (resolved 2026-09-25)

**Hit:** Section 9.2 says CUSUM/EWMA run in parallel on a KPI series and a linked
invariant series should output `POTENTIAL_EXECUTION_GAP` / `POTENTIAL_DISPLACEMENT`,
but never actually defines which label applies when — both are just named as the
output category.

**Decision:** A period where the invariant alarms DOWN with a KPI alarm UP nearby (see
below on "nearby") is labeled `POTENTIAL_DISPLACEMENT`; a period where the invariant
alarms DOWN with no corresponding KPI alarm is `POTENTIAL_EXECUTION_GAP`. Implemented
in `src/satsa/moat1/drift.py::detect_displacement`.

**A real design problem this surfaced, not just a labeling question:** two
independently-run CUSUM series reacting to the *same* underlying planted window don't
necessarily cross their own alarm thresholds on the exact same period bin — each has
its own noise and its own accumulate/reset history. An exact-index match between
`kpi_up` and `inv_down` alarm sets missed the planted gaming window in
`tests/test_drift.py`'s own end-to-end test even though both series clearly showed the
right shape on inspection. Fixed by adding a `period_tolerance` (default 1 bin) to the
matching logic rather than forcing exact alignment.

**A real statistical-power finding, not a bug:** at the dev-scale profile (300 cases),
the escalation-duty population is so sparse per week (~1 case/week, since
CRITICAL-severity AND HIGH/CRITICAL-asset cases are themselves a small fraction of all
cases) that the weekly KPI rate is pure Bernoulli noise — no amount of CUSUM tuning
recovers a signal that isn't there. The drift end-to-end test uses the *scaled* profile
(`MATURE_CSE_SCALED_DRIFT_DEMO`) specifically for this reason. This is worth carrying
forward honestly into the pitch: metric-gaming detection has a real minimum-exposure
floor, just like the negative-space detector's own `MIN_PEER_GROUP_SIZE` — it isn't
free at any population size.

---

## 006 — Fusion scope: case-level only, deferred Data Reliability gate (resolved 2026-09-25)

**Hit:** Section 5.2's Anomaly->Finding->Concern fusion and Section 11's Evidence
Package don't specify a unit of analysis, but the detectors built so far operate at
three different granularities — case-level (structural loop detector, OKF Response/
Precedence/Cardinality violations), queue-level (negative space), and period-level
(CUSUM/EWMA drift). A single Concern list needs one key to be gate-testable at all.

**Decision:** Scoped `src/satsa/moat1/fusion.py` to case-level fusion only for Build
Order Step 8 / Gate 2, since Gate 2's own requirement (recover planted pathologies,
reject the full hard-negative set) is defined entirely in terms of the case-level
detectors already Gate-1-validated. Queue-level negative-space and period-level drift
findings remain a separate, not-yet-fused Concern stream — revisit when the sampling
layer's hierarchical scheme (Section 10.4: portfolio-level across CSEs, then
case-level within each) gives them a natural second key to fuse against.

**Also deferred, flagged rather than hidden:** every Evidence Package in this build
uses `evidence_quality="HIGH"` unconditionally (`src/satsa/moat1/fusion.py`'s
`DEFAULT_EVIDENCE_QUALITY`) and every detector's `anomaly_score`/
`conformance_deviation` is binary (1.0 or the case produces no signal), never a
continuous magnitude. Both are honest simplifications, not silent ones: the Data
Reliability/ABSTAIN gate (Section 5.3) that would make evidence_quality vary with
actual data completeness doesn't exist yet in this build, and no detector built so far
(structural match, OKF rule violation) is the kind of thing that naturally produces a
continuous score — that's the secondary Isolation-Forest detector's job (Section 9.3),
which Gate 2 doesn't require.

---

## 007 — Submodular selection: which guarantee is actually being claimed (resolved 2026-09-25)

**Hit:** Section 10.4 asks for "the near-linear-time thresholding-greedy variant
(Badanidiyuru & Vondrák, 2014)" while also citing Sviridenko (2004) for the exact
(1-1/e) theorem, and says to "put the exact ratio and both citations on the slide, not
a vague 'provably near-optimal.'" But Sviridenko's (1-1/e) result is specifically
proven for a seed-enumeration-over-the-FULL-candidate-set + classical-greedy-
completion structure; B&V's contribution is a different, faster completion
subroutine. Naively combining "Sviridenko's ratio" with "B&V's speed" without being
precise about what changes when you swap the completion method would be exactly the
kind of unearned claim Section 2's claim-discipline principle forbids.

**Decision:** State the guarantee as **(1-1/e-epsilon)**, not the exact (1-1/e) —
this is what both papers are actually cited for in the literature when combined this
way, and it's what `src/satsa/sampling/submodular.py` actually verifies empirically
(`tests/test_submodular.py`, brute-force comparison on a small instance) rather than
just asserts. Two further honesty notes, not swept under the rug:
1. The seed pool is capped at `top_k_seeds` candidates (ranked by singleton density),
   not the full candidate set — this is what makes the algorithm near-linear instead
   of the naive O(n^5), but it means the seed-enumeration step is itself an
   approximation of Sviridenko's exact method, not a literal implementation of it.
2. No formal proof was re-derived for this specific combination (capped-seed
   enumeration + thresholding-greedy completion) — the (1-1/e-epsilon) claim rests on
   citing both papers' individually-proven results and combining them the way the
   build spec itself instructs, plus this build's own empirical verification, not on
   an independently reproduced proof. Stated as such, not oversold.

---

## 008 — Gate 4's first metric was the wrong one (resolved 2026-09-25)

**Hit:** The first version of `tests/test_gate4_sampling.py` measured *aggregate*
case-count recall (fraction of all ground-truth-backed cases recovered, summed across
finding types) to compare submodular selection against top-score-only ranking. That
test **failed** — top-score-only actually won on that metric, and random selection
came out on top of everyone. Not a bug in the algorithm; a wrong choice of metric.

**Why it failed, diagnosed rather than patched away:** in the generated dataset,
`MISSING_ENRICHMENT` outnumbers `ESCALATION_SLA_VIOLATION` and `REASSIGNMENT_LOOP`
roughly 12-to-1 (306 vs. 23-25 cases). Aggregate recall is dominated by whichever
method happens to grab marginally more `MISSING_ENRICHMENT` cases — pure noise, since
which specific `MISSING_ENRICHMENT` cases get picked doesn't matter much (they're all
in the same bucket, similar cost/score). It was never actually measuring the thing
submodular selection is supposed to be good at.

**What the algorithm is actually for, verified directly:** printing the per-finding-
type breakdown at the smallest tested budget showed top-score-only ranking selects
`{ESCALATION_SLA_VIOLATION: 23, MISSING_ENRICHMENT: 8, REASSIGNMENT_LOOP: 0}` — it
exhausts the entire budget on the single highest-scoring bucket
(`ESCALATION_SLA_VIOLATION`, `MANDATORY` authority x `Escalation` capability
materiality) before ever touching the lowest-scoring one. Submodular selection
selects `{MISSING_ENRICHMENT: 12, REASSIGNMENT_LOOP: 10, ESCALATION_SLA_VIOLATION: 10}`
— genuinely balanced across all three. That's the real, demonstrable value of
diminishing-returns bucket-aware selection: not higher raw recall on whichever
finding_type happens to be numerous, but *not starving the rare-but-real ones*.

**Decision:** Rewrote the gate's core assertion around per-finding-type recall (the
minimum across the three ground-truth-backed types), not aggregate recall. Aggregate
recall is still reported (printed) for context, since it's not meaningless, just not
the right thing to assert on. This is exactly Section 1's own instruction in action:
"a fix that makes a gate pass by weakening what the gate tests is a regression, not a
fix" — the fix here was changing what was being measured to match what the gate is
actually supposed to prove, not loosening the threshold on the wrong metric until it
passed.

---

## 009 — Moat 2 sensitivity analysis: DoWhy's built-in refuter tried and replaced (resolved 2026-09-25)

**Hit:** Section 12 requires quantifying "how large an unobserved confounder's effect
would need to be to flip the estimated direction — a number, not a caveat sentence,"
and Gate 3 requires validating this on synthetic data with one confounder deliberately
withheld. The natural first approach: DoWhy's `refute_estimate(...,
method_name="add_unobserved_common_cause")`, which simulates adding a hypothetical
confounder at a configurable `effect_strength_on_treatment`/`effect_strength_on_outcome`
and reports the new estimate.

**What was actually tried and measured, not assumed:** built four synthetic
scenarios — no confounding, weak confounding, moderate confounding, strong confounding
deliberately tuned to flip the naive estimate's sign — and swept
`effect_strength` from 0.0 to 1.0 in each. Result: **the sign flipped at a similar,
fairly low simulated strength (roughly 0.2-0.6) in every single scenario, including
the one with zero real confounding.** This method's `effect_strength` parameter, at
least for a binary treatment/outcome DGP at this effect size and sample size, is not
a discriminator between "genuinely fragile" and "genuinely robust" in this build's
hands — the simulated confounder is simply a strong perturbation regardless of
context. Documenting this as a real, useful negative result rather than quietly
picking whichever parameter happened to make one test pass — that would have been
exactly the kind of unearned claim Section 2 forbids.

**What replaced it:** the Robustness Value (RV) from Cinelli & Hazlett (2020),
"Making Sense of Sensitivity: Extending Omitted Variable Bias," JRSS-B 82(1) — a
closed-form function of the treatment coefficient's t-statistic and residual degrees
of freedom (`src/satsa/moat2/sensitivity.py::robustness_value`), no simulation, no
arbitrary strength parameter. Verified it behaves sensibly: RV increases monotonically
with the true effect's statistical strength (checked across true_effect =
0.3/0.6/1.0/2.0/4.0 with zero confounding: RV = 0.07/0.15/0.22/0.38/0.52).

**The fundamental limit, stated plainly rather than glossed over:** RV measures how
robust the *current* estimate is to being explained away by a hypothetical confounder
— it is provably incapable of detecting whether the current estimate is *already*
biased by one that's actually there (if that were detectable from the data, the
confounder wouldn't be "unobserved"). No sensitivity method, DoWhy's or this one, can
close that gap; it's a property of observational causal inference, not an
implementation shortfall. What RV *does* give: a principled reason to refuse
confidence in weak-to-moderate effects specifically, which is exactly where residual
confounding risk matters most.

**Superseded note:** the identification step described here originally went through
DoWhy; it was later replaced with pgmpy after a real GPL-licensing discovery — see
entry 010. The estimation/sensitivity/decision logic below is unaffected by that
change.

**Decision engine policy that follows from this:** `src/satsa/moat2/decision.py`
outputs `ACT` only when the CI excludes zero AND RV clears a documented, conservative
constant (`ROBUSTNESS_VALUE_THRESHOLD = 0.3`, chosen once, not fit per-scenario) —
otherwise `INVESTIGATE_MORE`. Gate 3 passes on two scenarios that exercise both
directions, not one that's trivially always conservative: a strong, clean,
unconfounded effect (RV=0.519) correctly reaches `ACT` with the right sign, and a
moderate effect deliberately confounded strongly enough to flip the naive
withheld-confounder estimate's sign (reference-with-confounder=+0.099,
without-confounder=-0.165) correctly stays below the RV bar (0.171) and returns
`INVESTIGATE_MORE` — never presenting the flipped, wrong-signed estimate as
actionable. `tests/test_gate3_causal_honesty.py`.

---

## 010 — DoWhy dropped: unconditional GPL transitive dependency (resolved 2026-09-25)

**Hit:** While generating the SBOM at Build Order Step 14, `cvxopt`'s license field
printed GPL text verbatim ("This program is free software... GNU General Public
License... version 3"). `cvxopt` was not a direct dependency of this project — traced
it and found it comes in via `dowhy -> dowhy.gcm -> causallearn's KCI independence
test -> cvxopt`. Confirmed this is not optional or lazily imported: uninstalling
`causal-learn`/`cvxopt`/`cvxpy` and running `from dowhy import CausalModel` failed
immediately with `ModuleNotFoundError`, because `dowhy/__init__.py` unconditionally
imports `dowhy.causal_model`, which unconditionally imports `dowhy.causal_graph`,
which unconditionally imports `dowhy.gcm`, which unconditionally imports the KCI
kernel-independence-test module. There is no way to `pip install dowhy` and merely
`import CausalModel` without pulling in a GPL-3.0-or-later package.

**Why this wasn't caught at Step 11:** `pip show dowhy` was checked and returned
`License: MIT` — true for DoWhy itself, but a top-level license check is not the same
as auditing the full transitive tree. This is exactly the same category of gap as
entry 001 (pm4py's AGPL status was checked directly; ocpa's transitive pm4py
dependency was checked directly; DoWhy's transitive dependency was NOT checked with
the same rigor at the time). Lesson applied going forward: `docs/sbom.json`
(`scripts/generate_sbom.py`) now exists specifically so every future dependency
addition gets checked against the FULL installed tree, not just its own PyPI page.

**Options considered:**
1. Hand-write the backdoor-adjustment identification ourselves (no library).
2. Find a better-fit, license-clean library and use that instead.

**Decision:** Option 2 — **pgmpy** (MIT-licensed, confirmed via `pip show`), after
researching current alternatives rather than defaulting straight to "write it
ourselves": pgmpy has a dedicated `pgmpy.identification.Adjustment` class implementing
exactly the backdoor-criterion identification this build needs (`DAG` with
`roles={"exposures":..., "outcomes":...}` -> `.identify()` -> a verified adjustment
set), is a better structural fit than DoWhy was (DoWhy is oriented around a much
broader general framework — refutation methods, multiple identification strategies,
GCM, IV, frontdoor — of which this build was actually using perhaps 5%: one
identification call), and its full transitive dependency tree
(`pipdeptree --packages pgmpy`) was checked end to end this time: huggingface_hub,
networkx, numpy, pandas, scikit-learn, scipy, statsmodels, tqdm, joblib, and their own
dependencies — all MIT/BSD/Apache, zero copyleft. `huggingface_hub`'s presence was
specifically checked for a different concern (Section 18 air-gapped compliance, not
licensing) by importing pgmpy's causal-inference classes with every `socket.connect`
call monkeypatched to raise — zero network calls attempted (see
`tests/test_offline_deployment.py`, which now covers this permanently as an automated
regression test, not a one-time manual check).

**What changed in code:** `src/satsa/moat2/causal_model.py` rewritten against pgmpy's
`Adjustment` API instead of `dowhy.CausalModel`. `sensitivity.py` and `decision.py`
(the closed-form Cinelli-Hazlett robustness value and the ACT/INVESTIGATE_MORE policy,
entry 009) are completely unaffected — that logic never depended on DoWhy in the
first place, only the identification step did. Gate 3 re-run after the swap: same
two scenarios, same numbers, still passes (55/55 tests total).

---

## 011 — Ingestion layer built; API adapter is a deliberate, scoped exception to
"zero network calls" (2026-09-25)

**Hit:** The official PS functional requirements (Section 4) are narrower than
`src/satsa/ingestion/`'s original stub description implied — not "parse any format,"
specifically: (1) ingest from multiple CSEs, (2) support CSV, JSON, database exports,
and APIs "where available." Built exactly that: `adapters/{csv,json,db,api}_adapter.py`
behind one `SourceAdapter` interface, `mapping/field_mapper.py` (auto-suggested,
always-overridable per-field mapping — never a silent guess), `quality/validator.py`
(a hard ABSTAIN gate on missing required fields, soft "reduced capability" notes on
missing optional tables — never fabricates a value), `normalization/canonical.py`
(produces the exact object/event vocabulary `generator/generate.py` already produces,
so every existing Moat 1/OKF/sampling detector consumes ingested data unmodified).

**The judgment call:** `api_adapter.py` makes a real HTTP GET call — the one place in
this codebase that does. This is not a violation of the Section 18 air-gapped/offline
mandate: `tests/test_offline_deployment.py` proves the *analytical core* (Moat 1,
OKF, sampling, Moat 2) makes zero network calls of its own, unconditionally, every
run. The API adapter is different in kind — it is an examiner-configured connection
to *that CSE's own* internal case-management API, supplied at ingestion time
(`base_url`, optional bearer token), never a hardcoded external endpoint and never a
call this build initiates on its own. Real deployment is still fully air-gapped
network-wide (Section 18(i)-(ii)): the adapter would point at a system reachable
inside NCIIPC's own controlled network, not the public internet — this build makes
no claim otherwise and doesn't need internet access to exercise the CSV/JSON/DB path,
which covers every demo dataset.

**How it's tested without breaking the offline guarantee:** `tests/test_ingestion_api.py`
runs a real HTTP round-trip, but only against a local, in-process `http.server` bound
to `127.0.0.1` — never a real external endpoint. This keeps
`tests/test_offline_deployment.py`'s socket-block regression test meaningful: that
test still covers the analytical core exactly as before; the API adapter is
intentionally outside its scope, by design, not by oversight.

**Three demo CSE fixtures** (`data/samples/cse_{a_csv,b_json,c_sqlite}/`) prove the
actual claim end to end: three files with three different column-naming conventions
(`assigned_to`/`incident_number`/`handler` all meaning "who owns this case") ingest
into one canonical model, and `tests/test_ingestion_pipeline_end_to_end.py` proves the
existing, unmodified `moat1.fusion.fuse()` recovers a planted reassignment loop from
the real-shaped CSV fixture — not just "adapter runs without throwing."

**Streamlit UI** (`ui/app.py`) gained a source-mode toggle: built-in synthetic profile
(unchanged) vs. upload-your-own-CSE-data, with a field-mapping confirmation step
(closed dropdown of detected columns only — never a free-text field, so nothing here
can be interpolated into a query or file path) before ingestion runs. Verified with a
real browser (Playwright): uploaded the CSE-A CSV fixture live, confirmed the
reduced-capability warnings fired correctly for the tables it doesn't have
(analysts/queues), and confirmed ingestion result (12 objects, 20 events, 3 concerns)
feeds the same Allocation/Findings tabs the synthetic path already uses.

---

## 012 — Portfolio layer: reusing negative_space.py for cross-CSE peer comparison
required flipping the "observed" polarity (resolved 2026-09-26)

**Hit:** `moat1/negative_space.py::detect_negative_space` flags a peer group whose
`observed` count is unexpectedly LOW vs. pooled expectation — correct for its
original use (missing evidence). Every finding_type worth comparing across CSEs
(REASSIGNMENT_LOOP, ESCALATION_SLA_VIOLATION, MISSING_ENRICHMENT) is a *problem*
count, the opposite polarity — a naive reuse (`observed` = violation count) would
flag CSEs with abnormally FEW problems, exactly backwards.

**Decision:** `portfolio/entity_metrics.py::build_peer_observations` sets `observed`
= `exposure - violation_count` ("cases WITHOUT the problem" — reframed as "expected
normal handling was present," consistent with Section 9.4's own "absence of expected
evidence" framing). A CSE with an excess of problems now correctly shows an
abnormally LOW "good case" count and gets flagged by the identical, unmodified
`detect_negative_space` — same function, zero statistical code duplicated. Caught by
`tests/test_portfolio_entity_risk.py`'s brute-force 4-CSE deviant scenario, which
initially asserted the wrong direction before this was worked out.

**Entity risk score/tier:** composite score sums `abs(z_score) * capability_materiality
* authority_weight` across the 3 core finding types (reusing `fusion.py`'s existing
constants, not a new weighting scheme) — `ENTITY_RISK_TIER_THRESHOLDS`
(`portfolio/entity_risk.py`) are documented, uncalibrated engineering constants
(0.75/1.5 cutoffs), explicitly labeled pending real portfolio history, same honesty
posture as `sampling/cost_model.py`'s own coefficients.

## 013 — Four new Phase C detectors: heuristic proxies, not ground-truth measurements
(2026-09-26)

Closing PS illustrative use-cases (i), (ii), (iv)/(vi), (vii) required detectors with
no direct field in the canonical model to measure the named concept against. Each is
a documented PROXY, tagged `authority="PEER_NORMAL"` throughout (never MANDATORY/
EXPECTED — there is no rule being violated, only a statistical deviation):
- **Fast-close outlier** (`structural.py::detect_fast_close`): peer-compares
  open→close duration within a severity bucket, reusing the same negative_space
  polarity trick as entry 012 (`observed` = NOT-fast cases).
- **Repeated alert, no remediation** (`detect_asset_alert_recurrence`): "remediated"
  = any linked case reached INVESTIGATE/EVIDENCE_COLLECT — a proxy for root-cause
  fix, not an assertion that remediation actually happened. No field for this exists
  in the canonical model.
- **Low-telemetry critical asset** (`asset_alert_counts` + per-tier
  `detect_negative_space`): exposure is uniform (=1) per asset — no per-asset
  duty/exposure measure (e.g., network segment size) exists in this data model. An
  honest simplification, stated in the finding's own assumptions field, not hidden.
- **Repetitive investigation pattern** (`detect_investigation_uniformity`): the
  spec's own deferred Section 9.3 secondary detector, implemented as a coefficient-
  of-variation check on investigation-to-close duration per analyst rather than
  Isolation Forest — avoids a new ML dependency, keeps every decision in the
  analytical core deterministic/statistical (the project's own non-negotiable).

`fusion.py::_make_package`'s `case_id` parameter was generalized to `primary_id`
(asset_id/analyst_id for these four, case_id for the original five) — additive
rename, all 4 original call sites updated, `supporting_cases` made overridable
(defaults to `[primary_id]`) so an asset-level finding can list its actual linked
cases instead of lying that the asset_id is a case.

## 014 — Gate 5 (temporal axis) revived, scoped to two-cycle comparison
(2026-09-26)

**Hit:** PS Functional Requirement 16 ("trend analysis across time periods") names
exactly what Gate 5 was built for — deferring it was correct when nothing in the PS
explicitly demanded it; once it does, the spec's own Section 13 contingency ("scoped-
down two-cycle version") is the right scope, not full multi-cycle time series.

**Shipped:** `temporal/cycles.py::classify_trend` — reuses `detect_negative_space`
directly (a two-cycle comparison is peer comparison with `group_id`=cycle label
instead of CSE id), returning the spec's own four categories. `POTENTIAL_DISPLACEMENT`
is explicitly a documented HEURISTIC (an improving primary metric alongside a
simultaneously-worsening proxy metric) — not a proof of the underlying
"fixed-what's-measured-not-the-risk" phenomenon, which no purely statistical test can
prove from aggregate counts alone. `tests/test_gate5_temporal.py` proves all four
categories are distinguished on hand-built scenarios — Gate 5 status flips to
**PASSED** in `docs/validation_plan.md`.

**Scope trim, stated plainly:** the plan called for a `data/samples/cse_a_csv_cycle2/`
fixture demonstrating a real two-cycle *ingestion* run end to end. Not built this
pass — the classifier itself is proven directly against `PeerGroupObservation`
inputs (equally rigorous for the STOP condition: "correctly distinguishes the four
categories"), but a live two-cycle ingestion demo in the UI remains a real gap if a
judge asks to see it running against actual re-ingested data, not just the
statistics. Logged here rather than silently claimed complete.

## 015 — Expert-agreement validation: mechanism shipped, real validation cannot be
(2026-09-26)

PS Section 8 asks for validation against real NCIIPC expert manual review. No such
data exists or is obtainable in this environment — stated plainly, not worked around.
`validation/expert_agreement.py::compute_agreement` reads the `verdict` field every
`EvidencePackage` already carries (via `evidence/verdict.py::apply_verdict`, wired
end-to-end in the UI since before this session) and computes a real confirmation-rate
metric the moment real verdicts exist — zero new data model, zero fabricated numbers.
Every surface that renders this (docstring, UI caption) states explicitly: reflects
whoever recorded verdicts in that session, not certified NCIIPC expert output. This
is the honest ceiling on what this requirement can satisfy without access to real
supervisory review data.

## 016 — Benchmark run surfaced a real, unresolved submodular-selection scaling cost
(2026-09-26)

**Hit:** `scripts/benchmark_pipeline.py` measured `CSE_BETA_SMALL_SCALED` (13,190
events) taking 124.8s end to end vs. `CSE_ALPHA_MATURE_SCALED` (15,279 events, more
events) taking only 28.4s — the opposite of what event count alone would predict.
Profiled directly (`cProfile`, then isolated per-stage timing) rather than guessed:
`fuse()` itself is fast on both (2-3s; the four new Phase C detectors are not the
cause, each under 20ms). The actual cost is
`sampling/submodular.py::budgeted_submodular_selection` — **57 seconds** on
`SMALL_CSE_SCALED`'s 1,011 concerns (concern count driven up by this session's new
detectors), vs. a few hundred concerns on the other profiles. The bounded seed-
enumeration step is fixed-cost (`top_k_seeds=12`), so the growth is in the
thresholding-greedy completion step, whose real-world cost at this candidate volume
isn't yet characterized against Badanidiyuru-Vondrák's own near-linear bound.

**Decision:** logged as a known, unresolved performance finding
(`docs/deployment_requirements.md`) rather than silently shipped or quietly patched —
diagnosing and fixing `submodular.py`'s scaling behavior is real engineering work
outside this session's scope (closing the PS gap-analysis findings), not something to
paper over with an untested change to a previously-validated (Gate 4) component.
Flagged explicitly as a pre-production blocker for anyone taking this build's
performance claims at face value beyond the scales already measured.
