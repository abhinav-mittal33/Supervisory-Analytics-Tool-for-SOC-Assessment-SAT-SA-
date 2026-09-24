"""Causal estimation for Moat 2 (build spec Section 12).

Identification (which adjustment set backdoor-identifies the effect, and under what
explicit unconfoundedness assumption) goes through DoWhy's `CausalModel` — this is
where a documented, formal statement of the estimand and its assumptions comes from,
per Section 12's "document treatment, outcome, confounders, assumptions, estimand
explicitly." The numeric estimate, its confidence interval, and the sensitivity input
(t-statistic, residual degrees of freedom) come from `statsmodels` OLS directly on the
backdoor-adjusted regression, not DoWhy's own estimator wrapper — verified more
reliable for extracting a usable CI and the inputs sensitivity.py needs (see
docs/assumptions.md entry 009 for why DoWhy's own simulation-based refuter was tried
first and found unsuitable for this build's sensitivity analysis).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm
from dowhy import CausalModel


@dataclass(frozen=True)
class CausalEstimate:
    treatment: str
    outcome: str
    confounders_used: tuple[str, ...]
    effect: float
    ci_low: float
    ci_high: float
    t_statistic: float
    df_resid: float
    estimand_description: str


def estimate_effect(
    df: pd.DataFrame, treatment: str, outcome: str, confounders: tuple[str, ...], alpha: float = 0.05
) -> CausalEstimate:
    model = CausalModel(data=df, treatment=treatment, outcome=outcome, common_causes=list(confounders))
    identified = model.identify_effect(proceed_when_unidentifiable=True)

    covariates = [treatment, *confounders]
    ols = sm.OLS(df[outcome], sm.add_constant(df[covariates])).fit()
    ci = ols.conf_int(alpha=alpha)

    return CausalEstimate(
        treatment=treatment,
        outcome=outcome,
        confounders_used=tuple(confounders),
        effect=float(ols.params[treatment]),
        ci_low=float(ci.loc[treatment, 0]),
        ci_high=float(ci.loc[treatment, 1]),
        t_statistic=float(ols.tvalues[treatment]),
        df_resid=float(ols.df_resid),
        estimand_description=str(identified),
    )
