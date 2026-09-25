"""Causal estimation for Moat 2 (build spec Section 12).

Identification (which adjustment set backdoor-identifies the effect, and whether the
declared confounders actually satisfy the backdoor criterion) goes through pgmpy's
`Adjustment` — chosen over the originally-planned DoWhy after DoWhy was found to
unconditionally pull in `cvxopt` (GPL-3.0-or-later) through its own package `__init__`
import chain (dowhy -> dowhy.gcm -> causal-learn's KCI independence test -> cvxopt),
confirmed by removing those packages and watching `from dowhy import CausalModel`
fail outright — not something we could avoid while still importing DoWhy at all. See
docs/assumptions.md entry 010 for the full account, including why pgmpy is a better
fit here regardless of the license issue (a small, purpose-built identification API
vs. a much heavier general framework we were using 1% of).

The numeric estimate, its confidence interval, and the sensitivity input (t-statistic,
residual degrees of freedom) come from `statsmodels` OLS directly on the
backdoor-adjusted regression, unchanged from before.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import statsmodels.api as sm
from pgmpy.base import DAG
from pgmpy.identification import Adjustment


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
    edges = [(c, treatment) for c in confounders] + [(c, outcome) for c in confounders] + [(treatment, outcome)]
    dag = DAG(ebunch=edges, roles={"exposures": treatment, "outcomes": outcome})
    dag_with_adjustment, identified = Adjustment(variant="minimal").identify(dag)
    adjustment_set = tuple(sorted(dag_with_adjustment.get_role_dict().get("adjustment", [])))

    covariates = [treatment, *adjustment_set]
    ols = sm.OLS(df[outcome], sm.add_constant(df[covariates])).fit()
    ci = ols.conf_int(alpha=alpha)

    estimand_description = (
        f"backdoor adjustment identified={identified}; "
        f"estimand: d/d[{treatment}] E[{outcome} | {', '.join(adjustment_set) or '(no adjustment needed)'}]; "
        f"unconfoundedness assumption: no unobserved common cause of {treatment} and {outcome} "
        f"outside {{{', '.join(adjustment_set)}}}"
    )

    return CausalEstimate(
        treatment=treatment,
        outcome=outcome,
        confounders_used=adjustment_set,
        effect=float(ols.params[treatment]),
        ci_low=float(ci.loc[treatment, 0]),
        ci_high=float(ci.loc[treatment, 1]),
        t_statistic=float(ols.tvalues[treatment]),
        df_resid=float(ols.df_resid),
        estimand_description=estimand_description,
    )
