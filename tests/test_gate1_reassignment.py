"""Gate 1 — Core pattern recovery (docs/validation_plan.md).

Recover the planted reassignment loop with measured precision/recall/F1, and
correctly reject its matched hard negative — STOP condition, not an aspiration.
"""
import pytest

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV, MATURE_CSE_SCALED, SMALL_CSE_SCALED
from satsa.moat1.structural import detect_reassignment_loops


def _ground_truth_sets(ground_truth):
    loops = [g for g in ground_truth if g["pathology"] == "REASSIGNMENT_LOOP"]
    positives = {g["case_id"] for g in loops if not g["is_hard_negative"]}
    hard_negatives = {g["case_id"] for g in loops if g["is_hard_negative"]}
    return positives, hard_negatives


@pytest.mark.parametrize("profile", [MATURE_CSE_DEV, MATURE_CSE_SCALED, SMALL_CSE_SCALED])
def test_gate1_precision_recall_f1_and_hard_negative_rejection(profile):
    ocel, ground_truth = generate(profile)
    actual_positives, actual_hard_negatives = _ground_truth_sets(ground_truth)

    signals = detect_reassignment_loops(ocel)
    flagged = {s.case_id for s in signals if s.flagged}
    structurally_detected = {s.case_id for s in signals if s.is_loop}

    # Section 9.1's own test: the raw structural pattern must be recognized in BOTH the
    # positive and the hard-negative set — proving the detector is genuinely reading
    # object relationships (which analyst, whether it repeats), not the justification
    # attribute. If it only "detected" the positives, it'd just be pattern-matching on
    # handover_reason, not on structure.
    assert actual_positives <= structurally_detected
    assert actual_hard_negatives <= structurally_detected

    # The actual Gate 1 requirement: hard negatives must be excluded from what's flagged.
    assert flagged.isdisjoint(actual_hard_negatives), (
        f"detector flagged {flagged & actual_hard_negatives} despite documented shift-change justification"
    )

    true_positives = flagged & actual_positives
    precision = len(true_positives) / len(flagged) if flagged else 1.0
    recall = len(true_positives) / len(actual_positives) if actual_positives else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    assert recall == 1.0, f"missed planted loops: {actual_positives - flagged}"
    assert precision == 1.0, f"false positives: {flagged - actual_positives}"
    assert f1 == 1.0

    print(f"[{profile.name}] Gate 1: precision={precision:.3f} recall={recall:.3f} f1={f1:.3f} "
          f"(positives={len(actual_positives)}, hard_negatives={len(actual_hard_negatives)})")
