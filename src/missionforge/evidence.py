"""Evidence contract objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    EvidenceTrustLevel,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)


_TRUST_RANK: dict[EvidenceTrustLevel, int] = {
    EvidenceTrustLevel.UNTRUSTED_WORKER_CLAIM: 0,
    EvidenceTrustLevel.LLM_INTERPRETATION: 1,
    EvidenceTrustLevel.ARTIFACT_REF: 2,
    EvidenceTrustLevel.COMMAND_RESULT: 3,
    EvidenceTrustLevel.TEST_RESULT: 4,
    EvidenceTrustLevel.SCHEMA_VALIDATION: 5,
    EvidenceTrustLevel.REVIEWER_DECISION: 6,
    EvidenceTrustLevel.HUMAN_ACCEPTANCE: 7,
}


def trust_satisfies(actual: EvidenceTrustLevel | str, required: EvidenceTrustLevel | str) -> bool:
    """Return whether actual evidence is at least as trusted as required."""

    actual_level = require_enum(actual, EvidenceTrustLevel, "actual")
    required_level = require_enum(required, EvidenceTrustLevel, "required")
    return _TRUST_RANK[actual_level] >= _TRUST_RANK[required_level]


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to an artifact produced or consumed by a mission."""

    artifact_id: str
    ref: str
    sha256: str | None = None
    media_type: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRef":
        data = require_mapping(payload, "artifact_ref")
        sha256 = data.get("sha256")
        media_type = data.get("media_type")
        return cls(
            artifact_id=require_non_empty_str(data.get("artifact_id"), "artifact_ref.artifact_id"),
            ref=validate_ref(data.get("ref"), "artifact_ref.ref"),
            sha256=require_non_empty_str(sha256, "artifact_ref.sha256") if sha256 is not None else None,
            media_type=require_non_empty_str(media_type, "artifact_ref.media_type") if media_type is not None else None,
        )

    def validate(self) -> None:
        require_non_empty_str(self.artifact_id, "artifact_ref.artifact_id")
        validate_ref(self.ref, "artifact_ref.ref")
        if self.sha256 is not None:
            require_non_empty_str(self.sha256, "artifact_ref.sha256")
        if self.media_type is not None:
            require_non_empty_str(self.media_type, "artifact_ref.media_type")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRef:
    """Reference to evidence with explicit reliability."""

    evidence_id: str
    ref: str
    trust_level: EvidenceTrustLevel
    kind: str = "artifact"
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceRef":
        data = require_mapping(payload, "evidence_ref")
        return cls(
            evidence_id=require_non_empty_str(data.get("evidence_id"), "evidence_ref.evidence_id"),
            ref=validate_ref(data.get("ref"), "evidence_ref.ref"),
            trust_level=require_enum(data.get("trust_level"), EvidenceTrustLevel, "evidence_ref.trust_level"),
            kind=require_non_empty_str(data.get("kind", "artifact"), "evidence_ref.kind"),
            source_refs=[validate_ref(item, "evidence_ref.source_refs[]") for item in require_str_list(data.get("source_refs", []), "evidence_ref.source_refs")],
        )

    def validate(self) -> None:
        require_non_empty_str(self.evidence_id, "evidence_ref.evidence_id")
        validate_ref(self.ref, "evidence_ref.ref")
        require_enum(self.trust_level, EvidenceTrustLevel, "evidence_ref.trust_level")
        require_non_empty_str(self.kind, "evidence_ref.kind")
        for ref in self.source_refs:
            validate_ref(ref, "evidence_ref.source_refs[]")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "evidence_id": self.evidence_id,
            "ref": self.ref,
            "trust_level": self.trust_level.value,
            "kind": self.kind,
            "source_refs": list(self.source_refs),
        }


def require_trust_for_acceptance(evidence: EvidenceRef, required: EvidenceTrustLevel) -> None:
    """Fail if evidence does not satisfy a required acceptance trust level."""

    if not trust_satisfies(evidence.trust_level, required):
        raise ContractValidationError(
            f"evidence {evidence.evidence_id!r} has trust {evidence.trust_level.value!r}, "
            f"requires {required.value!r}"
        )
