import json

from satsa.evidence.export import export_evidence_package, export_evidence_packages
from satsa.evidence.package import EvidencePackage, Provenance


def _pkg(finding_id):
    return EvidencePackage(
        finding_id=finding_id, finding_type="REASSIGNMENT_LOOP", capability="Operational Discipline",
        authority="EXPECTED", rule_id=None, rule_version=None, anomaly_score=1.0, finding_score=1.0,
        concern_score=0.35, confidence=1.0, evidence_quality="HIGH", estimated_review_cost_minutes=12.0,
        affected_objects=["CASE001"], assumptions=["analyst_sequence=('ANL1','ANL2')"],
        provenance=Provenance("satsa-generator", "", "CASE001", "", "", "1.0"),
    )


def test_single_export_round_trips_through_json():
    raw = export_evidence_package(_pkg("F1"))
    data = json.loads(raw)
    assert data["finding_id"] == "F1"
    assert data["finding_type"] == "REASSIGNMENT_LOOP"
    assert data["provenance"]["source_record_id"] == "CASE001"


def test_bulk_export_includes_cse_id_and_every_finding():
    raw = export_evidence_packages([_pkg("F1"), _pkg("F2")], cse_id="CSE_D")
    data = json.loads(raw)
    assert data["cse_id"] == "CSE_D"
    assert data["finding_count"] == 2
    assert {f["finding_id"] for f in data["findings"]} == {"F1", "F2"}
