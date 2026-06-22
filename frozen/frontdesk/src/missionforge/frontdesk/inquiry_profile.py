"""Product inquiry metadata contracts for FrontDesk."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Self

from ..contracts import (
    AuthorityRequirement,
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)


PRODUCT_INQUIRY_PROFILE_SCHEMA_VERSION = "missionforge.frontdesk.product_inquiry_profile.v1"


class SlotRequirement(StrEnum):
    """How strongly a product compiler needs a slot."""

    BLOCKING = "blocking"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
    CONDITIONAL = "conditional"


class SlotValueType(StrEnum):
    """Expected value shape for a product inquiry slot."""

    FREE_TEXT = "free_text"
    ENUM = "enum"
    BOOLEAN = "boolean"
    NUMBER = "number"
    REF = "ref"
    REF_LIST = "ref_list"
    STRING_LIST = "string_list"
    ARTIFACT_PATH = "artifact_path"
    ARTIFACT_PATH_LIST = "artifact_path_list"


class InquiryConfidence(StrEnum):
    """How a FrontDesk slot value was obtained."""

    OBSERVED = "observed"
    INFERRED = "inferred"
    ASSUMED = "assumed"


@dataclass(frozen=True)
class ProductActivation:
    """Authoring-time signal that a product profile applies."""

    activation_id: str
    summary: str
    trigger_terms: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_activation",
            {"activation_id", "summary", "trigger_terms", "source_refs"},
        )
        item = cls(
            activation_id=require_non_empty_str(data.get("activation_id"), "product_activation.activation_id"),
            summary=require_non_empty_str(data.get("summary"), "product_activation.summary"),
            trigger_terms=require_str_list(data.get("trigger_terms", []), "product_activation.trigger_terms"),
            source_refs=require_str_list(data.get("source_refs", []), "product_activation.source_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.activation_id, "product_activation.activation_id")
        require_non_empty_str(self.summary, "product_activation.summary")
        require_str_list(self.trigger_terms, "product_activation.trigger_terms")
        _validate_ref_list(self.source_refs, "product_activation.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "product_activation")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "summary": self.summary,
            "trigger_terms": list(self.trigger_terms),
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class SlotTargetMapping:
    """Opaque product compiler target path for one slot."""

    target: str
    description: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "slot_target_mapping", {"target", "description"})
        item = cls(
            target=require_non_empty_str(data.get("target"), "slot_target_mapping.target"),
            description=str(data.get("description", "")),
        )
        item.validate()
        return item

    def validate(self) -> None:
        target = require_non_empty_str(self.target, "slot_target_mapping.target")
        if "." not in target or any(not part for part in target.split(".")):
            raise ContractValidationError("slot_target_mapping.target must be a non-empty dotted path")
        assert_refs_only_payload(self.to_dict_without_validation(), "slot_target_mapping")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {"target": self.target, "description": self.description}

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class InquirySlot:
    """One product-specific information slot FrontDesk should resolve."""

    slot_id: str
    question: str
    requirement: SlotRequirement
    value_type: SlotValueType
    maps_to: list[SlotTargetMapping] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    default_value: Any = None
    description: str = ""
    examples: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "inquiry_slot",
            {
                "slot_id",
                "question",
                "requirement",
                "value_type",
                "maps_to",
                "choices",
                "default_value",
                "description",
                "examples",
            },
        )
        item = cls(
            slot_id=require_non_empty_str(data.get("slot_id"), "inquiry_slot.slot_id"),
            question=require_non_empty_str(data.get("question"), "inquiry_slot.question"),
            requirement=require_enum(data.get("requirement"), SlotRequirement, "inquiry_slot.requirement"),
            value_type=require_enum(data.get("value_type"), SlotValueType, "inquiry_slot.value_type"),
            maps_to=[
                SlotTargetMapping.from_dict(require_mapping(child, "inquiry_slot.maps_to[]"))
                for child in data.get("maps_to", [])
            ],
            choices=require_str_list(data.get("choices", []), "inquiry_slot.choices"),
            default_value=ensure_json_value(data.get("default_value"), "inquiry_slot.default_value"),
            description=str(data.get("description", "")),
            examples=require_str_list(data.get("examples", []), "inquiry_slot.examples"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.slot_id, "inquiry_slot.slot_id")
        require_non_empty_str(self.question, "inquiry_slot.question")
        requirement = require_enum(self.requirement, SlotRequirement, "inquiry_slot.requirement")
        value_type = require_enum(self.value_type, SlotValueType, "inquiry_slot.value_type")
        if requirement == SlotRequirement.BLOCKING and not self.maps_to:
            raise ContractValidationError("blocking inquiry slots must declare at least one maps_to target")
        for mapping in self.maps_to:
            mapping.validate()
        require_str_list(self.choices, "inquiry_slot.choices")
        if value_type == SlotValueType.ENUM and not self.choices:
            raise ContractValidationError("enum inquiry slots require choices")
        if value_type in _REF_LIKE_SLOT_TYPES:
            _validate_ref_like_value(self.default_value, "inquiry_slot.default_value", value_type, allow_none=True)
            for choice in self.choices:
                validate_ref(choice, "inquiry_slot.choices[]")
        ensure_json_value(self.default_value, "inquiry_slot.default_value")
        require_str_list(self.examples, "inquiry_slot.examples")
        assert_refs_only_payload(self.to_dict_without_validation(), "inquiry_slot")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "question": self.question,
            "requirement": self.requirement.value,
            "value_type": self.value_type.value,
            "maps_to": [mapping.to_dict() for mapping in self.maps_to],
            "choices": list(self.choices),
            "default_value": ensure_json_value(self.default_value, "inquiry_slot.default_value"),
            "description": self.description,
            "examples": list(self.examples),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RiskDimension:
    """Product-specific risk dimension FrontDesk should notice."""

    risk_id: str
    description: str
    severity: str = "advisory"
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "risk_dimension", {"risk_id", "description", "severity", "source_refs"})
        item = cls(
            risk_id=require_non_empty_str(data.get("risk_id"), "risk_dimension.risk_id"),
            description=require_non_empty_str(data.get("description"), "risk_dimension.description"),
            severity=require_non_empty_str(data.get("severity", "advisory"), "risk_dimension.severity"),
            source_refs=require_str_list(data.get("source_refs", []), "risk_dimension.source_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.risk_id, "risk_dimension.risk_id")
        require_non_empty_str(self.description, "risk_dimension.description")
        if self.severity not in {"advisory", "blocking", "review"}:
            raise ContractValidationError("risk_dimension.severity must be advisory, blocking, or review")
        _validate_ref_list(self.source_refs, "risk_dimension.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "risk_dimension")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "description": self.description,
            "severity": self.severity,
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ArtifactArchetype:
    """Expected product artifact family."""

    artifact_id: str
    purpose: str
    expected_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "artifact_archetype", {"artifact_id", "purpose", "expected_refs"})
        item = cls(
            artifact_id=require_non_empty_str(data.get("artifact_id"), "artifact_archetype.artifact_id"),
            purpose=require_non_empty_str(data.get("purpose"), "artifact_archetype.purpose"),
            expected_refs=require_str_list(data.get("expected_refs", []), "artifact_archetype.expected_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.artifact_id, "artifact_archetype.artifact_id")
        require_non_empty_str(self.purpose, "artifact_archetype.purpose")
        _validate_ref_list(self.expected_refs, "artifact_archetype.expected_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "artifact_archetype")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "purpose": self.purpose,
            "expected_refs": list(self.expected_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class AcceptancePrerequisite:
    """Product readiness prerequisite outside generic MissionIR closure."""

    prerequisite_id: str
    description: str
    authority: AuthorityRequirement = AuthorityRequirement.REVIEWER
    evidence_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "acceptance_prerequisite",
            {"prerequisite_id", "description", "authority", "evidence_refs"},
        )
        item = cls(
            prerequisite_id=require_non_empty_str(
                data.get("prerequisite_id"),
                "acceptance_prerequisite.prerequisite_id",
            ),
            description=require_non_empty_str(data.get("description"), "acceptance_prerequisite.description"),
            authority=require_enum(
                data.get("authority", AuthorityRequirement.REVIEWER.value),
                AuthorityRequirement,
                "acceptance_prerequisite.authority",
            ),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "acceptance_prerequisite.evidence_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.prerequisite_id, "acceptance_prerequisite.prerequisite_id")
        require_non_empty_str(self.description, "acceptance_prerequisite.description")
        require_enum(self.authority, AuthorityRequirement, "acceptance_prerequisite.authority")
        _validate_ref_list(self.evidence_refs, "acceptance_prerequisite.evidence_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "acceptance_prerequisite")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "prerequisite_id": self.prerequisite_id,
            "description": self.description,
            "authority": self.authority.value,
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class CompilerReadiness:
    """Slots and risk checks needed before a product compiler may run."""

    blocking_slot_ids: list[str] = field(default_factory=list)
    recommended_slot_ids: list[str] = field(default_factory=list)
    human_review_risk_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "compiler_readiness",
            {"blocking_slot_ids", "recommended_slot_ids", "human_review_risk_ids"},
        )
        item = cls(
            blocking_slot_ids=require_str_list(data.get("blocking_slot_ids", []), "compiler_readiness.blocking_slot_ids"),
            recommended_slot_ids=require_str_list(
                data.get("recommended_slot_ids", []),
                "compiler_readiness.recommended_slot_ids",
            ),
            human_review_risk_ids=require_str_list(
                data.get("human_review_risk_ids", []),
                "compiler_readiness.human_review_risk_ids",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_str_list(self.blocking_slot_ids, "compiler_readiness.blocking_slot_ids")
        require_str_list(self.recommended_slot_ids, "compiler_readiness.recommended_slot_ids")
        require_str_list(self.human_review_risk_ids, "compiler_readiness.human_review_risk_ids")
        assert_refs_only_payload(self.to_dict_without_validation(), "compiler_readiness")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "blocking_slot_ids": list(self.blocking_slot_ids),
            "recommended_slot_ids": list(self.recommended_slot_ids),
            "human_review_risk_ids": list(self.human_review_risk_ids),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class SourcePolicy:
    """Product source admission boundaries for authoring-time context."""

    allowed_source_refs: list[str] = field(default_factory=list)
    excluded_source_refs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "source_policy", {"allowed_source_refs", "excluded_source_refs", "notes"})
        item = cls(
            allowed_source_refs=require_str_list(data.get("allowed_source_refs", []), "source_policy.allowed_source_refs"),
            excluded_source_refs=require_str_list(
                data.get("excluded_source_refs", []),
                "source_policy.excluded_source_refs",
            ),
            notes=require_str_list(data.get("notes", []), "source_policy.notes"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        _validate_ref_list(self.allowed_source_refs, "source_policy.allowed_source_refs")
        _validate_ref_list(self.excluded_source_refs, "source_policy.excluded_source_refs")
        require_str_list(self.notes, "source_policy.notes")
        assert_refs_only_payload(self.to_dict_without_validation(), "source_policy")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "allowed_source_refs": list(self.allowed_source_refs),
            "excluded_source_refs": list(self.excluded_source_refs),
            "notes": list(self.notes),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ProductInquiryProfile:
    """Product-specific FrontDesk questioning profile."""

    product_id: str
    version: str
    display_name: str
    activations: list[ProductActivation] = field(default_factory=list)
    slots: list[InquirySlot] = field(default_factory=list)
    risk_dimensions: list[RiskDimension] = field(default_factory=list)
    artifact_archetypes: list[ArtifactArchetype] = field(default_factory=list)
    acceptance_prerequisites: list[AcceptancePrerequisite] = field(default_factory=list)
    compiler_readiness: CompilerReadiness = field(default_factory=CompilerReadiness)
    source_policy: SourcePolicy = field(default_factory=SourcePolicy)
    schema_version: str = PRODUCT_INQUIRY_PROFILE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_inquiry_profile",
            {
                "schema_version",
                "product_id",
                "version",
                "display_name",
                "activations",
                "slots",
                "risk_dimensions",
                "artifact_archetypes",
                "acceptance_prerequisites",
                "compiler_readiness",
                "source_policy",
                "profile_hash",
            },
        )
        profile = cls(
            product_id=require_non_empty_str(data.get("product_id"), "product_inquiry_profile.product_id"),
            version=require_non_empty_str(data.get("version"), "product_inquiry_profile.version"),
            display_name=require_non_empty_str(data.get("display_name"), "product_inquiry_profile.display_name"),
            activations=[
                ProductActivation.from_dict(require_mapping(child, "product_inquiry_profile.activations[]"))
                for child in data.get("activations", [])
            ],
            slots=[
                InquirySlot.from_dict(require_mapping(child, "product_inquiry_profile.slots[]"))
                for child in data.get("slots", [])
            ],
            risk_dimensions=[
                RiskDimension.from_dict(require_mapping(child, "product_inquiry_profile.risk_dimensions[]"))
                for child in data.get("risk_dimensions", [])
            ],
            artifact_archetypes=[
                ArtifactArchetype.from_dict(require_mapping(child, "product_inquiry_profile.artifact_archetypes[]"))
                for child in data.get("artifact_archetypes", [])
            ],
            acceptance_prerequisites=[
                AcceptancePrerequisite.from_dict(
                    require_mapping(child, "product_inquiry_profile.acceptance_prerequisites[]")
                )
                for child in data.get("acceptance_prerequisites", [])
            ],
            compiler_readiness=CompilerReadiness.from_dict(
                require_mapping(data.get("compiler_readiness", {}), "product_inquiry_profile.compiler_readiness")
            ),
            source_policy=SourcePolicy.from_dict(
                require_mapping(data.get("source_policy", {}), "product_inquiry_profile.source_policy")
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_INQUIRY_PROFILE_SCHEMA_VERSION),
                "product_inquiry_profile.schema_version",
            ),
        )
        profile.validate()
        if data.get("profile_hash") not in {None, profile.profile_hash}:
            raise ContractValidationError("product_inquiry_profile.profile_hash does not match payload")
        return profile

    @property
    def profile_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    @property
    def slot_ids(self) -> list[str]:
        return [slot.slot_id for slot in self.slots]

    def validate(self) -> None:
        if self.schema_version != PRODUCT_INQUIRY_PROFILE_SCHEMA_VERSION:
            raise ContractValidationError("product_inquiry_profile.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_inquiry_profile.product_id")
        require_non_empty_str(self.version, "product_inquiry_profile.version")
        require_non_empty_str(self.display_name, "product_inquiry_profile.display_name")
        _require_unique(self.slot_ids, "product_inquiry_profile.slots[].slot_id")
        slot_ids = set(self.slot_ids)
        for slot in self.slots:
            slot.validate()
        unknown_blocking = sorted(set(self.compiler_readiness.blocking_slot_ids) - slot_ids)
        if unknown_blocking:
            raise ContractValidationError(f"compiler_readiness.blocking_slot_ids reference unknown slots: {unknown_blocking}")
        unknown_recommended = sorted(set(self.compiler_readiness.recommended_slot_ids) - slot_ids)
        if unknown_recommended:
            raise ContractValidationError(
                f"compiler_readiness.recommended_slot_ids reference unknown slots: {unknown_recommended}"
            )
        risk_ids = [risk.risk_id for risk in self.risk_dimensions]
        _require_unique(risk_ids, "product_inquiry_profile.risk_dimensions[].risk_id")
        unknown_review_risks = sorted(set(self.compiler_readiness.human_review_risk_ids) - set(risk_ids))
        if unknown_review_risks:
            raise ContractValidationError(
                f"compiler_readiness.human_review_risk_ids reference unknown risks: {unknown_review_risks}"
            )
        for item in self.activations:
            item.validate()
        for risk in self.risk_dimensions:
            risk.validate()
        for artifact in self.artifact_archetypes:
            artifact.validate()
        for prerequisite in self.acceptance_prerequisites:
            prerequisite.validate()
        self.compiler_readiness.validate()
        self.source_policy.validate()
        assert_refs_only_payload(self.to_dict_without_hash(), "product_inquiry_profile")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "version": self.version,
            "display_name": self.display_name,
            "activations": [item.to_dict() for item in self.activations],
            "slots": [item.to_dict() for item in self.slots],
            "risk_dimensions": [item.to_dict() for item in self.risk_dimensions],
            "artifact_archetypes": [item.to_dict() for item in self.artifact_archetypes],
            "acceptance_prerequisites": [item.to_dict() for item in self.acceptance_prerequisites],
            "compiler_readiness": self.compiler_readiness.to_dict(),
            "source_policy": self.source_policy.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["profile_hash"] = self.profile_hash
        return payload


_REF_LIKE_SLOT_TYPES = {
    SlotValueType.REF,
    SlotValueType.REF_LIST,
    SlotValueType.ARTIFACT_PATH,
    SlotValueType.ARTIFACT_PATH_LIST,
}


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
    return data


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for ref in values:
        validate_ref(ref, f"{field_name}[]")


def _require_unique(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise ContractValidationError(f"{field_name} contains duplicate value(s): {sorted(set(duplicates))}")


def _validate_ref_like_value(value: Any, field_name: str, value_type: SlotValueType, *, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if value_type in {SlotValueType.REF, SlotValueType.ARTIFACT_PATH}:
        validate_ref(value, field_name)
        return
    if value_type in {SlotValueType.REF_LIST, SlotValueType.ARTIFACT_PATH_LIST}:
        for ref in require_str_list(value, field_name):
            validate_ref(ref, f"{field_name}[]")


__all__ = [
    "PRODUCT_INQUIRY_PROFILE_SCHEMA_VERSION",
    "AcceptancePrerequisite",
    "ArtifactArchetype",
    "CompilerReadiness",
    "InquiryConfidence",
    "InquirySlot",
    "ProductActivation",
    "ProductInquiryProfile",
    "RiskDimension",
    "SlotRequirement",
    "SlotTargetMapping",
    "SlotValueType",
    "SourcePolicy",
]
