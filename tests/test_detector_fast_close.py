from datetime import datetime, timedelta, timezone

from satsa.moat1.structural import detect_fast_close
from satsa.ocel.model import OCEL, Event, Relationship

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _events(case_id, assign_offset_min, close_offset_min):
    return [
        Event(f"ASSIGN_{case_id}", "ASSIGN", T0 + timedelta(minutes=assign_offset_min), (), (Relationship(case_id, "assignment_for_case"),)),
        Event(f"CLOSE_{case_id}", "CLOSE", T0 + timedelta(minutes=close_offset_min), (), (Relationship(case_id, "close_for_case"),)),
    ]


def test_case_closed_within_threshold_is_flagged_fast():
    ocel = OCEL()
    ocel.events = _events("CASE_FAST", 0, 10)
    signals = detect_fast_close(ocel, fast_threshold_minutes=30.0)
    assert signals[0].is_fast is True
    assert signals[0].duration_minutes == 10.0


def test_case_closed_well_outside_threshold_is_not_flagged():
    ocel = OCEL()
    ocel.events = _events("CASE_NORMAL", 0, 120)
    signals = detect_fast_close(ocel, fast_threshold_minutes=30.0)
    assert signals[0].is_fast is False


def test_case_with_no_close_event_produces_no_signal():
    ocel = OCEL()
    ocel.events = [Event("ASSIGN_X", "ASSIGN", T0, (), (Relationship("CASE_OPEN", "assignment_for_case"),))]
    assert detect_fast_close(ocel) == []
