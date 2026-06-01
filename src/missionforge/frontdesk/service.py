"""High-level FrontDesk authoring facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..contracts import ContractValidationError, require_mapping, require_non_empty_str, validate_ref
from ..ir import MissionIR
from ..product_integration import ProductCompileResult, ProductCompileStatus, ProductIntegration, ProductTaskContractCompileResult, TaskContractProductIntegration
from ..profiles import ProfileRegistry
from ..runner import MissionRuntime
from .compiler import FrontDeskCompileResult, approved_hash_for
from .freeze_gate import FrontDeskFreezeGate
from .inquiry_profile import ProductInquiryProfile, SlotRequirement, SlotValueType
from .intent_bundle import (
    FrontDeskIntentBundle,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    ProductHypothesis,
    RiskFlag,
    SlotValue,
    SlotValueStatus,
)
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
    ProfileRecommendationSet,
    SanitizedSourceSet,
)
from .mission_mapper import MissionMappingResult
from .need_griller import NeedGrillResult
from .pi_node_runner import FrontDeskPiNodeRunner, frontdesk_pi_node_execution_ref, frontdesk_pi_node_spec_ref
from .scout import ScoutResult, WorkspaceScout
from .semantic_coverage import SemanticCoverageChecker, SemanticCoverageResult
from .solution_architect import SolutionArchitectureResult
from .spec_grill_schema import (
    CoreNeedBrief,
    DecisionTree,
    FreezeGateDecision,
    FrontDeskFreezeGateResult,
    MissionIRMappingReport,
    MissionSemanticCoverageReport,
    MissionSolutionPlan,
    NeedGrillingReadiness,
    NeedGrillingReport,
    PlanRiskRegister,
    PlanReviewDecision,
    PlanReviewRecord,
    SemanticCoverageStatus,
    stable_bundle_hash,
)
from .state import (
    AUTHORING_APPROVAL_REF,
    CONVERSATION_REF,
    CORE_NEED_BRIEF_REF,
    DECISION_TREE_REF,
    DOMAIN_LANGUAGE_REF,
    DRAFT_MISSION_REF,
    FREEZE_GATE_RESULT_REF,
    INTENT_BUNDLE_CANDIDATE_REF,
    INTENT_BUNDLE_REF,
    MISSION_AUDIT_REF,
    MISSION_BRIEF_REF,
    MISSION_MAPPING_REPORT_REF,
    MISSION_PLAN_REF,
    NEED_GRILLING_REPORT_REF,
    PLAN_REVIEW_REF,
    PLAN_RISK_REGISTER_REF,
    PROFILE_CATALOG_SNAPSHOT_REF,
    PRODUCT_INQUIRY_PROFILE_REF,
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
from ..workers import WorkerAdapter


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
    missing_product_slots: list[str] = field(default_factory=list)
    product_context: dict[str, Any] = field(default_factory=dict)

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
            "missing_product_slots": list(self.missing_product_slots or []),
            "product_context": self.product_context or {},
        }


class FrontDesk:
    """Programmatic FrontDesk API."""

    def __init__(
        self,
        workspace: str | Path = ".",
        *,
        registry: ProfileRegistry | None = None,
        worker: WorkerAdapter | None = None,
    ) -> None:
        self.workspace = FrontDeskWorkspace(workspace)
        self.registry = registry
        self.worker = worker
        self.pi_node_runner = FrontDeskPiNodeRunner()
        if worker is not None:
            self._validate_piworker_adapter(worker)

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
        self._fail_llm_required(session, "draft")

    def scout(self, session_ref: str) -> ScoutResult:
        session = self.load_session(session_ref)
        result = WorkspaceScout(registry=self.registry).scout(session=session, workspace=self.workspace)
        updated = session.transition(FrontDeskStatus.ELICITING, next_action="grill")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def grill(self, session_ref: str, *, require_core_need: bool = False) -> NeedGrillResult:
        session = self.load_session(session_ref)
        worker = self._worker_or_fail(session, "need grilling")
        if not self.workspace.exists(WORKSPACE_FACTS_REF):
            self.scout(session_ref)
            session = self.load_session(session_ref)
        visible_refs = [
            CONVERSATION_REF,
            WORKSPACE_FACTS_REF,
            SOURCE_ADMISSION_REPORT_REF,
            PROFILE_CATALOG_SNAPSHOT_REF,
        ]
        if self.workspace.exists(PRODUCT_INQUIRY_PROFILE_REF):
            visible_refs.append(PRODUCT_INQUIRY_PROFILE_REF)
        expected_outputs = [DECISION_TREE_REF, NEED_GRILLING_REPORT_REF]
        optional_outputs = [CORE_NEED_BRIEF_REF]
        if require_core_need:
            expected_outputs.append(CORE_NEED_BRIEF_REF)
            optional_outputs = []
        self.pi_node_runner.run_node(
            node_name="need_griller",
            session_id=session.session_id,
            visible_refs=visible_refs,
            expected_outputs=expected_outputs,
            optional_outputs=optional_outputs,
            worker=worker,
            workspace=self.workspace.workspace,
        )
        self._require_ai_artifact(session, DECISION_TREE_REF, "need_griller")
        self._require_ai_artifact(session, NEED_GRILLING_REPORT_REF, "need_griller")
        decision_tree = DecisionTree.from_dict(self.workspace.read_json(DECISION_TREE_REF))
        report = NeedGrillingReport.from_dict(self.workspace.read_json(NEED_GRILLING_REPORT_REF))
        core_need = None
        if report.readiness == NeedGrillingReadiness.CORE_NEED_READY:
            self._require_ai_artifact(session, CORE_NEED_BRIEF_REF, "need_griller")
            core_need = CoreNeedBrief.from_dict(self.workspace.read_json(CORE_NEED_BRIEF_REF))
            updated = session.transition(FrontDeskStatus.ELICITING, next_action="cover_semantics")
        elif report.readiness == NeedGrillingReadiness.NEEDS_CLARIFICATION or report.next_question is not None:
            updated = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="answer_question")
        elif report.readiness == NeedGrillingReadiness.HUMAN_REVIEW_REQUIRED:
            updated = session.transition(FrontDeskStatus.HUMAN_REVIEW_REQUIRED, next_action="human_review")
        else:
            self._fail_llm_required(session, "need grilling")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return NeedGrillResult(decision_tree=decision_tree, report=report, core_need_brief=core_need)

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
        worker = self._worker_or_fail(session, "solution architecture")
        self._require_ai_artifact(session, CORE_NEED_BRIEF_REF, "need_griller")
        if not self.workspace.exists(SEMANTIC_COVERAGE_REF):
            self.cover_semantics(session_ref)
            session = self.load_session(session_ref)
        visible_refs = [
            CORE_NEED_BRIEF_REF,
            SEMANTIC_LOCK_REF,
            MISSION_BRIEF_REF,
            SEMANTIC_COVERAGE_REF,
            PROFILE_CATALOG_SNAPSHOT_REF,
        ]
        if self.workspace.exists(PRODUCT_INQUIRY_PROFILE_REF):
            visible_refs.append(PRODUCT_INQUIRY_PROFILE_REF)
        self.pi_node_runner.run_node(
            node_name="solution_architect",
            session_id=session.session_id,
            visible_refs=visible_refs,
            expected_outputs=[
                SOLUTION_PLAN_REF,
                SOLUTION_PLAN_MARKDOWN_REF,
                PLAN_RISK_REGISTER_REF,
                PROFILE_RECOMMENDATIONS_REF,
                MISSION_PLAN_REF,
            ],
            worker=worker,
            workspace=self.workspace.workspace,
        )
        for ref in (
            SOLUTION_PLAN_REF,
            SOLUTION_PLAN_MARKDOWN_REF,
            PLAN_RISK_REGISTER_REF,
            PROFILE_RECOMMENDATIONS_REF,
            MISSION_PLAN_REF,
        ):
            self._require_ai_artifact(session, ref, "solution_architect")
        solution_plan = MissionSolutionPlan.from_dict(self.workspace.read_json(SOLUTION_PLAN_REF))
        risk_register = PlanRiskRegister.from_dict(self.workspace.read_json(PLAN_RISK_REGISTER_REF))
        recommendations = ProfileRecommendationSet.from_dict(self.workspace.read_json(PROFILE_RECOMMENDATIONS_REF))
        self._validate_profile_recommendations(recommendations)
        mission_plan = MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF))
        markdown = self.workspace.resolve_ref(SOLUTION_PLAN_MARKDOWN_REF).read_text(encoding="utf-8")
        updated = session.transition(FrontDeskStatus.DRAFT_READY, next_action="build_intent_bundle")
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return SolutionArchitectureResult(
            solution_plan=solution_plan,
            risk_register=risk_register,
            profile_recommendations=recommendations,
            mission_plan=mission_plan,
            solution_plan_markdown=markdown,
        )

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
        self._fail_llm_required(session, "MissionIR mapping")

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

    def build_intent_bundle(
        self,
        session_ref: str,
        *,
        product_context: ProductInquiryProfile | dict[str, Any] | None = None,
    ) -> FrontDeskIntentBundle:
        """Build and persist a refs-first FrontDeskIntentBundle."""

        session = self.load_session(session_ref)
        profile = self._coerce_product_context(product_context)
        if self.workspace.exists(INTENT_BUNDLE_REF):
            bundle = FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_REF))
            if profile is not None and bundle.product_context.product_id != profile.product_id:
                raise ContractValidationError("existing FrontDesk intent bundle product context does not match requested profile")
            if profile is not None:
                self._ensure_intent_artifacts(session.session_ref)
                session = self.load_session(session.session_ref)
                return self._validated_existing_product_intent_bundle(
                    session=session,
                    profile=profile,
                    generic_refs=self._intent_generic_refs(session),
                    product_snapshot=self._product_context_snapshot_for(profile),
                )
            return bundle
        self._ensure_intent_artifacts(session.session_ref)
        session = self.load_session(session.session_ref)
        generic_refs = self._intent_generic_refs(session)
        product_snapshot = ProductContextSnapshot()
        if profile is not None:
            self.workspace.write_json(PRODUCT_INQUIRY_PROFILE_REF, profile.to_dict())
            product_snapshot = self._product_context_snapshot_for(profile)

        if profile is not None:
            bundle = self._build_product_intent_bundle(session, profile, generic_refs, product_snapshot)
            self.workspace.write_json(INTENT_BUNDLE_REF, bundle.to_dict())
            if bundle.missing_blocking_slots:
                updated = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="answer_question")
            else:
                updated = session.transition(session.status, next_action="compile_product")
            self.workspace.write_json(updated.session_ref, updated.to_dict())
            return bundle

        slot_values = self._build_slot_values(profile, generic_refs)
        missing_blocking_slots = self._missing_blocking_slots(profile, slot_values)
        clarification_questions = [
            slot.question
            for slot in slot_values
            if slot.status == SlotValueStatus.MISSING and slot.question
        ]
        readiness = self._intent_readiness(profile, missing_blocking_slots)
        bundle = FrontDeskIntentBundle(
            session_id=session.session_id,
            intent_bundle_ref=INTENT_BUNDLE_REF,
            generic_refs=generic_refs,
            product_context=product_snapshot,
            slot_values=slot_values,
            product_hypotheses=self._product_hypotheses(generic_refs),
            risk_flags=self._risk_flags(profile, generic_refs),
            missing_blocking_slots=missing_blocking_slots,
            readiness=readiness,
            clarification_questions=clarification_questions,
            evidence_refs=generic_refs.refs,
        )
        self.workspace.write_json(INTENT_BUNDLE_REF, bundle.to_dict())
        if missing_blocking_slots:
            updated = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="answer_question")
        else:
            updated = session.transition(session.status, next_action="compile_product" if profile else session.next_action)
        self.workspace.write_json(updated.session_ref, updated.to_dict())
        return bundle

    def _product_context_snapshot_for(self, profile: ProductInquiryProfile) -> ProductContextSnapshot:
        return ProductContextSnapshot(
            product_id=profile.product_id,
            display_name=profile.display_name,
            profile_ref=PRODUCT_INQUIRY_PROFILE_REF,
            profile_hash=profile.profile_hash,
            version=profile.version,
        )

    def _validated_existing_product_intent_bundle(
        self,
        *,
        session: FrontDeskAuthoringSession,
        profile: ProductInquiryProfile,
        generic_refs: IntentGenericRefs,
        product_snapshot: ProductContextSnapshot,
    ) -> FrontDeskIntentBundle:
        self._require_ai_artifact(
            session,
            INTENT_BUNDLE_CANDIDATE_REF,
            "intent_bundle_author",
            product_profile_hash=profile.profile_hash,
        )
        candidate = FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_CANDIDATE_REF))
        expected = self._finalize_product_intent_candidate(
            session=session,
            profile=profile,
            candidate=candidate,
            generic_refs=generic_refs,
            product_snapshot=product_snapshot,
        )
        existing = FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_REF))
        if existing.to_dict() != expected.to_dict():
            raise ContractValidationError("existing FrontDesk intent bundle is stale or tampered")
        return existing

    def compile_product(self, session_ref: str, integration: ProductIntegration) -> ProductCompileResult:
        """Compile a FrontDesk intent bundle through an external product integration."""

        session = self.load_session(session_ref)
        profile = integration.inquiry_profile() if hasattr(integration, "inquiry_profile") else None
        if profile is not None:
            bundle = self.build_intent_bundle(session.session_ref, product_context=profile)
        elif self.workspace.exists(INTENT_BUNDLE_REF):
            bundle = FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_REF))
        else:
            bundle = self.build_intent_bundle(session.session_ref, product_context=profile)
        result = integration.compile_intent(bundle, workspace=self.workspace.workspace)
        result.validate()
        if result.status == ProductCompileStatus.NEEDS_CLARIFICATION:
            updated = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="answer_question")
            self.workspace.write_json(updated.session_ref, updated.to_dict())
        return result

    def compile_product_task_contract(
        self,
        session_ref: str,
        integration: TaskContractProductIntegration,
    ) -> ProductTaskContractCompileResult:
        """Compile a FrontDesk intent bundle through the default TaskContract product path."""

        session = self.load_session(session_ref)
        profile = integration.inquiry_profile() if hasattr(integration, "inquiry_profile") else None
        if profile is not None:
            bundle = self.build_intent_bundle(session.session_ref, product_context=profile)
        elif self.workspace.exists(INTENT_BUNDLE_REF):
            bundle = FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_REF))
        else:
            bundle = self.build_intent_bundle(session.session_ref, product_context=profile)
        result = integration.compile_task_contract(bundle, workspace=self.workspace.workspace)
        result.validate()
        if result.status == ProductCompileStatus.NEEDS_CLARIFICATION:
            updated = session.transition(FrontDeskStatus.NEEDS_CLARIFICATION, next_action="answer_question")
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
            "product_inquiry_profile_ref": session.product_inquiry_profile_ref,
            "intent_bundle_ref": session.intent_bundle_ref,
            "mission_audit_ref": session.mission_audit_ref,
            "authoring_approval_ref": session.authoring_approval_ref,
            "freeze_gate_result_ref": FREEZE_GATE_RESULT_REF,
            "freeze_manifest_ref": session.freeze_manifest_ref,
            "mission_ir_ref": session.mission_ir_ref,
            "frozen_contract_ref": session.frozen_contract_ref,
        }
        for node_name in ("need_griller", "solution_architect", "intent_bundle_author", "mission_ir_mapper"):
            refs[f"{node_name}_node_spec_ref"] = frontdesk_pi_node_spec_ref(
                session_id=session.session_id,
                node_name=node_name,
            )
            refs[f"{node_name}_execution_ref"] = frontdesk_pi_node_execution_ref(
                session_id=session.session_id,
                node_name=node_name,
            )
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
            missing_product_slots=self._missing_product_slots(),
            product_context=self._product_context_snapshot(),
        )

    def _validate_piworker_adapter(self, worker: WorkerAdapter) -> None:
        if getattr(worker, "adapter_family", "") != "piworker":
            raise ContractValidationError("FrontDesk worker must be an explicit PiWorker-compatible adapter")

    def _worker_or_fail(self, session: FrontDeskAuthoringSession, operation: str) -> WorkerAdapter:
        if self.worker is None:
            self._fail_llm_required(session, operation)
        self._validate_piworker_adapter(self.worker)
        return self.worker

    def _require_ai_artifact(
        self,
        session: FrontDeskAuthoringSession,
        ref: str,
        node_name: str,
        *,
        product_profile_hash: str = "",
    ) -> None:
        self.pi_node_runner.require_ai_authored(
            workspace=self.workspace.workspace,
            ref=ref,
            node_name=node_name,
            session_id=session.session_id,
            product_profile_hash=product_profile_hash,
        )

    def _validate_profile_recommendations(self, recommendations: ProfileRecommendationSet) -> None:
        registry = self.registry or ProfileRegistry.builtins()
        for recommendation in recommendations.selected_capability_profiles:
            registry.get_capability(recommendation.profile_id)
        for recommendation in recommendations.selected_verification_profiles:
            registry.get_verification(recommendation.profile_id)

    def _coerce_product_context(
        self,
        product_context: ProductInquiryProfile | dict[str, Any] | None,
    ) -> ProductInquiryProfile | None:
        if product_context is None:
            return None
        if isinstance(product_context, ProductInquiryProfile):
            product_context.validate()
            return product_context
        return ProductInquiryProfile.from_dict(require_mapping(product_context, "frontdesk.product_context"))

    def _build_product_intent_bundle(
        self,
        session: FrontDeskAuthoringSession,
        profile: ProductInquiryProfile,
        generic_refs: IntentGenericRefs,
        product_snapshot: ProductContextSnapshot,
    ) -> FrontDeskIntentBundle:
        worker = self._worker_or_fail(session, "intent bundle authoring")
        visible_refs = [
            PRODUCT_INQUIRY_PROFILE_REF,
            CORE_NEED_BRIEF_REF,
            SEMANTIC_LOCK_REF,
            MISSION_BRIEF_REF,
            SEMANTIC_COVERAGE_REF,
            SOLUTION_PLAN_REF,
            MISSION_PLAN_REF,
            SOURCE_ADMISSION_REPORT_REF,
            SANITIZED_SOURCES_REF,
        ]
        self.pi_node_runner.run_node(
            node_name="intent_bundle_author",
            session_id=session.session_id,
            visible_refs=visible_refs,
            expected_outputs=[INTENT_BUNDLE_CANDIDATE_REF],
            worker=worker,
            workspace=self.workspace.workspace,
            product_profile_hash=profile.profile_hash,
        )
        self._require_ai_artifact(
            session,
            INTENT_BUNDLE_CANDIDATE_REF,
            "intent_bundle_author",
            product_profile_hash=profile.profile_hash,
        )
        candidate = FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_CANDIDATE_REF))
        return self._finalize_product_intent_candidate(
            session=session,
            profile=profile,
            candidate=candidate,
            generic_refs=generic_refs,
            product_snapshot=product_snapshot,
        )

    def _finalize_product_intent_candidate(
        self,
        *,
        session: FrontDeskAuthoringSession,
        profile: ProductInquiryProfile,
        candidate: FrontDeskIntentBundle,
        generic_refs: IntentGenericRefs,
        product_snapshot: ProductContextSnapshot,
    ) -> FrontDeskIntentBundle:
        if candidate.session_id != session.session_id:
            raise ContractValidationError("intent bundle candidate session_id does not match FrontDesk session")
        if candidate.product_context.product_id != profile.product_id:
            raise ContractValidationError("intent bundle candidate product_id does not match ProductInquiryProfile")
        if candidate.product_context.profile_hash != profile.profile_hash:
            raise ContractValidationError("intent bundle candidate profile_hash does not match ProductInquiryProfile")
        expected_slot_ids = set(profile.slot_ids)
        candidate_slot_ids = {slot.slot_id for slot in candidate.slot_values}
        if candidate_slot_ids != expected_slot_ids:
            missing = sorted(expected_slot_ids - candidate_slot_ids)
            extra = sorted(candidate_slot_ids - expected_slot_ids)
            raise ContractValidationError(
                f"intent bundle candidate slot set mismatch; missing={missing}, extra={extra}"
            )
        slot_by_id = {slot.slot_id: slot for slot in profile.slots}
        for slot_value in candidate.slot_values:
            slot = slot_by_id[slot_value.slot_id]
            self._validate_slot_value_against_profile(slot_value, slot)
            self._validate_source_policy(profile, slot_value.source_refs, f"slot:{slot_value.slot_id}")
        for hypothesis in candidate.product_hypotheses:
            self._validate_source_policy(profile, hypothesis.source_refs, f"hypothesis:{hypothesis.hypothesis_id}")
        for risk in candidate.risk_flags:
            self._validate_source_policy(profile, risk.source_refs, f"risk:{risk.risk_id}")
        self._validate_source_policy(profile, candidate.evidence_refs, "intent_bundle.evidence_refs")
        missing_blocking_slots = self._missing_blocking_slots(profile, list(candidate.slot_values))
        clarification_questions = list(candidate.clarification_questions)
        for slot_value in candidate.slot_values:
            if slot_value.slot_id in missing_blocking_slots and slot_value.question:
                clarification_questions.append(slot_value.question)
        clarification_questions = _unique_non_empty(clarification_questions)
        readiness = self._intent_readiness(profile, missing_blocking_slots)
        return FrontDeskIntentBundle(
            session_id=session.session_id,
            intent_bundle_ref=INTENT_BUNDLE_REF,
            generic_refs=generic_refs,
            product_context=product_snapshot,
            slot_values=list(candidate.slot_values),
            product_hypotheses=list(candidate.product_hypotheses),
            risk_flags=list(candidate.risk_flags),
            missing_blocking_slots=missing_blocking_slots,
            readiness=readiness,
            clarification_questions=clarification_questions,
            evidence_refs=list(candidate.evidence_refs),
        )

    def _validate_slot_value_against_profile(self, slot_value: SlotValue, slot) -> None:
        if slot.value_type == SlotValueType.ENUM and slot_value.status in {
            SlotValueStatus.CONFIRMED,
            SlotValueStatus.INFERRED,
            SlotValueStatus.ASSUMED,
        }:
            if str(slot_value.value) not in set(slot.choices):
                raise ContractValidationError(f"slot {slot.slot_id} value is not one of the declared choices")
        if slot.value_type in {SlotValueType.REF, SlotValueType.ARTIFACT_PATH} and slot_value.value:
            validate_ref(str(slot_value.value), f"slot_value.{slot.slot_id}.value")
        if slot.value_type in {SlotValueType.REF_LIST, SlotValueType.ARTIFACT_PATH_LIST} and slot_value.value:
            if not isinstance(slot_value.value, list):
                raise ContractValidationError(f"slot {slot.slot_id} requires a list value")
            for item in slot_value.value:
                validate_ref(str(item), f"slot_value.{slot.slot_id}.value[]")

    def _validate_source_policy(self, profile: ProductInquiryProfile, refs: list[str], label: str) -> None:
        allowed = set(profile.source_policy.allowed_source_refs)
        excluded = set(profile.source_policy.excluded_source_refs)
        for ref in refs:
            safe = validate_ref(ref, f"{label}.source_refs[]")
            if safe in excluded:
                raise ContractValidationError(f"{label} cites excluded source ref: {safe}")
            if allowed and safe not in allowed:
                raise ContractValidationError(f"{label} cites source ref outside product source policy: {safe}")

    def _ensure_intent_artifacts(self, session_ref: str) -> None:
        session = self.load_session(session_ref)
        if not self.workspace.exists(WORKSPACE_FACTS_REF):
            self.scout(session_ref)
        if not self.workspace.exists(NEED_GRILLING_REPORT_REF):
            self._fail_llm_required(session, "intent bundle authoring")
        self._require_ai_artifact(session, NEED_GRILLING_REPORT_REF, "need_griller")
        if not self.workspace.exists(CORE_NEED_BRIEF_REF):
            self._fail_llm_required(session, "intent bundle authoring")
        self._require_ai_artifact(session, CORE_NEED_BRIEF_REF, "need_griller")
        if not self.workspace.exists(SEMANTIC_COVERAGE_REF):
            self.cover_semantics(session_ref)
        if not self.workspace.exists(SOLUTION_PLAN_REF):
            self._fail_llm_required(session, "intent bundle authoring")
        self._require_ai_artifact(session, SOLUTION_PLAN_REF, "solution_architect")
        if not self.workspace.exists(MISSION_PLAN_REF):
            self._fail_llm_required(session, "intent bundle authoring")
        self._require_ai_artifact(session, MISSION_PLAN_REF, "solution_architect")

    def _intent_generic_refs(self, session: FrontDeskAuthoringSession) -> IntentGenericRefs:
        return IntentGenericRefs(
            session_ref=session.session_ref,
            workspace_facts_ref=self._existing_ref(WORKSPACE_FACTS_REF),
            source_admission_report_ref=self._existing_ref(SOURCE_ADMISSION_REPORT_REF),
            core_need_brief_ref=self._existing_ref(CORE_NEED_BRIEF_REF),
            sanitized_sources_ref=self._existing_ref(SANITIZED_SOURCES_REF),
            semantic_lock_ref=self._existing_ref(SEMANTIC_LOCK_REF),
            mission_brief_ref=self._existing_ref(MISSION_BRIEF_REF),
            semantic_coverage_ref=self._existing_ref(SEMANTIC_COVERAGE_REF),
            solution_plan_ref=self._existing_ref(SOLUTION_PLAN_REF),
            mission_plan_ref=self._existing_ref(MISSION_PLAN_REF),
            mission_mapping_report_ref=self._existing_ref(MISSION_MAPPING_REPORT_REF),
            draft_mission_ref=self._existing_ref(DRAFT_MISSION_REF),
        )

    def _existing_ref(self, ref: str) -> str:
        return ref if self.workspace.exists(ref) else ""

    def _build_slot_values(
        self,
        profile: ProductInquiryProfile | None,
        generic_refs: IntentGenericRefs,
    ) -> list[SlotValue]:
        if profile is None:
            return []
        return [self._slot_value_for(slot, generic_refs) for slot in profile.slots]

    def _slot_value_for(self, slot, generic_refs: IntentGenericRefs) -> SlotValue:
        if slot.default_value not in (None, "", []):
            return SlotValue(
                slot_id=slot.slot_id,
                status=SlotValueStatus.ASSUMED,
                value=slot.default_value,
                confidence="assumed",
                source_refs=[],
                question=slot.question,
            )
        return SlotValue(
            slot_id=slot.slot_id,
            status=SlotValueStatus.MISSING,
            value=None,
            confidence="missing",
            source_refs=[],
            question=slot.question,
        )

    def _missing_blocking_slots(
        self,
        profile: ProductInquiryProfile | None,
        slot_values: list[SlotValue],
    ) -> list[str]:
        if profile is None:
            return []
        missing_ids = {
            slot.slot_id
            for slot in slot_values
            if slot.status == SlotValueStatus.MISSING
        }
        blocking_ids = set(profile.compiler_readiness.blocking_slot_ids)
        blocking_ids.update(slot.slot_id for slot in profile.slots if slot.requirement == SlotRequirement.BLOCKING)
        return sorted(missing_ids & blocking_ids)

    def _intent_readiness(
        self,
        profile: ProductInquiryProfile | None,
        missing_blocking_slots: list[str],
    ) -> IntentBundleReadiness:
        if profile is None:
            return IntentBundleReadiness.GENERIC_COMPILE_ONLY
        if missing_blocking_slots:
            return IntentBundleReadiness.NEEDS_CLARIFICATION
        return IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE

    def _product_hypotheses(self, generic_refs: IntentGenericRefs) -> list[ProductHypothesis]:
        core_need = self._read_core_need()
        brief = self._read_mission_brief()
        statement = (core_need.desired_outcome if core_need else "") or (brief.goal if brief else "")
        if not statement:
            return []
        return [
            ProductHypothesis(
                hypothesis_id="generic_user_outcome",
                statement=statement,
                confidence="inferred",
                source_refs=[ref for ref in (generic_refs.core_need_brief_ref, generic_refs.mission_brief_ref) if ref],
            )
        ]

    def _risk_flags(
        self,
        profile: ProductInquiryProfile | None,
        generic_refs: IntentGenericRefs,
    ) -> list[RiskFlag]:
        if profile is None:
            return []
        return [
            RiskFlag(
                risk_id=risk.risk_id,
                status="needs_review",
                rationale=risk.description,
                source_refs=[generic_refs.solution_plan_ref] if generic_refs.solution_plan_ref else [],
            )
            for risk in profile.risk_dimensions
        ]

    def _read_core_need(self) -> CoreNeedBrief | None:
        if not self.workspace.exists(CORE_NEED_BRIEF_REF):
            return None
        return CoreNeedBrief.from_dict(self.workspace.read_json(CORE_NEED_BRIEF_REF))

    def _read_mission_brief(self) -> MissionBrief | None:
        if not self.workspace.exists(MISSION_BRIEF_REF):
            return None
        return MissionBrief.from_dict(self.workspace.read_json(MISSION_BRIEF_REF))

    def _read_solution_plan(self) -> MissionSolutionPlan | None:
        if not self.workspace.exists(SOLUTION_PLAN_REF):
            return None
        return MissionSolutionPlan.from_dict(self.workspace.read_json(SOLUTION_PLAN_REF))

    def _read_mission_plan(self) -> MissionPlan | None:
        if not self.workspace.exists(MISSION_PLAN_REF):
            return None
        return MissionPlan.from_dict(self.workspace.read_json(MISSION_PLAN_REF))

    def _missing_product_slots(self) -> list[str]:
        if not self.workspace.exists(INTENT_BUNDLE_REF):
            return []
        return FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_REF)).missing_blocking_slots

    def _product_context_snapshot(self) -> dict[str, Any]:
        if not self.workspace.exists(INTENT_BUNDLE_REF):
            return {}
        return FrontDeskIntentBundle.from_dict(self.workspace.read_json(INTENT_BUNDLE_REF)).product_context.to_dict()

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

    def _fail_llm_required(self, session: FrontDeskAuthoringSession, operation: str) -> None:
        reason = (
            f"FrontDesk {operation} requires an explicit LLM/PiWorker node; "
            "deterministic fallback is forbidden"
        )
        try:
            failed = session.transition(FrontDeskStatus.FAILED_CLOSED, next_action="configure_frontdesk_llm")
            self.workspace.write_json(failed.session_ref, failed.to_dict())
        except ContractValidationError:
            pass
        raise ContractValidationError(reason)

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


def _unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = value.strip()
        if text and text not in result:
            result.append(text)
    return result
