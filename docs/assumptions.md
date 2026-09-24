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

**Decision so far:** Build Moat 2 on **DoWhy** (MIT-licensed, verify at Step 11) for
the graphical-model + potential-outcomes estimation and its refutation API
(`add_unobserved_common_cause` for the withheld-confounder sensitivity number Gate 3
requires), with a hand-written process-aware preprocessing layer that extracts
treatment/outcome/confounders from OCEL structure before handing a tabular frame to
DoWhy. This preprocessing step is the real engineering work — flagged here so it
isn't mistaken for "just call a library" later. Not yet implemented; revisit and
re-verify DoWhy's actual installed capability at Build Order Step 11.

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
