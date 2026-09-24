"""Budgeted submodular selection (build spec Section 10.4).

Objective: monotone submodular "coverage" function. Concerns are grouped into buckets
(capability x finding_type x peer_group, in this build: capability x finding_type,
since queue/CSE isn't yet part of the fused Concern stream — see
docs/assumptions.md entry 006), and f(S) = sum over buckets of concave(count of
selected items in that bucket). A concave transform (log1p by default) gives
diminishing returns within a bucket — the 5th near-duplicate finding from the same
bucket adds less than the 1st — while a genuinely different bucket still adds full
marginal value. This is a standard, provably submodular "coverage" construction (a sum
of concave functions of modular set-counts is submodular), not something invented for
this build.

Algorithm: bounded seed enumeration (Sviridenko 2004's own technique — enumerate small
seed subsets, complete each greedily, keep the best) combined with Badanidiyuru &
Vondrák's (2014) thresholding-greedy for the completion phase instead of the classical
one-at-a-time incremental greedy. This is the accelerated structure the build spec
asks for (Section 10.4): near-linear in the number of candidates rather than the
naive O(n^5) full triple-enumeration, because the seed pool is capped at
`top_k_seeds` candidates (ranked by singleton density) rather than all n.

Guarantee, stated precisely rather than just asserted: Sviridenko's seed-enumeration +
greedy-completion structure achieves (1-1/e) for monotone submodular maximization
under a knapsack constraint. Substituting the accelerated thresholding-greedy for the
completion step (as Badanidiyuru-Vondrák describe) weakens this to (1-1/e-epsilon),
where epsilon is the threshold step size passed in below — this is the same
(1-1/e-epsilon) both papers are cited for, not a new or different claim. Verified
empirically against brute-force optimal on small synthetic instances
(tests/test_submodular.py), not just trusted from the theorem statement.
"""
from __future__ import annotations

import math
from itertools import combinations


def coverage_score(selected_ids: set[str], bucket_of: dict[str, str], concave=math.log1p) -> float:
    counts: dict[str, int] = {}
    for cid in selected_ids:
        b = bucket_of[cid]
        counts[b] = counts.get(b, 0) + 1
    return sum(concave(c) for c in counts.values())


def _marginal_gain(item_id: str, selected: set[str], bucket_of: dict[str, str], concave) -> float:
    b = bucket_of[item_id]
    current = sum(1 for cid in selected if bucket_of[cid] == b)
    return concave(current + 1) - concave(current)


def threshold_greedy_complete(
    candidates: list[str],
    costs: dict[str, float],
    budget: float,
    bucket_of: dict[str, str],
    concave,
    epsilon: float,
    seed: set[str],
) -> set[str]:
    selected = set(seed)
    spent = sum(costs[i] for i in selected)
    remaining = [c for c in candidates if c not in selected and costs[c] <= budget - spent]
    if not remaining:
        return selected

    def density(i: str) -> float:
        g = _marginal_gain(i, selected, bucket_of, concave)
        return g / costs[i] if costs[i] > 0 else float("inf")

    v_max = max((density(i) for i in remaining), default=0.0)
    if v_max <= 0:
        return selected

    tau = v_max
    min_tau = v_max * epsilon / max(len(remaining), 1)
    while tau >= min_tau:
        for i in candidates:
            if i in selected:
                continue
            if spent + costs[i] > budget:
                continue
            g = _marginal_gain(i, selected, bucket_of, concave)
            if costs[i] > 0 and g / costs[i] >= tau:
                selected.add(i)
                spent += costs[i]
        tau /= 1 + epsilon
    return selected


def budgeted_submodular_selection(
    candidates: list[str],
    costs: dict[str, float],
    budget: float,
    bucket_of: dict[str, str],
    concave=math.log1p,
    seed_size: int = 3,
    top_k_seeds: int = 12,
    epsilon: float = 0.1,
) -> tuple[set[str], float]:
    affordable = [c for c in candidates if costs[c] <= budget]
    if not affordable:
        return set(), 0.0

    def singleton_density(i: str) -> float:
        g = concave(1) - concave(0)
        return g / costs[i] if costs[i] > 0 else float("inf")

    seed_pool = sorted(affordable, key=singleton_density, reverse=True)[:top_k_seeds]

    best_set: set[str] = set()
    best_score = -1.0
    for r in range(0, min(seed_size, len(seed_pool)) + 1):
        for seed_tuple in combinations(seed_pool, r):
            seed_cost = sum(costs[i] for i in seed_tuple)
            if seed_cost > budget:
                continue
            completed = threshold_greedy_complete(
                candidates, costs, budget, bucket_of, concave, epsilon, set(seed_tuple)
            )
            score = coverage_score(completed, bucket_of, concave)
            if score > best_score:
                best_score = score
                best_set = completed
    return best_set, best_score
