# Validation Gates — STOP conditions, not aspirations

A gate is not "passed" until its pytest module (`tests/test_gateN_*.py`) is green.
Weakening a test to make a gate pass is a regression, not a fix (Section 1, item 3).

- **Gate 0 — Data validity.** `tests/test_gate0_ocel.py`. OCEL opens, validates,
  round-trips (write -> read -> write); five object types present with required
  attributes; timestamps present; relationships present and qualified; ground-truth
  IDs correspond to real synthetic records. **Status: PASSED (7/7), 2026-09-25**, on
  the dev-scale `CSE_ALPHA_MATURE_DEV` profile (300 cases, 669 objects, 2015 events,
  12 planted ground-truth pathology instances — 6 `REASSIGNMENT_LOOP` positives, 6
  matched hard negatives). One real bug caught and fixed in the process: the
  SQLite/JSON timestamp formatter truncated sub-second precision, which broke
  round-trip identity on any event whose timestamp carried microseconds — fixed by
  switching to `datetime.isoformat()` in both `ocel/sqlite_io.py` and
  `ocel/json_io.py`. A second bug (sqlite3 cursor reuse silently truncating a nested
  query's outer loop) was also caught and fixed in `ocel/sqlite_io.py::read_sqlite`.

  Re-confirmed at full scale, 2026-09-25 (`tests/test_gate0_scaled_profiles.py`),
  against two structurally distinct calibrated CSE profiles (Build Order Step 4):
  `CSE_ALPHA_MATURE_SCALED` (2,200 cases, 4,626 objects, 14,706 events) and
  `CSE_BETA_SMALL_SCALED` (2,000 cases, 4,068 objects, 12,753 events) — see
  `docs/references.md` for the calibration citations.

- **Gate 1 — Core pattern recovery.** `tests/test_gate1_reassignment.py`. Recover the
  planted reassignment loop (precision/recall/F1) and correctly reject its matched
  hard negative. **Status: PASSED, 2026-09-25**, on all three generated datasets:
  precision=1.000 recall=1.000 F1=1.000 in every case (dev: 6 positives/6 hard
  negatives; mature-scaled: 25/25; small-scaled: 20/20). Detector:
  `src/satsa/moat1/structural.py::detect_reassignment_loops`. The test also confirms
  the Section 9.1 requirement directly: the *raw* structural pattern (repeated analyst
  within a small analyst set, ignoring the justification attribute) is detected in
  BOTH the positive and hard-negative sets before the justification filter is applied
  — proving the detector reads object relationships, not the `handover_reason`
  attribute, to find the loop shape itself. Two background-noise categories
  (`SINGLE_REASSIGNMENT`, `REASSIGNMENT_CHAIN_NO_LOOP` — same-ish event counts, no
  repeated analyst) were added to the generator specifically so this gate has real
  negatives to reject, not just an absence of any reassignment activity.

- **Gate 2 — Full pathology + hard-negative benchmark.** `tests/test_gate2_pathologies.py`.
  All planted pathologies recovered, precision/recall/false-positive rate reported,
  true-negative rate on the full hard-negative set. Any numeric target here is an
  engineering target, not a real-world performance claim. **Status: PASSED,
  2026-09-25**, on all three generated profiles: precision=1.000 recall=1.000
  fp_rate=0.000 on `REASSIGNMENT_LOOP`, true-negative rate=1.000 on the full
  hard-negative set (planted shift-change hard negatives + the
  `REASSIGNMENT_CHAIN_NO_LOOP` count-only false-positive trap). Fusion:
  `src/satsa/moat1/fusion.py::fuse`. The real thing this gate forced: the weaker
  `REASSIGN-CARD-001` OKF rule (count > 2 reassignments) *does* fire on every hard
  negative and every chain-no-loop case — fusion must explicitly suppress it wherever
  the finer structural detector has already ruled on the same case, logged as an audit
  note, or this gate fails outright regardless of the reassignment-loop finding_type's
  own numbers looking perfect in isolation.

- **Gate 3 — Causal honesty test.** `tests/test_gate3_causal_honesty.py`. Withheld-
  confounder + sensitivity-analysis requirement. STOP and withhold causal results from
  the demo on failure. **Status: not started.**

- **Gate 4 — Sampling validation.** `tests/test_gate4_sampling.py`. Recall@Budget and
  Supervisory Yield measured against random, top-score, and simulated-manual
  baselines, at multiple budget levels. **Status: PASSED, 2026-09-25**, on
  `CSE_ALPHA_MATURE_SCALED`. Real result, not a forced one (the first version of this
  test used aggregate case-count recall and *failed* — top-score-only ranking
  actually won on that metric, because one finding_type (`MISSING_ENRICHMENT`, 306
  cases) outnumbers the others roughly 12-to-1 and drowned out the real signal; see
  `docs/assumptions.md` entry 008): on the corrected metric (recall per finding_type,
  the minimum across the three ground-truth-backed types), top-score-only ranking
  gets **zero** `REASSIGNMENT_LOOP` recall at every tested budget fraction (0.1
  through 0.4) because it exhausts the budget on the single highest-scoring bucket
  (`ESCALATION_SLA_VIOLATION`, `MANDATORY` authority) first — while the submodular
  selector covers all three finding types even at the smallest budget (40-43% minimum
  per-type recall vs. 0%). That gap is the demonstrated core value of
  diminishing-returns bucket-aware selection over a naive ranked list (Section 10.1).

- **Gate 5 [optional].** Only if the temporal axis (Section 13) is attempted: correctly
  distinguishes `VERIFIED_IMPROVEMENT` / `POTENTIAL_DISPLACEMENT` / `REGRESSED` /
  `INSUFFICIENT_EVIDENCE`. **Status: deferred, cut first under time pressure.**
