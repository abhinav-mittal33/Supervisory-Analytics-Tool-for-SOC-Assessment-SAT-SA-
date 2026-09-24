"""Build Order Step 4 — second, structurally distinct, full-scale CSE profile.

Confirms Gate 0 still holds once the generator is scaled up (Section 14.5: validate
small first, scale after — Gate 0 already passed at dev-scale in
tests/test_gate0_ocel.py; this file is the "scale after" half), and that the two
profiles are genuinely structurally distinct rather than the same generator reseeded
(Section 14.2 — cross-CSE variance is what the peer-comparison/negative-space
baselines need to be demonstrable at all).
"""
import pytest

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED, SMALL_CSE_SCALED
from satsa.ocel import json_io, sqlite_io, validate

REQUIRED_OBJECT_TYPES = {"Alert", "Case", "Analyst", "Queue", "Asset"}


@pytest.mark.parametrize("profile", [MATURE_CSE_SCALED, SMALL_CSE_SCALED])
def test_gate0_holds_at_full_scale(profile, tmp_path):
    ocel, ground_truth = generate(profile)

    assert len(ocel.objects) > 0
    assert len([o for o in ocel.objects if o.type == "Case"]) == profile.num_cases
    assert len([o for o in ocel.objects if o.type == "Analyst"]) == profile.num_analysts

    sqlite_path = str(tmp_path / f"{profile.name}.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    validate.validate_all(ocel, sqlite_path, required_object_types=REQUIRED_OBJECT_TYPES)

    back = sqlite_io.read_sqlite(sqlite_path)
    assert {o.id for o in back.objects} == {o.id for o in ocel.objects}
    assert {e.id for e in back.events} == {e.id for e in ocel.events}

    positives = [g for g in ground_truth if not g["is_hard_negative"]]
    hard_negatives = [g for g in ground_truth if g["is_hard_negative"]]
    assert len(positives) == profile.num_reassignment_loop_positive
    assert len(hard_negatives) == profile.num_reassignment_loop_hard_negative


def test_the_two_scaled_profiles_are_structurally_distinct():
    """Two identical populations can't show a meaningful peer deviation (Section 14.2) —
    assert the generated data actually differs, not just the input parameters."""
    mature_ocel, _ = generate(MATURE_CSE_SCALED)
    small_ocel, _ = generate(SMALL_CSE_SCALED)

    assert MATURE_CSE_SCALED.num_analysts != SMALL_CSE_SCALED.num_analysts
    assert MATURE_CSE_SCALED.telemetry_coverage != SMALL_CSE_SCALED.telemetry_coverage
    assert MATURE_CSE_SCALED.escalation_compliance_rate != SMALL_CSE_SCALED.escalation_compliance_rate

    def escalated_case_count(ocel):
        return len({r.target_id for e in ocel.events if e.type == "ESCALATE" for r in e.relationships})

    mature_escalations = escalated_case_count(mature_ocel)
    small_escalations = escalated_case_count(small_ocel)
    # Different escalation_compliance_rate + different severity/criticality weighting
    # should produce a materially different absolute escalation count even accounting
    # for the mature profile's slightly larger case count.
    assert mature_escalations != small_escalations
