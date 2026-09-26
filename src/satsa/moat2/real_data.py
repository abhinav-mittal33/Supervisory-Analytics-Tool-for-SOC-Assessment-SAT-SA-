"""Builds the real-data DataFrame `moat2/intervention.py::analyze_intervention`
needs, from an actual ingested/generated OCEL — Moat 2 was validated (Gate 3) only
against synthetic scenarios (`synthetic_causal_data.py`); this is what actually
connects it to a live CSE's data.

One estimand, applied generically across every case-level finding type: "does
assigning a SENIOR-tier analyst reduce this case's chance of falling into the
problem this finding_type flags?" (treatment=analyst tier, outcome=case avoided the
problem). The treatment is fixed; the outcome is parameterized by whichever set of
flagged case_ids the caller passes in — those sets already exist as soon as `fuse()`
has run (`{c.affected_objects[0] for c in result.concerns if c.finding_type == ft}`),
so this works for REASSIGNMENT_LOOP, ESCALATION_SLA_VIOLATION, MISSING_ENRICHMENT,
and EXCESSIVE_REASSIGNMENT_CARDINALITY without any new detector code — one real
estimand, four finding types, not four bespoke analyses.

Cases whose current assignee's tier could not be determined (no analysts data
ingested for this CSE) are dropped, not guessed — an examiner needs to know if the
answer is "no real estimate possible," not see a fabricated 50/50 coin-flip encoded
as data.
"""
from __future__ import annotations

import pandas as pd

from satsa.moat1.structural import detect_reassignment_loops
from satsa.ocel.model import OCEL

TREATMENT_COL = "T_senior_assigned"
OUTCOME_COL = "Y_case_ok"

# Kept for backward compatibility with existing call sites/tests.
REASSIGNMENT_LOOP_TREATMENT = TREATMENT_COL
REASSIGNMENT_LOOP_OUTCOME = OUTCOME_COL


def _current_assignee(ocel: OCEL, case_id: str) -> str | None:
    for o in ocel.objects:
        if o.id == case_id and o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "current_assignee":
                    return r.target_id
    return None


def _analyst_tier(ocel: OCEL, analyst_id: str) -> str | None:
    for o in ocel.objects:
        if o.id == analyst_id and o.type == "Analyst":
            return next((a.value for a in o.attributes if a.name == "tier"), None)
    return None


def build_case_outcome_dataframe(ocel: OCEL, flagged_case_ids: set[str]) -> pd.DataFrame:
    """One row per Case whose current assignee has a known (not UNKNOWN/missing)
    tier. Rows with no resolvable tier are dropped, not defaulted — see module
    docstring. `flagged_case_ids` is whichever finding_type's own flagged-case set
    the caller is analyzing — the outcome is simply "this case is NOT in that set."
    """
    rows = []
    for o in ocel.objects:
        if o.type != "Case":
            continue
        analyst_id = _current_assignee(ocel, o.id)
        if analyst_id is None:
            continue
        tier = _analyst_tier(ocel, analyst_id)
        if tier not in ("SENIOR", "JUNIOR"):
            continue
        rows.append({
            "case_id": o.id,
            TREATMENT_COL: 1 if tier == "SENIOR" else 0,
            OUTCOME_COL: 0 if o.id in flagged_case_ids else 1,
        })
    return pd.DataFrame(rows)


def build_reassignment_loop_dataframe(ocel: OCEL) -> pd.DataFrame:
    """Convenience wrapper for the original single-estimand call sites/tests —
    equivalent to `build_case_outcome_dataframe(ocel, <reassignment-loop-flagged case
    ids>)`."""
    loop_flagged = {s.case_id for s in detect_reassignment_loops(ocel) if s.flagged}
    return build_case_outcome_dataframe(ocel, loop_flagged)


def has_enough_variation(df: pd.DataFrame, min_rows: int = 6) -> bool:
    """A degenerate (all-same-treatment or all-same-outcome, or too few rows)
    DataFrame can't identify anything — statsmodels/pgmpy would either crash or
    silently return a meaningless fit. Checked explicitly so the UI can say
    'insufficient data' instead of a stack trace or a fabricated number."""
    if len(df) < min_rows:
        return False
    return df[TREATMENT_COL].nunique() > 1 and df[OUTCOME_COL].nunique() > 1
