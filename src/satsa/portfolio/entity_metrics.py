"""Turns per-CSE fusion output into the exact `PeerGroupObservation` shape
`moat1/negative_space.py` already defines — no new statistical machinery, this file
only reshapes data so the existing, Gate-2-proven engine can run one level up
(CSE-vs-CSE instead of queue-vs-queue within one CSE).
"""
from __future__ import annotations

from satsa.moat1.fusion import FusionResult
from satsa.moat1.negative_space import PeerGroupObservation
from satsa.ocel.model import OCEL

# Finding types with a real ground-truth-backed detector behind them (Gates 1/2/4) —
# the only ones honest to compare across entities. EXCESSIVE_REASSIGNMENT_CARDINALITY
# is deliberately excluded: fusion.py suppresses it wherever the structural detector
# already ruled on the same case, so its raw count is not a clean cross-entity signal.
CORE_FINDING_TYPES = ("REASSIGNMENT_LOOP", "ESCALATION_SLA_VIOLATION", "MISSING_ENRICHMENT")


def case_count(ocel: OCEL) -> int:
    return sum(1 for o in ocel.objects if o.type == "Case")


def build_peer_observations(
    datasets: dict[str, tuple[OCEL, FusionResult]], finding_type: str
) -> list[PeerGroupObservation]:
    """`detect_negative_space` flags a peer group whose `observed` count is
    unexpectedly LOW vs. its peers (Section 9.4's own "absence of expected evidence"
    framing). Every `finding_type` here is a *problem* count (a loop, a violation) —
    the opposite polarity — so `observed` is deliberately the count of cases WITHOUT
    the problem ("expected normal handling was present"), not the raw violation
    count. This keeps every finding_type flowing through the identical, unmodified
    negative-space engine with one consistent meaning: a flagged peer group is one
    with abnormally little evidence of expected-normal behavior, whatever the
    specific finding_type actually measures.
    """
    observations = []
    for cse_id, (ocel, result) in datasets.items():
        exposure = case_count(ocel)
        flagged_cases = {c.affected_objects[0] for c in result.concerns if c.finding_type == finding_type}
        observations.append(PeerGroupObservation(group_id=cse_id, exposure=exposure, observed=exposure - len(flagged_cases)))
    return observations
