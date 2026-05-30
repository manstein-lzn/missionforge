"""FrontDesk intent bundle contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Self

from ..contracts import (
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


FRONTDESK_INTENT_BUNDLE_SCHEMA_VERSION = "missionforge.frontdesk.intent_bundle.v1"


class SlotValueStatus(StrEnum):
    """Resolution status for one product slot."""

    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    ASSUMED = "assumed"
    MISSING = "missing"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


class IntentBundleReadiness(StrEnum):
    """Whether an intent bundle may be consumed by product integration."""

    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_PRODUCT_COMPILE = "ready_for_product_compile"
    GENERIC_COMPILE_ONLY = "generic_compile_only"
    UNSUPPORTED_PRODUCT = "unsupported_product"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    FAILED_CLOSED = "failed_closed"


@dataclass(frozen=True)
class ProductContextSnapshot:
    """Refs-only snapshot of product identity used during inquiry."""

    product_id: str = "generic"
    display_name: str = "Generic MissionForge"
    profile_ref: str = ""
    profile_hash: str = ""
    version: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_context_snapshot",
            {"product_id", "display_name", "profile_ref", "profile_hash", "version"},
        )
        item = cls(
            product_id=require_non_empty_str(data.get("product_id", "generic"), "product_context_snapshot.product_id"),
            display_name=require_non_empty_str(
                data.get("display_name", "Generic MissionForge"),
                "product_context_snapshot.display_name",
            ),
            profile_ref=str(data.get("profile_ref", "")),
            profile_hash=str(data.get("profile_hash", "")),
            version=str(data.get("version", "")),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.product_id, "product_context_snapshot.product_id")
        require_non_empty_str(self.display_name, "product_context_snapshot.display_name")
        if self.profile_ref:
            validate_ref(self.profile_ref, "product_context_snapshot.profile_ref")
        if self.profile_hash and not self.profile_hash.startswith("sha256:"):
            raise ContractValidationError("product_context_snapshot.profile_hash must be sha256:*")
        assert_refs_only_payload(self.to_dict_without_validation(), "product_context_snapshot")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "display_name": self.display_name,
            "profile_ref": self.profile_ref,
            "profile_hash": self.profile_hash,
            "version": self.version,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class IntentGenericRefs:
    """Generic FrontDesk artifact refs admitted into product compilation."""

    session_ref: str = "frontdesk/session.json"
    workspace_facts_ref: str = ""
    source_admission_report_ref: str = ""
    core_need_brief_ref: str = ""
    sanitized_sources_ref: str = ""
    semantic_lock_ref: str = ""
    mission_brief_ref: str = ""
    semantic_coverage_ref: str = ""
    solution_plan_ref: str = ""
    mission_plan_ref: str = ""
    mission_mapping_report_ref: str = ""
    draft_mission_ref: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "intent_generic_refs",
            {
                "session_ref",
                "workspace_facts_ref",
                "source_admission_report_ref",
                "core_need_brief_ref",
                "sanitized_sources_ref",
                "semantic_lock_ref",
                "mission_brief_ref",
                "semantic_coverage_ref",
                "solution_plan_ref",
                "mission_plan_ref",
                "mission_mapping_report_ref",
                "draft_mission_ref",
            },
        )
        item = cls(
            session_ref=data.get("session_ref", "frontdesk/session.json"),
            workspace_facts_ref=str(data.get("workspace_facts_ref", "")),
            source_admission_report_ref=str(data.get("source_admission_report_ref", "")),
            core_need_brief_ref=str(data.get("core_need_brief_ref", "")),
            sanitized_sources_ref=str(data.get("sanitized_sources_ref", "")),
            semantic_lock_ref=str(data.get("semantic_lock_ref", "")),
            mission_brief_ref=str(data.get("mission_brief_ref", "")),
            semantic_coverage_ref=str(data.get("semantic_coverage_ref", "")),
            solution_plan_ref=str(data.get("solution_plan_ref", "")),
            mission_plan_ref=str(data.get("mission_plan_ref", "")),
            mission_mapping_report_ref=str(data.get("mission_mapping_report_ref", "")),
            draft_mission_ref=str(data.get("draft_mission_ref", "")),
        )
        item.validate()
        return item

    @property
    def refs(self) -> list[str]:
        return [
            ref
            for ref in (
                self.session_ref,
                self.workspace_facts_ref,
                self.source_admission_report_ref,
                self.core_need_brief_ref,
                self.sanitized_sources_ref,
                self.semantic_lock_ref,
                self.mission_brief_ref,
                self.semantic_coverage_ref,
                self.solution_plan_ref,
                self.mission_plan_ref,
                self.mission_mapping_report_ref,
                self.draft_mission_ref,
            )
            if ref
        ]

    def validate(self) -> None:
        for name, ref in self.to_dict_without_validation().items():
            if ref:
                validate_ref(ref, f"intent_generic_refs.{name}")
        assert_refs_only_payload(self.to_dict_without_validation(), "intent_generic_refs")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "session_ref": self.session_ref,
            "workspace_facts_ref": self.workspace_facts_ref,
            "source_admission_report_ref": self.source_admission_report_ref,
            "core_need_brief_ref": self.core_need_brief_ref,
            "sanitized_sources_ref": self.sanitized_sources_ref,
            "semantic_lock_ref": self.semantic_lock_ref,
            "mission_brief_ref": self.mission_brief_ref,
            "semantic_coverage_ref": self.semantic_coverage_ref,
            "solution_plan_ref": self.solution_plan_ref,
            "mission_plan_ref": self.mission_plan_ref,
            "mission_mapping_report_ref": self.mission_mapping_report_ref,
            "draft_mission_ref": self.draft_mission_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class SlotValue:
    """Resolved value for one ProductInquiryProfile slot."""

    slot_id: str
    status: SlotValueStatus
    value: Any = None
    confidence: str = "inferred"
    source_refs: list[str] = field(default_factory=list)
    question: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "slot_value",
            {"slot_id", "status", "value", "confidence", "source_refs", "question"},
        )
        item = cls(
            slot_id=require_non_empty_str(data.get("slot_id"), "slot_value.slot_id"),
            status=require_enum(data.get("status"), SlotValueStatus, "slot_value.status"),
            value=ensure_json_value(data.get("value"), "slot_value.value"),
            confidence=require_non_empty_str(data.get("confidence", "inferred"), "slot_value.confidence"),
            source_refs=require_str_list(data.get("source_refs", []), "slot_value.source_refs"),
            question=str(data.get("question", "")),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.slot_id, "slot_value.slot_id")
        status = require_enum(self.status, SlotValueStatus, "slot_value.status")
        ensure_json_value(self.value, "slot_value.value")
        require_non_empty_str(self.confidence, "slot_value.confidence")
        _validate_ref_list(self.source_refs, "slot_value.source_refs")
        if status in {SlotValueStatus.CONFIRMED, SlotValueStatus.INFERRED, SlotValueStatus.ASSUMED} and self.value in (
            None,
            "",
            [],
        ):
            raise ContractValidationError("resolved slot values require a non-empty value")
        if status == SlotValueStatus.MISSING and not self.question:
            raise ContractValidationError("missing slot values require a clarification question")
        assert_refs_only_payload(self.to_dict_without_validation(), "slot_value")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "status": self.status.value,
            "value": ensure_json_value(self.value, "slot_value.value"),
            "confidence": self.confidence,
            "source_refs": list(self.source_refs),
            "question": self.question,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ProductHypothesis:
    """Product-scope hypothesis derived from structured FrontDesk artifacts."""

    hypothesis_id: str
    statement: str
    confidence: str = "inferred"
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "product_hypothesis", {"hypothesis_id", "statement", "confidence", "source_refs"})
        item = cls(
            hypothesis_id=require_non_empty_str(data.get("hypothesis_id"), "product_hypothesis.hypothesis_id"),
            statement=require_non_empty_str(data.get("statement"), "product_hypothesis.statement"),
            confidence=require_non_empty_str(data.get("confidence", "inferred"), "product_hypothesis.confidence"),
            source_refs=require_str_list(data.get("source_refs", []), "product_hypothesis.source_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.hypothesis_id, "product_hypothesis.hypothesis_id")
        require_non_empty_str(self.statement, "product_hypothesis.statement")
        require_non_empty_str(self.confidence, "product_hypothesis.confidence")
        _validate_ref_list(self.source_refs, "product_hypothesis.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "product_hypothesis")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "confidence": self.confidence,
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RiskFlag:
    """Observed or inferred product risk flag."""

    risk_id: str
    status: str
    rationale: str
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(payload, "risk_flag", {"risk_id", "status", "rationale", "source_refs"})
        item = cls(
            risk_id=require_non_empty_str(data.get("risk_id"), "risk_flag.risk_id"),
            status=require_non_empty_str(data.get("status"), "risk_flag.status"),
            rationale=require_non_empty_str(data.get("rationale"), "risk_flag.rationale"),
            source_refs=require_str_list(data.get("source_refs", []), "risk_flag.source_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.risk_id, "risk_flag.risk_id")
        if self.status not in {"observed", "inferred", "not_observed", "needs_review"}:
            raise ContractValidationError("risk_flag.status must be observed, inferred, not_observed, or needs_review")
        require_non_empty_str(self.rationale, "risk_flag.rationale")
        _validate_ref_list(self.source_refs, "risk_flag.source_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "risk_flag")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "status": self.status,
            "rationale": self.rationale,
            "source_refs": list(self.source_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class FrontDeskIntentBundle:
    """Formal product-aware FrontDesk output consumed by integrations."""

    session_id: str
    intent_bundle_ref: str
    generic_refs: IntentGenericRefs
    product_context: ProductContextSnapshot = field(default_factory=ProductContextSnapshot)
    slot_values: list[SlotValue] = field(default_factory=list)
    product_hypotheses: list[ProductHypothesis] = field(default_factory=list)
    risk_flags: list[RiskFlag] = field(default_factory=list)
    missing_blocking_slots: list[str] = field(default_factory=list)
    readiness: IntentBundleReadiness = IntentBundleReadiness.GENERIC_COMPILE_ONLY
    clarification_questions: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = FRONTDESK_INTENT_BUNDLE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "frontdesk_intent_bundle",
            {
                "schema_version",
                "session_id",
                "intent_bundle_ref",
                "generic_refs",
                "product_context",
                "slot_values",
                "product_hypotheses",
                "risk_flags",
                "missing_blocking_slots",
                "readiness",
                "clarification_questions",
                "evidence_refs",
                "bundle_hash",
            },
        )
        bundle = cls(
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_intent_bundle.session_id"),
            intent_bundle_ref=validate_ref(data.get("intent_bundle_ref"), "frontdesk_intent_bundle.intent_bundle_ref"),
            generic_refs=IntentGenericRefs.from_dict(
                require_mapping(data.get("generic_refs"), "frontdesk_intent_bundle.generic_refs")
            ),
            product_context=ProductContextSnapshot.from_dict(
                require_mapping(data.get("product_context", {}), "frontdesk_intent_bundle.product_context")
            ),
            slot_values=[
                SlotValue.from_dict(require_mapping(child, "frontdesk_intent_bundle.slot_values[]"))
                for child in data.get("slot_values", [])
            ],
            product_hypotheses=[
                ProductHypothesis.from_dict(require_mapping(child, "frontdesk_intent_bundle.product_hypotheses[]"))
                for child in data.get("product_hypotheses", [])
            ],
            risk_flags=[
                RiskFlag.from_dict(require_mapping(child, "frontdesk_intent_bundle.risk_flags[]"))
                for child in data.get("risk_flags", [])
            ],
            missing_blocking_slots=require_str_list(
                data.get("missing_blocking_slots", []),
                "frontdesk_intent_bundle.missing_blocking_slots",
            ),
            readiness=require_enum(
                data.get("readiness", IntentBundleReadiness.GENERIC_COMPILE_ONLY.value),
                IntentBundleReadiness,
                "frontdesk_intent_bundle.readiness",
            ),
            clarification_questions=require_str_list(
                data.get("clarification_questions", []),
                "frontdesk_intent_bundle.clarification_questions",
            ),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "frontdesk_intent_bundle.evidence_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", FRONTDESK_INTENT_BUNDLE_SCHEMA_VERSION),
                "frontdesk_intent_bundle.schema_version",
            ),
        )
        bundle.validate()
        if data.get("bundle_hash") not in {None, bundle.bundle_hash}:
            raise ContractValidationError("frontdesk_intent_bundle.bundle_hash does not match payload")
        return bundle

    @property
    def bundle_hash(self) -> str:
        return stable_json_hash(self.to_dict_without_hash())

    def slot_value(self, slot_id: str) -> SlotValue | None:
        for slot in self.slot_values:
            if slot.slot_id == slot_id:
                return slot
        return None

    def validate(self) -> None:
        if self.schema_version != FRONTDESK_INTENT_BUNDLE_SCHEMA_VERSION:
            raise ContractValidationError("frontdesk_intent_bundle.schema_version is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_intent_bundle.session_id")
        validate_ref(self.intent_bundle_ref, "frontdesk_intent_bundle.intent_bundle_ref")
        self.generic_refs.validate()
        self.product_context.validate()
        slot_ids = [slot.slot_id for slot in self.slot_values]
        _require_unique(slot_ids, "frontdesk_intent_bundle.slot_values[].slot_id")
        for slot in self.slot_values:
            slot.validate()
        for hypothesis in self.product_hypotheses:
            hypothesis.validate()
        for flag in self.risk_flags:
            flag.validate()
        require_str_list(self.missing_blocking_slots, "frontdesk_intent_bundle.missing_blocking_slots")
        missing_set = set(self.missing_blocking_slots)
        confirmed_missing_conflicts = [
            slot.slot_id
            for slot in self.slot_values
            if slot.slot_id in missing_set
            and slot.status in {SlotValueStatus.CONFIRMED, SlotValueStatus.INFERRED, SlotValueStatus.ASSUMED}
        ]
        if confirmed_missing_conflicts:
            raise ContractValidationError(
                f"missing_blocking_slots contains resolved slot(s): {sorted(confirmed_missing_conflicts)}"
            )
        readiness = require_enum(self.readiness, IntentBundleReadiness, "frontdesk_intent_bundle.readiness")
        if readiness == IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE and self.missing_blocking_slots:
            raise ContractValidationError("ready_for_product_compile requires no missing blocking slots")
        if readiness == IntentBundleReadiness.NEEDS_CLARIFICATION and not (
            self.missing_blocking_slots or self.clarification_questions
        ):
            raise ContractValidationError("needs_clarification requires missing slots or clarification questions")
        require_str_list(self.clarification_questions, "frontdesk_intent_bundle.clarification_questions")
        _validate_ref_list(self.evidence_refs, "frontdesk_intent_bundle.evidence_refs")
        payload = self.to_dict_without_hash()
        payload["generic_ref_values"] = self.generic_refs.refs
        del payload["generic_refs"]
        assert_refs_only_payload(payload, "frontdesk_intent_bundle")

    def to_dict_without_hash(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "intent_bundle_ref": self.intent_bundle_ref,
            "generic_refs": self.generic_refs.to_dict(),
            "product_context": self.product_context.to_dict(),
            "slot_values": [item.to_dict() for item in self.slot_values],
            "product_hypotheses": [item.to_dict() for item in self.product_hypotheses],
            "risk_flags": [item.to_dict() for item in self.risk_flags],
            "missing_blocking_slots": list(self.missing_blocking_slots),
            "readiness": self.readiness.value,
            "clarification_questions": list(self.clarification_questions),
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = self.to_dict_without_hash()
        payload["bundle_hash"] = self.bundle_hash
        return payload


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


__all__ = [
    "FRONTDESK_INTENT_BUNDLE_SCHEMA_VERSION",
    "FrontDeskIntentBundle",
    "IntentBundleReadiness",
    "IntentGenericRefs",
    "ProductContextSnapshot",
    "ProductHypothesis",
    "RiskFlag",
    "SlotValue",
    "SlotValueStatus",
]
