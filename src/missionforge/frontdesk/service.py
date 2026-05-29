"""High-level FrontDesk authoring facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, require_non_empty_str, validate_ref
from ..ir import MissionIR
from ..profiles import ProfileRegistry
from ..runner import MissionRuntime
from .compiler import FrontDeskCompileResult, approved_hash_for
from .freeze_gate import FrontDeskFreezeGate
from .schema import (
    ApprovalAuthority,
    AuditDecision,
    AuthoringApproval,
    ConversationRole,
    ConversationTurn,
    MissionAuthoringAudit,
    MissionBrief,
    MissionPlan,
    MissionSemanticLock,
    ProfileRecommendation,
    ProfileRecommendationKind,
    ProfileRecommendationSet,
    SanitizedSourceSet,
)
from .state import (
    AUTHORING_APPROVAL_REF,
    MISSION_AUDIT_REF,
    MISSION_BRIEF_REF,
    MISSION_PLAN_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SANITIZED_SOURCES_REF,
    SEMANTIC_LOCK_REF,
    FrontDeskAuthoringSession,
)
from .schema import FrontDeskStatus
from .workspace import FrontDeskWorkspace


@dataclass(frozen=True)
class FrontDeskInspectResult:
    """Refs-only FrontDesk inspection result."""

    session_id: str
    status: str
    next_action: str
    refs: dict[str, str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "next_action": self.next_action,
            "artifact_ref_map": dict(self.refs),
            "warnings": list(self.warnings),
        }


class FrontDesk:
    """Programmatic FrontDesk API."""

    def __init__(self, workspace: str | Path = ".", *, registry: ProfileRegistry | None = None) -> None:
        self.workspace = FrontDeskWorkspace(workspace)
        self.registry = registry

    def start(self, text: str, *, session_id: str = "frontdesk-session") -> FrontDeskAuthoringSession:
        require_non_empty_str(text, "frontdesk.start.text")
        session = FrontDeskAuthoringSession.new(session_id).transition(FrontDeskStatus.ELICITING)
        self.workspace.write_json(session.session_ref, session.to_dict())
        self._append_turn(session, role=ConversationRole.USER, text=text)
        return session

    def answer(self, session_ref: str, text: str) -> FrontDeskAuthoringSession:
        require_non_empty_str(text, "frontdesk.answer.text")
        session = self.load_session(session_ref)
        self._append_turn(session, role=ConversationRole.USER, text=text)
        if session.status == FrontDeskStatus.NEW:
            session = session.transition(FrontDeskStatus.ELICITING)
        self.workspace.write_json(session.session_ref, session.to_dict())
        return session

    def draft(self, session_ref: str) -> FrontDeskAuthoringSession:
        session = self.load_session(session_ref)
        turns = self.workspace.read_jsonl(session.conversation_ref)
        text = _conversation_text(self.workspace, turns)
        semantic_lock, brief, sources, profiles, plan = deterministic_frontdesk_draft(session.session_id, text)
        self.workspace.write_json(SANITIZED_SOURCES_REF, sources.to_dict())
        self.workspace.write_json(SEMANTIC_LOCK_REF, semantic_lock.to_dict())
        self.workspace.write_json(MISSION_BRIEF_REF, brief.to_dict())
        self.workspace.write_json(PROFILE_RECOMMENDATIONS_REF, profiles.to_dict())
        self.workspace.write_json(MISSION_PLAN_REF, plan.to_dict())
        draft_session = session.transition(FrontDeskStatus.DRAFT_READY)
        self.workspace.write_json(draft_session.session_ref, draft_session.to_dict())
        return draft_session

    def audit(self, session_ref: str) -> MissionAuthoringAudit:
        session = self.load_session(session_ref)
        brief = MissionBrief.from_dict(self.workspace.read_json(MISSION_BRIEF_REF))
        profiles = ProfileRecommendationSet.from_dict(self.workspace.read_json(PROFILE_RECOMMENDATIONS_REF))
        plan = MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF))
        findings: list[str] = []
        if not brief.success_signals:
            findings.append("Mission brief has no success signals.")
        if not profiles.selected_verification_profiles:
            findings.append("No verification profile selected.")
        if not plan.expected_artifacts:
            findings.append("No expected artifacts planned.")
        decision = AuditDecision.NEEDS_CLARIFICATION if findings else AuditDecision.APPROVE
        audit = MissionAuthoringAudit(
            session_id=session.session_id,
            decision=decision,
            findings=findings,
            required_followup_questions=["What observable output proves success?"] if findings else [],
        )
        self.workspace.write_json(MISSION_AUDIT_REF, audit.to_dict())
        next_status = FrontDeskStatus.NEEDS_CLARIFICATION if findings else FrontDeskStatus.APPROVAL_REQUIRED
        updated = session.transition(next_status)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return audit

    def approve(
        self,
        session_ref: str,
        *,
        approved_by: str,
        authority: ApprovalAuthority = ApprovalAuthority.USER,
    ) -> AuthoringApproval:
        session = self.load_session(session_ref)
        semantic_lock = MissionSemanticLock.from_dict(self.workspace.read_json(SEMANTIC_LOCK_REF))
        brief = MissionBrief.from_dict(self.workspace.read_json(MISSION_BRIEF_REF))
        profiles = ProfileRecommendationSet.from_dict(self.workspace.read_json(PROFILE_RECOMMENDATIONS_REF))
        plan = MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF))
        approval = AuthoringApproval(
            session_id=session.session_id,
            approved_by=approved_by,
            authority=authority,
            approved_ref=MISSION_PLAN_REF,
            approved_hash=approved_hash_for(semantic_lock.to_dict(), brief.to_dict(), profiles.to_dict(), plan.to_dict()),
        )
        self.workspace.write_json(AUTHORING_APPROVAL_REF, approval.to_dict())
        updated = session.transition(FrontDeskStatus.APPROVED)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return approval

    def freeze(self, session_ref: str) -> FrontDeskCompileResult:
        session = self.load_session(session_ref)
        if not self.workspace.exists(AUTHORING_APPROVAL_REF):
            raise ContractValidationError("FrontDesk freeze requires authoring approval")
        result = FrontDeskFreezeGate(registry=self.registry).freeze(
            semantic_lock=MissionSemanticLock.from_dict(self.workspace.read_json(SEMANTIC_LOCK_REF)),
            mission_brief=MissionBrief.from_dict(self.workspace.read_json(MISSION_BRIEF_REF)),
            profile_recommendations=ProfileRecommendationSet.from_dict(
                self.workspace.read_json(PROFILE_RECOMMENDATIONS_REF)
            ),
            mission_plan=MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF)),
            approval=AuthoringApproval.from_dict(self.workspace.read_json(AUTHORING_APPROVAL_REF)),
            sanitized_sources=SanitizedSourceSet.from_dict(self.workspace.read_json(SANITIZED_SOURCES_REF)),
            workspace=self.workspace.workspace,
        )
        updated = session.with_freeze(
            mission_ir_ref=result.mission_ir_ref,
            frozen_contract_ref=result.frozen_contract_ref,
            contract_hash=result.contract_hash,
        )
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def run(self, session_ref: str, *, runtime: MissionRuntime | None = None) -> Any:
        session = self.load_session(session_ref)
        mission_ref = validate_ref(session.mission_ir_ref, "frontdesk.run.mission_ir_ref")
        mission = MissionIR.from_dict(self.workspace.read_json(mission_ref))
        active_runtime = runtime or MissionRuntime(workspace=self.workspace.workspace)
        result = active_runtime.run(mission)
        updated = session.transition(FrontDeskStatus.HANDED_OFF)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def inspect(self, session_ref: str) -> FrontDeskInspectResult:
        session = self.load_session(session_ref)
        refs = {
            "session_ref": session.session_ref,
            "semantic_lock_ref": session.semantic_lock_ref,
            "mission_brief_ref": session.mission_brief_ref,
            "profile_recommendations_ref": session.profile_recommendations_ref,
            "mission_plan_ref": session.mission_plan_ref,
            "mission_audit_ref": session.mission_audit_ref,
            "authoring_approval_ref": session.authoring_approval_ref,
            "freeze_manifest_ref": session.freeze_manifest_ref,
            "mission_ir_ref": session.mission_ir_ref,
            "frozen_contract_ref": session.frozen_contract_ref,
        }
        return FrontDeskInspectResult(
            session_id=session.session_id,
            status=session.status.value,
            next_action=session.next_action,
            refs=refs,
            warnings=list(session.warnings),
        )

    def load_session(self, session_ref: str) -> FrontDeskAuthoringSession:
        return FrontDeskAuthoringSession.from_dict(self.workspace.read_json(validate_ref(session_ref, "frontdesk.session_ref")))

    def _append_turn(self, session: FrontDeskAuthoringSession, *, role: ConversationRole, text: str) -> None:
        turn_index = len(self.workspace.read_jsonl(session.conversation_ref)) + 1
        content_ref = f"frontdesk/turns/turn-{turn_index:03d}.txt"
        self.workspace.write_text_provenance(content_ref, text)
        turn = ConversationTurn(
            turn_id=f"turn-{turn_index:03d}",
            role=role,
            content_ref=content_ref,
        )
        self.workspace.append_jsonl(session.conversation_ref, turn.to_dict())


def deterministic_frontdesk_draft(
    session_id: str,
    text: str,
) -> tuple[MissionSemanticLock, MissionBrief, SanitizedSourceSet, ProfileRecommendationSet, MissionPlan]:
    """Create deterministic authoring artifacts for offline tests and first product slice."""

    normalized = require_non_empty_str(text or "Create a MissionForge deliverable.", "frontdesk.draft.text")
    summary = normalized.splitlines()[0][:160]
    source_ref = "frontdesk/sanitized_sources.json"
    expected_artifact = _infer_expected_artifact(normalized)
    deliverable_type = _infer_deliverable_type(expected_artifact)
    semantic_lock = MissionSemanticLock(
        session_id=session_id,
        summary=summary,
        requirement_clauses=[summary],
        source_refs=[source_ref],
        non_goals=["Do not use raw conversation as runtime task truth."],
    )
    brief = MissionBrief(
        session_id=session_id,
        goal=summary,
        deliverable_type=deliverable_type,
        success_signals=[f"{expected_artifact} exists."],
        target_users=["missionforge_user"],
        non_goals=["Do not bypass verifier-owned closure."],
    )
    sources = SanitizedSourceSet(
        session_id=session_id,
        admitted_source_refs=[source_ref],
        excluded_source_refs=["frontdesk/conversation.jsonl"],
        redaction_notes=["Raw conversation remains provenance only."],
    )
    profiles = ProfileRecommendationSet(
        session_id=session_id,
        recommendations=[
            ProfileRecommendation(
                profile_id="user_provided_evidence_only",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="FrontDesk admits sanitized source refs only.",
            ),
            ProfileRecommendation(
                profile_id="explicit_output_root",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="The expected artifact declares its output root.",
                requirements={"output_root": expected_artifact.split("/", 1)[0]},
            ),
            ProfileRecommendation(
                profile_id="generic_local_verification",
                kind=ProfileRecommendationKind.VERIFICATION,
                rationale="The draft can be checked with local file validators.",
            ),
        ],
    )
    constraint_id = f"FD-{session_id}-C-authoring-contract"
    plan = MissionPlan(
        session_id=session_id,
        expected_artifacts=[expected_artifact],
        validators=[
            {
                "validator_id": f"V-{session_id}-artifact-exists",
                "constraint_refs": [constraint_id],
                "type": "file_exists",
                "inputs": {"path": expected_artifact},
            }
        ],
    )
    return semantic_lock, brief, sources, profiles, plan

def _conversation_text(workspace: FrontDeskWorkspace, turns: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for turn in turns:
        content_ref = turn.get("content_ref")
        if isinstance(content_ref, str) and workspace.exists(content_ref):
            values.append(workspace.store.read_text(content_ref))
    return " ".join(values) or "Create a MissionForge deliverable."


def _infer_expected_artifact(text: str) -> str:
    lowered = text.lower()
    if "skill.md" in lowered:
        return "package/SKILL.md"
    if "readme" in lowered:
        return "package/README.md"
    if "doc" in lowered:
        return "docs/output.md"
    return "artifacts/frontdesk_output.md"


def _infer_deliverable_type(expected_artifact: str) -> str:
    if expected_artifact.startswith("package/"):
        return "capability_bundle"
    if expected_artifact.startswith("docs/"):
        return "documentation_change"
    return "artifact"
