"""Beta-Binomial feedback loop (build spec Section 10.6), debiased.

Per bucket (capability x finding_type — peer_group/CSE dimension deferred, see
docs/assumptions.md entry 006), two SEPARATE Beta posteriors are tracked:
risk-selected verdicts and random-calibration verdicts. Updating from risk-selected
verdicts alone teaches "P(TRUE | we already thought this was likely)" — an inflated,
self-confirming number — not "P(TRUE | population)". The random-calibration posterior
is what estimates the latter; the risk-selected posterior is kept and exposed
specifically so the gap between the two is visible, not hidden.

Per-verdict routing (Section 5.1 / 10.6's own table):
- TRUE_SUPERVISORY_FINDING -> success
- FALSE_POSITIVE, OUT_OF_SCOPE -> failure
- INCONCLUSIVE, DATA_QUALITY_ISSUE, EXPECTED_LEGITIMATE_BEHAVIOR,
  DUPLICATE_OF_EXISTING_FINDING -> no posterior update at all (each of the latter
  three instead feeds a different downstream mechanism — reliability model, OKF
  exception candidates, duplicate-finding linkage respectively — none of which are
  built in this step; logged, not silently dropped).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from satsa.evidence.verdict import BETA_BINOMIAL_FAILURE, BETA_BINOMIAL_SUCCESS, NO_POSTERIOR_UPDATE, Verdict


@dataclass
class BetaPosterior:
    alpha: float = 1.0  # uniform Beta(1,1) prior
    beta: float = 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def n_observations(self) -> int:
        return int(self.alpha + self.beta - 2)


@dataclass
class BucketPosteriors:
    risk_selected: BetaPosterior = field(default_factory=BetaPosterior)
    random_calibration: BetaPosterior = field(default_factory=BetaPosterior)


class BetaBinomialFeedback:
    def __init__(self) -> None:
        self._buckets: dict[str, BucketPosteriors] = {}
        self.skipped_log: list[str] = []

    def _bucket(self, bucket_key: str) -> BucketPosteriors:
        return self._buckets.setdefault(bucket_key, BucketPosteriors())

    def record(self, bucket_key: str, verdict: Verdict, sample: str) -> None:
        """sample is 'risk_selected' or 'random_calibration' — which sample the
        finding_id was drawn from, tracked explicitly so it updates the RIGHT
        posterior, never blended."""
        if sample not in ("risk_selected", "random_calibration"):
            raise ValueError(f"unknown sample type {sample!r}")

        bucket = self._bucket(bucket_key)
        posterior = bucket.risk_selected if sample == "risk_selected" else bucket.random_calibration

        if verdict.verdict in BETA_BINOMIAL_SUCCESS:
            posterior.alpha += 1
        elif verdict.verdict in BETA_BINOMIAL_FAILURE:
            posterior.beta += 1
        elif verdict.verdict in NO_POSTERIOR_UPDATE:
            self.skipped_log.append(f"{verdict.finding_id}: verdict={verdict.verdict} does not update the true-finding-rate posterior")
        else:
            raise ValueError(f"unrouted verdict {verdict.verdict!r}")

    def debiased_true_finding_rate(self, bucket_key: str, min_calibration_observations: int = 5) -> tuple[float, str]:
        """Returns (rate, source). Prefers the random-calibration posterior once it
        has enough observations to be trusted; otherwise falls back to the
        risk-selected posterior with an explicit caveat that it's likely inflated,
        rather than silently presenting an unreliable number as if it were debiased."""
        bucket = self._bucket(bucket_key)
        if bucket.random_calibration.n_observations >= min_calibration_observations:
            return bucket.random_calibration.mean, "random_calibration"
        return bucket.risk_selected.mean, "risk_selected (uncalibrated — too few random-calibration observations)"

    def bucket_keys(self) -> list[str]:
        return list(self._buckets.keys())

    def get(self, bucket_key: str) -> BucketPosteriors:
        return self._bucket(bucket_key)
