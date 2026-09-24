"""Build Order Step 10 — Beta-Binomial feedback loop, debiased (Section 10.6)."""
import random

from satsa.evidence.verdict import Verdict
from satsa.sampling.feedback import BetaBinomialFeedback


def _verdict(vtype: str, fid: str = "F") -> Verdict:
    if vtype == "TRUE_SUPERVISORY_FINDING":
        return Verdict(fid, vtype, capability_link="Escalation", sub_type="PROCESS_VIOLATION", authority_violated="MANDATORY")
    return Verdict(fid, vtype)


def test_success_and_failure_route_to_the_correct_posterior_side():
    fb = BetaBinomialFeedback()
    fb.record("bucket1", _verdict("TRUE_SUPERVISORY_FINDING"), "risk_selected")
    fb.record("bucket1", _verdict("FALSE_POSITIVE"), "risk_selected")
    posterior = fb.get("bucket1").risk_selected
    assert posterior.alpha == 2.0  # prior 1 + one success
    assert posterior.beta == 2.0  # prior 1 + one failure


def test_no_posterior_update_verdicts_are_logged_not_silently_dropped():
    fb = BetaBinomialFeedback()
    for vtype in ["INCONCLUSIVE", "DATA_QUALITY_ISSUE", "EXPECTED_LEGITIMATE_BEHAVIOR", "DUPLICATE_OF_EXISTING_FINDING"]:
        fb.record("bucket1", _verdict(vtype), "risk_selected")
    posterior = fb.get("bucket1").risk_selected
    assert posterior.alpha == 1.0 and posterior.beta == 1.0  # untouched, still the prior
    assert len(fb.skipped_log) == 4


def test_risk_selected_and_random_calibration_are_tracked_independently():
    fb = BetaBinomialFeedback()
    for _ in range(10):
        fb.record("bucket1", _verdict("TRUE_SUPERVISORY_FINDING"), "risk_selected")
    for _ in range(10):
        fb.record("bucket1", _verdict("FALSE_POSITIVE"), "random_calibration")

    bucket = fb.get("bucket1")
    assert bucket.risk_selected.mean > 0.9
    assert bucket.random_calibration.mean < 0.2


def test_posterior_mean_converges_toward_the_true_simulated_rate():
    rng = random.Random(7)
    true_rate = 0.3
    fb = BetaBinomialFeedback()
    for i in range(500):
        is_true = rng.random() < true_rate
        fb.record("bucket1", _verdict("TRUE_SUPERVISORY_FINDING" if is_true else "FALSE_POSITIVE", f"F{i}"), "random_calibration")
    mean = fb.get("bucket1").random_calibration.mean
    assert abs(mean - true_rate) < 0.05


def test_debiased_rate_falls_back_to_risk_selected_with_caveat_when_calibration_sparse():
    fb = BetaBinomialFeedback()
    for i in range(20):
        fb.record("bucket1", _verdict("TRUE_SUPERVISORY_FINDING", f"F{i}"), "risk_selected")
    rate, source = fb.debiased_true_finding_rate("bucket1", min_calibration_observations=5)
    assert source.startswith("risk_selected")
    assert rate > 0.9  # the (likely inflated) risk-selected estimate

    for i in range(10):
        fb.record("bucket1", _verdict("FALSE_POSITIVE", f"C{i}"), "random_calibration")
    rate2, source2 = fb.debiased_true_finding_rate("bucket1", min_calibration_observations=5)
    assert source2 == "random_calibration"
    assert rate2 < rate, "debiased estimate should differ from the inflated risk-selected one once calibration data exists"
