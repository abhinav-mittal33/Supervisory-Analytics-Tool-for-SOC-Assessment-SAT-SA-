from satsa.moat1.structural import asset_alert_counts
from satsa.ocel.model import EPOCH, OCEL, Obj, ObjectAttributeValue, Relationship


def _asset(asset_id, criticality):
    return Obj(asset_id, "Asset", (ObjectAttributeValue("criticality", criticality, EPOCH),), ())


def _alert(alert_id, asset_id):
    return Obj(alert_id, "Alert", (), (Relationship(asset_id, "raised_on_asset"),))


def test_counts_alerts_per_asset_and_carries_criticality():
    ocel = OCEL()
    ocel.objects = [
        _asset("AST_CRIT", "CRITICAL"), _alert("AL1", "AST_CRIT"),
        _asset("AST_LOW", "LOW"), _alert("AL2", "AST_LOW"), _alert("AL3", "AST_LOW"),
    ]
    counts = {aid: (crit, n) for aid, crit, n in asset_alert_counts(ocel)}
    assert counts["AST_CRIT"] == ("CRITICAL", 1)
    assert counts["AST_LOW"] == ("LOW", 2)


def test_asset_with_zero_alerts_still_appears_with_zero_count():
    ocel = OCEL()
    ocel.objects = [_asset("AST_SILENT", "HIGH")]
    counts = {aid: n for aid, _crit, n in asset_alert_counts(ocel)}
    assert counts["AST_SILENT"] == 0
