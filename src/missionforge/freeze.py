"""Mission expansion and freezing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import ContractValidationError, require_non_empty_str, stable_json_hash
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

    def to_dict(self) -> dict[str, Any]:
        require_non_empty_str(self.mission_id, "contract_manifest.mission_id")
        require_non_empty_str(self.contract_hash, "contract_manifest.contract_hash")
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
    evidence_requirements: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "objective": dict(self.objective),
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "constraints": [_constraint_to_dict(constraint) for constraint in self.constraints],
            "validators": [validator.to_dict() for validator in self.validators],
            "profile_expansions": [expansion.to_dict() for expansion in self.profile_expansions],
            "verification_profile_ids": list(self.verification_profile_ids),
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

    def to_dict(self) -> dict[str, Any]:
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
