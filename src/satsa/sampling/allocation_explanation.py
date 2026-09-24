"""Allocation-explanation objects (build spec Section 10.5).

"Every allocation decision ships with a structured 'why' — never a bare number of
hours." This builds that structured explanation from a completed budgeted selection:
what got selected and why (per-capability breakdown, concern-score weight), and what
spending more would additionally buy (re-run the same selection with extra budget on
top of what's already selected, report the marginal gain).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from satsa.evidence.package import EvidencePackage
from satsa.sampling.submodular import coverage_score, threshold_greedy_complete


@dataclass(frozen=True)
class AllocationExplanation:
    allocated_minutes: float
    num_concerns_selected: int
    coverage_score: float
    per_capability_counts: dict[str, int] = field(default_factory=dict)
    per_capability_concern_score_sum: dict[str, float] = field(default_factory=dict)
    marginal_coverage_gain_from_increment: float = 0.0
    newly_covered_capabilities_from_increment: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def explain_allocation(
    selected_ids: set[str],
    concerns: list[EvidencePackage],
    budget: float,
    increment_minutes: float = 60.0,
    epsilon: float = 0.1,
) -> AllocationExplanation:
    by_id = {c.finding_id: c for c in concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in concerns}
    costs = {c.finding_id: c.estimated_review_cost_minutes for c in concerns}

    per_capability_counts: dict[str, int] = {}
    per_capability_score: dict[str, float] = {}
    for fid in selected_ids:
        c = by_id[fid]
        per_capability_counts[c.capability] = per_capability_counts.get(c.capability, 0) + 1
        per_capability_score[c.capability] = per_capability_score.get(c.capability, 0.0) + c.concern_score

    base_score = coverage_score(selected_ids, bucket_of)

    with_increment = threshold_greedy_complete(
        list(by_id.keys()), costs, budget + increment_minutes, bucket_of, math.log1p, epsilon, set(selected_ids)
    )
    incremented_score = coverage_score(with_increment, bucket_of)
    newly_added = with_increment - selected_ids
    newly_covered_capabilities = sorted({by_id[fid].capability for fid in newly_added})

    notes = [
        f"selected {len(selected_ids)} concerns across {len(per_capability_counts)} capabilities within {budget:.0f} minutes",
    ]
    if newly_added:
        notes.append(
            f"an additional {increment_minutes:.0f} minutes would cover {len(newly_added)} more concerns "
            f"(capabilities: {', '.join(newly_covered_capabilities)})"
        )
    else:
        notes.append(f"an additional {increment_minutes:.0f} minutes would not add any new concerns at this budget")

    return AllocationExplanation(
        allocated_minutes=budget,
        num_concerns_selected=len(selected_ids),
        coverage_score=base_score,
        per_capability_counts=per_capability_counts,
        per_capability_concern_score_sum=per_capability_score,
        marginal_coverage_gain_from_increment=incremented_score - base_score,
        newly_covered_capabilities_from_increment=newly_covered_capabilities,
        notes=notes,
    )
