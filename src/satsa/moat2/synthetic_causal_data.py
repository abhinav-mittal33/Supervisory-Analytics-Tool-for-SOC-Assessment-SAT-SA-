"""Synthetic data for Moat 2 (build spec Section 12) and its Gate 3 causal-honesty
test: a confounder C, a controllable treatment T (e.g. "senior analyst assigned"),
and an outcome Y (e.g. "escalated on time"), where C confounds T -> Y by design when
`confounder_strength_on_treatment` is nonzero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_intervention_scenario(
    n: int,
    seed: int,
    true_effect: float,
    confounder_strength_on_treatment: float,
    confounder_strength_on_outcome: float,
    base_treatment_rate: float = -0.5,
    base_outcome_rate: float = -0.5,
) -> pd.DataFrame:
    """C ~ Bernoulli(0.4). T ~ Bernoulli(sigmoid(base_treatment_rate +
    confounder_strength_on_treatment * C)). Y ~ Bernoulli(sigmoid(base_outcome_rate +
    true_effect * T + confounder_strength_on_outcome * C)). The TRUE causal effect of
    T on Y is `true_effect`; C confounds the T-Y association whenever both strength
    parameters are nonzero.
    """
    rng = np.random.default_rng(seed)
    c = rng.binomial(1, 0.4, n)
    p_t = 1 / (1 + np.exp(-(base_treatment_rate + confounder_strength_on_treatment * c)))
    t = rng.binomial(1, p_t, n)
    p_y = 1 / (1 + np.exp(-(base_outcome_rate + true_effect * t + confounder_strength_on_outcome * c)))
    y = rng.binomial(1, p_y, n)
    return pd.DataFrame({"C": c, "T": t, "Y": y})
