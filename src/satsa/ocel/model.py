"""In-memory OCEL 2.0 data model.

Field names and structure follow the OCEL 2.0 Specification (Berti et al.,
arXiv:2403.01975) Section 4 (Formal Definitions), Section 6 (relational format), and
Section 8 (JSON format) — see docs/references.md for full citation and
docs/assumptions.md entry 001 for why this is a from-scratch implementation rather
than a wrapper around pm4py/ocpa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class AttributeDef:
    name: str
    type: str  # "string" | "float" | "boolean" | "time"


@dataclass(frozen=True)
class TypeDef:
    name: str
    attributes: tuple[AttributeDef, ...] = ()


@dataclass(frozen=True)
class Relationship:
    """E2O (event->object) or O2O (object->object) edge, always qualified."""
    target_id: str
    qualifier: str


@dataclass(frozen=True)
class EventAttributeValue:
    name: str
    value: object


@dataclass(frozen=True)
class ObjectAttributeValue:
    """time=EPOCH marks the object's initial value per the OCEL 2.0 SQLite convention."""
    name: str
    value: object
    time: datetime


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    time: datetime
    attributes: tuple[EventAttributeValue, ...] = ()
    relationships: tuple[Relationship, ...] = ()  # E2O


@dataclass(frozen=True)
class Obj:
    id: str
    type: str
    attributes: tuple[ObjectAttributeValue, ...] = ()
    relationships: tuple[Relationship, ...] = ()  # O2O


@dataclass
class OCEL:
    event_types: list[TypeDef] = field(default_factory=list)
    object_types: list[TypeDef] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    objects: list[Obj] = field(default_factory=list)
