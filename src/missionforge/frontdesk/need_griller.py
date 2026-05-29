"""Active NeedGriller for FrontDesk spec-grill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import ContractValidationError, require_non_empty_str
from .scout import _conversation_text
from .spec_grill_schema import (
    CoreNeedBrief,
    DecisionNode,
    DecisionOption,
    DecisionStatus,
    DecisionTree,
    DomainLanguage,
    GrillingQuestion,
    NeedGrillingReadiness,
    NeedGrillingReport,
    QuestionAnswerType,
    WorkspaceFacts,
)
from .state import (
    CONVERSATION_REF,
    CORE_NEED_BRIEF_REF,
    DECISION_TREE_REF,
    DOMAIN_LANGUAGE_REF,
    NEED_GRILLING_REPORT_REF,
    WORKSPACE_FACTS_REF,
    FrontDeskAuthoringSession,
)
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class NeedGrillResult:
    """Artifacts written by NeedGriller."""

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


class NeedGriller:
    """Deterministic active griller used by offline FrontDesk tests."""

    def grill(
        self,
        *,
        session: FrontDeskAuthoringSession,
        workspace: FrontDeskWorkspace,
        max_questions: int = 1,
    ) -> NeedGrillResult:
        session.validate()
        if max_questions < 1:
            raise ContractValidationError("need_griller.max_questions must be >= 1")
        text = _conversation_text(workspace, session.conversation_ref)
        facts = _load_workspace_facts(workspace, session.session_id)
        domain = _load_domain_language(workspace, session.session_id)
        ready = _has_core_need(text)
        decision = _build_decision(text, ready)
        tree = DecisionTree(session_id=session.session_id, decisions=[decision])

        if ready:
            brief = _core_need_brief(session.session_id, text, domain)
            report = NeedGrillingReport(
                session_id=session.session_id,
                readiness=NeedGrillingReadiness.CORE_NEED_READY,
                observations=[_observation(text)],
                inferences=[_inference(text)],
                confirmed_requirements=list(brief.success_signals),
                open_decision_ids=tree.open_blocking_decision_ids,
                next_question=None,
                decision_tree_ref=DECISION_TREE_REF,
                core_need_brief_ref=CORE_NEED_BRIEF_REF,
            )
            workspace.write_json(DECISION_TREE_REF, tree.to_dict())
            workspace.write_json(CORE_NEED_BRIEF_REF, brief.to_dict())
            workspace.write_json(NEED_GRILLING_REPORT_REF, report.to_dict())
            return NeedGrillResult(decision_tree=tree, report=report, core_need_brief=brief)

        question = _next_question(text, facts, domain)
        report = NeedGrillingReport(
            session_id=session.session_id,
            readiness=NeedGrillingReadiness.NEEDS_CLARIFICATION,
            observations=[_observation(text)],
            inferences=[question.inference],
            confirmed_requirements=[],
            open_decision_ids=tree.open_blocking_decision_ids,
            next_question=question,
            decision_tree_ref=DECISION_TREE_REF,
            core_need_brief_ref="",
        )
        workspace.write_json(DECISION_TREE_REF, tree.to_dict())
        workspace.write_json(NEED_GRILLING_REPORT_REF, report.to_dict())
        return NeedGrillResult(decision_tree=tree, report=report)


def _load_workspace_facts(workspace: FrontDeskWorkspace, session_id: str) -> WorkspaceFacts:
    if workspace.exists(WORKSPACE_FACTS_REF):
        return WorkspaceFacts.from_dict(workspace.read_json(WORKSPACE_FACTS_REF))
    return WorkspaceFacts(session_id=session_id)


def _load_domain_language(workspace: FrontDeskWorkspace, session_id: str) -> DomainLanguage:
    if workspace.exists(DOMAIN_LANGUAGE_REF):
        return DomainLanguage.from_dict(workspace.read_json(DOMAIN_LANGUAGE_REF))
    return DomainLanguage(session_id=session_id)


def _has_core_need(text: str) -> bool:
    lowered = text.lower()
    if not lowered.strip():
        return False
    output_signal = any(
        token in lowered
        for token in (
            "expected output",
            "output is",
            "write ",
            "create ",
            "build ",
            "produce ",
            "deliver",
            "docs/",
            "package/",
            ".md",
        )
    )
    success_signal = any(token in lowered for token in ("success", "verify", "validator", "exists", "passes"))
    pain_signal = any(
        token in lowered
        for token in (
            "pain",
            "problem",
            "need",
            "goal",
            "want",
            "prevent",
            "avoid",
            "privacy",
            "performance",
        )
    )
    implementation_only = any(token in lowered for token in ("use rust", "rust implementation", "rewrite in rust"))
    if implementation_only and not (output_signal and (success_signal or pain_signal)):
        return False
    return output_signal and (success_signal or pain_signal or len(lowered.split()) >= 8)


def _build_decision(text: str, ready: bool) -> DecisionNode:
    status = DecisionStatus.CONFIRMED if ready else DecisionStatus.OPEN
    hypothesis = _inference(text)
    return DecisionNode(
        decision_id="D-core-need",
        topic="core_need",
        status=status,
        current_hypothesis=hypothesis,
        options=[
            DecisionOption(option_id="O-authoring-clarity", summary="Need better authoring clarity."),
            DecisionOption(option_id="O-runtime-performance", summary="Need runtime performance or packaging."),
            DecisionOption(option_id="O-boundary-protection", summary="Need to protect generic core boundaries."),
        ],
        blocking=True,
        source_refs=[CONVERSATION_REF],
        chosen_option_id="O-authoring-clarity" if ready else "",
    )


def _core_need_brief(session_id: str, text: str, domain: DomainLanguage) -> CoreNeedBrief:
    expected_artifact = _infer_expected_artifact(text)
    constraints = list(domain.risk_terms)
    if "Rust" in domain.implementation_terms:
        constraints.append("Treat Rust as an implementation preference until performance or packaging scope is proven.")
    return CoreNeedBrief(
        session_id=require_non_empty_str(session_id, "core_need_brief.session_id"),
        core_pain=_core_pain(text),
        target_users=["missionforge_user"],
        usage_moment="Before MissionRuntime starts.",
        desired_outcome=f"Produce {expected_artifact} as a verifiable MissionForge artifact.",
        success_signals=[f"{expected_artifact} exists."],
        constraints=constraints,
        non_goals=["Do not use raw conversation as runtime task truth."],
        source_refs=[CONVERSATION_REF],
    )


def _next_question(text: str, facts: WorkspaceFacts, domain: DomainLanguage) -> GrillingQuestion:
    lowered = text.lower()
    answered = " ".join(facts.questions_answered_by_workspace).lower()
    if "profile" in lowered and "profiles are available" in answered:
        inference = "The available profile list can be discovered from the workspace, so the open issue is the user goal, not profile inventory."
        recommended = "Confirm the outcome and verification signal instead of asking which profiles exist."
        question = "What observable output should prove this mission succeeded?"
        why = "A known profile catalog does not tell FrontDesk what success should mean for this user."
    elif any(term.lower() == "rust" for term in domain.implementation_terms) or "rust" in lowered:
        inference = "The Rust request is likely an implementation hypothesis rather than the complete mission."
        recommended = "Start from the pain: performance, packaging, protecting core assets, or preventing task-specific pollution."
        question = "Is your main concern performance, packaging, protecting core assets from edits, or preventing task-specific MissionForge pollution?"
        why = "The answer decides whether the first mission should plan a native core, a packaging boundary, or a profile/integration boundary."
    elif "privacy" in lowered or "secret" in lowered or "credential" in lowered:
        inference = "The user has a privacy or raw-data boundary concern that needs a verifier-visible constraint."
        recommended = "Treat privacy as a blocking constraint and keep raw material provenance-only."
        question = "Which data must stay provenance-only and never enter MissionIR, work units, metrics, or runtime artifacts?"
        why = "The answer determines source admission, semantic coverage, and freeze checks."
    else:
        inference = "The request is not yet specific enough to create a testable MissionIR contract."
        recommended = "Clarify the observable output and success signal before implementation details."
        question = "What concrete output should MissionForge produce, and what observable check proves it succeeded?"
        why = "MissionIR requires expected artifacts and verification signals before runtime can start."
    return GrillingQuestion(
        question_id="Q-001",
        inference=inference,
        recommended_answer=recommended,
        question=question,
        why_this_matters=why,
        blocks_freeze=True,
        expected_answer_type=QuestionAnswerType.CHOICE_OR_FREE_TEXT,
        related_decision_ids=["D-core-need"],
    )


def _observation(text: str) -> str:
    return f"User expression captured as sanitized requirement evidence: {_first_sentence(text)}"


def _inference(text: str) -> str:
    lowered = text.lower()
    if "rust" in lowered:
        return "The user may need performance, packaging, or core-boundary protection rather than Rust as an end in itself."
    if "privacy" in lowered or "secret" in lowered:
        return "The user needs privacy and source-admission constraints to be visible in the mission contract."
    if text.strip():
        return "The user needs a structured, verifiable MissionIR authoring outcome."
    return "The user need is not yet stated."


def _core_pain(text: str) -> str:
    lowered = text.lower()
    if "privacy" in lowered or "secret" in lowered:
        return "Sensitive or raw user material must not leak into runtime-facing mission truth."
    if "rust" in lowered:
        return "The user wants implementation choices to support durable generic MissionForge boundaries."
    return "The user needs natural-language intent turned into a verifiable MissionIR contract."


def _first_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "Create a MissionForge deliverable."
    for separator in (".", "?", "!"):
        if separator in normalized:
            return normalized.split(separator, 1)[0][:200].strip() + separator
    return normalized[:200]


def _infer_expected_artifact(text: str) -> str:
    lowered = text.lower()
    if "package/readme.md" in lowered:
        return "package/README.md"
    if "docs/output.md" in lowered:
        return "docs/output.md"
    if "package/skill.md" in lowered:
        return "package/SKILL.md"
    if "skill.md" in lowered:
        return "package/SKILL.md"
    if "readme" in lowered:
        return "package/README.md"
    if "doc" in lowered:
        return "docs/output.md"
    return "artifacts/frontdesk_output.md"


def grill_frontdesk_session(
    *,
    session: FrontDeskAuthoringSession,
    workspace: FrontDeskWorkspace,
    max_questions: int = 1,
) -> NeedGrillResult:
    return NeedGriller().grill(session=session, workspace=workspace, max_questions=max_questions)


__all__ = ["NeedGrillResult", "NeedGriller", "grill_frontdesk_session"]
