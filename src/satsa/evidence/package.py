"""Evidence Package schema (build spec Section 11).

Confidence and evidence-quality are kept as two separate fields deliberately, per the
spec's own instruction — never blended into one number. A finding can be HIGH
evidence-quality and LOW confidence at the same time.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Provenance:
    source_system: str
    source_file: str
    source_record_id: str
    ingestion_batch_id: str
    ingestion_timestamp: str
    schema_version: str


@dataclass
class EvidencePackage:
    finding_id: str
    finding_type: str
    capability: str
    authority: str
    rule_id: str | None
    rule_version: str | None
    anomaly_score: float
    finding_score: float
    concern_score: float
    confidence: float
    evidence_quality: str  # HIGH | MEDIUM | LOW
    estimated_review_cost_minutes: float
    affected_objects: list[str] = field(default_factory=list)
    supporting_cases: list[str] = field(default_factory=list)
    supporting_events: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    provenance: Provenance | None = None

    verdict: str | None = None
    verdict_capability_link: str | None = None
    verdict_sub_type: str | None = None
    verdict_authority_violated: str | None = None
    duplicate_of_finding_id: str | None = None
    source_records: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.evidence_quality not in {"HIGH", "MEDIUM", "LOW"}:
            raise ValueError(f"{self.finding_id}: invalid evidence_quality {self.evidence_quality!r}")
