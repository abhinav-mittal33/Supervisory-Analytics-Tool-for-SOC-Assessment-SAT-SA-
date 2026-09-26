from satsa.ingestion.normalization.canonical import build_ocel


def _relationship_targets(ocel, obj_or_event, qualifier):
    return [r.target_id for r in obj_or_event.relationships if r.qualifier == qualifier]


def test_build_ocel_produces_the_same_vocabulary_generate_py_uses():
    tables = {
        "cases": [{"case_id": "C1", "analyst_id": "A1", "queue_id": "Q1", "status": "OPEN",
                    "opened_at": "2026-01-01T09:00:00Z", "closed_at": None, "alert_id": None}],
        "case_events": [
            {"case_id": "C1", "event": "reassigned", "actor": "A2", "ts": "2026-01-01T09:10:00Z", "handover_reason": None},
            {"case_id": "C1", "event": "closed", "actor": None, "ts": "2026-01-01T09:20:00Z", "handover_reason": None},
        ],
    }
    ocel = build_ocel(tables, cse_id="CSE_TEST")

    case = next(o for o in ocel.objects if o.id == "C1")
    assert case.type == "Case"
    assert {a.name: a.value for a in case.attributes if a.time.year == 1970}["cse_id"] == "CSE_TEST"
    assert "A1" in _relationship_targets(ocel, case, "current_assignee")

    reassign_events = [e for e in ocel.events if e.type == "REASSIGN"]
    assert len(reassign_events) == 1
    assert _relationship_targets(ocel, reassign_events[0], "reassigned_to") == ["A2"]

    analyst_ids = {o.id for o in ocel.objects if o.type == "Analyst"}
    assert {"A1", "A2"} <= analyst_ids


def test_unrecognized_event_text_is_skipped_not_guessed():
    tables = {
        "cases": [{"case_id": "C1"}],
        "case_events": [{"case_id": "C1", "event": "coffee_break", "ts": "2026-01-01T09:00:00Z"}],
    }
    ocel = build_ocel(tables, cse_id="CSE_TEST")
    assert not any(e.type not in {"OPEN_CASE", "ASSIGN"} for e in ocel.events)


def test_missing_asset_gets_explicit_unknown_stand_in_not_fabricated_value():
    tables = {
        "alerts": [{"alert_id": "AL1", "asset_id": "AST_UNSEEN", "severity": "HIGH"}],
        "cases": [{"case_id": "C1", "alert_id": "AL1"}],
        "case_events": [],
    }
    ocel = build_ocel(tables, cse_id="CSE_TEST")
    asset = next(o for o in ocel.objects if o.id == "AST_UNSEEN")
    assert {a.name: a.value for a in asset.attributes}["criticality"] == "UNKNOWN"
