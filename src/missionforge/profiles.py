"""Profile declarations and deterministic expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
)
from .ir import CapabilityProfileRef, MissionConstraint
from .verification import ValidatorSpec


@dataclass(frozen=True)
class CapabilityProfile:
    """Reusable capability compiler data."""

    profile_id: str
    version: str
    constraints: list[dict[str, Any]] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityProfile":
        data = require_mapping(payload, "capability_profile")
        profile = cls(
            profile_id=require_non_empty_str(data.get("profile_id"), "capability_profile.profile_id"),
            version=require_non_empty_str(data.get("version", "1.0"), "capability_profile.version"),
            constraints=[require_mapping(item, "capability_profile.constraints[]") for item in data.get("constraints", [])],
            evidence_requirements=require_str_list(
                data.get("evidence_requirements", []),
                "capability_profile.evidence_requirements",
            ),
            required_artifacts=require_str_list(data.get("required_artifacts", []), "capability_profile.required_artifacts"),
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        require_non_empty_str(self.profile_id, "capability_profile.profile_id")
        require_non_empty_str(self.version, "capability_profile.version")
        for item in self.constraints:
            require_mapping(item, "capability_profile.constraints[]")
        require_str_list(self.evidence_requirements, "capability_profile.evidence_requirements")
        require_str_list(self.required_artifacts, "capability_profile.required_artifacts")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "constraints": [dict(item) for item in self.constraints],
            "evidence_requirements": list(self.evidence_requirements),
            "required_artifacts": list(self.required_artifacts),
        }

    @property
    def profile_hash(self) -> str:
        return stable_json_hash(self.to_dict())


@dataclass(frozen=True)
class VerificationProfile:
    """Reusable validator-language declaration."""

    profile_id: str
    version: str
    validator_types: list[str] = field(default_factory=list)
    review_questions: list[str] = field(default_factory=list)
    known_gaps: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerificationProfile":
        data = require_mapping(payload, "verification_profile")
        profile = cls(
            profile_id=require_non_empty_str(data.get("profile_id"), "verification_profile.profile_id"),
            version=require_non_empty_str(data.get("version", "1.0"), "verification_profile.version"),
            validator_types=require_str_list(data.get("validator_types", []), "verification_profile.validator_types"),
            review_questions=require_str_list(data.get("review_questions", []), "verification_profile.review_questions"),
            known_gaps=require_str_list(data.get("known_gaps", []), "verification_profile.known_gaps"),
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        require_non_empty_str(self.profile_id, "verification_profile.profile_id")
        require_non_empty_str(self.version, "verification_profile.version")
        require_str_list(self.validator_types, "verification_profile.validator_types")
        require_str_list(self.review_questions, "verification_profile.review_questions")
        require_str_list(self.known_gaps, "verification_profile.known_gaps")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "validator_types": list(self.validator_types),
            "review_questions": list(self.review_questions),
            "known_gaps": list(self.known_gaps),
        }

    @property
    def profile_hash(self) -> str:
        return stable_json_hash(self.to_dict())


@dataclass(frozen=True)
class ProfileExpansion:
    """Profile-generated fragments with provenance."""

    source_profile_id: str
    source_profile_version: str
    source_profile_hash: str
    source_ref_hash: str
    source_ref_requirements: dict[str, Any] = field(default_factory=dict)
    constraints: list[MissionConstraint] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    validator_types: list[str] = field(default_factory=list)
    review_questions: list[str] = field(default_factory=list)
    known_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_profile_id": self.source_profile_id,
            "source_profile_version": self.source_profile_version,
            "source_profile_hash": self.source_profile_hash,
            "source_ref_hash": self.source_ref_hash,
            "source_ref_requirements": ensure_json_value(
                require_mapping(self.source_ref_requirements, "profile_expansion.source_ref_requirements"),
                "profile_expansion.source_ref_requirements",
            ),
            "constraints": [constraint.to_dict() if hasattr(constraint, "to_dict") else _constraint_to_dict(constraint) for constraint in self.constraints],
            "evidence_requirements": list(self.evidence_requirements),
            "required_artifacts": list(self.required_artifacts),
            "validator_types": list(self.validator_types),
            "review_questions": list(self.review_questions),
            "known_gaps": list(self.known_gaps),
        }


class ProfileRegistry:
    """Deterministic in-memory profile registry."""

    def __init__(
        self,
        *,
        capability_profiles: list[CapabilityProfile] | None = None,
        verification_profiles: list[VerificationProfile] | None = None,
    ) -> None:
        self._capability_profiles = {profile.profile_id: profile for profile in capability_profiles or []}
        self._verification_profiles = {profile.profile_id: profile for profile in verification_profiles or []}

    @classmethod
    def builtins(cls) -> "ProfileRegistry":
        return cls(
            capability_profiles=[
                CapabilityProfile(
                    profile_id="user_provided_evidence_only",
                    version="1.0",
                    constraints=[
                        {
                            "constraint_id": "P-user_provided_evidence_only-C-001",
                            "kind": "data_boundary",
                            "priority": "must",
                            "statement": "Use only admitted source refs for task facts.",
                            "source_refs": [],
                            "evidence_obligations": ["evidence/source_manifest.json"],
                            "repair_hints": ["Remove unsupported or unproven task facts."],
                        }
                    ],
                    evidence_requirements=["evidence/source_manifest.json"],
                ),
                CapabilityProfile(
                    profile_id="explicit_output_root",
                    version="1.0",
                    constraints=[
                        {
                            "constraint_id": "P-explicit_output_root-C-001",
                            "kind": "workspace_boundary",
                            "priority": "must",
                            "statement": "Write mission outputs only under declared output roots.",
                            "source_refs": [],
                            "evidence_obligations": ["evidence/output_manifest.json"],
                            "repair_hints": ["Move outputs under the declared output root."],
                        }
                    ],
                    evidence_requirements=["evidence/output_manifest.json"],
                ),
            ],
            verification_profiles=[
                VerificationProfile(
                    profile_id="generic_local_verification",
                    version="1.0",
                    validator_types=[
                        "artifact_hash",
                        "command",
                        "file_contains",
                        "file_exists",
                        "forbidden_path",
                        "json_field_exists",
                    ],
                    review_questions=["Do executable validators cover the mission's blocking claims?"],
                    known_gaps=[],
                )
            ],
        )

    def get_capability(self, profile_id: str) -> CapabilityProfile:
        try:
            return self._capability_profiles[profile_id]
        except KeyError as exc:
            raise ContractValidationError(f"unknown capability profile: {profile_id}") from exc

    def get_verification(self, profile_id: str) -> VerificationProfile:
        try:
            return self._verification_profiles[profile_id]
        except KeyError as exc:
            raise ContractValidationError(f"unknown verification profile: {profile_id}") from exc

    def expand_capability_ref(self, ref: CapabilityProfileRef) -> ProfileExpansion:
        profile = self.get_capability(ref.profile_id)
        constraints = [MissionConstraint.from_dict(item) for item in profile.constraints]
        return ProfileExpansion(
            source_profile_id=profile.profile_id,
            source_profile_version=profile.version,
            source_profile_hash=profile.profile_hash,
            source_ref_hash=_profile_ref_hash(ref.profile_id, ref.requirements),
            source_ref_requirements=ensure_json_value(
                require_mapping(ref.requirements, "profile.requirements"),
                "profile.requirements",
            ),
            constraints=constraints,
            evidence_requirements=profile.evidence_requirements,
            required_artifacts=profile.required_artifacts,
        )

    def expand_verification_ref(self, profile_id: str) -> ProfileExpansion:
        profile = self.get_verification(profile_id)
        return ProfileExpansion(
            source_profile_id=profile.profile_id,
            source_profile_version=profile.version,
            source_profile_hash=profile.profile_hash,
            source_ref_hash=_profile_ref_hash(profile_id, {}),
            source_ref_requirements={},
            validator_types=profile.validator_types,
            review_questions=profile.review_questions,
            known_gaps=profile.known_gaps,
        )


def verification_profile_refs_from_payload(payload: Mapping[str, Any]) -> list[str]:
    """Extract verification profile ids from a MissionIR verification payload."""

    data = require_mapping(payload, "verification")
    raw_refs = data.get("verification_profiles")
    if raw_refs is None:
        return ["generic_local_verification"]
    if not isinstance(raw_refs, list):
        raise ContractValidationError("verification.verification_profiles must be a list")
    result: list[str] = []
    for item in raw_refs:
        if isinstance(item, str):
            result.append(require_non_empty_str(item, "verification.verification_profiles[]"))
        else:
            ref_payload = require_mapping(item, "verification.verification_profiles[]")
            result.append(require_non_empty_str(ref_payload.get("profile_id"), "verification.verification_profiles[].profile_id"))
    return result


def validators_from_payload(payload: Mapping[str, Any]) -> list[ValidatorSpec]:
    """Extract validator specs from a MissionIR verification payload."""

    data = require_mapping(payload, "verification")
    return [
        ValidatorSpec.from_dict(require_mapping(item, "verification.validators[]"))
        for item in data.get("validators", [])
    ]


def _constraint_to_dict(constraint: MissionConstraint) -> dict[str, Any]:
    return {
        "constraint_id": constraint.constraint_id,
        "kind": constraint.kind,
        "statement": constraint.statement,
        "priority": constraint.priority,
        "source_refs": list(constraint.source_refs),
        "evidence_obligations": list(constraint.evidence_obligations),
        "validator": constraint.validator,
        "repair_hints": list(constraint.repair_hints),
    }


def _profile_ref_hash(profile_id: str, requirements: Mapping[str, Any]) -> str:
    return stable_json_hash(
        {
            "profile_id": require_non_empty_str(profile_id, "profile.profile_id"),
            "requirements": ensure_json_value(
                require_mapping(requirements, "profile.requirements"),
                "profile.requirements",
            ),
        }
    )
