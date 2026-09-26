from datetime import datetime, timedelta, timezone

from satsa.moat2.real_data import (
    REASSIGNMENT_LOOP_OUTCOME,
    REASSIGNMENT_LOOP_TREATMENT,
    build_case_outcome_dataframe,
    build_reassignment_loop_dataframe,
    has_enough_variation,
)
from satsa.ocel.model import EPOCH, OCEL, Event, Obj, ObjectAttributeValue, Relationship

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _analyst(aid, tier):
    return Obj(aid, "Analyst", (ObjectAttributeValue("tier", tier, EPOCH),), ())


def _loop_events(case_id):
    a, b = "ANL_JUNIOR", "ANL_SENIOR"  # target doesn't matter for loop detection, just repetition
    return [
        Event(f"R1_{case_id}", "REASSIGN", T0, (), (Relationship(case_id, "reassignment_for_case"), Relationship(a, "reassigned_to"))),
        Event(f"R2_{case_id}", "REASSIGN", T0 + timedelta(minutes=10), (), (Relationship(case_id, "reassignment_for_case"), Relationship(b, "reassigned_to"))),
        Event(f"R3_{case_id}", "REASSIGN", T0 + timedelta(minutes=20), (), (Relationship(case_id, "reassignment_for_case"), Relationship(a, "reassigned_to"))),
    ]


def _case(case_id, analyst_id, looped: bool):
    return Obj(case_id, "Case", (), (Relationship(analyst_id, "current_assignee"),)), (_loop_events(case_id) if looped else [])


def _build_ocel(cases):
    ocel = OCEL()
    ocel.objects = [_analyst("ANL_SENIOR", "SENIOR"), _analyst("ANL_JUNIOR", "JUNIOR")]
    for case_id, analyst_id, looped in cases:
        obj, events = _case(case_id, analyst_id, looped)
        ocel.objects.append(obj)
        ocel.events += events
    return ocel


def test_build_dataframe_maps_tier_to_treatment_and_loop_to_outcome():
    ocel = _build_ocel([
        ("C1", "ANL_SENIOR", False), ("C2", "ANL_SENIOR", False), ("C3", "ANL_SENIOR", True),
        ("C4", "ANL_JUNIOR", True), ("C5", "ANL_JUNIOR", True), ("C6", "ANL_JUNIOR", False),
    ])
    df = build_reassignment_loop_dataframe(ocel)
    assert len(df) == 6
    by_case = df.set_index("case_id")
    assert by_case.loc["C1", REASSIGNMENT_LOOP_TREATMENT] == 1  # SENIOR
    assert by_case.loc["C1", REASSIGNMENT_LOOP_OUTCOME] == 1   # no loop
    assert by_case.loc["C3", REASSIGNMENT_LOOP_OUTCOME] == 0   # looped
    assert by_case.loc["C4", REASSIGNMENT_LOOP_TREATMENT] == 0  # JUNIOR


def test_cases_with_unknown_tier_are_dropped_not_guessed():
    ocel = _build_ocel([("C1", "ANL_SENIOR", False)])
    ocel.objects.append(Obj("C2", "Case", (), (Relationship("ANL_MYSTERY", "current_assignee"),)))
    df = build_reassignment_loop_dataframe(ocel)
    assert "C2" not in set(df["case_id"])


def test_has_enough_variation_true_for_a_real_mixed_sample():
    ocel = _build_ocel([
        ("C1", "ANL_SENIOR", False), ("C2", "ANL_SENIOR", False), ("C3", "ANL_SENIOR", True),
        ("C4", "ANL_JUNIOR", True), ("C5", "ANL_JUNIOR", True), ("C6", "ANL_JUNIOR", False),
    ])
    assert has_enough_variation(build_reassignment_loop_dataframe(ocel)) is True


def test_has_enough_variation_false_when_every_case_looped():
    ocel = _build_ocel([(f"C{i}", "ANL_SENIOR" if i % 2 else "ANL_JUNIOR", True) for i in range(6)])
    assert has_enough_variation(build_reassignment_loop_dataframe(ocel)) is False


def test_has_enough_variation_false_below_min_rows():
    ocel = _build_ocel([("C1", "ANL_SENIOR", False), ("C2", "ANL_JUNIOR", True)])
    assert has_enough_variation(build_reassignment_loop_dataframe(ocel)) is False


def test_generic_builder_supports_a_different_finding_types_flagged_set_on_the_same_ocel():
    """The same OCEL, analyzed against two DIFFERENT flagged-case sets (as if two
    different finding_types), must produce two independently-correct dataframes —
    proving this is a real, reusable estimand, not hardcoded to reassignment loops."""
    ocel = _build_ocel([
        ("C1", "ANL_SENIOR", False), ("C2", "ANL_SENIOR", False), ("C3", "ANL_SENIOR", True),
        ("C4", "ANL_JUNIOR", True), ("C5", "ANL_JUNIOR", True), ("C6", "ANL_JUNIOR", False),
    ])
    loop_flagged = {"C3", "C4", "C5"}
    other_flagged = {"C1", "C6"}  # a different, unrelated finding_type's flagged set

    loop_df = build_case_outcome_dataframe(ocel, loop_flagged).set_index("case_id")
    other_df = build_case_outcome_dataframe(ocel, other_flagged).set_index("case_id")

    assert loop_df.loc["C3", "Y_case_ok"] == 0 and other_df.loc["C3", "Y_case_ok"] == 1
    assert other_df.loc["C1", "Y_case_ok"] == 0 and loop_df.loc["C1", "Y_case_ok"] == 1
