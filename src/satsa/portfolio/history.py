"""Per-CSE submission history — the "monthly data, company-wise, tracked over time"
requirement: every ingestion run (real upload or sample) is recorded as a dated
batch, so a later cycle can be compared against the CSE's own last submission
(PS req 16 — trend across time periods — via `temporal/cycles.py::classify_trend`)
and so an examiner can browse back through everything a CSE has ever submitted, not
just the latest snapshot.

Storage is plain files on disk under `data/portfolio_history/<cse_id>/<batch_id>/` —
a `manifest.json` (small, always present) plus an `ocel.sqlite` (the full dataset for
that batch, present for every REAL submission; absent for the one synthetic demo-seed
batch, which has no real underlying data to browse — see `seed_demo_history`). Fully
local, no database service, consistent with the offline/air-gapped constraint
(Section 18) — this is just files.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from satsa.moat1.fusion import FusionResult, fuse
from satsa.moat1.negative_space import PeerGroupObservation
from satsa.ocel import sqlite_io
from satsa.ocel.model import OCEL
from satsa.okf import compiler
from satsa.portfolio.entity_metrics import CORE_FINDING_TYPES, case_count

HISTORY_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "portfolio_history"


@dataclass(frozen=True)
class SubmissionRecord:
    cse_id: str
    submitted_at: str  # ISO 8601
    case_count: int
    concern_count: int
    per_finding_type: dict[str, dict[str, int]] = field(default_factory=dict)  # finding_type -> {case_count, flagged_count}
    note: str = ""  # e.g. "demo seed — not a real historical submission"
    has_data: bool = True  # False only for the synthetic demo-seed batch (no ocel.sqlite to browse)
    source_system: str = "satsa-generator"  # adapter class name for a real import (e.g. "CSVAdapter")


def _batch_id(submitted_at: datetime) -> str:
    return submitted_at.strftime("%Y%m%dT%H%M%SZ")


def _batch_dir(cse_id: str, submitted_at: datetime) -> Path:
    d = HISTORY_DIR / cse_id / _batch_id(submitted_at)
    d.mkdir(parents=True, exist_ok=True)
    return d


def record_submission(
    cse_id: str, ocel: OCEL, result: FusionResult, submitted_at: datetime | None = None, note: str = "",
    _store_ocel: bool = True, source_system: str = "satsa-generator",
) -> SubmissionRecord:
    submitted_at = submitted_at or datetime.now(timezone.utc)
    total_cases = case_count(ocel)
    per_type = {}
    for ft in CORE_FINDING_TYPES:
        flagged = len({c.affected_objects[0] for c in result.concerns if c.finding_type == ft and c.affected_objects})
        per_type[ft] = {"case_count": total_cases, "flagged_count": flagged}

    record = SubmissionRecord(
        cse_id=cse_id, submitted_at=submitted_at.isoformat(), case_count=total_cases,
        concern_count=len(result.concerns), per_finding_type=per_type, note=note, has_data=_store_ocel,
        source_system=source_system,
    )
    batch_dir = _batch_dir(cse_id, submitted_at)
    (batch_dir / "manifest.json").write_text(json.dumps(asdict(record), indent=2))
    if _store_ocel:
        sqlite_io.write_sqlite(ocel, str(batch_dir / "ocel.sqlite"))
    return record


def list_entity_ids() -> list[str]:
    """Every entity that has ever recorded a batch to history — including ones
    imported via a background job that never touched `st.session_state` directly
    (Phase F), so the UI can discover them purely from disk."""
    if not HISTORY_DIR.exists():
        return []
    return sorted(d.name for d in HISTORY_DIR.iterdir() if d.is_dir())


def list_submissions(cse_id: str) -> list[SubmissionRecord]:
    d = HISTORY_DIR / cse_id
    if not d.exists():
        return []
    records = []
    for batch_dir in sorted(d.iterdir()):
        manifest = batch_dir / "manifest.json"
        if manifest.exists():
            records.append(SubmissionRecord(**json.loads(manifest.read_text())))
    return sorted(records, key=lambda r: r.submitted_at)


def latest_two(cse_id: str) -> tuple[SubmissionRecord | None, SubmissionRecord | None]:
    records = list_submissions(cse_id)
    if len(records) < 2:
        return None, (records[-1] if records else None)
    return records[-2], records[-1]


def record_verdict(cse_id: str, submitted_at: str, finding_id: str, verdict_fields: dict) -> None:
    """Persists one examiner verdict to `<batch_dir>/verdicts.json`, keyed by
    finding_id. Needed because `load_batch()` always re-fuses fresh from the stored
    OCEL (by design — never a stale serialized FusionResult, see its own docstring),
    which otherwise silently discards any verdict recorded on a previous load: the
    in-memory `apply_verdict()` mutation never survived a reload at all
    (docs/assumptions.md entry 025) — recording a verdict, then reloading the page,
    lost it. `finding_id` is stable across reloads of the SAME batch because `fuse()`
    assigns ids deterministically from the same stored OCEL every time."""
    dt = datetime.fromisoformat(submitted_at)
    batch_dir = HISTORY_DIR / cse_id / _batch_id(dt)
    verdicts_path = batch_dir / "verdicts.json"
    verdicts = json.loads(verdicts_path.read_text()) if verdicts_path.exists() else {}
    verdicts[finding_id] = verdict_fields
    verdicts_path.write_text(json.dumps(verdicts, indent=2))


def load_verdicts(cse_id: str, submitted_at: str) -> dict[str, dict]:
    """Returns {finding_id: verdict_fields} previously recorded for this batch, or
    {} if none. Deliberately separate from manifest.json — verdicts are examiner
    input layered on top of immutable evidence (same split `apply_verdict()`'s own
    docstring describes), not generated/regenerated data."""
    dt = datetime.fromisoformat(submitted_at)
    verdicts_path = HISTORY_DIR / cse_id / _batch_id(dt) / "verdicts.json"
    return json.loads(verdicts_path.read_text()) if verdicts_path.exists() else {}


def load_batch(cse_id: str, submitted_at: str) -> tuple[OCEL, FusionResult] | None:
    """Re-fuses the batch live from its stored OCEL — never a stale serialized
    FusionResult — so it always reflects the current detector logic, not whatever
    logic existed when the batch was first recorded. Returns None if this batch
    has no stored dataset (the demo-seed cycle).

    Any previously-recorded verdicts are re-applied after the re-fuse (entry 025) —
    otherwise every reload would silently come back with every finding unverdicted,
    even ones an examiner already reviewed."""
    dt = datetime.fromisoformat(submitted_at)
    batch_dir = HISTORY_DIR / cse_id / _batch_id(dt)
    ocel_path = batch_dir / "ocel.sqlite"
    if not ocel_path.exists():
        return None
    manifest = batch_dir / "manifest.json"
    # .get(), not [] -- manifests written before this field existed don't have it.
    source_system = json.loads(manifest.read_text()).get("source_system", "satsa-generator") if manifest.exists() else "satsa-generator"
    ocel = sqlite_io.read_sqlite(str(ocel_path))
    conn = compiler.connect(str(ocel_path))
    result = fuse(ocel, conn, cse_id=cse_id, source_system=source_system)
    stored_verdicts = load_verdicts(cse_id, submitted_at)
    if stored_verdicts:
        for pkg in result.concerns:
            v = stored_verdicts.get(pkg.finding_id)
            if v:
                for field_name, value in v.items():
                    setattr(pkg, field_name, value)
    return ocel, result


def trend_observations(prior: SubmissionRecord, current: SubmissionRecord, finding_type: str) -> tuple[PeerGroupObservation, PeerGroupObservation]:
    """Same 'observed = cases WITHOUT the problem' convention as
    portfolio/entity_metrics.py, applied across cycles instead of across entities."""
    p = prior.per_finding_type.get(finding_type, {"case_count": 0, "flagged_count": 0})
    c = current.per_finding_type.get(finding_type, {"case_count": 0, "flagged_count": 0})
    prior_obs = PeerGroupObservation(group_id="prior", exposure=p["case_count"], observed=p["case_count"] - p["flagged_count"])
    current_obs = PeerGroupObservation(group_id="current", exposure=c["case_count"], observed=c["case_count"] - c["flagged_count"])
    return prior_obs, current_obs


def seed_demo_history(cse_id: str, ocel: OCEL, result: FusionResult, source_system: str = "satsa-generator") -> None:
    """Writes one synthetic 'one cycle ago' submission for a sample CSE, purely so
    the trend view and batch browser have something to show without requiring a
    real second upload. No real dataset backs this seeded batch (`has_data=False`)
    — it is never presented as a real historical record. Idempotent: does nothing
    if this CSE already has any history."""
    if list_submissions(cse_id):
        return
    prior_time = datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
    current = record_submission(cse_id, ocel, result, note="", source_system=source_system)
    worse_per_type = {
        ft: {"case_count": vals["case_count"], "flagged_count": min(vals["case_count"], vals["flagged_count"] + max(2, vals["case_count"] // 3))}
        for ft, vals in current.per_finding_type.items()
    }
    seeded = SubmissionRecord(
        cse_id=cse_id, submitted_at=prior_time.isoformat(), case_count=current.case_count,
        concern_count=current.concern_count, per_finding_type=worse_per_type,
        note="DEMO SEED — a synthetic prior cycle for illustration, not a real historical submission.",
        has_data=False, source_system=source_system,
    )
    batch_dir = _batch_dir(cse_id, prior_time)
    (batch_dir / "manifest.json").write_text(json.dumps(asdict(seeded), indent=2))
