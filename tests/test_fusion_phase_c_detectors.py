"""Confirms the four Phase C detectors are actually wired into fuse() end to end —
not just unit-tested in isolation (see tests/test_detector_*.py for the isolated,
planted-positive/hard-negative checks)."""
from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler

NEW_FINDING_TYPES = {
    "FAST_CLOSE_OUTLIER",
    "REPEATED_ALERT_NO_REMEDIATION",
    "LOW_TELEMETRY_CRITICAL_ASSET",
    "REPETITIVE_INVESTIGATION_PATTERN",
}


def test_at_least_one_phase_c_finding_type_fires_on_scaled_data(tmp_path):
    ocel, _ = generate(MATURE_CSE_SCALED)
    sqlite_path = str(tmp_path / "scaled.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    concerns = fuse(ocel, conn).concerns

    present = {c.finding_type for c in concerns} & NEW_FINDING_TYPES
    assert present, "none of the 4 Phase C detectors produced a concern on real generated data"


def test_low_telemetry_and_investigation_uniformity_have_no_case_level_supporting_cases_lie():
    """Asset/analyst-level findings must not silently claim a fabricated case_id."""
    ocel, _ = generate(MATURE_CSE_SCALED)
    import tempfile
    sqlite_path = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False).name
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    concerns = fuse(ocel, conn).concerns
    for c in concerns:
        if c.finding_type == "REPETITIVE_INVESTIGATION_PATTERN":
            assert c.supporting_cases == []
            assert c.affected_objects[0].startswith("ANL")
