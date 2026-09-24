"""Synthetic CSE data generator (build spec Section 14, Build Order Step 2).

Produces a five-object-type (Alert, Case, Analyst, Queue, Asset) OCEL 2.0 log for one
CSE profile, plus a ground-truth sidecar recording every planted pathology instance
(Section 14, "ground-truth IDs correspond to real synthetic records" — Gate 0).

Planted pathology (Section 9.2 / Section 15): a REASSIGNMENT_LOOP is a case where the
same two Analyst objects are cycled through repeatedly. The matched hard negative is
the *same* structural loop (same object-centric shape — a naive "count reassignments
per case" feature would misfire on both identically), but each REASSIGN event carries
`handover_reason=SHIFT_CHANGE` and lands on shift-boundary timing. A detector that
doesn't inspect that per-event attribute can't tell the two apart; this is exactly
what makes it a *hard* negative rather than a trivial one.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from satsa.ocel.model import (
    EPOCH,
    OCEL,
    AttributeDef,
    Event,
    EventAttributeValue,
    Obj,
    ObjectAttributeValue,
    Relationship,
    TypeDef,
)
from satsa.generator.profiles import CSEProfile

BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def generate(profile: CSEProfile) -> tuple[OCEL, list[dict]]:
    rng = random.Random(profile.seed)
    ocel = OCEL()
    ocel.object_types = [
        TypeDef("Asset", (AttributeDef("criticality", "string"), AttributeDef("asset_type", "string"))),
        TypeDef("Alert", (AttributeDef("severity", "string"), AttributeDef("category", "string"))),
        TypeDef("Case", (AttributeDef("status", "string"),)),
        TypeDef("Analyst", (AttributeDef("tier", "string"),)),
        TypeDef("Queue", (AttributeDef("name", "string"),)),
    ]
    ocel.event_types = [
        TypeDef("ALERT_RAISED", ()),
        TypeDef("OPEN_CASE", ()),
        TypeDef("ASSIGN", ()),
        TypeDef("ENRICH", ()),
        TypeDef("INVESTIGATE", ()),
        TypeDef("ESCALATE", ()),
        TypeDef("EVIDENCE_COLLECT", ()),
        TypeDef("REASSIGN", (AttributeDef("handover_reason", "string"),)),
        TypeDef("CLOSE", ()),
    ]

    assets: list[tuple[str, str]] = []
    for i in range(profile.num_assets):
        crit = _weighted_choice(rng, profile.asset_criticality_weights)
        atype = rng.choice(["Server", "Database", "Endpoint", "NetworkDevice"])
        aid = f"AST{i + 1:04d}"
        ocel.objects.append(
            Obj(
                aid,
                "Asset",
                (
                    ObjectAttributeValue("criticality", crit, EPOCH),
                    ObjectAttributeValue("asset_type", atype, EPOCH),
                ),
                (),
            )
        )
        assets.append((aid, crit))

    exposed = [a for a in assets if rng.random() < profile.telemetry_coverage] or assets

    analysts = [f"ANL{i + 1:03d}" for i in range(profile.num_analysts)]
    for aid in analysts:
        tier = rng.choice(["JUNIOR", "SENIOR"])
        ocel.objects.append(Obj(aid, "Analyst", (ObjectAttributeValue("tier", tier, EPOCH),), ()))

    queues = [f"QUE{i + 1:02d}" for i in range(profile.num_queues)]
    for qid in queues:
        ocel.objects.append(Obj(qid, "Queue", (ObjectAttributeValue("name", qid, EPOCH),), ()))

    # Reassignment activity buckets, drawn from disjoint index slices so a case never
    # falls into more than one category. Two "background noise" categories exist
    # specifically so Gate 1 (tests/test_gate1_reassignment.py) has real negatives to
    # tell the loop pattern apart from: a single routine handoff, and a reassignment
    # *chain* through distinct specialists that never repeats an analyst — the latter
    # is exactly the trap Section 9.1 warns about (same reassignment *count* as a real
    # loop, but no object-relationship cycle, so a naive "count reassignments per case"
    # feature would misfire on it while a genuinely object-centric detector must not).
    shuffled_pool = list(range(profile.num_cases))
    rng.shuffle(shuffled_pool)
    n_special = profile.num_reassignment_loop_positive + profile.num_reassignment_loop_hard_negative
    n_single = max(0, int(profile.num_cases * 0.10))
    n_chain = max(0, int(profile.num_cases * 0.05))

    special = shuffled_pool[:n_special]
    positive_indices = set(special[: profile.num_reassignment_loop_positive])
    hard_negative_indices = set(special[profile.num_reassignment_loop_positive : n_special])
    single_reassignment_indices = set(shuffled_pool[n_special : n_special + n_single])
    chain_no_loop_indices = set(
        shuffled_pool[n_special + n_single : n_special + n_single + n_chain]
    )

    ground_truth: list[dict] = []
    event_counter = 0

    def next_eid() -> str:
        nonlocal event_counter
        event_counter += 1
        return f"E{event_counter:06d}"

    for case_idx in range(profile.num_cases):
        case_id = f"CASE{case_idx + 1:05d}"
        alert_id = f"ALRT{case_idx + 1:05d}"
        asset_id, asset_crit = rng.choice(exposed)
        severity = _weighted_choice(rng, profile.alert_severity_weights)
        category = _weighted_choice(rng, profile.alert_category_weights)

        t = BASE_TIME + timedelta(hours=rng.uniform(0, 24 * 60))

        ocel.events.append(Event(next_eid(), "ALERT_RAISED", t, (), (Relationship(asset_id, "alert_on_asset"),)))
        ocel.objects.append(
            Obj(
                alert_id,
                "Alert",
                (
                    ObjectAttributeValue("severity", severity, EPOCH),
                    ObjectAttributeValue("category", category, EPOCH),
                ),
                (Relationship(asset_id, "raised_on_asset"),),
            )
        )

        t += timedelta(minutes=rng.uniform(1, 30))
        ocel.events.append(
            Event(next_eid(), "OPEN_CASE", t, (), (Relationship(alert_id, "opened_from_alert"),))
        )
        case_attrs = [ObjectAttributeValue("status", "OPEN", EPOCH)]
        case_rels = [Relationship(alert_id, "case_for_alert")]

        analyst = rng.choice(analysts)
        queue = rng.choice(queues)
        t += timedelta(minutes=rng.uniform(1, 15))
        ocel.events.append(
            Event(
                next_eid(),
                "ASSIGN",
                t,
                (),
                (Relationship(case_id, "assignment_for_case"), Relationship(analyst, "assigned_to"), Relationship(queue, "routed_via")),
            )
        )
        case_rels.append(Relationship(analyst, "current_assignee"))
        case_rels.append(Relationship(queue, "current_queue"))

        # Escalation branches off the ASSIGN timestamp, not the end of the
        # enrich/investigate sequence below — a CRITICAL alert on a HIGH/CRITICAL
        # asset should escalate immediately in parallel with (not strictly after)
        # deeper investigation, which is also the only way a 30-minute SLA
        # (OKF rule ESC-CRIT-001) is ever achievable given enrich+investigate alone
        # can take well over 30 minutes.
        mandatory_escalation = severity == "CRITICAL" and asset_crit in ("HIGH", "CRITICAL")
        if mandatory_escalation:
            roll = rng.random()
            if roll < profile.escalation_compliance_rate:
                escalate_time = t + timedelta(minutes=rng.uniform(5, 25))  # within the 30-min SLA
                ocel.events.append(Event(next_eid(), "ESCALATE", escalate_time, (), (Relationship(case_id, "escalation_for_case"),)))
            elif roll < profile.escalation_compliance_rate + (1 - profile.escalation_compliance_rate) / 2:
                escalate_time = t + timedelta(minutes=rng.uniform(35, 180))  # escalated, but past the SLA
                ocel.events.append(Event(next_eid(), "ESCALATE", escalate_time, (), (Relationship(case_id, "escalation_for_case"),)))
            # else: never escalated — the structural negative-space case (Section 9.2):
            # no ESCALATE event, no relationship, nothing to find in a flat case-level table.

        if case_idx in positive_indices or case_idx in hard_negative_indices:
            is_hard_negative = case_idx in hard_negative_indices
            analyst_a, analyst_b = rng.sample(analysts, 2)
            loop_len = 4
            cycle = [analyst_a, analyst_b, analyst_a, analyst_b][:loop_len]
            for target in cycle:
                if is_hard_negative:
                    t += timedelta(hours=8)
                    attrs = (EventAttributeValue("handover_reason", "SHIFT_CHANGE"),)
                else:
                    t += timedelta(minutes=rng.uniform(5, 45))
                    attrs = ()
                ocel.events.append(
                    Event(
                        next_eid(),
                        "REASSIGN",
                        t,
                        attrs,
                        (Relationship(case_id, "reassignment_for_case"), Relationship(target, "reassigned_to")),
                    )
                )
                analyst = target
            ground_truth.append(
                {
                    "case_id": case_id,
                    "pathology": "REASSIGNMENT_LOOP",
                    "is_hard_negative": is_hard_negative,
                    "analysts_involved": [analyst_a, analyst_b],
                    "reassignment_count": loop_len,
                }
            )
        elif case_idx in single_reassignment_indices:
            target = rng.choice([a for a in analysts if a != analyst])
            t += timedelta(minutes=rng.uniform(5, 45))
            ocel.events.append(
                Event(
                    next_eid(),
                    "REASSIGN",
                    t,
                    (),
                    (Relationship(case_id, "reassignment_for_case"), Relationship(target, "reassigned_to")),
                )
            )
            analyst = target
            ground_truth.append(
                {
                    "case_id": case_id,
                    "pathology": "SINGLE_REASSIGNMENT",
                    "is_hard_negative": False,
                    "analysts_involved": [target],
                    "reassignment_count": 1,
                }
            )
        elif case_idx in chain_no_loop_indices:
            chain_targets = rng.sample([a for a in analysts if a != analyst], 3)
            for target in chain_targets:
                t += timedelta(minutes=rng.uniform(5, 45))
                ocel.events.append(
                    Event(
                        next_eid(),
                        "REASSIGN",
                        t,
                        (),
                        (Relationship(case_id, "reassignment_for_case"), Relationship(target, "reassigned_to")),
                    )
                )
                analyst = target
            ground_truth.append(
                {
                    "case_id": case_id,
                    "pathology": "REASSIGNMENT_CHAIN_NO_LOOP",
                    "is_hard_negative": False,
                    "analysts_involved": chain_targets,
                    "reassignment_count": len(chain_targets),
                }
            )

        if rng.random() < profile.enrichment_rate:
            t += timedelta(minutes=rng.uniform(10, 60))
            ocel.events.append(Event(next_eid(), "ENRICH", t, (), (Relationship(case_id, "enrich_for_case"),)))

        t += timedelta(minutes=rng.uniform(15, 120))
        ocel.events.append(
            Event(next_eid(), "INVESTIGATE", t, (), (Relationship(case_id, "investigate_for_case"), Relationship(analyst, "investigated_by")))
        )

        if rng.random() < 0.7:
            t += timedelta(minutes=rng.uniform(10, 90))
            ocel.events.append(Event(next_eid(), "EVIDENCE_COLLECT", t, (), (Relationship(case_id, "evidence_for_case"),)))

        t += timedelta(minutes=rng.uniform(15, 60))
        ocel.events.append(Event(next_eid(), "CLOSE", t, (), (Relationship(case_id, "close_for_case"),)))
        case_attrs.append(ObjectAttributeValue("status", "CLOSED", t))

        ocel.objects.append(Obj(case_id, "Case", tuple(case_attrs), tuple(case_rels)))

    return ocel, ground_truth
