"""OKF rule schema (build spec Section 6.3 / 6.4).

Scope note (Section 6.3): the full schema including `version` and
`effective_from`/`effective_to` is implemented so the architecture story is complete,
but every rule in this build uses `version="1.0"` with a single effective period —
no multi-version conflict-resolution logic. That's real production machinery with no
payoff for a ~10-20 rule demo (per the spec's own instruction).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

AUTHORITY_CLASSES = {"MANDATORY", "EXPECTED", "PEER_NORMAL", "OPTIONAL", "UNKNOWN"}
CONSTRAINT_TEMPLATES = {"RESPONSE", "PRECEDENCE", "CARDINALITY", "NOT_CO_EXISTENCE"}

_UNIT_TO_MINUTES = {"minutes": 1, "hours": 60, "days": 60 * 24}


@dataclass(frozen=True)
class TimeConstraint:
    operator: str  # "<=", "<", ">=", ">", "=="
    value: float
    unit: str  # "minutes" | "hours" | "days"

    def to_timedelta(self) -> timedelta:
        return timedelta(minutes=self.value * _UNIT_TO_MINUTES[self.unit])


@dataclass(frozen=True)
class OKFRule:
    rule_id: str
    capability: str
    authority: str
    constraint_template: str
    source_type: str
    source_reference: str
    applies_when: dict = field(default_factory=dict)
    expected_behavior: dict = field(default_factory=dict)
    required_evidence: tuple[str, ...] = ()
    time_constraint: TimeConstraint | None = None
    version: str = "1.0"
    effective_from: str = "2026-01-01"
    effective_to: str | None = None

    def __post_init__(self) -> None:
        if self.authority not in AUTHORITY_CLASSES:
            raise ValueError(f"{self.rule_id}: unknown authority class {self.authority!r}")
        if self.constraint_template not in CONSTRAINT_TEMPLATES:
            raise ValueError(f"{self.rule_id}: unknown constraint template {self.constraint_template!r}")


@dataclass(frozen=True)
class Violation:
    rule_id: str
    case_id: str
    capability: str
    authority: str
    detail: str
