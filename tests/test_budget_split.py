"""Build Order Step 9 — triple-sample budget split, swept against real fused Concerns
and real ground truth (not a synthetic toy), per Section 10.3's own instruction: don't
mandate a split ratio, sweep it, and pick a documented default from the sweep.
"""
from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.sampling.budget_split import BudgetSplit, split_budget, sweep_risk_fraction


def test_budget_split_fractions_must_sum_to_one():
    BudgetSplit(baseline_fraction=0.5, random_calibration_fraction=0.2, risk_fraction=0.3)  # ok
    try:
        BudgetSplit(baseline_fraction=0.5, random_calibration_fraction=0.5, risk_fraction=0.5)
        assert False, "expected a ValueError for fractions summing to 1.5"
    except ValueError:
        pass


def test_split_budget_arithmetic():
    b_base, b_calib, b_risk = split_budget(1000.0, BudgetSplit(0.6, 0.1, 0.3))
    assert b_base == 600.0
    assert b_calib == 100.0
    assert b_risk == 300.0


def test_sweep_against_real_concerns_reports_recall_at_budget(tmp_path):
    ocel, ground_truth = generate(MATURE_CSE_SCALED)
    sqlite_path = str(tmp_path / "budget_sweep.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    result = fuse(ocel, conn)
    assert result.concerns, "no concerns produced — sweep would be vacuous"

    loops = [g for g in ground_truth if g["pathology"] == "REASSIGNMENT_LOOP" and not g["is_hard_negative"]]
    true_positive_case_ids = {g["case_id"] for g in loops}
    assert true_positive_case_ids <= {c.affected_objects[0] for c in result.concerns}

    total_cost = sum(c.estimated_review_cost_minutes for c in result.concerns)
    # Deliberately constrained below total cost so the budget forces real tradeoffs —
    # a sweep against an unconstrained budget where everything fits is vacuous too.
    total_budget_minutes = total_cost * 0.3

    risk_fractions = [0.5, 0.6, 0.7, 0.8, 0.9]
    sweep = sweep_risk_fraction(result.concerns, true_positive_case_ids, total_budget_minutes, risk_fractions)

    for row in sweep:
        print(f"risk_fraction={row['risk_fraction']:.1f} B_risk={row['b_risk_minutes']:.0f}min "
              f"selected={row['num_selected']} recall={row['recall']:.3f}")

    # Recall must be monotonically non-decreasing as B_risk's own share of the
    # (fixed) total budget grows — more risk-selected budget can only recover more
    # or the same, never fewer, true positives.
    recalls = [row["recall"] for row in sweep]
    assert all(recalls[i] <= recalls[i + 1] + 1e-9 for i in range(len(recalls) - 1))

    # Pick a documented default: the smallest risk_fraction whose recall is within 2
    # percentage points of the best recall achieved anywhere in the sweep — i.e. the
    # point where spending more of the budget on risk-selection stops paying off in
    # recall terms, so the remainder can go to the baseline/random-calibration split
    # instead of chasing marginal recall gains.
    best_recall = max(recalls)
    default_row = next(row for row in sweep if row["recall"] >= best_recall - 0.02)
    print(f"documented default: risk_fraction={default_row['risk_fraction']:.1f} "
          f"(recall={default_row['recall']:.3f} vs best={best_recall:.3f})")
    assert 0.5 <= default_row["risk_fraction"] <= 0.9
