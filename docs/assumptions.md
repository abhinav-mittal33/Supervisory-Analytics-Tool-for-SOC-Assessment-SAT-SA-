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

## 003 — BPIC dataset license check (open, revisit at Step 4)

**Hit:** Section 14.4 asks for a real, public, structurally-adjacent event log (BPIC
2013/2014 incident/ITSM logs) to anchor the generic case-lifecycle skeleton's timing
and branching statistics. Research confirms both datasets are real and hosted on
4TU.ResearchData, but exact per-dataset license terms were not verified file-by-file
in this pass.

**Decision so far:** Defer to Build Order Step 4 (second CSE profile + calibration).
Will download and check the license file accompanying each specific dataset directly
before using any of its statistics, and record the citation + license in
`docs/references.md`. If licensing is unclear or restrictive, fall back to
Section 14.2-14.3 alone (calibrated-synthetic, no real-log grounding) — an explicitly
defensible position per the spec's own text.
