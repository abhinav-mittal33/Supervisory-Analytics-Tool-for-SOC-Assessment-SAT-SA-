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
