"""Gate 4 — Sampling validation (docs/validation_plan.md).

Recall@Budget and Supervisory Yield measured against random selection, top-score-only
ranking, and simulated current manual sampling, at multiple budget levels.

Simulated examiner verdicts: since there's no real human reviewer, each concern's
TRUE_SUPERVISORY_FINDING/FALSE_POSITIVE verdict is drawn stochastically per
finding_type from a documented, seeded rate — a simulation parameter for testing this
gate's machinery, never presented as a real accuracy claim about any detector.
EXCESSIVE_REASSIGNMENT_CARDINALITY is deliberately given a low simulated true rate,
consistent with this build's own documented skepticism of that rule
(src/satsa/okf/rules.py's docstring) — it is NOT counted toward ground-truth recall,
only toward the simulated-yield metric.
"""
import random

from satsa.evidence.verdict import Verdict
from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.sampling.baselines import random_selection, stratified_manual_selection, top_score_selection
from satsa.sampling.submodular import budgeted_submodular_selection

SIMULATED_TRUE_RATE = {
    "REASSIGNMENT_LOOP": 0.95,
    "ESCALATION_SLA_VIOLATION": 0.90,
    "MISSING_ENRICHMENT": 0.85,
    "EXCESSIVE_REASSIGNMENT_CARDINALITY": 0.50,
    # Phase C detectors are heuristic/proxy-based (no planted ground truth exists
    # for any of them — see moat1/structural.py docstrings) — given a deliberately
    # moderate simulated rate for this gate's machinery only, same "not a real
    # accuracy claim" caveat as EXCESSIVE_REASSIGNMENT_CARDINALITY above.
    "FAST_CLOSE_OUTLIER": 0.50,
    "REPEATED_ALERT_NO_REMEDIATION": 0.50,
    "LOW_TELEMETRY_CRITICAL_ASSET": 0.50,
    "REPETITIVE_INVESTIGATION_PATTERN": 0.50,
}
GROUND_TRUTH_BACKED_TYPES = {"REASSIGNMENT_LOOP", "ESCALATION_SLA_VIOLATION", "MISSING_ENRICHMENT"}


def _simulate_verdict(rng: random.Random, concern) -> Verdict:
    is_true = rng.random() < SIMULATED_TRUE_RATE[concern.finding_type]
    if is_true:
        return Verdict(
            concern.finding_id, "TRUE_SUPERVISORY_FINDING",
            capability_link=concern.capability, sub_type="PROCESS_VIOLATION", authority_violated=concern.authority,
        )
    return Verdict(concern.finding_id, "FALSE_POSITIVE")


def _recall(selected: set[str], ground_truth_ids: set[str], id_of) -> float:
    if not ground_truth_ids:
        return float("nan")
    selected_gt = {id_of[fid] for fid in selected if id_of[fid] in ground_truth_ids}
    return len(selected_gt) / len(ground_truth_ids)


def _recall_per_type(selected: set[str], candidates: list[str], type_of, case_of, finding_types) -> dict[str, float]:
    result = {}
    for ft in finding_types:
        cases_of_type = {case_of[fid] for fid in candidates if type_of[fid] == ft}
        if not cases_of_type:
            continue
        selected_cases_of_type = {case_of[fid] for fid in selected if type_of[fid] == ft}
        result[ft] = len(selected_cases_of_type) / len(cases_of_type)
    return result


def test_gate4_recall_and_yield_vs_baselines(tmp_path):
    ocel, ground_truth = generate(MATURE_CSE_SCALED)
    sqlite_path = str(tmp_path / "gate4.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    concerns = fuse(ocel, conn).concerns
    assert concerns

    candidates = [c.finding_id for c in concerns]
    costs = {c.finding_id: c.estimated_review_cost_minutes for c in concerns}
    scores = {c.finding_id: c.concern_score for c in concerns}
    bucket_of = {c.finding_id: f"{c.capability}|{c.finding_type}" for c in concerns}
    type_of = {c.finding_id: c.finding_type for c in concerns}
    case_of = {c.finding_id: c.affected_objects[0] for c in concerns}
    concern_by_id = {c.finding_id: c for c in concerns}

    # Real ground truth: any case with a ground-truth-backed concern type.
    ground_truth_case_ids = {case_of[fid] for fid in candidates if type_of[fid] in GROUND_TRUTH_BACKED_TYPES}
    assert ground_truth_case_ids

    total_cost = sum(costs.values())
    verdict_rng = random.Random(2026)
    verdicts = {fid: _simulate_verdict(verdict_rng, concern_by_id[fid]) for fid in candidates}

    def yield_per_hour(selected: set[str]) -> float:
        hours = sum(costs[fid] for fid in selected) / 60.0
        if hours == 0:
            return 0.0
        n_true = sum(1 for fid in selected if verdicts[fid].verdict == "TRUE_SUPERVISORY_FINDING")
        return n_true / hours

    budget_fractions = [0.1, 0.2, 0.3, 0.4]
    submodular_recalls, random_recalls, topscore_recalls, manual_recalls = [], [], [], []
    submodular_min_type_recalls, topscore_min_type_recalls = [], []

    for bf in budget_fractions:
        budget = total_cost * bf
        rng = random.Random(int(bf * 1000))

        sel_submodular, _ = budgeted_submodular_selection(candidates, costs, budget, bucket_of)
        sel_random = random_selection(candidates, costs, budget, rng)
        sel_topscore = top_score_selection(candidates, costs, scores, budget)
        sel_manual = stratified_manual_selection(candidates, costs, type_of, budget)

        r_sub = _recall(sel_submodular, ground_truth_case_ids, case_of)
        r_rand = _recall(sel_random, ground_truth_case_ids, case_of)
        r_top = _recall(sel_topscore, ground_truth_case_ids, case_of)
        r_man = _recall(sel_manual, ground_truth_case_ids, case_of)
        submodular_recalls.append(r_sub)
        random_recalls.append(r_rand)
        topscore_recalls.append(r_top)
        manual_recalls.append(r_man)

        sub_by_type = _recall_per_type(sel_submodular, candidates, type_of, case_of, GROUND_TRUTH_BACKED_TYPES)
        top_by_type = _recall_per_type(sel_topscore, candidates, type_of, case_of, GROUND_TRUTH_BACKED_TYPES)
        submodular_min_type_recalls.append(min(sub_by_type.values()))
        topscore_min_type_recalls.append(min(top_by_type.values()))

        print(
            f"budget_fraction={bf:.1f} minutes={budget:.0f} | "
            f"aggregate recall submodular={r_sub:.3f} random={r_rand:.3f} top-score={r_top:.3f} manual={r_man:.3f} | "
            f"yield/hr submodular={yield_per_hour(sel_submodular):.3f} random={yield_per_hour(sel_random):.3f} "
            f"top-score={yield_per_hour(sel_topscore):.3f} manual={yield_per_hour(sel_manual):.3f}"
        )
        print(f"  per-type recall submodular={sub_by_type} top-score={top_by_type}")

    # The real, demonstrated claim (verified empirically, not just aggregate recall,
    # which turned out to be the WRONG metric here — see docs/assumptions.md entry
    # 008 for why): MISSING_ENRICHMENT outnumbers ESCALATION_SLA_VIOLATION and
    # REASSIGNMENT_LOOP roughly 12-to-1 in this generated dataset, so aggregate
    # case-count recall is dominated by whichever method happens to grab more
    # MISSING_ENRICHMENT cases — noise, not signal. The actual value of
    # diminishing-returns bucket-aware selection is BALANCED coverage across finding
    # types: top-score-only ranking spends the entire low budget on the single
    # highest-scoring bucket (ESCALATION_SLA_VIOLATION, MANDATORY authority) and
    # recovers ZERO REASSIGNMENT_LOOP cases at bf=0.1, while submodular selection
    # covers all three types even at the smallest budget. That's what
    # "diminishing returns per bucket" is actually for (Section 10.1).
    for i, bf in enumerate(budget_fractions):
        assert submodular_min_type_recalls[i] >= topscore_min_type_recalls[i], (
            f"at budget_fraction={bf}: submodular's worst-covered finding_type recall "
            f"({submodular_min_type_recalls[i]:.3f}) should be >= top-score's "
            f"({topscore_min_type_recalls[i]:.3f})"
        )
    assert submodular_min_type_recalls[0] > 0, "submodular selection should cover every finding_type even at the smallest budget"
    assert topscore_min_type_recalls[0] == 0.0, "expected top-score-only ranking to fully starve at least one finding_type at the smallest budget — if not, the comparison below is vacuous"
