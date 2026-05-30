"""LLM NeedGriller contract for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError
from .spec_grill_schema import CoreNeedBrief, DecisionTree, NeedGrillingReport
from .state import (
    CONVERSATION_REF,
    CORE_NEED_BRIEF_REF,
    DECISION_TREE_REF,
    NEED_GRILLING_REPORT_REF,
    SOURCE_ADMISSION_REPORT_REF,
    WORKSPACE_FACTS_REF,
    FrontDeskAuthoringSession,
)
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class NeedGrillResult:
    """Artifacts written by an LLM-backed NeedGriller node."""

    decision_tree: DecisionTree
    report: NeedGrillingReport
    core_need_brief: CoreNeedBrief | None = None

    @property
    def refs(self) -> list[str]:
        refs = [DECISION_TREE_REF, NEED_GRILLING_REPORT_REF]
        if self.core_need_brief is not None:
            refs.append(CORE_NEED_BRIEF_REF)
        return refs

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_tree": self.decision_tree.to_dict(),
            "need_grilling_report": self.report.to_dict(),
            "core_need_brief": self.core_need_brief.to_dict() if self.core_need_brief else None,
            "refs": list(self.refs),
        }


def need_griller_node_template(session_id: str) -> dict[str, Any]:
    """Return the static role and output template for the NeedGriller AI node."""

    return {
        "node": "frontdesk.need_griller",
        "session_id": session_id,
        "role": (
            "Act as a restrained requirements interviewer. Infer the user's real pain, "
            "ask only high-value clarification questions, and return structured FrontDesk artifacts."
        ),
        "visible_refs": [CONVERSATION_REF, WORKSPACE_FACTS_REF, SOURCE_ADMISSION_REPORT_REF],
        "expected_outputs": [DECISION_TREE_REF, NEED_GRILLING_REPORT_REF],
        "optional_outputs": [CORE_NEED_BRIEF_REF],
        "output_contract": {
            "decision_tree_ref": DECISION_TREE_REF,
            "need_grilling_report_ref": NEED_GRILLING_REPORT_REF,
            "core_need_brief_ref": CORE_NEED_BRIEF_REF,
        },
        "rules": [
            "Do not copy raw conversation into runtime truth.",
            "Do not approve, freeze, run, or verify the mission.",
            "Do not invent product-specific compiler behavior.",
            "Use refs and structured fields only.",
        ],
    }


class NeedGriller:
    """Service boundary for an LLM-backed NeedGriller node."""

    def grill(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
        max_questions: int = 1,
    ) -> NeedGrillResult:
        session.validate()
        raise ContractValidationError(
            "NeedGriller requires an LLM/PiWorker-authored output; deterministic need grilling has been removed"
        )


def grill_frontdesk_session(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
    max_questions: int = 1,
) -> NeedGrillResult:
    return NeedGriller().grill(session=session, workspace=workspace, max_questions=max_questions)


__all__ = ["NeedGrillResult", "NeedGriller", "grill_frontdesk_session", "need_griller_node_template"]
