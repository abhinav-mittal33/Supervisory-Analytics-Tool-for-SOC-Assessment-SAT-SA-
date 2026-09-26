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
  the demo on failure. **Status: PASSED, 2026-09-25.** Two scenarios, both through the
  identical pipeline (no scenario-specific tuning): a strong, clean, unconfounded
  effect correctly reaches `ACT` with the right sign (effect=0.601, robustness
  value=0.519); a moderate effect deliberately confounded strongly enough to flip the
  naive withheld-confounder estimate's sign (with-confounder=+0.099,
  without-confounder=-0.165) correctly falls below the robustness bar (0.171 < 0.3)
  and returns `INVESTIGATE_MORE` rather than presenting the flipped estimate as
  actionable. DoWhy's own built-in sensitivity refuter was tried first and found
  unsuitable for this build's data (see `docs/assumptions.md` entry 009) — replaced
  with the closed-form Cinelli-Hazlett Robustness Value.

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

- **Gate 5 — Temporal axis, two-cycle comparison.** `tests/test_gate5_temporal.py`.
  Correctly distinguishes `VERIFIED_IMPROVEMENT` / `POTENTIAL_DISPLACEMENT` /
  `REGRESSED` / `INSUFFICIENT_EVIDENCE`. **Status: PASSED, 2026-09-26** — revived
  from "deferred" because PS Functional Requirement 16 ("trend analysis across time
  periods") names this directly. Scoped exactly to the spec's own Section 13
  contingency (two-cycle, not full time series). All four categories verified
  against hand-built `PeerGroupObservation` scenarios: a clear rate improvement with
  no proxy given → `VERIFIED_IMPROVEMENT`; the same improvement alongside a proxy
  metric that simultaneously worsens → `POTENTIAL_DISPLACEMENT`; a clear regression →
  `REGRESSED`; either cycle below `MIN_PEER_GROUP_SIZE` or a rate shift too small to
  clear the z-threshold → `INSUFFICIENT_EVIDENCE`. Implementation:
  `src/satsa/temporal/cycles.py::classify_trend`, reusing
  `moat1/negative_space.py::detect_negative_space` unmodified (see
  `docs/assumptions.md` entry 014 for the reuse mechanics and the one honest scope
  trim: a live two-cycle *ingestion* fixture wasn't built this pass, only the
  classifier itself, proven directly).

## Offline deployment verification (Section 18, Build Order Step 14)

Not a numbered gate, but a hard requirement. **Status: PASSED, 2026-09-25**
(`tests/test_offline_deployment.py`) — the full pipeline (generate -> OCEL ->
OKF/DuckDB -> Moat 1 fusion -> sampling/submodular selection -> Moat 2 causal
estimation) runs to completion with every `socket.connect`/`connect_ex` call
monkeypatched to raise immediately. Chosen over a manual real-network-disconnect test
because this session has no safe, reversible way to toggle a shared machine's network
interface, and the programmatic block is strictly more rigorous — it catches an
attempted connection instantly rather than relying on a timeout or a silently-caught
exception going unnoticed. This is also the check that would have caught
`huggingface_hub` (a pgmpy dependency — see `docs/assumptions.md` entry 010) trying to
phone home, had it done so; it doesn't.

A software bill of materials (`docs/sbom.json`, `scripts/generate_sbom.py`) covers 124
installed packages, zero GPL/AGPL/LGPL among them — generated directly from the
virtualenv's own package metadata, not hand-maintained.

## Ingestion layer verification (Functional Requirements 1-2, not a numbered gate)

Not one of the five required gates, but held to the same standard: a real,
end-to-end proof, not "the adapter imports without an exception." **Status: PASSED,
2026-09-25** (`tests/test_ingestion_pipeline_end_to_end.py` + the per-adapter test
modules, 29 tests total) — three deliberately heterogeneous demo CSE exports
(`data/samples/cse_a_csv`, `cse_b_json`, `cse_c_sqlite`), each with a different
column-naming convention for the same concepts (`assigned_to` / `incident_number` /
`handler`), each ingest through their own adapter into the identical canonical
object/event vocabulary `generator/generate.py` produces. The real assertion: the
existing, unmodified `moat1.structural.detect_reassignment_loops` recovers a planted
reassignment loop from the CSV fixture's real-shaped data — proving the ingestion
layer's output is actually usable by every downstream detector, not merely
well-formed. The data-reliability/ABSTAIN gate (`quality/validator.py`) is separately
tested for both directions: missing required fields correctly ABSTAIN rather than
silently coercing bad data, and missing optional tables (alerts/assets/analysts/
queues) correctly report reduced capability rather than fabricating a value. See
`docs/assumptions.md` entry 011 for the full design and the one deliberate,
documented exception to the zero-network-calls posture (the generic API adapter,
tested only against a local in-process server).

## Portfolio layer verification (PS req 8/9, not a numbered gate)

**Status: PASSED, 2026-09-26** (`tests/test_portfolio_entity_risk.py`, 5 tests).
Cross-CSE peer comparison (`portfolio/peer_comparison.py`) and entity-level risk
indicators (`portfolio/entity_risk.py`) proven against a hand-built 4-CSE scenario
with one deliberately deviant entity (same brute-force verification standard Gate 4
used for submodular selection): the deviant CSE is correctly flagged, correctly
ranks first by `entity_risk_score`, and a uniform-peers scenario (no real deviation)
correctly leaves every entity at `LOW` tier. Both modules reuse
`moat1/negative_space.py::detect_negative_space` unmodified — see
`docs/assumptions.md` entry 012 for the "observed" polarity reframing this required.
Live-verified in the UI's Portfolio tab against the 3 real sample CSE fixtures
(CSV/JSON/SQLite, three different column-naming conventions) via Playwright.

## Phase C detectors verification (PS illustrative use-cases i, ii, iv/vi, vii)

**Status: PASSED, 2026-09-26** (11 unit tests across
`tests/test_detector_fast_close.py`, `test_detector_asset_recurrence.py`,
`test_detector_asset_telemetry.py`, `test_detector_investigation_uniformity.py`,
plus `tests/test_fusion_phase_c_detectors.py` proving all four are wired into
`fuse()` and fire on real generated data). Each detector tested against a planted
positive AND a matched hard negative (not just "doesn't crash") — e.g. the asset-
recurrence detector correctly distinguishes an asset with 3 unremediated alerts
(flagged) from an identical asset whose alerts WERE investigated (not flagged). All
four are honest statistical/deterministic proxies, tagged `authority="PEER_NORMAL"`
throughout — see `docs/assumptions.md` entry 013 for exactly what each proxies for
and why.

## Reporting and expert-agreement verification (PS req 15-17, Section 8)

**Status: PASSED, 2026-09-26** (`tests/test_report_builder.py`,
`tests/test_expert_agreement.py`, 10 tests total). The generated HTML report
(`reporting/report_builder.py`) is checked for real content — every supplied
entity's risk tier and every concern's finding_id must appear in the output string,
and untrusted finding content is verified HTML-escaped (a `<script>` payload in a
finding's rationale does not survive into the rendered report). The expert-agreement
mechanism (`validation/expert_agreement.py`) is checked against hand-built verdicted
concerns for correct confirmation-rate arithmetic and per-finding-type/per-authority
breakdowns — see `docs/assumptions.md` entry 015 for why this ships as a mechanism
only: no real NCIIPC expert-review data exists in this environment to validate
against, and nothing here pretends otherwise.

## Performance/scalability evidence (PS req 7, deliverables vi/viii)

**Status: measured, not a pass/fail gate** — `scripts/benchmark_pipeline.py`,
results in `docs/deployment_requirements.md`. Real wall-clock and peak-memory numbers
across all 3 synthetic profiles plus a 2-CSE portfolio run. This measurement pass
also surfaced a genuine, unresolved performance finding in the pre-existing
submodular-selection component at high concern volumes — logged honestly
(`docs/assumptions.md` entry 016) rather than hidden or silently patched.
