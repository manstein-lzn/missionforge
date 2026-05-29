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
from .mission_mapper import MissionIRMapper, MissionMappingResult
from .need_griller import NeedGrillResult, NeedGriller
from .scout import ScoutResult, WorkspaceScout
from .semantic_coverage import SemanticCoverageChecker, SemanticCoverageResult
from .solution_architect import SolutionArchitect, SolutionArchitectureResult
from .spec_grill_schema import (
    FreezeGateDecision,
    FrontDeskFreezeGateResult,
    MissionIRMappingReport,
    MissionSemanticCoverageReport,
    MissionSolutionPlan,
    PlanReviewDecision,
    PlanReviewRecord,
    SemanticCoverageStatus,
    stable_bundle_hash,
)
from .state import (
    AUTHORING_APPROVAL_REF,
    CORE_NEED_BRIEF_REF,
    DECISION_TREE_REF,
    DOMAIN_LANGUAGE_REF,
    DRAFT_MISSION_REF,
    FREEZE_GATE_RESULT_REF,
    MISSION_AUDIT_REF,
    MISSION_BRIEF_REF,
    MISSION_MAPPING_REPORT_REF,
    MISSION_PLAN_REF,
    NEED_GRILLING_REPORT_REF,
    PLAN_REVIEW_REF,
    PLAN_RISK_REGISTER_REF,
    PROFILE_CATALOG_SNAPSHOT_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SANITIZED_SOURCES_REF,
    SEMANTIC_LOCK_REF,
    SEMANTIC_COVERAGE_REF,
    SOLUTION_PLAN_MARKDOWN_REF,
    SOLUTION_PLAN_REF,
    SOURCE_ADMISSION_REPORT_REF,
    WORKSPACE_FACTS_REF,
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
    missing_artifacts: list[str]
    failed_gates: list[str]
    latest_question: dict[str, Any] | None = None
    plan_review_status: str = ""
    freeze_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "next_action": self.next_action,
            "artifact_ref_map": dict(self.refs),
            "warnings": list(self.warnings),
            "missing_artifacts": list(self.missing_artifacts),
            "failed_gates": list(self.failed_gates),
            "latest_question": self.latest_question,
            "plan_review_status": self.plan_review_status,
            "freeze_ready": self.freeze_ready,
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
        self.scout(session_ref)
        grill = self.grill(session_ref)
        if grill.report.readiness.value != "core_need_ready":
            draft_session = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="answer_question")
            self.workspace.write_json(draft_session.session_ref, draft_session.to_dict())
            return draft_session
        self.cover_semantics(session_ref)
        self.plan_solution(session_ref)
        self.review_plan(
            session_ref,
            reviewed_by="frontdesk.policy",
            decision=PlanReviewDecision.APPROVE,
            authority=ApprovalAuthority.POLICY,
            notes=["Policy review for deterministic offline FrontDesk draft."],
        )
        self.map_mission(session_ref)
        draft_session = session.transition(FrontDeskStatus.DRAFT_READY, next_action="audit")
        self.workspace.write_json(draft_session.session_ref, draft_session.to_dict())
        return draft_session

    def scout(self, session_ref: str) -> ScoutResult:
        session = self.load_session(session_ref)
        result = WorkspaceScout(registry=self.registry).scout(session=session, workspace=self.workspace)
        updated = session.transition(FrontDeskStatus.ELICITING, next_action="grill")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def grill(self, session_ref: str) -> NeedGrillResult:
        session = self.load_session(session_ref)
        if not self.workspace.exists(WORKSPACE_FACTS_REF):
            self.scout(session_ref)
            session = self.load_session(session_ref)
        result = NeedGriller().grill(session=session, workspace=self.workspace)
        next_action = "semantic_coverage" if result.report.readiness.value == "core_need_ready" else "answer_question"
        updated = session.transition(FrontDeskStatus.ELICITING, next_action=next_action)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def cover_semantics(self, session_ref: str) -> SemanticCoverageResult:
        session = self.load_session(session_ref)
        result = SemanticCoverageChecker().cover(session=session, workspace=self.workspace)
        next_action = "plan_solution" if result.coverage_report.status == SemanticCoverageStatus.PASSED else "answer_question"
        target_status = FrontDeskStatus.ELICITING if result.coverage_report.status == SemanticCoverageStatus.PASSED else FrontDeskStatus.NEEDS_CLARIFICATION
        updated = session.transition(target_status, next_action=next_action)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def plan_solution(self, session_ref: str) -> SolutionArchitectureResult:
        session = self.load_session(session_ref)
        result = SolutionArchitect(registry=self.registry).plan(session=session, workspace=self.workspace)
        updated = session.transition(FrontDeskStatus.DRAFT_READY, next_action="review_plan")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def review_plan(
        self,
        session_ref: str,
        *,
        reviewed_by: str,
        decision: PlanReviewDecision = PlanReviewDecision.APPROVE,
        authority: ApprovalAuthority = ApprovalAuthority.USER,
        notes: list[str] | None = None,
        requested_changes: list[str] | None = None,
    ) -> PlanReviewRecord:
        session = self.load_session(session_ref)
        solution_plan = MissionSolutionPlan.from_dict(self.workspace.read_json(SOLUTION_PLAN_REF))
        review = PlanReviewRecord(
            session_id=session.session_id,
            decision=decision,
            reviewed_plan_ref=SOLUTION_PLAN_REF,
            reviewed_plan_hash=solution_plan.plan_hash,
            reviewed_by=reviewed_by,
            authority=authority,
            review_notes=list(notes or []),
            requested_changes=list(requested_changes or []),
        )
        self.workspace.write_json(PLAN_REVIEW_REF, review.to_dict())
        if decision == PlanReviewDecision.APPROVE:
            updated = session.transition(FrontDeskStatus.DRAFT_READY, next_action="map_mission")
        elif decision == PlanReviewDecision.HUMAN_REVIEW_REQUIRED:
            updated = session.transition(FrontDeskStatus.HUMAN_REVIEW_REQUIRED, next_action="human_review")
        else:
            updated = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="plan_solution")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return review

    def map_mission(self, session_ref: str) -> MissionMappingResult:
        session = self.load_session(session_ref)
        result = MissionIRMapper().map(session=session, workspace=self.workspace)
        updated = session.transition(FrontDeskStatus.AUDIT_REQUIRED, next_action="audit")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def audit(self, session_ref: str) -> MissionAuthoringAudit:
        session = self.load_session(session_ref)
        brief = MissionBrief.from_dict(self.workspace.read_json(MISSION_BRIEF_REF))
        profiles = ProfileRecommendationSet.from_dict(self.workspace.read_json(PROFILE_RECOMMENDATIONS_REF))
        plan = MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF))
        findings: list[str] = []
        if self.workspace.exists(SEMANTIC_COVERAGE_REF):
            coverage = MissionSemanticCoverageReport.from_dict(self.workspace.read_json(SEMANTIC_COVERAGE_REF))
            if coverage.status != SemanticCoverageStatus.PASSED:
                findings.append("Semantic coverage has blocking unmapped signals.")
        if self.workspace.exists(MISSION_MAPPING_REPORT_REF):
            mapping_report = MissionIRMappingReport.from_dict(self.workspace.read_json(MISSION_MAPPING_REPORT_REF))
            if mapping_report.has_blocking_gaps:
                findings.append("MissionIR mapping report has blocking gaps.")
        else:
            findings.append("MissionIR mapping report is missing.")
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
        approved_payloads = self._approved_spec_grill_payloads()
        approval = AuthoringApproval(
            session_id=session.session_id,
            approved_by=approved_by,
            authority=authority,
            approved_ref=MISSION_PLAN_REF,
            approved_hash=stable_bundle_hash(*approved_payloads),
        )
        self.workspace.write_json(AUTHORING_APPROVAL_REF, approval.to_dict())
        updated = session.transition(FrontDeskStatus.APPROVED)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return approval

    def freeze(self, session_ref: str) -> FrontDeskCompileResult:
        session = self.load_session(session_ref)
        if not self.workspace.exists(AUTHORING_APPROVAL_REF):
            raise ContractValidationError("FrontDesk freeze requires authoring approval")
        self._validate_spec_grill_freeze_inputs(session)
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
        gate_result = FrontDeskFreezeGateResult(
            session_id=session.session_id,
            decision=FreezeGateDecision.FREEZE,
            passed_checks=[
                "semantic_coverage",
                "plan_review",
                "mapping_report",
                "authoring_audit",
                "authoring_approval",
                "mission_freeze",
            ],
            failed_checks=[],
            artifact_refs=[result.freeze_manifest_ref, result.mission_ir_ref, result.frozen_contract_ref],
            reason="All spec-grill freeze checks passed.",
        )
        self.workspace.write_json(FREEZE_GATE_RESULT_REF, gate_result.to_dict())
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
            "workspace_facts_ref": WORKSPACE_FACTS_REF,
            "profile_catalog_snapshot_ref": PROFILE_CATALOG_SNAPSHOT_REF,
            "domain_language_ref": DOMAIN_LANGUAGE_REF,
            "source_admission_report_ref": SOURCE_ADMISSION_REPORT_REF,
            "decision_tree_ref": DECISION_TREE_REF,
            "core_need_brief_ref": CORE_NEED_BRIEF_REF,
            "need_grilling_report_ref": NEED_GRILLING_REPORT_REF,
            "semantic_lock_ref": session.semantic_lock_ref,
            "semantic_coverage_ref": SEMANTIC_COVERAGE_REF,
            "mission_brief_ref": session.mission_brief_ref,
            "profile_recommendations_ref": session.profile_recommendations_ref,
            "solution_plan_ref": SOLUTION_PLAN_REF,
            "solution_plan_markdown_ref": SOLUTION_PLAN_MARKDOWN_REF,
            "plan_risk_register_ref": PLAN_RISK_REGISTER_REF,
            "plan_review_ref": PLAN_REVIEW_REF,
            "mission_plan_ref": session.mission_plan_ref,
            "mission_mapping_report_ref": MISSION_MAPPING_REPORT_REF,
            "mission_audit_ref": session.mission_audit_ref,
            "authoring_approval_ref": session.authoring_approval_ref,
            "freeze_gate_result_ref": FREEZE_GATE_RESULT_REF,
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
            missing_artifacts=self._missing_frontdesk_artifacts(),
            failed_gates=self._failed_frontdesk_gates(),
            latest_question=self._latest_question(),
            plan_review_status=self._plan_review_status(),
            freeze_ready=self._freeze_ready(),
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

    def _validate_spec_grill_freeze_inputs(self, session: FrontDeskAuthoringSession) -> None:
        missing = [
            ref
            for ref in (
                SEMANTIC_COVERAGE_REF,
                SOLUTION_PLAN_REF,
                PLAN_REVIEW_REF,
                MISSION_MAPPING_REPORT_REF,
                MISSION_AUDIT_REF,
            )
            if not self.workspace.exists(ref)
        ]
        if missing:
            self._fail_freeze(
                session,
                [f"missing:{ref}" for ref in missing],
                "FrontDesk freeze requires complete spec-grill artifacts",
            )
        coverage = MissionSemanticCoverageReport.from_dict(self.workspace.read_json(SEMANTIC_COVERAGE_REF))
        if coverage.status != SemanticCoverageStatus.PASSED:
            self._fail_freeze(session, ["semantic_coverage"], "FrontDesk freeze requires passing semantic coverage")
        solution_plan = MissionSolutionPlan.from_dict(self.workspace.read_json(SOLUTION_PLAN_REF))
        plan_review = PlanReviewRecord.from_dict(self.workspace.read_json(PLAN_REVIEW_REF))
        if plan_review.decision != PlanReviewDecision.APPROVE:
            self._fail_freeze(session, ["plan_review"], "FrontDesk freeze requires approved plan review")
        if plan_review.reviewed_plan_hash != solution_plan.plan_hash:
            self._fail_freeze(session, ["plan_review_hash"], "FrontDesk freeze requires current plan review hash")
        mapping_report = MissionIRMappingReport.from_dict(self.workspace.read_json(MISSION_MAPPING_REPORT_REF))
        if mapping_report.has_blocking_gaps:
            self._fail_freeze(
                session,
                ["mission_mapping_report"],
                "FrontDesk freeze requires complete MissionIR mapping coverage",
            )
        audit = MissionAuthoringAudit.from_dict(self.workspace.read_json(MISSION_AUDIT_REF))
        if audit.decision != AuditDecision.APPROVE:
            self._fail_freeze(session, ["mission_audit"], "FrontDesk freeze requires approved authoring audit")
        approval = AuthoringApproval.from_dict(self.workspace.read_json(AUTHORING_APPROVAL_REF))
        current_hash = stable_bundle_hash(*self._approved_spec_grill_payloads())
        if approval.approved_hash != current_hash:
            self._fail_freeze(session, ["authoring_approval_hash"], "FrontDesk freeze requires current approval hash")

    def _approved_spec_grill_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = [
            MissionSemanticLock.from_dict(self.workspace.read_json(SEMANTIC_LOCK_REF)).to_dict(),
            MissionBrief.from_dict(self.workspace.read_json(MISSION_BRIEF_REF)).to_dict(),
            SanitizedSourceSet.from_dict(self.workspace.read_json(SANITIZED_SOURCES_REF)).to_dict(),
            ProfileRecommendationSet.from_dict(self.workspace.read_json(PROFILE_RECOMMENDATIONS_REF)).to_dict(),
            MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF)).to_dict(),
        ]
        for ref, loader in (
            (SEMANTIC_COVERAGE_REF, MissionSemanticCoverageReport.from_dict),
            (SOLUTION_PLAN_REF, MissionSolutionPlan.from_dict),
            (PLAN_REVIEW_REF, PlanReviewRecord.from_dict),
            (MISSION_MAPPING_REPORT_REF, MissionIRMappingReport.from_dict),
            (MISSION_AUDIT_REF, MissionAuthoringAudit.from_dict),
        ):
            if self.workspace.exists(ref):
                payloads.append(loader(self.workspace.read_json(ref)).to_dict())
        if self.workspace.exists(DRAFT_MISSION_REF):
            payloads.append(MissionIR.from_dict(self.workspace.read_json(DRAFT_MISSION_REF)).to_dict())
        return payloads

    def _fail_freeze(self, session: FrontDeskAuthoringSession, failed_checks: list[str], reason: str) -> None:
        gate_result = FrontDeskFreezeGateResult(
            session_id=session.session_id,
            decision=FreezeGateDecision.FAILED_CLOSED,
            failed_checks=failed_checks,
            reason=reason,
        )
        self.workspace.write_json(FREEZE_GATE_RESULT_REF, gate_result.to_dict())
        raise ContractValidationError(reason)

    def _expected_frontdesk_artifact_refs(self) -> list[str]:
        return [
            WORKSPACE_FACTS_REF,
            PROFILE_CATALOG_SNAPSHOT_REF,
            DOMAIN_LANGUAGE_REF,
            SOURCE_ADMISSION_REPORT_REF,
            DECISION_TREE_REF,
            NEED_GRILLING_REPORT_REF,
            CORE_NEED_BRIEF_REF,
            SANITIZED_SOURCES_REF,
            SEMANTIC_LOCK_REF,
            MISSION_BRIEF_REF,
            SEMANTIC_COVERAGE_REF,
            SOLUTION_PLAN_REF,
            PLAN_REVIEW_REF,
            PROFILE_RECOMMENDATIONS_REF,
            MISSION_PLAN_REF,
            DRAFT_MISSION_REF,
            MISSION_MAPPING_REPORT_REF,
            MISSION_AUDIT_REF,
            AUTHORING_APPROVAL_REF,
        ]

    def _missing_frontdesk_artifacts(self) -> list[str]:
        return [ref for ref in self._expected_frontdesk_artifact_refs() if not self.workspace.exists(ref)]

    def _failed_frontdesk_gates(self) -> list[str]:
        failed: list[str] = []
        if self.workspace.exists(FREEZE_GATE_RESULT_REF):
            failed.extend(FrontDeskFreezeGateResult.from_dict(self.workspace.read_json(FREEZE_GATE_RESULT_REF)).failed_checks)
        if self.workspace.exists(SEMANTIC_COVERAGE_REF):
            coverage = MissionSemanticCoverageReport.from_dict(self.workspace.read_json(SEMANTIC_COVERAGE_REF))
            if coverage.status != SemanticCoverageStatus.PASSED:
                failed.append("semantic_coverage")
        if self.workspace.exists(MISSION_MAPPING_REPORT_REF):
            mapping = MissionIRMappingReport.from_dict(self.workspace.read_json(MISSION_MAPPING_REPORT_REF))
            if mapping.has_blocking_gaps:
                failed.append("mission_mapping_report")
        if self.workspace.exists(MISSION_AUDIT_REF):
            audit = MissionAuthoringAudit.from_dict(self.workspace.read_json(MISSION_AUDIT_REF))
            if audit.decision != AuditDecision.APPROVE:
                failed.append("mission_audit")
        return sorted(set(failed))

    def _latest_question(self) -> dict[str, Any] | None:
        if not self.workspace.exists(NEED_GRILLING_REPORT_REF):
            return None
        from .spec_grill_schema import NeedGrillingReport

        report = NeedGrillingReport.from_dict(self.workspace.read_json(NEED_GRILLING_REPORT_REF))
        return report.next_question.to_dict() if report.next_question else None

    def _plan_review_status(self) -> str:
        if not self.workspace.exists(PLAN_REVIEW_REF):
            return "missing"
        return PlanReviewRecord.from_dict(self.workspace.read_json(PLAN_REVIEW_REF)).decision.value

    def _freeze_ready(self) -> bool:
        return (
            not self._missing_frontdesk_artifacts()
            and not self._failed_frontdesk_gates()
            and self._plan_review_status() == PlanReviewDecision.APPROVE.value
        )


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
