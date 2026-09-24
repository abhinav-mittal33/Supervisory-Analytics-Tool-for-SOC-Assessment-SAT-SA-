"""Gate 0 — Data validity (docs/validation_plan.md).

OCEL opens, validates, round-trips; five object types present with required
attributes; timestamps present; relationships present and qualified; ground-truth IDs
correspond to real synthetic records.
"""
import json
from pathlib import Path

import pytest

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV
from satsa.ocel import json_io, sqlite_io, validate

REQUIRED_OBJECT_TYPES = {"Alert", "Case", "Analyst", "Queue", "Asset"}


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    ocel, ground_truth = generate(MATURE_CSE_DEV)
    d = tmp_path_factory.mktemp("gate0")
    sqlite_path = str(d / "cse_alpha_dev.sqlite")
    json_path = str(d / "cse_alpha_dev.json")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    json_io.write_json(ocel, json_path)
    return ocel, ground_truth, sqlite_path, json_path


def test_five_object_types_present_with_required_attributes(generated):
    ocel, _, _, _ = generated
    present = {t.name: {a.name for a in t.attributes} for t in ocel.object_types}
    assert REQUIRED_OBJECT_TYPES <= set(present)
    assert present["Asset"] >= {"criticality", "asset_type"}
    assert present["Alert"] >= {"severity", "category"}
    assert present["Case"] >= {"status"}
    assert present["Analyst"] >= {"tier"}
    assert present["Queue"] >= {"name"}


def test_json_schema_validates(generated):
    ocel, _, _, _ = generated
    validate.validate_json(ocel)  # raises on failure


def test_sqlite_structure_validates(generated):
    _, _, sqlite_path, _ = generated
    validate.validate_sqlite_structure(sqlite_path)  # raises on failure


def test_semantic_requirements(generated):
    ocel, _, _, _ = generated
    validate.validate_semantic(ocel, required_object_types=REQUIRED_OBJECT_TYPES)  # raises on failure


def test_round_trip_sqlite_preserves_identity_and_relationships(generated):
    ocel, _, sqlite_path, _ = generated
    back = sqlite_io.read_sqlite(sqlite_path)

    assert {o.id for o in back.objects} == {o.id for o in ocel.objects}
    assert {e.id for e in back.events} == {e.id for e in ocel.events}

    orig_by_id = {e.id: e for e in ocel.events}
    for e in back.events:
        orig = orig_by_id[e.id]
        assert e.type == orig.type
        assert {(r.target_id, r.qualifier) for r in e.relationships} == {
            (r.target_id, r.qualifier) for r in orig.relationships
        }

    orig_obj_by_id = {o.id: o for o in ocel.objects}
    for o in back.objects:
        orig = orig_obj_by_id[o.id]
        assert {(a.name, str(a.value), a.time) for a in o.attributes} == {
            (a.name, str(a.value), a.time) for a in orig.attributes
        }


def test_round_trip_json_preserves_identity(generated):
    ocel, _, _, json_path = generated
    back = json_io.read_json(json_path)
    assert {o.id for o in back.objects} == {o.id for o in ocel.objects}
    assert {e.id for e in back.events} == {e.id for e in ocel.events}


def test_ground_truth_ids_correspond_to_real_records(generated):
    ocel, ground_truth, _, _ = generated
    assert ground_truth, "generator planted no ground-truth pathology instances"
    object_ids = {o.id for o in ocel.objects}
    for entry in ground_truth:
        assert entry["case_id"] in object_ids
        for analyst_id in entry["analysts_involved"]:
            assert analyst_id in object_ids

    loops = [g for g in ground_truth if g["pathology"] == "REASSIGNMENT_LOOP"]
    positives = [g for g in loops if not g["is_hard_negative"]]
    hard_negatives = [g for g in loops if g["is_hard_negative"]]
    assert positives, "no positive REASSIGNMENT_LOOP instances planted"
    assert hard_negatives, "no matched hard-negative instances planted"
    assert len(positives) == MATURE_CSE_DEV.num_reassignment_loop_positive
    assert len(hard_negatives) == MATURE_CSE_DEV.num_reassignment_loop_hard_negative
