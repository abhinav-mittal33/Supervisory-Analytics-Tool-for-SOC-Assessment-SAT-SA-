"""ACT / INVESTIGATE_MORE decision (build spec Section 12): never force a
recommendation when uncertainty is too high relative to the decision's stakes.

ROBUSTNESS_VALUE_THRESHOLD is a documented, conservative constant, not tuned to make
any specific scenario pass — see docs/assumptions.md entry 009. Because RV measures
statistical strength re-expressed as "confounding units" rather than detecting actual
hidden bias (sensitivity.py's docstring explains why that's a fundamental limit, not
an implementation gap), the honest, conservative policy is: only ACT on an effect
that is both distinguishable from zero AND strong enough that a substantial
confounder would be needed to fully explain it away. Weak-to-moderate effects — where
residual confounding risk matters most — correctly fall back to INVESTIGATE_MORE
whether or not they happen to actually be confounded.
"""
from __future__ import annotations

ROBUSTNESS_VALUE_THRESHOLD = 0.3


def decide(effect: float, ci_low: float, ci_high: float, robustness_value: float) -> str:
    ci_excludes_zero = ci_low > 0 or ci_high < 0
    robust_enough = robustness_value >= ROBUSTNESS_VALUE_THRESHOLD
    if ci_excludes_zero and robust_enough:
        return "ACT"
    return "INVESTIGATE_MORE"
