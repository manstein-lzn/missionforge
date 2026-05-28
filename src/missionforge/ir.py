"""Mission IR schema and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .contracts import MissionValidationError


MISSION_IR_SCHEMA_VERSION = "missionforge.mission_ir.v1"
PRIORITIES = {"must", "should", "may"}


def _require_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissionValidationError(f"{field_name} must be a non-empty string")
    return value


def _str_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise MissionValidationError(f"{field_name} must be a list of non-empty strings")
    return list(value)


def _mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MissionValidationError(f"{field_name} must be a mapping")
    return dict(value)


@dataclass(frozen=True)
class MissionObjective:
    """Human-intelligible mission goal."""

    summary: str
    deliverable_type: str
    success_signals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionObjective":
        return cls(
            summary=_require_non_empty_str(payload.get("summary"), "objective.summary"),
            deliverable_type=_require_non_empty_str(payload.get("deliverable_type"), "objective.deliverable_type"),
            success_signals=_str_list(payload.get("success_signals", []), "objective.success_signals"),
        )

    def validate(self) -> None:
        _require_non_empty_str(self.summary, "objective.summary")
        _require_non_empty_str(self.deliverable_type, "objective.deliverable_type")
        _str_list(self.success_signals, "objective.success_signals")


@dataclass(frozen=True)
class MissionConstraint:
    """One verifiable mission constraint."""

    constraint_id: str
    kind: str
    statement: str
    priority: str = "must"
    source_refs: list[str] = field(default_factory=list)
    evidence_obligations: list[str] = field(default_factory=list)
    validator: str | None = None
    repair_hints: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionConstraint":
        validator = payload.get("validator")
        if validator is not None:
            validator = _require_non_empty_str(validator, "constraint.validator")
        return cls(
            constraint_id=_require_non_empty_str(payload.get("constraint_id"), "constraint.constraint_id"),
            kind=_require_non_empty_str(payload.get("kind"), "constraint.kind"),
            statement=_require_non_empty_str(payload.get("statement"), "constraint.statement"),
            priority=_require_non_empty_str(payload.get("priority", "must"), "constraint.priority"),
            source_refs=_str_list(payload.get("source_refs", []), "constraint.source_refs"),
            evidence_obligations=_str_list(
                payload.get("evidence_obligations", []),
                "constraint.evidence_obligations",
            ),
            validator=validator,
            repair_hints=_str_list(payload.get("repair_hints", []), "constraint.repair_hints"),
        )

    def validate(self) -> None:
        _require_non_empty_str(self.constraint_id, "constraint.constraint_id")
        _require_non_empty_str(self.kind, "constraint.kind")
        _require_non_empty_str(self.statement, "constraint.statement")
        if self.priority not in PRIORITIES:
            raise MissionValidationError(f"constraint.priority must be one of {sorted(PRIORITIES)}")
        _str_list(self.source_refs, "constraint.source_refs")
        _str_list(self.evidence_obligations, "constraint.evidence_obligations")
        if self.validator is not None:
            _require_non_empty_str(self.validator, "constraint.validator")
        _str_list(self.repair_hints, "constraint.repair_hints")


@dataclass(frozen=True)
class CapabilityProfileRef:
    """Reference to a reusable mission capability profile."""

    profile_id: str
    requirements: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityProfileRef":
        return cls(
            profile_id=_require_non_empty_str(payload.get("profile_id"), "profile.profile_id"),
            requirements=_mapping(payload.get("requirements", {}), "profile.requirements"),
        )

    def validate(self) -> None:
        _require_non_empty_str(self.profile_id, "profile.profile_id")
        _mapping(self.requirements, "profile.requirements")


@dataclass(frozen=True)
class MissionIR:
    """Canonical mission contract consumed by MissionForge."""

    mission_id: str
    objective: MissionObjective
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    constraints: list[MissionConstraint] = field(default_factory=list)
    capability_profiles: list[CapabilityProfileRef] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    repair_policy: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    observability: dict[str, Any] = field(default_factory=dict)
    schema_version: str = MISSION_IR_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionIR":
        if not isinstance(payload, Mapping):
            raise MissionValidationError("MissionIR payload must be a mapping")
        objective_payload = _mapping(payload.get("objective"), "objective")
        mission = cls(
            schema_version=_require_non_empty_str(payload.get("schema_version"), "schema_version"),
            mission_id=_require_non_empty_str(payload.get("mission_id"), "mission_id"),
            objective=MissionObjective.from_dict(objective_payload),
            inputs=_mapping(payload.get("inputs", {}), "inputs"),
            outputs=_mapping(payload.get("outputs", {}), "outputs"),
            constraints=[
                MissionConstraint.from_dict(_mapping(item, "constraints[]"))
                for item in payload.get("constraints", [])
            ],
            capability_profiles=[
                CapabilityProfileRef.from_dict(_mapping(item, "capability_profiles[]"))
                for item in payload.get("capability_profiles", [])
            ],
            verification=_mapping(payload.get("verification", {}), "verification"),
            repair_policy=_mapping(payload.get("repair_policy", {}), "repair_policy"),
            budget=_mapping(payload.get("budget", {}), "budget"),
            observability=_mapping(payload.get("observability", {}), "observability"),
        )
        mission.validate()
        return mission

    def validate(self) -> None:
        if self.schema_version != MISSION_IR_SCHEMA_VERSION:
            raise MissionValidationError(f"unsupported schema_version: {self.schema_version}")
        _require_non_empty_str(self.mission_id, "mission_id")
        self.objective.validate()
        _mapping(self.inputs, "inputs")
        _mapping(self.outputs, "outputs")
        seen_constraints: set[str] = set()
        for constraint in self.constraints:
            constraint.validate()
            if constraint.constraint_id in seen_constraints:
                raise MissionValidationError(f"duplicate constraint_id: {constraint.constraint_id}")
            seen_constraints.add(constraint.constraint_id)
        for profile in self.capability_profiles:
            profile.validate()
        _mapping(self.verification, "verification")
        _mapping(self.repair_policy, "repair_policy")
        _mapping(self.budget, "budget")
        _mapping(self.observability, "observability")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)
