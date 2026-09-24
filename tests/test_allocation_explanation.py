"""Build Order Step 9 — allocation-explanation objects (Section 10.5): every
allocation ships with a structured "why," never a bare number of hours."""
from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.sampling.allocation_explanation import explain_allocation
from satsa.sampling.submodular import budgeted_submodular_selection


def test_explanation_reflects_a_real_selection(tmp_path):
    ocel, _ = generate(MATURE_CSE_SCALED)
    sqlite_path = str(tmp_path / "alloc_explain.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    concerns = fuse(ocel, conn).concerns
    assert concerns

    candidates = [c.finding_id for c in concerns]
    costs = {c.finding_id: c.estimated_review_cost_minutes for c in concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in concerns}
    total_cost = sum(costs.values())
    budget = total_cost * 0.3

    selected, _ = budgeted_submodular_selection(candidates, costs, budget, bucket_of)
    explanation = explain_allocation(selected, concerns, budget, increment_minutes=total_cost * 0.1)

    assert explanation.num_concerns_selected == len(selected)
    assert sum(explanation.per_capability_counts.values()) == len(selected)
    assert explanation.marginal_coverage_gain_from_increment >= 0.0
    assert explanation.notes, "expected at least one structured explanatory note"
    assert all(isinstance(n, str) and n for n in explanation.notes)
    print("\n".join(explanation.notes))
    print("per-capability:", explanation.per_capability_counts)
