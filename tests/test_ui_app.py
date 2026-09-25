"""Build Order Step 13 — Examiner UI. Only the pure logic is unit-tested here
(case_trace); the interactive rendering (tabs, verdict form, audit trail) was verified
by launching the real Streamlit server and driving it with a browser — see the
build's own working notes, not reproducible as a headless pytest without a browser
dependency this project doesn't otherwise need.
"""
from datetime import datetime, timezone

from satsa.ocel.model import OCEL, Event, Obj, Relationship, TypeDef
from satsa.ui.app import case_trace


def test_case_trace_includes_every_event_touching_the_case():
    ocel = OCEL()
    ocel.object_types = [TypeDef("Case", ()), TypeDef("Analyst", ())]
    ocel.event_types = [TypeDef("ASSIGN", ()), TypeDef("CLOSE", ())]
    ocel.objects = [Obj("C1", "Case", (), ()), Obj("A1", "Analyst", (), ())]
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ocel.events = [
        Event("e1", "ASSIGN", t0, (), (Relationship("C1", "assignment_for_case"), Relationship("A1", "assigned_to"))),
        Event("e2", "CLOSE", t0, (), (Relationship("C1", "close_for_case"),)),
        Event("e3", "ASSIGN", t0, (), (Relationship("C2_OTHER_CASE", "assignment_for_case"),)),
    ]

    trace = case_trace(ocel, "C1")
    assert [row["event_type"] for row in trace] == ["ASSIGN", "CLOSE"]
    assert "assigned_to->A1" in trace[0]["other_relationships"]


def test_case_trace_is_chronologically_ordered():
    ocel = OCEL()
    ocel.object_types = [TypeDef("Case", ())]
    ocel.event_types = [TypeDef("X", ())]
    ocel.objects = [Obj("C1", "Case", (), ())]
    ocel.events = [
        Event("e2", "X", datetime(2026, 1, 2, tzinfo=timezone.utc), (), (Relationship("C1", "x_for_case"),)),
        Event("e1", "X", datetime(2026, 1, 1, tzinfo=timezone.utc), (), (Relationship("C1", "x_for_case"),)),
    ]
    trace = case_trace(ocel, "C1")
    assert [row["time"] for row in trace] == sorted(row["time"] for row in trace)
