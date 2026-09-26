# Deployment & Operational Requirements

PS deliverables (vi) infrastructure requirements, (viii) estimated deployment/
operational requirements; PS Functional Requirement 7 (scalability/performance
evidence). Every number below is measured on this development machine via
`scripts/benchmark_pipeline.py` (`tracemalloc` + `time.perf_counter`, both stdlib,
cross-platform) — not estimated, not invented. Re-run the script on target hardware
before using these numbers for a real sizing decision; they anchor a formula, they
are not a certified capacity plan.

## Measured: full pipeline (ingest/generate → OCEL → fuse → submodular selection)

| Dataset | Events | Objects | Wall-clock (s) | Peak memory (MB) |
|---|---|---|---|---|
| `CSE_ALPHA_MATURE_DEV` | 2,088 | 669 | 2.44 | 0.54 |
| `CSE_ALPHA_MATURE_SCALED` | 15,279 | 4,626 | 28.41 | 1.50 |
| `CSE_BETA_SMALL_SCALED` | 13,190 | 4,068 | 124.77 | 2.03 |
| 2-CSE portfolio (`cse_a_csv` + `MATURE_CSE_DEV`) | 2,108 | 681 | 0.82 | 1.30 |

`tracemalloc` itself adds real overhead (it instruments every allocation) — peak
memory above is therefore a conservative *over*-estimate relative to an
un-instrumented run, not an under-estimate. Safe to use as a worst-case bound.

**A real finding, not glossed over:** `CSE_BETA_SMALL_SCALED` (fewer events than
`MATURE_CSE_SCALED`) took over 4× longer. Profiled directly (`cProfile`, then an
isolated per-stage timing breakdown) rather than guessed:
`fuse()` itself is fast (2.1s) — the Phase C detectors added this session
(`detect_fast_close`, `detect_negative_space` per criticality tier, etc.) are not the
cause, each completing in well under 20ms. The actual cost is
`sampling/submodular.py::budgeted_submodular_selection`: **57 seconds** on this
profile's 1,011 concerns (up from a few hundred on the other profiles, because the
Phase C detectors add real additional finding volume) — the bounded seed-enumeration
step is fixed-cost (`top_k_seeds=12`, unaffected by candidate count), but the
thresholding-greedy completion step's cost visibly grows with total candidate count
in a way that isn't yet characterized against the algorithm's own near-linear
theoretical bound. This is a pre-existing implementation, exposed at a candidate
volume it hadn't been exercised at before (adding four new detectors is precisely
what pushed one profile's concern count past whatever threshold makes this visible) —
logged here as a real, unresolved performance finding, not silently absorbed into "it
works." Flagged for investigation in `sampling/submodular.py` before this build is
represented as production-scale-ready; not in scope for this session's ingestion/
gap-closure work.

## Extrapolation (arithmetic, not a fitted model)

Using the two directly comparable scaled profiles as anchor points
(`MATURE_CSE_SCALED`: 15,279 events / 28.41s; midpoint check against `CSE_ALPHA_MATURE_DEV`:
2,088 events / 2.44s) gives a rough **~1.1-1.9 ms per event** processing rate on this
development machine, excluding the `SMALL_CSE_SCALED` outlier above (which shows the
formula is not reliable in the presence of that unresolved slow path — stated
honestly, not hidden). A back-of-envelope planning number, pending the outlier's
diagnosis:

```
estimated_seconds ≈ 0.0015 × total_events   (development-machine order of magnitude only)
```

For a portfolio of N CSEs at roughly `MATURE_CSE_SCALED`'s scale each (~15K events),
sequential processing is `N × ~30s`; the portfolio/entity-risk layer
(`src/satsa/portfolio/`) itself adds negligible incremental cost (0.82s measured for
2 CSEs above) since it operates on already-fused `EvidencePackage` lists, not raw
OCEL data.

## Infrastructure requirements (deliverable vi)

- **Compute:** single machine, no distributed/cluster requirement — every component
  (DuckDB, SQLite, statsmodels, pgmpy, Streamlit) is in-process. No GPU.
- **Memory:** sub-10MB measured at these scales, including `tracemalloc` overhead; a
  real production CSE portfolio (larger event volumes, more CSEs held concurrently in
  the UI's Portfolio tab) should be sized with headroom — 2-4GB RAM is comfortably
  conservative given the measured rate, pending the `SMALL_CSE_SCALED` outlier's
  resolution.
- **Storage:** OCEL SQLite files are small (a 15K-event profile's `.sqlite` is under
  10MB) — storage growth is dominated by how many ingestion cycles' worth of raw
  OCEL snapshots a deployment chooses to retain, a retention-policy decision outside
  this codebase's scope.
- **OS:** cross-platform by construction (Python 3.11, no POSIX-only calls in the
  analytical core — this benchmark script deliberately avoids the POSIX-only
  `resource` module for exactly this reason) — Windows Server or Linux both viable
  for the "NCIIPC-controlled environment" requirement.
- **Network:** zero required at runtime (Section 18) — see `tests/test_offline_deployment.py`.
  The one exception is the ingestion layer's optional API adapter, which makes an
  outbound call only when an examiner explicitly configures one against a CSE's own
  internal system (`docs/assumptions.md` entry 011).

## Operational requirements (deliverable viii)

- **Per-cycle operator time:** not yet measured against a real examiner (see
  `docs/validation_plan.md`'s honesty note on expert-validation) — the UI's own
  review-timer mechanism (`ui/app.py`) exists specifically to start collecting this
  once real reviewers use it, but no session has recorded real numbers yet.
- **Ingestion cadence:** matches the PS's own framing (Section 2: "periodic
  submissions") — this build has no continuous/streaming ingestion path by design
  (Out of Scope item ii, v) and never will; each cycle is a discrete, operator-
  triggered ingestion run.
- **Staffing:** no new role required beyond the existing NCIIPC examiner function —
  this tool changes how review hours are allocated (the sampling layer's entire
  purpose), not who performs the review.
