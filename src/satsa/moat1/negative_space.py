"""Exposure-adjusted negative space (build spec Section 9.4).

Models Expected_k for a peer group via a Poisson regression with an exposure offset
rather than a raw ratio, because a raw ratio has no way to express how much to trust
itself. The pooled rate is itself an *estimate*, not a fixed constant, so its
confidence interval (not a point value) is what gets propagated into each peer
group's expected-count bounds — this is the "method that accounts for sampling error
when the baseline is itself estimated from a peer regression" the spec asks for,
as opposed to an exact CI appropriate to a genuinely fixed/known baseline.

Peer groups below MIN_PEER_GROUP_SIZE get their own rate estimate pulled toward the
pooled rate via empirical-Bayes (Poisson-Gamma conjugate) shrinkage, rather than a raw
percentile/z-score computed on a handful of cases (Section 9.4's explicit instruction).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import statsmodels.api as sm

MIN_PEER_GROUP_SIZE = 10
Z_CONCERN_THRESHOLD = -2.0  # observed this far below expected (in SD units) is flagged


@dataclass(frozen=True)
class PeerGroupObservation:
    group_id: str
    exposure: int  # count of duty-eligible cases in this peer group
    observed: int  # count of those cases where the expected evidence WAS present


@dataclass(frozen=True)
class NegativeSpaceFinding:
    group_id: str
    exposure: int
    observed: int
    expected: float
    expected_ci_low: float
    expected_ci_high: float
    shrunk: bool
    z_score: float | None
    abstain_reason: str | None  # None if a real (non-abstained) finding

    @property
    def flagged(self) -> bool:
        return self.abstain_reason is None and self.z_score is not None and self.z_score <= Z_CONCERN_THRESHOLD


def _fit_pooled_rate(observations: list[PeerGroupObservation], alpha: float) -> tuple[float, float, float]:
    counts = np.array([o.observed for o in observations], dtype=float)
    exposure = np.array([o.exposure for o in observations], dtype=float)
    exog = np.ones((len(observations), 1))
    model = sm.GLM(counts, exog, family=sm.families.Poisson(), offset=np.log(exposure))
    result = model.fit()
    log_rate = result.params[0]
    ci_low, ci_high = result.conf_int(alpha=alpha)[0]
    return float(np.exp(log_rate)), float(np.exp(ci_low)), float(np.exp(ci_high))


def _empirical_bayes_rate(observed: int, exposure: int, all_observations: list[PeerGroupObservation]) -> float:
    rates = np.array([o.observed / o.exposure for o in all_observations if o.exposure > 0])
    mean_rate = rates.mean()
    var_rate = rates.var(ddof=1) if len(rates) > 1 else 0.0
    if var_rate <= 0:
        return mean_rate  # degenerate case: no dispersion across peers to build a prior from
    beta = mean_rate / var_rate
    alpha_prior = mean_rate * beta
    return (alpha_prior + observed) / (beta + exposure)


def detect_negative_space(
    observations: list[PeerGroupObservation], alpha: float = 0.05
) -> list[NegativeSpaceFinding]:
    if len(observations) < 2:
        return [
            NegativeSpaceFinding(o.group_id, o.exposure, o.observed, float("nan"), float("nan"), float("nan"), False, None, "INSUFFICIENT_EVIDENCE")
            for o in observations
        ]

    # A zero-exposure group contributes log(0) = -inf to its own offset and would
    # break the pooled-rate fit for every OTHER group too — exclude it from fitting;
    # it gets its own INSUFFICIENT_EXPOSURE abstain below regardless.
    fittable = [o for o in observations if o.exposure > 0]
    if len(fittable) < 2:
        return [
            NegativeSpaceFinding(o.group_id, o.exposure, o.observed, float("nan"), float("nan"), float("nan"), False, None, "INSUFFICIENT_EVIDENCE")
            for o in observations
        ]
    pooled_rate, ci_low_rate, ci_high_rate = _fit_pooled_rate(fittable, alpha)

    findings = []
    for o in observations:
        if o.exposure == 0:
            findings.append(
                NegativeSpaceFinding(o.group_id, 0, o.observed, 0.0, 0.0, 0.0, False, None, "INSUFFICIENT_EXPOSURE")
            )
            continue

        shrunk = o.exposure < MIN_PEER_GROUP_SIZE
        rate = _empirical_bayes_rate(o.observed, o.exposure, observations) if shrunk else pooled_rate

        expected = rate * o.exposure
        expected_ci_low = ci_low_rate * o.exposure
        expected_ci_high = ci_high_rate * o.exposure
        sd = expected**0.5 if expected > 0 else None
        z = (o.observed - expected) / sd if sd else None

        findings.append(
            NegativeSpaceFinding(o.group_id, o.exposure, o.observed, expected, expected_ci_low, expected_ci_high, shrunk, z, None)
        )
    return findings
