"""LLM-assisted FrontDesk elicitation boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..contracts import ContractValidationError, ensure_json_value, require_bool, require_mapping, require_non_empty_str
from .schema import MissionBrief, MissionSemanticLock, reject_raw_authoring_fields


class FrontDeskLLMClient(Protocol):
    """Structured-output client used by FrontDesk authoring nodes."""

    def complete_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ClarificationQuestion:
    """One high-value FrontDesk clarification question."""

    question_id: str
    text: str
    reason: str
    blocks_freeze: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ClarificationQuestion":
        data = require_mapping(payload, "clarification_question")
        _reject_unknown(data, {"question_id", "text", "reason", "blocks_freeze"}, "clarification_question")
        return cls(
            question_id=require_non_empty_str(data.get("question_id"), "clarification_question.question_id"),
            text=require_non_empty_str(data.get("text"), "clarification_question.text"),
            reason=require_non_empty_str(data.get("reason"), "clarification_question.reason"),
            blocks_freeze=require_bool(data.get("blocks_freeze", True), "clarification_question.blocks_freeze"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "text": self.text,
            "reason": self.reason,
            "blocks_freeze": self.blocks_freeze,
        }


@dataclass(frozen=True)
class ElicitationResult:
    """Validated elicitor output."""

    session_id: str
    readiness: str
    semantic_lock: MissionSemanticLock
    mission_brief: MissionBrief
    questions: list[ClarificationQuestion] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ElicitationResult":
        data = require_mapping(payload, "elicitation_result")
        _reject_unknown(
            data,
            {"session_id", "readiness", "semantic_lock", "mission_brief", "questions"},
            "elicitation_result",
        )
        reject_raw_authoring_fields(data, "elicitation_result")
        readiness = require_non_empty_str(data.get("readiness"), "elicitation_result.readiness")
        if readiness not in {"needs_clarification", "draft_ready"}:
            raise ContractValidationError("elicitation_result.readiness is invalid")
        result = cls(
            session_id=require_non_empty_str(data.get("session_id"), "elicitation_result.session_id"),
            readiness=readiness,
            semantic_lock=MissionSemanticLock.from_dict(require_mapping(data.get("semantic_lock"), "semantic_lock")),
            mission_brief=MissionBrief.from_dict(require_mapping(data.get("mission_brief"), "mission_brief")),
            questions=[
                ClarificationQuestion.from_dict(require_mapping(child, "elicitation_result.questions[]"))
                for child in data.get("questions", [])
            ],
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.session_id, "elicitation_result.session_id")
        if self.semantic_lock.session_id != self.session_id or self.mission_brief.session_id != self.session_id:
            raise ContractValidationError("elicitation_result session ids do not match")
        if self.readiness == "needs_clarification" and not self.questions:
            raise ContractValidationError("elicitation_result needs at least one clarification question")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "session_id": self.session_id,
            "readiness": self.readiness,
            "semantic_lock": self.semantic_lock.to_dict(),
            "mission_brief": self.mission_brief.to_dict(),
            "questions": [question.to_dict() for question in self.questions],
        }


class RequirementsElicitor:
    """Schema-validating elicitor wrapper."""

    def elicit(self, *, session_id: str, user_summary: str, client: FrontDeskLLMClient) -> ElicitationResult:
        payload = {
            "node": "requirements_elicitor",
            "session_id": session_id,
            "user_summary": user_summary,
            "contract": "Return ElicitationResult JSON only. Do not approve or freeze.",
        }
        response = ensure_json_value(client.complete_json(payload), "elicitor.response")
        return ElicitationResult.from_dict(require_mapping(response, "elicitor.response"))


class ScriptedFrontDeskLLMClient:
    """Deterministic test client for FrontDesk LLM node contracts."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)

    def complete_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._responses:
            raise ContractValidationError("scripted FrontDesk client has no response")
        return self._responses.pop(0)


def _reject_unknown(data: dict[str, Any], allowed: set[str], field_name: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise ContractValidationError(f"{field_name} contains unknown field(s): {', '.join(extra)}")
