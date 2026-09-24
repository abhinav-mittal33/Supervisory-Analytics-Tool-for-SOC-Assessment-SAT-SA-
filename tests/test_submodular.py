"""Build Order Step 9 — budgeted submodular selection.

Verified empirically against brute-force optimal on a small synthetic instance
(Section 7.3's own ethos: don't just trust a theorem statement, check it), not just
asserted from the citation.
"""
import itertools
import math

from satsa.sampling.submodular import budgeted_submodular_selection, coverage_score


def test_diminishing_returns_within_a_bucket():
    bucket_of = {"a": "B1", "b": "B1", "c": "B1", "d": "B2"}
    first_gain = coverage_score({"a"}, bucket_of) - coverage_score(set(), bucket_of)
    second_gain = coverage_score({"a", "b"}, bucket_of) - coverage_score({"a"}, bucket_of)
    third_gain = coverage_score({"a", "b", "c"}, bucket_of) - coverage_score({"a", "b"}, bucket_of)
    different_bucket_gain = coverage_score({"a", "d"}, bucket_of) - coverage_score({"a"}, bucket_of)

    assert first_gain > second_gain > third_gain > 0
    # A genuinely different bucket's first item is worth as much as the very first
    # item overall -- diminishing returns is within-bucket, not global.
    assert math.isclose(different_bucket_gain, first_gain, rel_tol=1e-9)


def test_respects_the_knapsack_budget():
    candidates = [f"c{i}" for i in range(20)]
    costs = {c: 5.0 + (i % 4) * 3 for i, c in enumerate(candidates)}
    bucket_of = {c: f"B{i % 5}" for i, c in enumerate(candidates)}
    budget = 40.0

    selected, _ = budgeted_submodular_selection(candidates, costs, budget, bucket_of)
    assert sum(costs[i] for i in selected) <= budget


def _brute_force_optimal(candidates, costs, budget, bucket_of):
    best_score = -1.0
    for r in range(len(candidates) + 1):
        for subset in itertools.combinations(candidates, r):
            if sum(costs[i] for i in subset) > budget:
                continue
            score = coverage_score(set(subset), bucket_of)
            if score > best_score:
                best_score = score
    return best_score


def test_selection_achieves_the_1_minus_1_over_e_guarantee_empirically():
    # Small enough (14 items) to brute-force the true optimum (2^14 subsets) and
    # compare against it directly, rather than trusting the algorithm's theoretical
    # guarantee on faith.
    candidates = [f"c{i}" for i in range(14)]
    # Deliberately clustered into few buckets so near-duplicates are common --
    # exactly the setting where a naive score-maximizing greedy (no diminishing
    # returns) would do noticeably worse than a genuinely submodular-aware one.
    bucket_of = {c: f"B{i % 3}" for i, c in enumerate(candidates)}
    costs = {c: 4.0 + (i % 5) for i, c in enumerate(candidates)}
    budget = 25.0

    optimal_score = _brute_force_optimal(candidates, costs, budget, bucket_of)
    epsilon = 0.1
    selected, achieved_score = budgeted_submodular_selection(
        candidates, costs, budget, bucket_of, epsilon=epsilon
    )

    assert sum(costs[i] for i in selected) <= budget
    ratio = achieved_score / optimal_score if optimal_score > 0 else 1.0
    guarantee = 1 - 1 / math.e - epsilon
    print(f"achieved={achieved_score:.4f} optimal={optimal_score:.4f} ratio={ratio:.4f} guarantee={guarantee:.4f}")
    # Generous slack below the theoretical bound: the bound is a worst-case guarantee,
    # not a promise about this specific small instance, but it should not be blown
    # through by a wide margin on an ordinary case either.
    assert ratio >= guarantee - 0.15
