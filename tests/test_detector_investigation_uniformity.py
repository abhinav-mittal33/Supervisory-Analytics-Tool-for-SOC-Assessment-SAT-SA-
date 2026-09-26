from datetime import datetime, timedelta, timezone

from satsa.moat1.structural import detect_investigation_uniformity
from satsa.ocel.model import OCEL, Event, Relationship

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _case_events(case_id, analyst_id, investigate_offset_min, close_offset_min):
    return [
        Event(f"INV_{case_id}", "INVESTIGATE", T0 + timedelta(minutes=investigate_offset_min), (),
              (Relationship(case_id, "investigate_for_case"), Relationship(analyst_id, "investigated_by"))),
        Event(f"CLOSE_{case_id}", "CLOSE", T0 + timedelta(minutes=close_offset_min), (), (Relationship(case_id, "close_for_case"),)),
    ]


def test_suspiciously_uniform_durations_are_flagged():
    ocel = OCEL()
    ocel.events = []
    # investigate-to-close duration ~60min every time, near-zero variance -> low CoV
    for i in range(6):
        ocel.events += _case_events(f"C{i}", "ANL_TEMPLATE", 0, 60 + (i % 2))  # 60 or 61 min
    signals = detect_investigation_uniformity(ocel, min_cases=5, cov_threshold=0.15)
    sig = next(s for s in signals if s.analyst_id == "ANL_TEMPLATE")
    assert sig.num_investigations == 6
    assert sig.flagged is True


def test_naturally_varied_durations_are_the_matched_hard_negative():
    ocel = OCEL()
    ocel.events = []
    durations = [20, 45, 90, 200, 15, 300]  # wide spread, not template-driven
    for i, dur in enumerate(durations):
        ocel.events += _case_events(f"C{i}", "ANL_NORMAL", 0, dur)
    signals = detect_investigation_uniformity(ocel, min_cases=5, cov_threshold=0.15)
    sig = next(s for s in signals if s.analyst_id == "ANL_NORMAL")
    assert sig.flagged is False


def test_below_min_cases_yields_no_cov_and_is_not_flagged():
    ocel = OCEL()
    ocel.events = []
    for i in range(3):
        ocel.events += _case_events(f"C{i}", "ANL_FEW", 0, 60)
    signals = detect_investigation_uniformity(ocel, min_cases=5)
    sig = next(s for s in signals if s.analyst_id == "ANL_FEW")
    assert sig.coefficient_of_variation is None
    assert sig.flagged is False
