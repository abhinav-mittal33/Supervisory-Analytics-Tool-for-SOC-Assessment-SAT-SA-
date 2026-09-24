# References & Calibration Traceability

## Standards implemented directly against

| Artifact | Source | License | Used for |
|---|---|---|---|
| OCEL 2.0 JSON Schema | `https://www.ocel-standard.org/2.0/ocel20-schema-json.json` | Published standard artifact (validator input, no library redistribution) | `src/satsa/ocel/validate.py` JSON validation |
| OCEL 2.0 Specification | Berti et al., *OCEL (Object-Centric Event Log) 2.0 Specification*, arXiv:2403.01975, Oct 2023 | CC BY 4.0 | Section 6 (relational SQLite format) implemented by hand in `src/satsa/ocel/sqlite_io.py` |

See `docs/assumptions.md` entry 001 for why this is implemented directly rather than
through pm4py/ocpa (both carry a copyleft dependency unsuitable for this deliverable).

## Public event-log grounding (Section 14.4)

| Dataset | Source | License | Status |
|---|---|---|---|
| BPI Challenge 2013 (Volvo IT incidents) | `https://data.4tu.nl/articles/dataset/BPI_Challenge_2013_incidents/12693914/1` | CC0 (4TU General Terms of Use, `General_terms_of_use.pdf`, published 2016-01-01, applies "where no other licence is given" — this dataset carries no dataset-specific override, confirmed on its own page) | Not yet used — generic case-lifecycle skeleton grounding deferred; calibration below already meets Section 14.3 on its own (see note) |
| BPI Challenge 2014 (Rabobank ITSM) | 4TU.ResearchData / tf-pm.org | Same 4TU CC0 default, not yet re-verified per-file | Not yet used |

Note: Section 14.4 frames the BPIC pull as an *additional* grounding layer, and
explicitly says "if nothing suitable is found quickly, proceed with the
calibrated-synthetic approach (14.2-14.3) alone; that is a fully defensible position on
its own." The calibration table below already anchors every generator rate to a cited
public benchmark, so the BPIC event logs are deferred rather than treated as a
blocker — revisit if the generic case-lifecycle skeleton's timing/branching shape needs
real-log grounding beyond the current hand-modeled lifecycle.

## Synthetic generator parameter calibration table (Section 14.3)

All figures below were extracted directly from the primary-source PDF text (fetched
and parsed locally, not taken from a secondary summary), so the quotes are exact.

| Parameter (in `src/satsa/generator/profiles.py`) | Value used | Cited source | Exact quote |
|---|---|---|---|
| `MATURE_CSE_SCALED.telemetry_coverage` | 0.90 | CardinalOps, *State of SIEM Detection Risk*, 5th Annual Report, 2025 Edition (`cardinalops.com/wp-content/uploads/2025/06/25-CardinalOps-2025-State-of-SIEM-Report.pdf`) | "Organizations are ingesting enough data into their SIEMs to cover **90%** of all MITRE ATT&CK techniques, on average" |
| `SMALL_CSE_SCALED.telemetry_coverage` (0.55, positioned well below the mature profile and below the realized-coverage figures cited here) | 0.55 | Same report | "Enterprise SIEMs only have detections for an average of **21%**" of ATT&CK techniques (aggregate, 5-year); "this year's **22%** average coverage score is a slight improvement over last year's **19%**"; "**13%** of an org's SIEM rules are broken" (cover statistic, 5-year aggregate) / "**10%** of rules that are broken" (this year's figure) |
| `MATURE_CSE_SCALED.num_analysts` = 40 (deliberately placed above the cited baseline band) | 40 | SANS SOC Survey 2025 (Christopher Crowley, July 2025; PDF mirror `elastic.co/pdf/sans-soc-survey-2025.pdf`) | "**2-10 people** is the most common size for a fully staffed SOC." |
| `SMALL_CSE_SCALED.num_analysts` = 6 (within the cited band) | 6 | Same report | Same quote as above |
| `SMALL_CSE_SCALED.escalation_compliance_rate` / lower data reliability framing | 0.45 (mature: 0.75) | Same report | "**42%** of SOCs dump all incoming data into a SIEM, often without a retrieval or management plan." — used qualitatively to justify the small profile's materially worse SLA-compliance and telemetry parameters, not as a direct 1:1 numeric mapping (that would overstate precision the source doesn't claim) |
| (context only, not directly mapped to a generator parameter) | — | Same report | "**79%** of SOCs are operational 24/7." |

Both `MATURE_CSE_SCALED` and `SMALL_CSE_SCALED` (`src/satsa/generator/profiles.py`)
scale the dev-shape-validated generator (Gate 0, `MATURE_CSE_DEV`) up to 2,000+
cases / 60-180 assets per Section 14.2's "comparable to or larger than ~2,000
cases/CSE, ~50 assets/CSE" instruction, and are structurally distinct (different
analyst/queue counts, different severity/criticality distributions, different
escalation/enrichment/telemetry rates) rather than the same generator reseeded.

## Causal engine (Section 12 / Moat 2) — pending, Build Order Step 11

| Library | License | Role |
|---|---|---|
| DoWhy | MIT (to re-verify at install time) | Graphical causal model, potential-outcomes estimation, refutation/sensitivity API |

## Sampling layer citations (Section 10.4, Build Order Step 9)

| Citation | Used for | Exact claim made |
|---|---|---|
| Sviridenko, M. (2004). "A note on maximizing a submodular set function subject to a knapsack constraint." *Operations Research Letters* 32(1). | The (1-1/e) worst-case guarantee's structure: bounded seed enumeration + greedy completion. | This build enumerates seed subsets up to size 3 from a capped top-K candidate pool (`top_k_seeds` in `src/satsa/sampling/submodular.py`), not the full candidate set — see the entry below for why the resulting guarantee is stated as (1-1/e-epsilon), not the exact (1-1/e). |
| Badanidiyuru, A. & Vondrák, J. (2014). "Fast algorithms for maximizing submodular functions." *SODA 2014*. | The near-linear-time thresholding-greedy completion step, replacing the classical one-at-a-time incremental greedy Sviridenko's method uses. | `threshold_greedy_complete` in `src/satsa/sampling/submodular.py`. |

**Exact claim for the pitch slide:** "(1-1/e-epsilon)-approximate budgeted submodular selection, combining Sviridenko's (2004) seed-enumeration structure with Badanidiyuru-Vondrák's (2014) near-linear thresholding-greedy completion" — not a bare "provably near-optimal." See `docs/assumptions.md` entry 007 for why the combined guarantee is stated with the epsilon term rather than as Sviridenko's exact (1-1/e).
