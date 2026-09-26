from satsa.ingestion.mapping.field_mapper import apply, apply_all


def test_apply_renames_source_columns_to_canonical_fields():
    raw = [{"incident_number": "INC-1", "owner": "J.Singh"}]
    mapped = apply(raw, {"case_id": "incident_number", "analyst_id": "owner", "status": None})
    assert mapped == [{"case_id": "INC-1", "analyst_id": "J.Singh", "status": None}]


def test_apply_missing_source_column_yields_none_not_an_error():
    raw = [{"case_id": "C1"}]
    mapped = apply(raw, {"case_id": "case_id", "status": "status"})
    assert mapped[0]["status"] is None


def test_apply_all_only_touches_known_canonical_tables():
    tables = {"cases": [{"id": "C1"}], "some_other_export": [{"x": 1}]}
    mapping = {"cases": {"case_id": "id"}}
    result = apply_all(tables, mapping)
    assert "some_other_export" not in result
    assert result["cases"] == [{"case_id": "C1"}]
