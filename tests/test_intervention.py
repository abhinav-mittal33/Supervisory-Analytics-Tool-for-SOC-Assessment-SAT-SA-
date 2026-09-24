"""Build Order Step 11 — Moat 2 is gated strictly behind TRUE_SUPERVISORY_FINDING
verdicts (Section 12), never running on raw anomalies or unconfirmed findings."""
import pytest

from satsa.evidence.verdict import Verdict
from satsa.moat2.intervention import MoatTwoGateError, analyze_intervention
from satsa.moat2.synthetic_causal_data import generate_intervention_scenario


def test_rejects_a_non_true_supervisory_finding_verdict():
    df = generate_intervention_scenario(n=500, seed=1, true_effect=2.0, confounder_strength_on_treatment=0.0, confounder_strength_on_outcome=0.0)
    verdict = Verdict("F1", "FALSE_POSITIVE")
    with pytest.raises(MoatTwoGateError):
        analyze_intervention(verdict, df, treatment="T", outcome="Y")


def test_runs_and_produces_a_structured_opportunity_for_a_confirmed_finding():
    df = generate_intervention_scenario(n=4000, seed=1, true_effect=3.0, confounder_strength_on_treatment=0.0, confounder_strength_on_outcome=0.0)
    verdict = Verdict("F1", "TRUE_SUPERVISORY_FINDING", capability_link="Operational Discipline",
                       sub_type="PROCESS_VIOLATION", authority_violated="EXPECTED")
    opportunity = analyze_intervention(verdict, df, treatment="T", outcome="Y", feasibility_note="staffing change, low cost")

    assert opportunity.finding_id == "F1"
    assert opportunity.effect > 0
    assert opportunity.decision in ("ACT", "INVESTIGATE_MORE")
    assert "backdoor" in opportunity.estimand_description.lower()
    assert opportunity.feasibility_note == "staffing change, low cost"
