"""Gate 2 — Full pathology + hard-negative benchmark (docs/validation_plan.md).

All planted pathologies recovered, precision/recall/false-positive rate reported, and
true-negative rate on the full hard-negative set — a detector that flags every hard
negative alongside every real pathology fails this gate regardless of its positive-set
numbers, no exceptions.
"""
import pytest

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV, MATURE_CSE_SCALED, SMALL_CSE_SCALED
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler


def _by_type(concerns, finding_type):
    return {c.affected_objects[0] for c in concerns if c.finding_type == finding_type}


@pytest.mark.parametrize("profile", [MATURE_CSE_DEV, MATURE_CSE_SCALED, SMALL_CSE_SCALED])
def test_gate2_full_pathology_and_hard_negative_benchmark(profile, tmp_path):
    ocel, ground_truth = generate(profile)
    sqlite_path = str(tmp_path / f"{profile.name}_gate2.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)

    result = fuse(ocel, conn)
    reassignment_loop_cases = _by_type(result.concerns, "REASSIGNMENT_LOOP")
    cardinality_cases = _by_type(result.concerns, "EXCESSIVE_REASSIGNMENT_CARDINALITY")

    loops = [g for g in ground_truth if g["pathology"] == "REASSIGNMENT_LOOP"]
    actual_positives = {g["case_id"] for g in loops if not g["is_hard_negative"]}
    actual_hard_negatives = {g["case_id"] for g in loops if g["is_hard_negative"]}
    chain_no_loop_cases = {g["case_id"] for g in ground_truth if g["pathology"] == "REASSIGNMENT_CHAIN_NO_LOOP"}

    # --- All planted pathologies recovered ---
    assert actual_positives <= reassignment_loop_cases, f"missed: {actual_positives - reassignment_loop_cases}"

    # --- Precision / recall / false-positive rate on the reassignment-loop finding_type ---
    true_positives = reassignment_loop_cases & actual_positives
    false_positives = reassignment_loop_cases - actual_positives
    precision = len(true_positives) / len(reassignment_loop_cases) if reassignment_loop_cases else 1.0
    recall = len(true_positives) / len(actual_positives) if actual_positives else 1.0
    fp_rate = len(false_positives) / len(actual_hard_negatives | chain_no_loop_cases) if (actual_hard_negatives | chain_no_loop_cases) else 0.0
    print(f"[{profile.name}] Gate 2 REASSIGNMENT_LOOP: precision={precision:.3f} recall={recall:.3f} fp_rate={fp_rate:.3f}")
    assert precision == 1.0
    assert recall == 1.0
    assert fp_rate == 0.0

    # --- True-negative rate on the FULL hard-negative set ---
    # A hard negative must produce NO reassignment-related Concern at all — neither
    # the real detector's own flag, nor a resurrected false positive from the weaker
    # REASSIGN-CARD-001 rule that fusion was supposed to suppress.
    for case_id in actual_hard_negatives:
        assert case_id not in reassignment_loop_cases, f"{case_id}: hard negative flagged as REASSIGNMENT_LOOP"
        assert case_id not in cardinality_cases, f"{case_id}: hard negative flagged as EXCESSIVE_REASSIGNMENT_CARDINALITY"

    # Same standard for the count-only false-positive trap (Section 9.1's own example):
    for case_id in chain_no_loop_cases:
        assert case_id not in reassignment_loop_cases
        assert case_id not in cardinality_cases, f"{case_id}: chain-no-loop flagged by count-only rule despite fusion suppression"

    true_negative_rate = 1.0  # both assertion loops above passed with zero exceptions
    print(f"[{profile.name}] Gate 2 hard-negative true-negative rate: {true_negative_rate:.3f} "
          f"(n={len(actual_hard_negatives) + len(chain_no_loop_cases)})")

    # --- Suppression actually happened, not just "nothing was ever flagged" ---
    assert result.suppressed, "expected at least one suppression audit note"
