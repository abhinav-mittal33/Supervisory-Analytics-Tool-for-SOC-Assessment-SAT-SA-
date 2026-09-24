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
  hard negative. **Status: not started.**

- **Gate 2 — Full pathology + hard-negative benchmark.** `tests/test_gate2_pathologies.py`.
  All planted pathologies recovered, precision/recall/false-positive rate reported,
  true-negative rate on the full hard-negative set. Any numeric target here is an
  engineering target, not a real-world performance claim. **Status: not started.**

- **Gate 3 — Causal honesty test.** `tests/test_gate3_causal_honesty.py`. Withheld-
  confounder + sensitivity-analysis requirement. STOP and withhold causal results from
  the demo on failure. **Status: not started.**

- **Gate 4 — Sampling validation.** `tests/test_gate4_sampling.py`. Recall@Budget and
  Supervisory Yield measured against random, top-score, and simulated-manual
  baselines, at multiple budget levels. **Status: not started.**

- **Gate 5 [optional].** Only if the temporal axis (Section 13) is attempted: correctly
  distinguishes `VERIFIED_IMPROVEMENT` / `POTENTIAL_DISPLACEMENT` / `REGRESSED` /
  `INSUFFICIENT_EVIDENCE`. **Status: deferred, cut first under time pressure.**
