"""Triple-sample budget split (build spec Section 10.3).

Splitting the whole examiner budget into risk-selected review alone can't validly
estimate the peer baseline, population prevalence, false-positive rate, and
true-finding rate simultaneously — a risk-selected sample is not a random sample of
the population it's drawn from. Three parts, each estimating something different:

- B_baseline — not reviewed at all, just counted; feeds the Expected_k regression
  (src/satsa/moat1/negative_space.py).
- B_random_calibration — a small uniform-random sample the examiner actually reviews,
  used to estimate true population prevalence vs. risk-selected prevalence.
- B_risk — the coverage-optimized selection (src/satsa/sampling/submodular.py) doing
  the actual prioritization work.

No specific split ratio is mandated here — it's configurable and swept
(tests/test_budget_split.py sweeps B_risk's share from 50% to 90% against this
build's real fused Concerns and ground truth, reporting how Recall@Budget changes,
and a default is picked from that sweep, not asserted a priori).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetSplit:
    baseline_fraction: float
    random_calibration_fraction: float
    risk_fraction: float

    def __post_init__(self) -> None:
        total = self.baseline_fraction + self.random_calibration_fraction + self.risk_fraction
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"fractions must sum to 1.0, got {total}")


def split_budget(total_budget_minutes: float, split: BudgetSplit) -> tuple[float, float, float]:
    """Returns (B_baseline, B_random_calibration, B_risk) in minutes."""
    return (
        total_budget_minutes * split.baseline_fraction,
        total_budget_minutes * split.random_calibration_fraction,
        total_budget_minutes * split.risk_fraction,
    )


def sweep_risk_fraction(
    concerns: list,
    true_positive_case_ids: set[str],
    total_budget_minutes: float,
    risk_fractions: list[float],
) -> list[dict]:
    """For each candidate risk_fraction, run the budgeted submodular selection at
    that share of the total budget and report Recall@Budget (Section 10.7's own
    headline metric) against a known set of true-positive cases — this is exactly
    how the spec asks the split ratio to be chosen: by sweeping and observing the
    tradeoff, not by asserting a ratio a priori."""
    from satsa.sampling.submodular import budgeted_submodular_selection

    candidates = [c.finding_id for c in concerns]
    costs = {c.finding_id: c.estimated_review_cost_minutes for c in concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in concerns}
    case_of = {c.finding_id: c.affected_objects[0] for c in concerns}

    results = []
    for rf in risk_fractions:
        b_risk = total_budget_minutes * rf
        selected, score = budgeted_submodular_selection(candidates, costs, b_risk, bucket_of)
        selected_cases = {case_of[fid] for fid in selected}
        recovered = selected_cases & true_positive_case_ids
        recall = len(recovered) / len(true_positive_case_ids) if true_positive_case_ids else float("nan")
        results.append(
            {
                "risk_fraction": rf,
                "b_risk_minutes": b_risk,
                "num_selected": len(selected),
                "recall": recall,
                "coverage_score": score,
            }
        )
    return results
