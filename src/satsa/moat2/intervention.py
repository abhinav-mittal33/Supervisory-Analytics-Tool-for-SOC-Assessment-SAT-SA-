"""Supervisory Intervention Decision Engine entry point (build spec Section 12).

Gated strictly behind TRUE_SUPERVISORY_FINDING verdicts — never runs on raw anomalies
or unconfirmed findings. Ties together identification+estimation (causal_model.py),
the robustness value (sensitivity.py), and the ACT/INVESTIGATE_MORE policy
(decision.py) into the single structured output Section 12 asks for: target, outcome,
effect, uncertainty, and an explicit decision — never a bare number.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from satsa.evidence.verdict import Verdict
from satsa.moat2.causal_model import estimate_effect
from satsa.moat2.decision import decide
from satsa.moat2.sensitivity import robustness_value


class MoatTwoGateError(ValueError):
    pass


@dataclass(frozen=True)
class InterventionOpportunity:
    finding_id: str
    target: str
    outcome: str
    effect: float
    ci_low: float
    ci_high: float
    robustness_value: float
    estimand_description: str
    decision: str
    feasibility_note: str


def analyze_intervention(
    verdict: Verdict,
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    confounders: tuple[str, ...] = (),
    feasibility_note: str = "not assessed",
) -> InterventionOpportunity:
    if verdict.verdict != "TRUE_SUPERVISORY_FINDING":
        raise MoatTwoGateError(
            f"{verdict.finding_id}: Moat 2 runs only on TRUE_SUPERVISORY_FINDING verdicts, got {verdict.verdict!r}"
        )

    est = estimate_effect(df, treatment=treatment, outcome=outcome, confounders=confounders)
    rv = robustness_value(est.t_statistic, est.df_resid)
    decision = decide(est.effect, est.ci_low, est.ci_high, rv)

    return InterventionOpportunity(
        finding_id=verdict.finding_id,
        target=treatment,
        outcome=outcome,
        effect=est.effect,
        ci_low=est.ci_low,
        ci_high=est.ci_high,
        robustness_value=rv,
        estimand_description=est.estimand_description,
        decision=decision,
        feasibility_note=feasibility_note,
    )
