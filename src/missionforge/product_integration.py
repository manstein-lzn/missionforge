"""Generic product integration contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Self, runtime_checkable

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    optional_ref,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str,
    require_str_list,
    validate_ref,
)


PRODUCT_TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION = "missionforge.product_task_contract_compile_result.v1"
PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION = "missionforge.product_clarification_request.v1"


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
            reason=require_str(data.get("reason", ""), "product_clarification_request.reason"),
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
class ProductTaskContractCompileResult:
    """Compiled TaskContract refs or a fail-closed clarification envelope."""

    product_id: str
    status: ProductCompileStatus
    intent_bundle_ref: str
    run_workspace_ref: str = ""
    task_contract_ref: str = ""
    workspace_policy_ref: str = ""
    permission_manifest_ref: str = ""
    product_request_ref: str = ""
    product_contract_ref: str = ""
    hard_check_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    missing_slot_ids: list[str] = field(default_factory=list)
    clarification_questions: list[ProductClarificationQuestion] = field(default_factory=list)
    reason: str = ""
    schema_version: str = PRODUCT_TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _strict_mapping(
            payload,
            "product_task_contract_compile_result",
            {
                "schema_version",
                "product_id",
                "status",
                "intent_bundle_ref",
                "run_workspace_ref",
                "task_contract_ref",
                "workspace_policy_ref",
                "permission_manifest_ref",
                "product_request_ref",
                "product_contract_ref",
                "hard_check_refs",
                "evidence_refs",
                "missing_slot_ids",
                "clarification_questions",
                "reason",
            },
        )
        result = cls(
            product_id=require_non_empty_str(
                data.get("product_id"),
                "product_task_contract_compile_result.product_id",
            ),
            status=require_enum(data.get("status"), ProductCompileStatus, "product_task_contract_compile_result.status"),
            intent_bundle_ref=validate_ref(
                data.get("intent_bundle_ref"),
                "product_task_contract_compile_result.intent_bundle_ref",
            ),
            run_workspace_ref=optional_ref(data.get("run_workspace_ref", ""), "product_task_contract_compile_result.run_workspace_ref"),
            task_contract_ref=optional_ref(data.get("task_contract_ref", ""), "product_task_contract_compile_result.task_contract_ref"),
            workspace_policy_ref=optional_ref(data.get("workspace_policy_ref", ""), "product_task_contract_compile_result.workspace_policy_ref"),
            permission_manifest_ref=optional_ref(data.get("permission_manifest_ref", ""), "product_task_contract_compile_result.permission_manifest_ref"),
            product_request_ref=optional_ref(data.get("product_request_ref", ""), "product_task_contract_compile_result.product_request_ref"),
            product_contract_ref=optional_ref(data.get("product_contract_ref", ""), "product_task_contract_compile_result.product_contract_ref"),
            hard_check_refs=require_str_list(
                data.get("hard_check_refs", []),
                "product_task_contract_compile_result.hard_check_refs",
            ),
            evidence_refs=require_str_list(
                data.get("evidence_refs", []),
                "product_task_contract_compile_result.evidence_refs",
            ),
            missing_slot_ids=require_str_list(
                data.get("missing_slot_ids", []),
                "product_task_contract_compile_result.missing_slot_ids",
            ),
            clarification_questions=[
                ProductClarificationQuestion.from_dict(
                    require_mapping(child, "product_task_contract_compile_result.clarification_questions[]")
                )
                for child in data.get("clarification_questions", [])
            ],
            reason=require_str(data.get("reason", ""), "product_task_contract_compile_result.reason"),
            schema_version=require_non_empty_str(
                data.get("schema_version", PRODUCT_TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION),
                "product_task_contract_compile_result.schema_version",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != PRODUCT_TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("product_task_contract_compile_result.schema_version is unsupported")
        require_non_empty_str(self.product_id, "product_task_contract_compile_result.product_id")
        status = require_enum(self.status, ProductCompileStatus, "product_task_contract_compile_result.status")
        validate_ref(self.intent_bundle_ref, "product_task_contract_compile_result.intent_bundle_ref")
        for name in (
            "run_workspace_ref",
            "task_contract_ref",
            "workspace_policy_ref",
            "permission_manifest_ref",
            "product_request_ref",
            "product_contract_ref",
        ):
            ref = getattr(self, name)
            if ref:
                validate_ref(ref, f"product_task_contract_compile_result.{name}")
        _validate_ref_list(self.hard_check_refs, "product_task_contract_compile_result.hard_check_refs")
        _validate_ref_list(self.evidence_refs, "product_task_contract_compile_result.evidence_refs")
        require_str_list(self.missing_slot_ids, "product_task_contract_compile_result.missing_slot_ids")
        for question in self.clarification_questions:
            question.validate()
        if self.run_workspace_ref:
            for name in (
                "task_contract_ref",
                "workspace_policy_ref",
                "permission_manifest_ref",
                "product_request_ref",
                "product_contract_ref",
            ):
                ref = getattr(self, name)
                if ref:
                    _validate_ref_under_root(
                        ref,
                        self.run_workspace_ref,
                        f"product_task_contract_compile_result.{name}",
                    )
        if status == ProductCompileStatus.COMPILED and not (
            self.run_workspace_ref
            and self.task_contract_ref
            and self.workspace_policy_ref
            and self.permission_manifest_ref
            and self.product_request_ref
            and self.product_contract_ref
        ):
            raise ContractValidationError("compiled product_task_contract_compile_result requires task contract refs")
        if status == ProductCompileStatus.NEEDS_CLARIFICATION and not (
            self.missing_slot_ids or self.clarification_questions
        ):
            raise ContractValidationError(
                "needs_clarification product_task_contract_compile_result requires missing slots or questions"
            )
        assert_refs_only_payload(self.to_dict(), "product_task_contract_compile_result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product_id": self.product_id,
            "status": self.status.value,
            "intent_bundle_ref": self.intent_bundle_ref,
            "run_workspace_ref": self.run_workspace_ref,
            "task_contract_ref": self.task_contract_ref,
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "product_request_ref": self.product_request_ref,
            "product_contract_ref": self.product_contract_ref,
            "hard_check_refs": list(self.hard_check_refs),
            "evidence_refs": list(self.evidence_refs),
            "missing_slot_ids": list(self.missing_slot_ids),
            "clarification_questions": [question.to_dict() for question in self.clarification_questions],
            "reason": self.reason,
        }


@runtime_checkable
class ProductIntegration(Protocol):
    """Protocol for products that compile FrontDesk intent into TaskContract refs."""

    product_id: str

    def inquiry_profile(self) -> Mapping[str, Any]:
        """Return authoring-time product inquiry metadata."""
        ...

    def compile_task_contract(
        self,
        bundle: Mapping[str, Any],
        *,
        workspace: str | Path = ".",
    ) -> ProductTaskContractCompileResult:
        """Compile a FrontDesk intent bundle into TaskContract runtime refs."""
        ...


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


def _validate_ref_under_root(ref: str, root_ref: str, field_name: str) -> None:
    safe_ref = validate_ref(ref, field_name)
    safe_root = validate_ref(root_ref, "product_task_contract_compile_result.run_workspace_ref")
    if safe_ref != safe_root and not safe_ref.startswith(f"{safe_root}/"):
        raise ContractValidationError(f"{field_name} must be under run_workspace_ref")


__all__ = [
    "PRODUCT_CLARIFICATION_REQUEST_SCHEMA_VERSION",
    "PRODUCT_TASK_CONTRACT_COMPILE_RESULT_SCHEMA_VERSION",
    "ProductClarificationQuestion",
    "ProductClarificationRequest",
    "ProductCompileStatus",
    "ProductTaskContractCompileResult",
    "ProductIntegration",
]
