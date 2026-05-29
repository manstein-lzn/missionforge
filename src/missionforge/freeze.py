"""Mission expansion and freezing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import ContractValidationError, require_mapping, require_non_empty_str, require_str_list, stable_json_hash
from .ir import MissionConstraint, MissionIR
from .profiles import (
    ProfileExpansion,
    ProfileRegistry,
    validators_from_payload,
    verification_profile_refs_from_payload,
)
from .verification import ValidatorSpec


@dataclass(frozen=True)
class ContractManifest:
    """Manifest describing the frozen contract inputs."""

    mission_id: str
    contract_hash: str
    profile_hashes: list[str] = field(default_factory=list)
    profile_ref_hashes: list[str] = field(default_factory=list)
    validator_ids: list[str] = field(default_factory=list)
    constraint_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ContractManifest":
        data = require_mapping(payload, "contract_manifest")
        manifest = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "contract_manifest.mission_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "contract_manifest.contract_hash"),
            profile_hashes=require_str_list(data.get("profile_hashes", []), "contract_manifest.profile_hashes"),
            profile_ref_hashes=require_str_list(
                data.get("profile_ref_hashes", []),
                "contract_manifest.profile_ref_hashes",
            ),
            validator_ids=require_str_list(data.get("validator_ids", []), "contract_manifest.validator_ids"),
            constraint_ids=require_str_list(data.get("constraint_ids", []), "contract_manifest.constraint_ids"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "contract_manifest.mission_id")
        require_non_empty_str(self.contract_hash, "contract_manifest.contract_hash")
        require_str_list(self.profile_hashes, "contract_manifest.profile_hashes")
        require_str_list(self.profile_ref_hashes, "contract_manifest.profile_ref_hashes")
        require_str_list(self.validator_ids, "contract_manifest.validator_ids")
        require_str_list(self.constraint_ids, "contract_manifest.constraint_ids")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "contract_hash": self.contract_hash,
            "profile_hashes": list(self.profile_hashes),
            "profile_ref_hashes": list(self.profile_ref_hashes),
            "validator_ids": list(self.validator_ids),
            "constraint_ids": list(self.constraint_ids),
        }


@dataclass(frozen=True)
class ExpandedMission:
    """MissionIR after deterministic profile expansion."""

    mission_id: str
    objective: dict[str, Any]
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    constraints: list[MissionConstraint]
    validators: list[ValidatorSpec]
    profile_expansions: list[ProfileExpansion]
    verification_profile_ids: list[str]
    manual_gates: list[dict[str, Any]] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExpandedMission":
        data = require_mapping(payload, "expanded_mission")
        expanded = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "expanded_mission.mission_id"),
            objective=require_mapping(data.get("objective", {}), "expanded_mission.objective"),
            inputs=require_mapping(data.get("inputs", {}), "expanded_mission.inputs"),
            outputs=require_mapping(data.get("outputs", {}), "expanded_mission.outputs"),
            constraints=[
                MissionConstraint.from_dict(require_mapping(item, "expanded_mission.constraints[]"))
                for item in data.get("constraints", [])
            ],
            validators=[
                ValidatorSpec.from_dict(require_mapping(item, "expanded_mission.validators[]"))
                for item in data.get("validators", [])
            ],
            profile_expansions=[
                _profile_expansion_from_dict(require_mapping(item, "expanded_mission.profile_expansions[]"))
                for item in data.get("profile_expansions", [])
            ],
            verification_profile_ids=require_str_list(
                data.get("verification_profile_ids", []),
                "expanded_mission.verification_profile_ids",
            ),
            manual_gates=[
                require_mapping(item, "expanded_mission.manual_gates[]")
                for item in data.get("manual_gates", [])
            ],
            evidence_requirements=require_str_list(
                data.get("evidence_requirements", []),
                "expanded_mission.evidence_requirements",
            ),
            required_artifacts=require_str_list(
                data.get("required_artifacts", []),
                "expanded_mission.required_artifacts",
            ),
        )
        expanded.validate()
        return expanded

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "expanded_mission.mission_id")
        require_mapping(self.objective, "expanded_mission.objective")
        require_mapping(self.inputs, "expanded_mission.inputs")
        require_mapping(self.outputs, "expanded_mission.outputs")
        for constraint in self.constraints:
            constraint.validate()
        for validator in self.validators:
            validator.validate()
        require_str_list(self.verification_profile_ids, "expanded_mission.verification_profile_ids")
        for gate in self.manual_gates:
            require_mapping(gate, "expanded_mission.manual_gates[]")
        require_str_list(self.evidence_requirements, "expanded_mission.evidence_requirements")
        require_str_list(self.required_artifacts, "expanded_mission.required_artifacts")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "objective": dict(self.objective),
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "constraints": [_constraint_to_dict(constraint) for constraint in self.constraints],
            "validators": [validator.to_dict() for validator in self.validators],
            "profile_expansions": [expansion.to_dict() for expansion in self.profile_expansions],
            "verification_profile_ids": list(self.verification_profile_ids),
            "manual_gates": [dict(gate) for gate in self.manual_gates],
            "evidence_requirements": list(self.evidence_requirements),
            "required_artifacts": list(self.required_artifacts),
        }


@dataclass(frozen=True)
class FrozenMissionContract:
    """Locked, hashed mission contract."""

    mission_id: str
    contract_hash: str
    expanded_mission: ExpandedMission
    manifest: ContractManifest

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrozenMissionContract":
        data = require_mapping(payload, "frozen_mission_contract")
        expanded = ExpandedMission.from_dict(require_mapping(data.get("expanded_mission"), "frozen_contract.expanded_mission"))
        manifest = ContractManifest.from_dict(require_mapping(data.get("manifest"), "frozen_contract.manifest"))
        contract = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "frozen_contract.mission_id"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "frozen_contract.contract_hash"),
            expanded_mission=expanded,
            manifest=manifest,
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "frozen_contract.mission_id")
        require_non_empty_str(self.contract_hash, "frozen_contract.contract_hash")
        self.expanded_mission.validate()
        self.manifest.validate()
        if self.mission_id != self.expanded_mission.mission_id:
            raise ContractValidationError("frozen contract mission_id does not match expanded mission")
        if self.manifest.contract_hash != self.contract_hash:
            raise ContractValidationError("frozen contract hash does not match manifest")
        expected_hash = stable_json_hash(self.expanded_mission.to_dict())
        if expected_hash != self.contract_hash:
            raise ContractValidationError("frozen contract hash does not match expanded mission")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "contract_hash": self.contract_hash,
            "expanded_mission": self.expanded_mission.to_dict(),
            "manifest": self.manifest.to_dict(),
        }


def expand_mission(mission: MissionIR, registry: ProfileRegistry | None = None) -> ExpandedMission:
    """Expand mission profile refs and validate validator language."""

    mission.validate()
    active_registry = registry or ProfileRegistry.builtins()
    expansions: list[ProfileExpansion] = []
    constraints: list[MissionConstraint] = list(mission.constraints)
    evidence_requirements: list[str] = list(mission.verification.get("required_evidence", []))
    required_artifacts: list[str] = list(mission.outputs.get("required_artifacts", []))

    for profile_ref in mission.capability_profiles:
        expansion = active_registry.expand_capability_ref(profile_ref)
        expansions.append(expansion)
        constraints.extend(expansion.constraints)
        evidence_requirements.extend(expansion.evidence_requirements)
        required_artifacts.extend(expansion.required_artifacts)

    verification_profile_ids = verification_profile_refs_from_payload(mission.verification)
    allowed_validator_types: set[str] = set()
    for profile_id in verification_profile_ids:
        expansion = active_registry.expand_verification_ref(profile_id)
        expansions.append(expansion)
        allowed_validator_types.update(expansion.validator_types)

    validators = validators_from_payload(mission.verification)
    for validator in validators:
        if validator.type not in allowed_validator_types:
            raise ContractValidationError(f"validator type {validator.type!r} is not declared by verification profiles")

    _reject_duplicate_constraints(constraints)
    _reject_duplicate_validators(validators)

    return ExpandedMission(
        mission_id=mission.mission_id,
        objective=mission.objective.to_dict() if hasattr(mission.objective, "to_dict") else {
            "summary": mission.objective.summary,
            "deliverable_type": mission.objective.deliverable_type,
            "success_signals": list(mission.objective.success_signals),
        },
        inputs=dict(mission.inputs),
        outputs=dict(mission.outputs),
        constraints=constraints,
        validators=validators,
        profile_expansions=expansions,
        verification_profile_ids=verification_profile_ids,
        manual_gates=[
            require_mapping(item, "verification.manual_gates[]")
            for item in mission.verification.get("manual_gates", [])
        ],
        evidence_requirements=_dedupe(evidence_requirements),
        required_artifacts=_dedupe(required_artifacts),
    )


def freeze_mission(mission: MissionIR, registry: ProfileRegistry | None = None) -> FrozenMissionContract:
    """Freeze an expanded mission into a stable hashed contract."""

    expanded = expand_mission(mission, registry=registry)
    contract_payload = expanded.to_dict()
    contract_hash = stable_json_hash(contract_payload)
    manifest = ContractManifest(
        mission_id=expanded.mission_id,
        contract_hash=contract_hash,
        profile_hashes=[expansion.source_profile_hash for expansion in expanded.profile_expansions],
        profile_ref_hashes=[expansion.source_ref_hash for expansion in expanded.profile_expansions],
        validator_ids=[validator.validator_id for validator in expanded.validators],
        constraint_ids=[constraint.constraint_id for constraint in expanded.constraints],
    )
    return FrozenMissionContract(
        mission_id=expanded.mission_id,
        contract_hash=contract_hash,
        expanded_mission=expanded,
        manifest=manifest,
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _profile_expansion_from_dict(payload: Mapping[str, Any]) -> ProfileExpansion:
    return ProfileExpansion(
        source_profile_id=require_non_empty_str(payload.get("source_profile_id"), "profile_expansion.source_profile_id"),
        source_profile_version=require_non_empty_str(
            payload.get("source_profile_version"),
            "profile_expansion.source_profile_version",
        ),
        source_profile_hash=require_non_empty_str(payload.get("source_profile_hash"), "profile_expansion.source_profile_hash"),
        source_ref_hash=require_non_empty_str(payload.get("source_ref_hash"), "profile_expansion.source_ref_hash"),
        source_ref_requirements=require_mapping(
            payload.get("source_ref_requirements", {}),
            "profile_expansion.source_ref_requirements",
        ),
        constraints=[
            MissionConstraint.from_dict(require_mapping(item, "profile_expansion.constraints[]"))
            for item in payload.get("constraints", [])
        ],
        evidence_requirements=require_str_list(
            payload.get("evidence_requirements", []),
            "profile_expansion.evidence_requirements",
        ),
        required_artifacts=require_str_list(payload.get("required_artifacts", []), "profile_expansion.required_artifacts"),
        validator_types=require_str_list(payload.get("validator_types", []), "profile_expansion.validator_types"),
        review_questions=require_str_list(payload.get("review_questions", []), "profile_expansion.review_questions"),
        known_gaps=require_str_list(payload.get("known_gaps", []), "profile_expansion.known_gaps"),
    )


def _reject_duplicate_constraints(constraints: list[MissionConstraint]) -> None:
    seen: set[str] = set()
    for constraint in constraints:
        if constraint.constraint_id in seen:
            raise ContractValidationError(f"duplicate expanded constraint_id: {constraint.constraint_id}")
        seen.add(constraint.constraint_id)


def _reject_duplicate_validators(validators: list[ValidatorSpec]) -> None:
    seen: set[str] = set()
    for validator in validators:
        if validator.validator_id in seen:
            raise ContractValidationError(f"duplicate validator_id: {validator.validator_id}")
        seen.add(validator.validator_id)


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
