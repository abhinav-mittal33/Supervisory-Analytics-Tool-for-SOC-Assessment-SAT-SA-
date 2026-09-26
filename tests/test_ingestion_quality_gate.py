from satsa.ingestion.quality.validator import validate


def test_missing_required_table_triggers_abstain():
    report = validate({"cases": [{"case_id": "C1"}]})  # no case_events at all
    assert report.status == "ABSTAIN"
    assert any("case_events" in e for e in report.errors)


def test_missing_required_field_triggers_abstain_not_silent_drop():
    report = validate({
        "cases": [{"case_id": None}],
        "case_events": [{"case_id": "C1", "event": "closed", "ts": "2026-01-01T09:00:00Z"}],
    })
    assert report.status == "ABSTAIN"
    assert any("case_id" in e for e in report.errors)


def test_orphan_case_event_is_a_hard_error():
    report = validate({
        "cases": [{"case_id": "C1"}],
        "case_events": [{"case_id": "C_NOT_A_REAL_CASE", "event": "closed", "ts": "2026-01-01T09:00:00Z"}],
    })
    assert report.status == "ABSTAIN"
    assert any("no matching row" in e for e in report.errors)


def test_valid_minimal_data_passes_with_reduced_capability_notes():
    report = validate({
        "cases": [{"case_id": "C1"}],
        "case_events": [{"case_id": "C1", "event": "closed", "ts": "2026-01-01T09:00:00Z"}],
    })
    assert report.status == "OK"
    assert any("alerts" in note for note in report.reduced_capability)
    assert any("assets" in note for note in report.reduced_capability)


def test_unrecognized_event_text_is_reported_not_silently_dropped():
    report = validate({
        "cases": [{"case_id": "C1"}],
        "case_events": [{"case_id": "C1", "event": "coffee_break", "ts": "2026-01-01T09:00:00Z"}],
    })
    assert report.status == "OK"
    assert any("coffee_break" in note for note in report.reduced_capability)


def test_low_confidence_cases_tracks_only_cases_with_unrecognized_events():
    report = validate({
        "cases": [{"case_id": "C1"}, {"case_id": "C2"}],
        "case_events": [
            {"case_id": "C1", "event": "coffee_break", "ts": "2026-01-01T09:00:00Z"},
            {"case_id": "C2", "event": "closed", "ts": "2026-01-01T09:05:00Z"},
        ],
    })
    assert report.low_confidence_cases == {"C1"}
