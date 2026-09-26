"""Cross-CSE peer comparison and benchmarking (PS Functional Requirement 8,
illustrative use-case v) — the literal instruction is "peer comparison ... across
entities," and `moat1/negative_space.py::detect_negative_space` already IS a peer
comparison engine, just applied within one CSE's queues/analysts today. This module
calls it unmodified, one level up.
"""
from __future__ import annotations

from satsa.moat1.fusion import FusionResult
from satsa.moat1.negative_space import NegativeSpaceFinding, detect_negative_space
from satsa.ocel.model import OCEL
from satsa.portfolio.entity_metrics import CORE_FINDING_TYPES, build_peer_observations


def compare_entities(
    datasets: dict[str, tuple[OCEL, FusionResult]], finding_type: str
) -> dict[str, NegativeSpaceFinding]:
    observations = build_peer_observations(datasets, finding_type)
    findings = detect_negative_space(observations)
    return {f.group_id: f for f in findings}


def compare_all_entities(
    datasets: dict[str, tuple[OCEL, FusionResult]], finding_types: tuple[str, ...] = CORE_FINDING_TYPES
) -> dict[str, dict[str, NegativeSpaceFinding]]:
    """finding_type -> {cse_id -> NegativeSpaceFinding}."""
    return {ft: compare_entities(datasets, ft) for ft in finding_types}
