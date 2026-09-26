"""Phase A: cse_id + low_confidence_cases threading through fuse() — additive,
default-None, must not change any existing (non-ingestion) call site's behavior."""
from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler


def _pipeline(tmp_path):
    ocel, _ = generate(MATURE_CSE_DEV)
    sqlite_path = str(tmp_path / "dev.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    return ocel, conn


def test_default_call_leaves_evidence_quality_and_cse_id_unaffected(tmp_path):
    ocel, conn = _pipeline(tmp_path)
    result = fuse(ocel, conn)
    assert result.concerns
    assert all(c.evidence_quality == "HIGH" for c in result.concerns)
    assert all(c.cse_id is None for c in result.concerns)


def test_cse_id_is_stamped_onto_every_concern(tmp_path):
    ocel, conn = _pipeline(tmp_path)
    result = fuse(ocel, conn, cse_id="CSE_TEST")
    assert result.concerns
    assert all(c.cse_id == "CSE_TEST" for c in result.concerns)


def test_low_confidence_case_gets_medium_evidence_quality_others_stay_high(tmp_path):
    ocel, conn = _pipeline(tmp_path)
    result = fuse(ocel, conn)
    all_case_ids = {c.affected_objects[0] for c in result.concerns}
    assert len(all_case_ids) >= 2, "need at least 2 concerned cases for a meaningful downgrade-vs-unaffected check"
    flagged_case = next(iter(all_case_ids))

    downgraded = fuse(ocel, conn, low_confidence_cases={flagged_case})
    by_case = {c.affected_objects[0]: c for c in downgraded.concerns}
    assert by_case[flagged_case].evidence_quality == "MEDIUM"
    assert any("downgraded" in a for a in by_case[flagged_case].assumptions)
    other_case = next(cid for cid in all_case_ids if cid != flagged_case)
    assert by_case[other_case].evidence_quality == "HIGH"
