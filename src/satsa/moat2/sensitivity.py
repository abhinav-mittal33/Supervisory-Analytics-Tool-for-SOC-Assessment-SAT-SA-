"""Sensitivity analysis for Moat 2 (build spec Section 12): "quantify how large an
unobserved confounder's effect would need to be to flip the estimated direction — a
number, not a caveat sentence."

Implements the Robustness Value (RV) in closed form: Cinelli, C. & Hazlett, C. (2020).
"Making Sense of Sensitivity: Extending Omitted Variable Bias." Journal of the Royal
Statistical Society, Series B, 82(1). RV_q answers: what is the minimum strength (as
partial R^2, symmetric on treatment and outcome) an unobserved confounder would need
to have to reduce the estimated effect to q times its current value (q=1 -> to
exactly zero)? A closed-form function of the treatment coefficient's own t-statistic
and residual degrees of freedom — no simulation, no arbitrarily-scaled "effect
strength" parameter to sweep.

Chosen over DoWhy's own `add_unobserved_common_cause` simulation-based refuter after
that refuter was tried first and found unsuitable here — see docs/assumptions.md
entry 009: on this build's synthetic binary-treatment/binary-outcome data, its
effect_strength sweep flipped the estimate's sign at a similar, fairly low simulated
strength REGARDLESS of whether the underlying data actually had strong confounding,
weak confounding, or none at all — not a usable discriminator in this build's hands.

A crucial, honest limitation stated plainly, not hidden: RV measures how STATISTICALLY
ROBUST the *current* estimate is to being explained away — it is fundamentally
incapable of detecting whether the current estimate is *already* biased by an omitted
confounder (that is provably impossible from observational data alone; if it were
possible, the confounder wouldn't be "unobserved" in any meaningful sense). What RV
does provide, and what this build's decision policy is built around: a documented,
conservative refusal to output ACT unless the observed association is strong enough
that a substantial confounder (RV above a documented bar) would be needed to explain
it away — which correctly makes weak-to-moderate effects (exactly where residual
confounding risk matters most) fall back to INVESTIGATE_MORE, whether or not they
happen to also be confounded.
"""
from __future__ import annotations

import math


def robustness_value(t_statistic: float, df_resid: float, q: float = 1.0) -> float:
    f = q * abs(t_statistic) / math.sqrt(df_resid)
    return 0.5 * (math.sqrt(f**4 + 4 * f**2) - f**2)
