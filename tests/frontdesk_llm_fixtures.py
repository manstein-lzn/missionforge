from __future__ import annotations

from pathlib import Path

from missionforge import FrontDesk
from missionforge.frontdesk.schema import ProfileRecommendation, ProfileRecommendationKind, ProfileRecommendationSet
from missionforge.frontdesk.pi_node_runner import FrontDeskPiNodeRunner
from missionforge.frontdesk.spec_grill_schema import (
    CoreNeedBrief,
    DecisionNode,
    DecisionOption,
    DecisionStatus,
    DecisionTree,
    MissionSolutionPlan,
    NeedGrillingReadiness,
    NeedGrillingReport,
    PlanRiskRegister,
    SolutionPlanStatus,
)
from missionforge.frontdesk.state import (
    CORE_NEED_BRIEF_REF,
    DECISION_TREE_REF,
    MISSION_PLAN_REF,
    NEED_GRILLING_REPORT_REF,
    PLAN_RISK_REGISTER_REF,
    PROFILE_RECOMMENDATIONS_REF,
    SOLUTION_PLAN_MARKDOWN_REF,
    SOLUTION_PLAN_REF,
)
from missionforge.frontdesk.schema import MissionPlan
from missionforge.piworker_call import PiWorkerCall
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult


class ScriptedFrontDeskPiWorker:
    """Test-only PiWorker-compatible writer for preauthored FrontDesk artifacts."""

    adapter_family = "piworker"
    adapter_id = "scripted_frontdesk_piworker"

    def __init__(self, payloads: dict[str, object], *, text_payloads: dict[str, str] | None = None) -> None:
        self.payloads = dict(payloads)
        self.text_payloads = dict(text_payloads or {})
        self.seen_calls: list[PiWorkerCall] = []

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store=None,
        exit_criteria=None,
        stop_conditions=None,
    ) -> WorkerAdapterResult:
        self.seen_calls.append(call)
        produced_refs: list[str] = []
        root = Path(workspace)
        for ref in call.writable_refs:
            if ref in self.payloads:
                path = root / ref
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = self.payloads[ref]
                if hasattr(payload, "to_dict"):
                    payload = payload.to_dict()
                import json

                path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                produced_refs.append(ref)
            elif ref in self.text_payloads:
                path = root / ref
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(self.text_payloads[ref], encoding="utf-8")
                produced_refs.append(ref)
        report = ExecutionReport(
            report_id=f"R-{call.call_id}",
            work_unit_id=call.call_id,
            status="completed",
            produced_artifacts=produced_refs,
            changed_refs=produced_refs,
            evidence_refs=["evidence/frontdesk_scripted_piworker.json"],
            worker_claims=[],
            metrics={"adapter_id": self.adapter_id},
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{call.call_id}/execution_report.json",
            ),
            event_evidence_refs=["evidence/frontdesk_scripted_piworker.json"],
            metrics={"adapter_result_status": "completed"},
        )


def seed_llm_authored_frontdesk_artifacts(
    frontdesk: FrontDesk,
    session_ref: str,
    *,
    expected_artifacts: list[str],
    desired_outcome: str | None = None,
    target_users: list[str] | None = None,
    deliverable_type: str = "artifact",
    success_signals: list[str] | None = None,
    constraints: list[str] | None = None,
    non_goals: list[str] | None = None,
) -> None:
    """Write schema-valid artifacts as a test double for LLM-authored FrontDesk nodes."""

    session = frontdesk.load_session(session_ref)
    frontdesk.scout(session_ref)
    outcome = desired_outcome or f"Produce {', '.join(expected_artifacts)} as verifiable artifact(s)."
    signals = success_signals or [f"{artifact} exists." for artifact in expected_artifacts]
    users = target_users or ["missionforge_user"]
    decision_tree = DecisionTree(
        session_id=session.session_id,
        decisions=[
            DecisionNode(
                decision_id="D-core-need",
                topic="core_need",
                status=DecisionStatus.CONFIRMED,
                current_hypothesis=outcome,
                options=[
                    DecisionOption(option_id="O-structured-output", summary="User needs a structured deliverable."),
                ],
                blocking=True,
                source_refs=["frontdesk/session.json"],
                chosen_option_id="O-structured-output",
            )
        ],
    )
    core_need = CoreNeedBrief(
        session_id=session.session_id,
        core_pain="The user needs an LLM-interpreted requirement converted into a bounded deliverable.",
        target_users=users,
        usage_moment="Before MissionRuntime starts.",
        deliverable_type=deliverable_type,
        desired_outcome=outcome,
        success_signals=signals,
        constraints=list(constraints or []),
        non_goals=list(non_goals or ["Do not use raw conversation as runtime task truth."]),
        source_refs=["frontdesk/session.json"],
    )
    report = NeedGrillingReport(
        session_id=session.session_id,
        readiness=NeedGrillingReadiness.CORE_NEED_READY,
        observations=["LLM-authored test fixture captured the user need."],
        inferences=[outcome],
        confirmed_requirements=list(signals),
        open_decision_ids=[],
        next_question=None,
        decision_tree_ref=DECISION_TREE_REF,
        core_need_brief_ref=CORE_NEED_BRIEF_REF,
    )
    FrontDeskPiNodeRunner().run_node(
        node_name="need_griller",
        session_id=session.session_id,
        visible_refs=[
            "frontdesk/conversation.jsonl",
            "frontdesk/workspace_facts.json",
            "frontdesk/source_admission_report.json",
            "frontdesk/profile_catalog_snapshot.json",
        ],
        expected_outputs=[DECISION_TREE_REF, NEED_GRILLING_REPORT_REF],
        optional_outputs=[CORE_NEED_BRIEF_REF],
        worker=ScriptedFrontDeskPiWorker(
            {
                DECISION_TREE_REF: decision_tree,
                CORE_NEED_BRIEF_REF: core_need,
                NEED_GRILLING_REPORT_REF: report,
            }
        ),
        workspace=frontdesk.workspace.workspace,
    )
    frontdesk.cover_semantics(session_ref)
    solution = MissionSolutionPlan(
        session_id=session.session_id,
        status=SolutionPlanStatus.AWAITING_REVIEW,
        summary=f"LLM-authored solution plan for: {outcome}",
        core_need_ref=CORE_NEED_BRIEF_REF,
        mvp_scope=[outcome],
        future_scope=[],
        rejected_directions=["Do not turn raw conversation into runtime task truth."],
        expected_artifacts=list(expected_artifacts),
        selected_capability_profile_ids=["user_provided_evidence_only", "explicit_output_root"],
        selected_verification_profile_ids=["generic_local_verification"],
        verification_strategy=[f"Verify that {artifact} exists." for artifact in expected_artifacts],
        risks=list(constraints or []),
        authority_requirements=["plan_review", "authoring_approval"],
        source_refs=[CORE_NEED_BRIEF_REF],
    )
    risk_register = PlanRiskRegister(
        session_id=session.session_id,
        risks=list(constraints or []),
        mitigations=["Keep raw conversation provenance-only."],
        source_refs=[CORE_NEED_BRIEF_REF],
    )
    recommendations = ProfileRecommendationSet(
        session_id=session.session_id,
        recommendations=[
            ProfileRecommendation(
                profile_id="user_provided_evidence_only",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="FrontDesk admits sanitized source refs only.",
            ),
            ProfileRecommendation(
                profile_id="explicit_output_root",
                kind=ProfileRecommendationKind.CAPABILITY,
                rationale="The solution plan declares an output root.",
            ),
            ProfileRecommendation(
                profile_id="generic_local_verification",
                kind=ProfileRecommendationKind.VERIFICATION,
                rationale="Expected artifacts are locally checkable.",
            ),
        ],
    )
    mission_plan = MissionPlan(
        session_id=session.session_id,
        expected_artifacts=list(expected_artifacts),
        constraints=[],
        validators=[{"validator_type": "file_exists", "path": artifact} for artifact in expected_artifacts],
        manual_gates=[],
        risk_notes=list(constraints or []),
    )
    FrontDeskPiNodeRunner().run_node(
        node_name="solution_architect",
        session_id=session.session_id,
        visible_refs=[
            CORE_NEED_BRIEF_REF,
            "frontdesk/semantic_lock.json",
            "frontdesk/mission_brief.json",
            "frontdesk/semantic_coverage.json",
            "frontdesk/profile_catalog_snapshot.json",
        ],
        expected_outputs=[
            SOLUTION_PLAN_REF,
            SOLUTION_PLAN_MARKDOWN_REF,
            PLAN_RISK_REGISTER_REF,
            PROFILE_RECOMMENDATIONS_REF,
            MISSION_PLAN_REF,
        ],
        worker=ScriptedFrontDeskPiWorker(
            {
                SOLUTION_PLAN_REF: solution,
                PLAN_RISK_REGISTER_REF: risk_register,
                PROFILE_RECOMMENDATIONS_REF: recommendations,
                MISSION_PLAN_REF: mission_plan,
            },
            text_payloads={SOLUTION_PLAN_MARKDOWN_REF: f"# Solution Plan\n\n{solution.summary}\n"},
        ),
        workspace=frontdesk.workspace.workspace,
    )
