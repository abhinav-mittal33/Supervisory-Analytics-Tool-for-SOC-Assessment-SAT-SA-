from datetime import datetime, timezone

from satsa.moat1.structural import detect_asset_alert_recurrence
from satsa.ocel.model import OCEL, Event, Obj, Relationship

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _alert(alert_id, asset_id):
    return Obj(alert_id, "Alert", (), (Relationship(asset_id, "raised_on_asset"),))


def _case_for_alert(case_id, alert_id):
    return Obj(case_id, "Case", (), (Relationship(alert_id, "case_for_alert"),))


def test_repeated_alerts_no_investigation_anywhere_is_flagged():
    ocel = OCEL()
    ocel.objects = [
        _alert("AL1", "AST_BAD"), _alert("AL2", "AST_BAD"), _alert("AL3", "AST_BAD"),
        _case_for_alert("C1", "AL1"), _case_for_alert("C2", "AL2"), _case_for_alert("C3", "AL3"),
    ]
    signals = detect_asset_alert_recurrence(ocel, min_alerts=3)
    sig = next(s for s in signals if s.asset_id == "AST_BAD")
    assert sig.alert_count == 3
    assert sig.remediated is False
    assert sig.flagged is True


def test_repeated_alerts_with_investigation_depth_is_the_matched_hard_negative():
    ocel = OCEL()
    ocel.objects = [
        _alert("AL1", "AST_OK"), _alert("AL2", "AST_OK"), _alert("AL3", "AST_OK"),
        _case_for_alert("C1", "AL1"), _case_for_alert("C2", "AL2"), _case_for_alert("C3", "AL3"),
    ]
    ocel.events = [Event("INV1", "INVESTIGATE", T0, (), (Relationship("C2", "investigate_for_case"),))]
    signals = detect_asset_alert_recurrence(ocel, min_alerts=3)
    sig = next(s for s in signals if s.asset_id == "AST_OK")
    assert sig.remediated is True
    assert sig.flagged is False


def test_below_min_alerts_threshold_is_not_flagged_regardless_of_remediation():
    ocel = OCEL()
    ocel.objects = [_alert("AL1", "AST_QUIET"), _case_for_alert("C1", "AL1")]
    signals = detect_asset_alert_recurrence(ocel, min_alerts=3)
    sig = next(s for s in signals if s.asset_id == "AST_QUIET")
    assert sig.alert_count == 1
    assert sig.flagged is False
