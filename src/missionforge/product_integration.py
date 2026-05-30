"""Generic product integration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .frontdesk.inquiry_profile import ProductInquiryProfile
from .frontdesk.intent_bundle import FrontDeskIntentBundle


PRODUCT_COMPILE_RESULT_SCHEMA_VERSION = "missionforge.product_compile_result.v1"
PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION = "missionforge.product_clarification_request.v1"
PRODUCT_ARTIFACT_REFS_SCHEMA_VERSION = "missionforge.product_artifact_refs.v1"


class ProductCompileStatus(StrEnum):
    """Product integration compilation status."""

    COMPILED = "compiled"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    FAILED_CLOSED = "failed_closed"


@dataclass(frozen=True)
class ProductClarificationQuestion:
    """One product integration clarification question."""

    question_id: str
    slot_id: str
    question: str
    choices: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_clarification_question",
            {"question_id", "slot_id", "question", "choices", "source_refs"},
        )
        item = cls(
            question_id=require_non_empty_str(
                data.get("question_id"),
                "product_clarification_question.question_id",
            ),
            slot_id=require_non_empty_str(data.get("slot_id"), "product_clarification_question.slot_id"),
            question=require_non_empty_str(data.get("question"), "product_clarification_question.question"),
            choices=require_str_list(data.get("choices", []), "product_clarification_question.choices"),
            source_refs=require_str_list(data.get("source_refs", []), "product_clarification_question.source_refs"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        require_non_empty_str(self.question_id, "product_clarification_question.question_id")
        require_non_empty_str(self.slot_id, "product_clarification_question.slot_id")
        require_non_empty_str(self.question, "product_clarification_question.question")
        require_str_list(self.choices, "product_clarification_question.choices")
        _validate_ref_list(self.source_refs, "product_clarification_question.source_refs")
        assert_refs_only_payload(self.to_dict(), "product_clarification_question")

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "slot_id": self.slot_id,
            "question": self.question,
            "choices": list(self.choices),
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class ProductClarificationRequest:
    """Structured clarification request returned by a product compiler."""

    product_id: str
    intent_bundle_ref: str
    missing_slot_ids: list[str] = field(default_factory=list)
    questions: list[ProductClarificationQuestion] = field(default_factory=list)
    reason: str = ""
    schema_version: str = PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_clarification_request",
            {
                "schema_version",
                "product_id",
                "intent_bundle_ref",
                "missing_slot_ids",
                "questions",
                "reason",
            },
        )
        item = cls(
            product_id=require_non_empty_str(data.get("product_id"), "product_clarification_request.product_id"),
            intent_bundle_ref=validate_ref(
                data.get("intent_bundle_ref"),
                "product_clarification_request.intent_bundle_ref",
            ),
            missing_slot_ids=require_str_list(
                data.get("missing_slot_ids", []),
                "product_clarification_request.missing_slot_ids",
            ),
            questions=[
                ProductClarificationQuestion.from_dict(
                    require_mapping(child, "product_clarification_request.questions[]")
                )
                for child in data.get("questions", [])
            ],
            reason=str(data.get("reason", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION),
                "product_clarification_request.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.schema_version != PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION:
            raise ContractValidationError("product_clarification_request.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_clarification_request.product_id")
        validate_ref(self.intent_bundle_ref, "product_clarification_request.intent_bundle_ref")
        require_str_list(self.missing_slot_ids, "product_clarification_request.missing_slot_ids")
        for question in self.questions:
            question.validate()
        if not self.missing_slot_ids and not self.questions:
            raise ContractValidationError("product_clarification_request requires missing slots or questions")
        assert_refs_only_payload(self.to_dict(), "product_clarification_request")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "intent_bundle_ref": self.intent_bundle_ref,
            "missing_slot_ids": list(self.missing_slot_ids),
            "questions": [question.to_dict() for question in self.questions],
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProductArtifactRefs:
    """Refs emitted by a product integration."""

    product_request_ref: str = ""
    product_contract_ref: str = ""
    mission_ir_ref: str = ""
    frozen_contract_ref: str = ""
    product_gate_spec_ref: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    schema_version: str = PRODUCT_ARTIFACT_REFS_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_artifact_refs",
            {
                "schema_version",
                "product_request_ref",
                "product_contract_ref",
                "mission_ir_ref",
                "frozen_contract_ref",
                "product_gate_spec_ref",
                "evidence_refs",
            },
        )
        item = cls(
            product_request_ref=str(data.get("product_request_ref", "")),
            product_contract_ref=str(data.get("product_contract_ref", "")),
            mission_ir_ref=str(data.get("mission_ir_ref", "")),
            frozen_contract_ref=str(data.get("frozen_contract_ref", "")),
            product_gate_spec_ref=str(data.get("product_gate_spec_ref", "")),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "product_artifact_refs.evidence_refs"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_ARTIFACT_REFS_SCHEMA_VERSION),
                "product_artifact_refs.schema_version",
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.schema_version != PRODUCT_ARTIFACT_REFS_SCHEMA_VERSION:
            raise ContractValidationError("product_artifact_refs.schema_version is unsupported")
        for name, ref in self.to_dict_without_validation().items():
            if name in {"schema_version", "evidence_refs"}:
                continue
            if ref:
                validate_ref(ref, f"product_artifact_refs.{name}")
        _validate_ref_list(self.evidence_refs, "product_artifact_refs.evidence_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "product_artifact_refs")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_request_ref": self.product_request_ref,
            "product_contract_ref": self.product_contract_ref,
            "mission_ir_ref": self.mission_ir_ref,
            "frozen_contract_ref": self.frozen_contract_ref,
            "product_gate_spec_ref": self.product_gate_spec_ref,
            "evidence_refs": list(self.evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class ProductCompileResult:
    """Compiled product artifacts or a fail-closed clarification envelope."""

    product_id: str
    status: ProductCompileStatus
    intent_bundle_ref: str
    product_request_ref: str = ""
    product_contract_ref: str = ""
    mission_ir_ref: str = ""
    frozen_contract_ref: str = ""
    product_gate_spec_ref: str = ""
    missing_slot_ids: list[str] = field(default_factory=list)
    clarification_questions: list[ProductClarificationQuestion] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    reason: str = ""
    schema_version: str = PRODUCT_COMPILE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_compile_result",
            {
                "schema_version",
                "product_id",
                "status",
                "intent_bundle_ref",
                "product_request_ref",
                "product_contract_ref",
                "mission_ir_ref",
                "frozen_contract_ref",
                "product_gate_spec_ref",
                "missing_slot_ids",
                "clarification_questions",
                "evidence_refs",
                "reason",
            },
        )
        result = cls(
            product_id=require_non_empty_str(data.get("product_id"), "product_compile_result.product_id"),
            status=require_enum(data.get("status"), ProductCompileStatus, "product_compile_result.status"),
            intent_bundle_ref=validate_ref(data.get("intent_bundle_ref"), "product_compile_result.intent_bundle_ref"),
            product_request_ref=str(data.get("product_request_ref", "")),
            product_contract_ref=str(data.get("product_contract_ref", "")),
            mission_ir_ref=str(data.get("mission_ir_ref", "")),
            frozen_contract_ref=str(data.get("frozen_contract_ref", "")),
            product_gate_spec_ref=str(data.get("product_gate_spec_ref", "")),
            missing_slot_ids=require_str_list(data.get("missing_slot_ids", []), "product_compile_result.missing_slot_ids"),
            clarification_questions=[
                ProductClarificationQuestion.from_dict(
                    require_mapping(child, "product_compile_result.clarification_questions[]")
                )
                for child in data.get("clarification_questions", [])
            ],
            evidence_refs=require_str_list(data.get("evidence_refs", []), "product_compile_result.evidence_refs"),
            reason=str(data.get("reason", "")),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_COMPILE_RESULT_SCHEMA_VERSION),
                "product_compile_result.schema_version",
            ),
        )
        result.validate()
        return result

    @property
    def artifact_refs(self) -> ProductArtifactRefs:
        return ProductArtifactRefs(
            product_request_ref=self.product_request_ref,
            product_contract_ref=self.product_contract_ref,
            mission_ir_ref=self.mission_ir_ref,
            frozen_contract_ref=self.frozen_contract_ref,
            product_gate_spec_ref=self.product_gate_spec_ref,
            evidence_refs=list(self.evidence_refs),
        )

    @property
    def clarification_request(self) -> ProductClarificationRequest | None:
        if self.status != ProductCompileStatus.NEEDS_CLARIFICATION:
            return None
        return ProductClarificationRequest(
            product_id=self.product_id,
            intent_bundle_ref=self.intent_bundle_ref,
            missing_slot_ids=list(self.missing_slot_ids),
            questions=list(self.clarification_questions),
            reason=self.reason,
        )

    def validate(self) -> None:
        if self.schema_version != PRODUCT_COMPILE_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("product_compile_result.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_compile_result.product_id")
        status = require_enum(self.status, ProductCompileStatus, "product_compile_result.status")
        validate_ref(self.intent_bundle_ref, "product_compile_result.intent_bundle_ref")
        for name in (
            "product_request_ref",
            "product_contract_ref",
            "mission_ir_ref",
            "frozen_contract_ref",
            "product_gate_spec_ref",
        ):
            ref = getattr(self, name)
            if ref:
                validate_ref(ref, f"product_compile_result.{name}")
        require_str_list(self.missing_slot_ids, "product_compile_result.missing_slot_ids")
        for question in self.clarification_questions:
            question.validate()
        _validate_ref_list(self.evidence_refs, "product_compile_result.evidence_refs")
        if status == ProductCompileStatus.COMPILED and not self.mission_ir_ref:
            raise ContractValidationError("compiled product_compile_result requires mission_ir_ref")
        if status == ProductCompileStatus.NEEDS_CLARIFICATION and not (
            self.missing_slot_ids or self.clarification_questions
        ):
            raise ContractValidationError("needs_clarification product_compile_result requires missing slots or questions")
        assert_refs_only_payload(self.to_dict(), "product_compile_result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "status": self.status.value,
            "intent_bundle_ref": self.intent_bundle_ref,
            "product_request_ref": self.product_request_ref,
            "product_contract_ref": self.product_contract_ref,
            "mission_ir_ref": self.mission_ir_ref,
            "frozen_contract_ref": self.frozen_contract_ref,
            "product_gate_spec_ref": self.product_gate_spec_ref,
            "missing_slot_ids": list(self.missing_slot_ids),
            "clarification_questions": [question.to_dict() for question in self.clarification_questions],
            "evidence_refs": list(self.evidence_refs),
            "reason": self.reason,
        }


@runtime_checkable
class ProductIntegration(Protocol):
    """Protocol implemented by product packages outside MissionForge core."""

    product_id: str

    def inquiry_profile(self) -> ProductInquiryProfile:
        """Return authoring-time product inquiry metadata."""

    def compile_intent(
        self,
        bundle: FrontDeskIntentBundle,
        *,
        workspace: str | Path = ".",
    ) -> ProductCompileResult:
        """Compile a FrontDesk intent bundle into product artifacts."""


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


__all__ = [
    "PRODUCT_ARTIFACT_REFS_SCHEMA_VERSION",
    "PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION",
    "PRODUCT_COMPILE_RESULT_SCHEMA_VERSION",
    "ProductArtifactRefs",
    "ProductClarificationQuestion",
    "ProductClarificationRequest",
    "ProductCompileResult",
    "ProductCompileStatus",
    "ProductIntegration",
]
