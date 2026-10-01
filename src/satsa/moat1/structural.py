"""Object-centric structural detectors — Moat 1 (build spec Section 9).

Every detector here must pass the Section 9.1 test before it counts as Moat 1: would
detection degrade or become impossible if the object relationships were removed and
this became a flat table of case-level features?

reassignment loop: yes. The signal is *which specific Analyst object* each REASSIGN
event points to, and whether that target repeats an analyst already seen earlier in
the same case's trace — a flat "count of REASSIGN events per case" feature cannot tell
a real ping-pong loop apart from a reassignment chain through three distinct
specialists with the same event count (see REASSIGNMENT_CHAIN_NO_LOOP in the
generator, planted specifically to catch a detector that only counts).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from satsa.ocel.model import Event, OCEL

HANDOVER_JUSTIFICATION_ATTR = "handover_reason"
HANDOVER_JUSTIFICATION_VALUE = "SHIFT_CHANGE"


@dataclass(frozen=True)
class ReassignmentSignal:
    case_id: str
    analyst_sequence: tuple[str, ...]
    is_loop: bool  # raw structural pattern: a repeated analyst within a small analyst set
    justified: bool  # every REASSIGN event in the trace carries the SOP-documented handover reason
    flagged: bool  # is_loop and not justified — the actual Concern-worthy output


def _relationship_target(event: Event, qualifier: str) -> str | None:
    for r in event.relationships:
        if r.qualifier == qualifier:
            return r.target_id
    return None


def _is_justified(event: Event) -> bool:
    return any(
        a.name == HANDOVER_JUSTIFICATION_ATTR and a.value == HANDOVER_JUSTIFICATION_VALUE
        for a in event.attributes
    )


def detect_reassignment_loops(
    ocel: OCEL, min_reassignments: int = 3, max_distinct_analysts: int = 2
) -> list[ReassignmentSignal]:
    case_ids = {o.id for o in ocel.objects if o.type == "Case"}
    events_by_case: dict[str, list[Event]] = {cid: [] for cid in case_ids}

    for e in ocel.events:
        if e.type != "REASSIGN":
            continue
        case_id = _relationship_target(e, "reassignment_for_case")
        if case_id in events_by_case:
            events_by_case[case_id].append(e)

    signals = []
    for case_id, events in events_by_case.items():
        if len(events) < min_reassignments:
            continue
        events_sorted = sorted(events, key=lambda e: e.time)
        sequence = tuple(_relationship_target(e, "reassigned_to") for e in events_sorted)
        distinct = set(sequence)
        has_repeat = len(sequence) != len(distinct)
        is_loop = has_repeat and len(distinct) <= max_distinct_analysts
        justified = all(_is_justified(e) for e in events_sorted)
        signals.append(
            ReassignmentSignal(
                case_id=case_id,
                analyst_sequence=sequence,
                is_loop=is_loop,
                justified=justified,
                flagged=is_loop and not justified,
            )
        )
    return signals


# ---------------------------------------------------------------------------
# Fast-close outlier (use-case i: "high-severity alerts closed unusually quickly").
# Object-centric per Section 9.1: the signal is which SPECIFIC events touch this
# case (earliest event vs. the CLOSE event), not a flat "case age" column that could
# exist without ever tracing the object relationships that produced it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FastCloseSignal:
    case_id: str
    duration_minutes: float
    is_fast: bool


def case_open_close_times(ocel: OCEL) -> dict[str, tuple]:
    events_for_case: dict[str, list[Event]] = {}
    for e in ocel.events:
        for r in e.relationships:
            if r.qualifier.endswith("_for_case"):
                events_for_case.setdefault(r.target_id, []).append(e)

    result = {}
    for case_id, events in events_for_case.items():
        close_events = [e for e in events if e.type == "CLOSE"]
        if not close_events:
            continue
        result[case_id] = (min(e.time for e in events), max(e.time for e in close_events))
    return result


def detect_fast_close(ocel: OCEL, fast_threshold_minutes: float = 30.0) -> list[FastCloseSignal]:
    signals = []
    for case_id, (open_t, close_t) in case_open_close_times(ocel).items():
        duration = (close_t - open_t).total_seconds() / 60.0
        signals.append(FastCloseSignal(case_id, duration, duration < fast_threshold_minutes))
    return signals


# ---------------------------------------------------------------------------
# Repeated alert, same asset, no remediation depth (use-case ii). Object-centric:
# the signal is the Asset<-raised_on_asset-Alert<-case_for_alert-Case chain plus
# which specific event types touched each linked case — not a flat per-asset alert
# count, which can't tell "3 alerts, each properly investigated" apart from "3
# alerts, none investigated."
#
# "Remediation" has no explicit field in the canonical model — this is a
# documented PROXY (any linked case reaching INVESTIGATE or EVIDENCE_COLLECT),
# not an assertion that root cause was actually fixed. Logged as an assumption on
# every finding this produces, not asserted as ground truth.
# ---------------------------------------------------------------------------

_REMEDIATION_DEPTH_EVENT_TYPES = {"INVESTIGATE", "EVIDENCE_COLLECT"}


@dataclass(frozen=True)
class AssetRecurrenceSignal:
    asset_id: str
    alert_count: int
    linked_case_ids: tuple[str, ...]
    remediated: bool
    flagged: bool


def detect_asset_alert_recurrence(ocel: OCEL, min_alerts: int = 3) -> list[AssetRecurrenceSignal]:
    alert_asset: dict[str, str] = {}
    for o in ocel.objects:
        if o.type == "Alert":
            for r in o.relationships:
                if r.qualifier == "raised_on_asset":
                    alert_asset[o.id] = r.target_id

    alert_cases: dict[str, list[str]] = {}
    for o in ocel.objects:
        if o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "case_for_alert":
                    alert_cases.setdefault(r.target_id, []).append(o.id)

    case_has_depth: dict[str, bool] = {}
    for e in ocel.events:
        if e.type in _REMEDIATION_DEPTH_EVENT_TYPES:
            for r in e.relationships:
                if r.qualifier.endswith("_for_case"):
                    case_has_depth[r.target_id] = True

    asset_alerts: dict[str, list[str]] = {}
    for alert_id, asset_id in alert_asset.items():
        asset_alerts.setdefault(asset_id, []).append(alert_id)

    signals = []
    for asset_id, alerts in asset_alerts.items():
        linked_cases = tuple(c for a in alerts for c in alert_cases.get(a, []))
        remediated = any(case_has_depth.get(c, False) for c in linked_cases)
        flagged = len(alerts) >= min_alerts and not remediated
        signals.append(AssetRecurrenceSignal(asset_id, len(alerts), linked_cases, remediated, flagged))
    return signals


# ---------------------------------------------------------------------------
# Asset alert-count per criticality tier (use-cases iv, vi: low/no telemetry on a
# critical asset) — raw extraction only; the statistical "is this unexpectedly low
# vs. same-tier peers" judgment is negative_space.py's job (fusion.py wires the two
# together), keeping this file's role limited to object-centric extraction.
# ---------------------------------------------------------------------------


def asset_alert_counts(ocel: OCEL) -> list[tuple]:
    """Returns (asset_id, criticality, alert_count) for every Asset object."""
    counts: dict[str, int] = {o.id: 0 for o in ocel.objects if o.type == "Asset"}
    for o in ocel.objects:
        if o.type == "Alert":
            for r in o.relationships:
                if r.qualifier == "raised_on_asset" and r.target_id in counts:
                    counts[r.target_id] += 1

    criticality_by_asset = {
        o.id: next((a.value for a in o.attributes if a.name == "criticality"), "UNKNOWN")
        for o in ocel.objects if o.type == "Asset"
    }
    return [(aid, criticality_by_asset[aid], count) for aid, count in counts.items()]


# ---------------------------------------------------------------------------
# Repetitive/template-driven investigation (use-case vii — the spec's own deferred
# Section 9.3 "secondary detector"). Implemented as a deterministic statistical
# check (coefficient of variation of investigation-to-close duration per analyst),
# not an ML anomaly model — keeps this build's "no black box in the analytical
# core" posture intact while still surfacing the named signal.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvestigationUniformitySignal:
    analyst_id: str
    num_investigations: int
    coefficient_of_variation: float | None
    flagged: bool


def detect_investigation_uniformity(
    ocel: OCEL, min_cases: int = 5, cov_threshold: float = 0.15
) -> list[InvestigationUniformitySignal]:
    close_times: dict[str, object] = {}
    for e in ocel.events:
        if e.type == "CLOSE":
            for r in e.relationships:
                if r.qualifier == "close_for_case":
                    close_times[r.target_id] = e.time

    durations_by_analyst: dict[str, list[float]] = {}
    for e in ocel.events:
        if e.type != "INVESTIGATE":
            continue
        case_id = _relationship_target(e, "investigate_for_case")
        analyst_id = _relationship_target(e, "investigated_by")
        if case_id in close_times and analyst_id:
            duration = (close_times[case_id] - e.time).total_seconds() / 60.0
            if duration >= 0:
                durations_by_analyst.setdefault(analyst_id, []).append(duration)

    signals = []
    for analyst_id, durations in durations_by_analyst.items():
        n = len(durations)
        if n < min_cases:
            signals.append(InvestigationUniformitySignal(analyst_id, n, None, False))
            continue
        mean = statistics.mean(durations)
        cov = (statistics.stdev(durations) / mean) if mean > 0 else None
        signals.append(InvestigationUniformitySignal(analyst_id, n, cov, cov is not None and cov < cov_threshold))
    return signals


# ---------------------------------------------------------------------------
# Investigation/escalation workload vs. caseload (use-case ix: workloads
# inconsistent with expected activity levels) — raw extraction only, same split as
# asset_alert_counts() above; the statistical "is this unexpectedly high/low vs.
# peers given the same caseload" judgment is negative_space.py's job (fusion.py
# wires the two together, two-sided unlike the asset-telemetry call site).
#
# Escalation is attributed to the QUEUE a case currently sits in, not an analyst —
# ESCALATE events carry no analyst or queue relationship at all in the canonical
# OCEL model (confirmed by reading generate.py), so analyst-level escalation
# workload isn't attempted; queue-level is the grain this model actually supports.
# ---------------------------------------------------------------------------


def analyst_investigation_counts(ocel: OCEL) -> list[tuple]:
    """Returns (analyst_id, assigned_case_count, investigation_count) for every
    Analyst object. assigned_case_count is each Case's `current_assignee` — the same
    duty-eligible-population proxy moat2/real_data.py already relies on elsewhere in
    this codebase (reflects the latest assignment only, not full case history)."""
    assigned: dict[str, int] = {o.id: 0 for o in ocel.objects if o.type == "Analyst"}
    for o in ocel.objects:
        if o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "current_assignee" and r.target_id in assigned:
                    assigned[r.target_id] += 1

    investigated: dict[str, int] = {aid: 0 for aid in assigned}
    for e in ocel.events:
        if e.type == "INVESTIGATE":
            analyst_id = _relationship_target(e, "investigated_by")
            if analyst_id in investigated:
                investigated[analyst_id] += 1

    return [(aid, assigned[aid], investigated[aid]) for aid in assigned]


def queue_escalation_counts(ocel: OCEL) -> list[tuple]:
    """Returns (queue_id, routed_case_count, escalation_count) for every Queue
    object. routed_case_count is each Case's `current_queue`; escalation_count
    resolves each ESCALATE event back to its case's current_queue, since the
    ESCALATE event itself names neither an analyst nor a queue directly."""
    queue_of_case: dict[str, str] = {}
    routed: dict[str, int] = {o.id: 0 for o in ocel.objects if o.type == "Queue"}
    for o in ocel.objects:
        if o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "current_queue":
                    queue_of_case[o.id] = r.target_id
                    if r.target_id in routed:
                        routed[r.target_id] += 1

    escalated: dict[str, int] = {qid: 0 for qid in routed}
    for e in ocel.events:
        if e.type == "ESCALATE":
            case_id = _relationship_target(e, "escalation_for_case")
            queue_id = queue_of_case.get(case_id)
            if queue_id in escalated:
                escalated[queue_id] += 1

    return [(qid, routed[qid], escalated[qid]) for qid in routed]
