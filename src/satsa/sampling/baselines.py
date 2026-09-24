"""Baselines for Gate 4 (Section 10.7): Recall@Budget and Supervisory Yield are
reported against random selection, top-score-only ranking, and simulated current
manual sampling — not against nothing.
"""
from __future__ import annotations

import random


def random_selection(candidates: list[str], costs: dict[str, float], budget: float, rng: random.Random) -> set[str]:
    order = list(candidates)
    rng.shuffle(order)
    selected: set[str] = set()
    spent = 0.0
    for c in order:
        if spent + costs[c] <= budget:
            selected.add(c)
            spent += costs[c]
    return selected


def top_score_selection(candidates: list[str], costs: dict[str, float], scores: dict[str, float], budget: float) -> set[str]:
    """The naive "just look at the ranked list from the top" baseline: greedily fill
    the budget by raw score, ignoring cost-efficiency and bucket diversity entirely —
    exactly what every public implementation of this problem already does, per
    Section 10.1."""
    order = sorted(candidates, key=lambda c: scores[c], reverse=True)
    selected: set[str] = set()
    spent = 0.0
    for c in order:
        if spent + costs[c] <= budget:
            selected.add(c)
            spent += costs[c]
    return selected


def stratified_manual_selection(
    candidates: list[str], costs: dict[str, float], type_of: dict[str, str], budget: float
) -> set[str]:
    """Simulated current manual sampling: an equal quota per finding_type, filled
    round-robin — how a lot of real manual audit practice actually works ("review N
    from each category") absent a data-driven prioritization tool. A simplification,
    not a claim to model any specific real CSE's actual manual process."""
    by_type: dict[str, list[str]] = {}
    for c in candidates:
        by_type.setdefault(type_of[c], []).append(c)
    for lst in by_type.values():
        lst.sort()  # deterministic order, no score-based bias

    selected: set[str] = set()
    spent = 0.0
    exhausted = False
    while not exhausted:
        exhausted = True
        for lst in by_type.values():
            if not lst:
                continue
            c = lst.pop(0)
            if spent + costs[c] <= budget:
                selected.add(c)
                spent += costs[c]
                exhausted = False
    return selected
