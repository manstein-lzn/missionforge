"""Kernel-backed DeepResearch v2 prototype.

This module is intentionally small: product code writes the academic request,
briefs, rubrics, and artifact refs, then lets MissionForge's root flow API own the
step execution, routing, retry, extension lock, and flow ledger boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

import missionforge as mf

from .citation_projector import CITATION_PROJECTION_VALIDATION_SCHEMA_VERSION, project_report_citations
from .product_contract import (
    AcademicResearchRequest,
    ResearchIntensity,
    ResearchIntensityProfile,
    research_intensity_profile,
    research_report_section_specs,
)
from .project_lifecycle import write_kernel_lifecycle_state, write_project_manifest
from .source_graph import project_source_graph
from .workspace import read_json_ref, write_json_ref, write_text_ref


_SOURCE_MAPPER_RUNTIME_MAX_TURNS = {
    ResearchIntensity.STANDARD: 12,
    ResearchIntensity.INTENSIVE: 18,
}

KERNEL_V2_RESULT_REF = "packages/deepresearch_kernel_v2_result.json"
KERNEL_V2_CONTRACT_REF = "contract/task_contract.json"
KERNEL_V2_WORKSPACE_POLICY_REF = "policy/workspace_policy.json"
KERNEL_V2_REQUEST_REF = "product_contract/research_request.json"
KERNEL_V2_OUTPUT_CONTRACT_REF = "product_contract/output_contract.json"
KERNEL_V2_PREVIOUS_RUN_INDEX_REF = "inputs/previous_run_index.json"
KERNEL_V2_SOURCE_MAPPER_BRIEF_REF = "manuals/source_mapper.md"
KERNEL_V2_RESEARCHER_BRIEF_REF = "manuals/researcher.md"
KERNEL_V2_REVIEWER_RUBRIC_REF = "rubrics/reviewer.md"
KERNEL_V2_JUDGE_RUBRIC_REF = "rubrics/judge.md"
KERNEL_V2_INITIAL_SOURCE_PACKET_REF = "sources/initial_source_packet.json"
KERNEL_V2_SOURCE_PACKET_REF = "sources/source_packet.json"
KERNEL_V2_CANONICAL_SOURCES_REF = "sources/canonical_sources.json"
KERNEL_V2_DEDUPE_MAP_REF = "sources/dedupe_map.json"
KERNEL_V2_SOURCE_GRAPH_REF = "sources/source_graph.json"
KERNEL_V2_FINAL_REPORT_REF = "reports/final_report.md"
KERNEL_V2_CITATION_PROJECTED_REPORT_REF = "reports/final_report.citation_projected.md"
KERNEL_V2_EVIDENCE_INDEX_REF = "reports/evidence_index.md"
KERNEL_V2_SOURCE_GAPS_REF = "reports/source_gaps.md"
KERNEL_V2_CITATION_REGISTRY_REF = "citations/citation_registry.json"
KERNEL_V2_REPORT_CITATION_MAP_REF = "citations/report_citation_map.json"
KERNEL_V2_INSIGHT_MAP_REF = "analysis/insight_map.json"
KERNEL_V2_CLAIM_INDEX_REF = "claims/claim_index.json"
KERNEL_V2_CLAIM_INDEX_VALIDATION_REF = "state/claim_index_validation.json"
KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF = "state/citation_projection_validation.json"
KERNEL_V2_REPORT_HTML_REF = "exports/final_report.html"
KERNEL_V2_RESEARCH_STATE_REF = "state/research_state.json"
KERNEL_V2_SOURCE_CONTROL_REF = "state/source_control.json"
KERNEL_V2_RESEARCHER_CONTROL_REF = "state/researcher_control.json"
KERNEL_V2_RUN_STATUS_REF = "state/run_status.json"
KERNEL_V2_REVIEWER_OBSERVATION_REF = "reviews/reviewer_observation.json"
KERNEL_V2_JUDGE_REPORT_REF = "judge/judge_report.json"
KERNEL_V2_USAGE_SUMMARY_REF = "metrics/usage_summary.json"


@dataclass(frozen=True)
class DeepResearchKernelV2Result:
    """Refs-first product result for the Kernel-backed DeepResearch v2 path."""

    request_id: str
    status: str
    run_workspace_ref: str
    result_ref: str
    flow_result_ref: str
    flow_ledger_ref: str
    run_events_ref: str
    run_snapshot_ref: str
    contract_ref: str
    final_report_ref: str
    citation_projected_report_ref: str
    report_html_ref: str
    source_packet_ref: str
    source_graph_ref: str
    canonical_sources_ref: str
    citation_registry_ref: str
    insight_map_ref: str
    claim_index_ref: str
    reviewer_observation_ref: str
    judge_report_ref: str
    usage_summary_ref: str
    run_status_ref: str
    draft_artifact_refs: list[str]
    evidence_refs: list[str]
    metric_refs: list[str]
    contract_hash: str
    schema_version: str = "missionforge_deepresearch.kernel_v2_result.v1"

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "status": self.status,
            "run_workspace_ref": self.run_workspace_ref,
            "result_ref": self.result_ref,
            "flow_result_ref": self.flow_result_ref,
            "flow_ledger_ref": self.flow_ledger_ref,
            "run_events_ref": self.run_events_ref,
            "run_snapshot_ref": self.run_snapshot_ref,
            "contract_ref": self.contract_ref,
            "final_report_ref": self.final_report_ref,
            "citation_projected_report_ref": self.citation_projected_report_ref,
            "report_html_ref": self.report_html_ref,
            "source_packet_ref": self.source_packet_ref,
            "source_graph_ref": self.source_graph_ref,
            "canonical_sources_ref": self.canonical_sources_ref,
            "citation_registry_ref": self.citation_registry_ref,
            "insight_map_ref": self.insight_map_ref,
            "claim_index_ref": self.claim_index_ref,
            "reviewer_observation_ref": self.reviewer_observation_ref,
            "judge_report_ref": self.judge_report_ref,
            "usage_summary_ref": self.usage_summary_ref,
            "run_status_ref": self.run_status_ref,
            "draft_artifact_refs": list(self.draft_artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "metric_refs": list(self.metric_refs),
            "contract_hash": self.contract_hash,
        }

    def validate(self) -> None:
        if self.schema_version != "missionforge_deepresearch.kernel_v2_result.v1":
            raise mf.ContractValidationError("deepresearch_kernel_v2_result.schema_version is unsupported")
        for field_name in (
            "run_workspace_ref",
            "result_ref",
            "flow_result_ref",
            "flow_ledger_ref",
            "run_events_ref",
            "run_snapshot_ref",
            "contract_ref",
            "final_report_ref",
            "citation_projected_report_ref",
            "report_html_ref",
            "source_packet_ref",
            "source_graph_ref",
            "canonical_sources_ref",
            "citation_registry_ref",
            "insight_map_ref",
            "claim_index_ref",
            "reviewer_observation_ref",
            "judge_report_ref",
            "usage_summary_ref",
            "run_status_ref",
        ):
            mf.validate_ref(getattr(self, field_name), f"deepresearch_kernel_v2_result.{field_name}")
        for ref in [*self.draft_artifact_refs, *self.evidence_refs, *self.metric_refs]:
            mf.validate_ref(ref, "deepresearch_kernel_v2_result.refs[]")
        if not self.contract_hash.startswith("sha256:"):
            raise mf.ContractValidationError("deepresearch_kernel_v2_result.contract_hash must be a sha256 hash")
        mf.assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_kernel_v2_result")


def run_deepresearch_kernel_v2(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    adapter: mf.PiWorkerCallAdapter | None = None,
    live_extension_mode: bool = False,
    extension_installer: Any | None = None,
    resume: bool = True,
    event_sink: Callable[[mf.FlowLedgerEvent], None] | None = None,
    runtime_progress_sink: mf.PiWorkerProgressSink | None = None,
) -> DeepResearchKernelV2Result:
    """Run the thin Kernel-backed DeepResearch v2 flow."""

    request.validate()
    root = Path(workspace).resolve()
    run_ref = f"runs/{request.request_id}"
    run_root = root / run_ref
    run_root.mkdir(parents=True, exist_ok=True)
    write_project_manifest(run_root, request_id=request.request_id)
    contract = _task_contract(request)
    contract_hash = mf.stable_json_hash(contract)
    flow = build_deepresearch_kernel_v2_flow(request, live_extension_mode=live_extension_mode)
    profile = research_intensity_profile(request.research_intensity)
    _write_kernel_v2_workspace(request, root=root, run_root=run_root, contract=contract)
    context = mf.StepCompileContext(
        flow_id=deepresearch_kernel_v2_flow_run_id(request.request_id),
        contract_id=contract["contract_id"],
        contract_hash=contract_hash,
        contract_ref=KERNEL_V2_CONTRACT_REF,
        workspace_policy_ref=KERNEL_V2_WORKSPACE_POLICY_REF,
    )
    flow_result = mf.run_flow(
        flow,
        context=context,
        workspace=run_root,
        adapter=_require_adapter(adapter),
        extension_lock_mode="install" if live_extension_mode else "verify-installed",
        extension_installer=extension_installer,
        max_steps=_kernel_v2_max_steps(profile.max_review_rounds),
        resume=resume,
        event_sink=event_sink,
        interaction_port=mf.FileInteractionPort(run_root),
        runtime_progress_sink=runtime_progress_sink,
    )
    _write_kernel_v2_source_graph(run_root)
    _write_kernel_v2_citation_projection(run_root)
    _write_kernel_v2_report_html(run_root)
    _write_kernel_v2_claim_index_validation(run_root)
    product_status = _kernel_v2_product_status(run_root, flow_result)
    usage_summary_ref = _write_kernel_v2_usage_summary(request, run_root=run_root, flow_result=flow_result)
    status_ref = _write_kernel_v2_run_status(
        request,
        run_root=run_root,
        flow_result=flow_result,
        product_status=product_status,
    )
    result = _kernel_v2_result(
        request=request,
        run_ref=run_ref,
        run_root=run_root,
        contract_hash=contract_hash,
        flow_result=flow_result,
        usage_summary_ref=usage_summary_ref,
        status_ref=status_ref,
        product_status=product_status,
    )
    write_json_ref(root, result.result_ref, result.to_dict())
    write_kernel_lifecycle_state(
        run_root,
        request_id=request.request_id,
        product_status=product_status,
        flow_result=flow_result,
        result_ref=KERNEL_V2_RESULT_REF,
        contract_ref=KERNEL_V2_CONTRACT_REF,
        run_status_ref=KERNEL_V2_RUN_STATUS_REF,
        research_state_ref=KERNEL_V2_RESEARCH_STATE_REF,
        final_report_ref=KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
    )
    return result


def deepresearch_kernel_v2_flow_run_id(request_id: str) -> str:
    """Return the product flow run id used by Kernel v2 and interaction events."""

    return f"deepresearch-v2-{request_id}"


def build_deepresearch_kernel_v2_flow(
    request: AcademicResearchRequest,
    *,
    live_extension_mode: bool = False,
) -> mf.Flow:
    """Declare the product flow without product-specific Python routing."""

    profile = research_intensity_profile(request.research_intensity)
    tools = ["read", "write", "edit", "academic"] if live_extension_mode else ["read", "write", "edit"]
    toolsets = [
        mf.Toolset(
            id="academic",
            package="local:extensions/pi-academic-sources",
            tools=["academic_provider_capabilities", "academic_search", "academic_fetch", "citation_lookup", "repo_search"],
            capability=mf.ExtensionCapability.WEB,
            network=True,
        )
    ] if live_extension_mode else []
    source_mapper = mf.Step(
        id="source_mapper",
        brief="Map the DeepResearch evidence base, write a durable source packet and research state, then hand off to synthesis.",
        inputs=[
            KERNEL_V2_CONTRACT_REF,
            KERNEL_V2_REQUEST_REF,
            KERNEL_V2_SOURCE_MAPPER_BRIEF_REF,
            KERNEL_V2_OUTPUT_CONTRACT_REF,
            KERNEL_V2_INITIAL_SOURCE_PACKET_REF,
            *_request_input_refs(request),
        ],
        outputs=[
            KERNEL_V2_SOURCE_PACKET_REF,
            KERNEL_V2_EVIDENCE_INDEX_REF,
            KERNEL_V2_SOURCE_GAPS_REF,
            KERNEL_V2_RESEARCH_STATE_REF,
            KERNEL_V2_SOURCE_CONTROL_REF,
        ],
        read=["contract", "product_contract", "manuals", "inputs", "sources", "reports", "state"],
        write=["sources", "reports", "state"],
        tools=tools,
        route_on=KERNEL_V2_SOURCE_CONTROL_REF,
        route_fields=["decision"],
        runtime_budget={
            "timeout_seconds": profile.piworker_timeout_seconds,
            "max_turns": _source_mapper_max_turns(profile.intensity),
        },
        network=live_extension_mode,
        failure=mf.FailurePolicy(retries=0, on_exhausted=mf.StepStatus.BLOCKED),
    )
    researcher = mf.Step(
        id="researcher",
        brief="Own DeepResearch synthesis: turn the source packet into insight, claim audit, final report, and hand off to review.",
        inputs=[
            KERNEL_V2_CONTRACT_REF,
            KERNEL_V2_REQUEST_REF,
            KERNEL_V2_RESEARCHER_BRIEF_REF,
            KERNEL_V2_OUTPUT_CONTRACT_REF,
            *_request_input_refs(request),
            KERNEL_V2_SOURCE_PACKET_REF,
            KERNEL_V2_EVIDENCE_INDEX_REF,
            KERNEL_V2_SOURCE_GAPS_REF,
            KERNEL_V2_RESEARCH_STATE_REF,
            KERNEL_V2_SOURCE_CONTROL_REF,
        ],
        outputs=[
            KERNEL_V2_FINAL_REPORT_REF,
            KERNEL_V2_EVIDENCE_INDEX_REF,
            KERNEL_V2_SOURCE_GAPS_REF,
            KERNEL_V2_INSIGHT_MAP_REF,
            KERNEL_V2_CLAIM_INDEX_REF,
            KERNEL_V2_RESEARCH_STATE_REF,
            KERNEL_V2_RESEARCHER_CONTROL_REF,
        ],
        read=["contract", "product_contract", "manuals", "inputs", "sources", "reports", "analysis", "claims", "reviews", "judge", "state"],
        write=["reports", "analysis", "claims", "state"],
        tools=["read", "write", "edit"],
        route_on=KERNEL_V2_RESEARCHER_CONTROL_REF,
        route_fields=["decision"],
        runtime_budget={"timeout_seconds": profile.piworker_timeout_seconds},
        network=False,
        failure=mf.FailurePolicy(retries=0, on_exhausted=mf.StepStatus.BLOCKED),
    )
    reviewer = mf.Step(
        id="reviewer",
        brief="Review the researcher-owned DeepResearch workspace and decide whether it needs another researcher pass or judge handoff.",
        inputs=[
            KERNEL_V2_CONTRACT_REF,
            KERNEL_V2_REQUEST_REF,
            KERNEL_V2_REVIEWER_RUBRIC_REF,
            *_request_input_refs(request),
            KERNEL_V2_SOURCE_PACKET_REF,
            KERNEL_V2_FINAL_REPORT_REF,
            KERNEL_V2_EVIDENCE_INDEX_REF,
            KERNEL_V2_SOURCE_GAPS_REF,
            KERNEL_V2_INSIGHT_MAP_REF,
            KERNEL_V2_CLAIM_INDEX_REF,
            KERNEL_V2_RESEARCH_STATE_REF,
            KERNEL_V2_RESEARCHER_CONTROL_REF,
        ],
        outputs=[KERNEL_V2_REVIEWER_OBSERVATION_REF],
        read=["contract", "product_contract", "rubrics", "inputs", "sources", "reports", "analysis", "claims", "state"],
        write=["reviews"],
        role=mf.PiWorkerCallRole.EXECUTOR,
        route_on=KERNEL_V2_REVIEWER_OBSERVATION_REF,
        route_fields=["decision"],
        runtime_budget={"timeout_seconds": profile.piworker_timeout_seconds},
        failure=mf.FailurePolicy(retries=1, on_exhausted=mf.StepStatus.BLOCKED),
    )
    judge = mf.Step(
        id="judge",
        brief="Independently judge the final DeepResearch package against the frozen contract and rubric.",
        inputs=[
            KERNEL_V2_CONTRACT_REF,
            KERNEL_V2_REQUEST_REF,
            KERNEL_V2_JUDGE_RUBRIC_REF,
            *_request_input_refs(request),
            KERNEL_V2_SOURCE_PACKET_REF,
            KERNEL_V2_FINAL_REPORT_REF,
            KERNEL_V2_EVIDENCE_INDEX_REF,
            KERNEL_V2_SOURCE_GAPS_REF,
            KERNEL_V2_INSIGHT_MAP_REF,
            KERNEL_V2_CLAIM_INDEX_REF,
            KERNEL_V2_RESEARCH_STATE_REF,
            KERNEL_V2_REVIEWER_OBSERVATION_REF,
        ],
        outputs=[KERNEL_V2_JUDGE_REPORT_REF],
        read=["contract", "product_contract", "rubrics", "inputs", "sources", "reports", "analysis", "claims", "reviews", "state"],
        write=["judge"],
        role=mf.PiWorkerCallRole.JUDGE,
        route_on=KERNEL_V2_JUDGE_REPORT_REF,
        route_fields=["decision"],
        runtime_budget={"timeout_seconds": profile.piworker_timeout_seconds},
        failure=mf.FailurePolicy(retries=1, on_exhausted=mf.StepStatus.BLOCKED),
    )
    return mf.Flow(
        id="deepresearch-v2",
        steps=[source_mapper, researcher, reviewer, judge],
        routes={
            "source_mapper.ready_for_synthesis": "researcher",
            "source_mapper.continue": "source_mapper",
            "source_mapper.blocked": mf.Flow.stop("blocked"),
            "researcher.ready_for_review": "reviewer",
            "researcher.continue": "researcher",
            "researcher.blocked": mf.Flow.stop("blocked"),
            "reviewer.ready_for_judge": "judge",
            "reviewer.revise_report": "researcher",
            "reviewer.continue": "source_mapper",
            "reviewer.blocked": mf.Flow.stop("blocked"),
            "reviewer.rejected": mf.Flow.stop("failed"),
            "judge.accepted": mf.Flow.stop("accepted"),
            "judge.repair": "researcher",
            "judge.revision_required": mf.Flow.stop("blocked"),
            "judge.rejected": mf.Flow.stop("failed"),
        },
        artifacts=[
            mf.Artifact(KERNEL_V2_SOURCE_PACKET_REF, role=mf.ArtifactRole.STATE, owner="piworker"),
            mf.Artifact(KERNEL_V2_CANONICAL_SOURCES_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_DEDUPE_MAP_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_SOURCE_GRAPH_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_FINAL_REPORT_REF, role=mf.ArtifactRole.OUTPUT, owner="piworker"),
            mf.Artifact(KERNEL_V2_CITATION_PROJECTED_REPORT_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_CITATION_REGISTRY_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_REPORT_CITATION_MAP_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_EVIDENCE_INDEX_REF, role=mf.ArtifactRole.OUTPUT, owner="piworker"),
            mf.Artifact(KERNEL_V2_SOURCE_GAPS_REF, role=mf.ArtifactRole.OUTPUT, owner="piworker"),
            mf.Artifact(KERNEL_V2_INSIGHT_MAP_REF, role=mf.ArtifactRole.STATE, owner="piworker"),
            mf.Artifact(KERNEL_V2_CLAIM_INDEX_REF, role=mf.ArtifactRole.STATE, owner="piworker"),
            mf.Artifact(KERNEL_V2_CLAIM_INDEX_VALIDATION_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_REPORT_HTML_REF, role=mf.ArtifactRole.PROJECTION, owner="runtime"),
            mf.Artifact(KERNEL_V2_RESEARCH_STATE_REF, role=mf.ArtifactRole.STATE, owner="piworker"),
            mf.Artifact(KERNEL_V2_RUN_STATUS_REF, role=mf.ArtifactRole.STATE, owner="runtime"),
            mf.Artifact(KERNEL_V2_SOURCE_CONTROL_REF, role=mf.ArtifactRole.DECISION, owner="piworker"),
            mf.Artifact(KERNEL_V2_RESEARCHER_CONTROL_REF, role=mf.ArtifactRole.DECISION, owner="piworker"),
            mf.Artifact(KERNEL_V2_REVIEWER_OBSERVATION_REF, role=mf.ArtifactRole.DECISION, owner="piworker"),
            mf.Artifact(KERNEL_V2_JUDGE_REPORT_REF, role=mf.ArtifactRole.DECISION, owner="piworker"),
        ],
        toolsets=toolsets,
    )


class KernelV2FixtureAdapter:
    """Fixture worker for validating Kernel v2 wiring only."""

    adapter_family = "fixture_deepresearch_kernel_v2"

    def run_call(
        self,
        call: mf.PiWorkerCall,
        *,
        workspace: str | Path = ".",
        **_kwargs: Any,
    ) -> mf.WorkerAdapterResult:
        step_id = str(call.metadata.get("kernel_step_id", ""))
        if step_id == "source_mapper":
            self._write_source_mapper_outputs(Path(workspace), call)
        elif step_id == "researcher":
            self._write_researcher_outputs(Path(workspace), call)
        elif step_id == "reviewer":
            self._write_reviewer_outputs(Path(workspace), call)
        elif step_id == "judge":
            self._write_judge_outputs(Path(workspace), call)
        else:
            raise mf.ContractValidationError(f"unknown kernel v2 fixture step: {step_id}")
        report_ref = f"attempts/{call.call_id}/execution_report.json"
        metrics_ref = f"attempts/{call.call_id}/metrics.json"
        write_json_ref(workspace, metrics_ref, {"fixture": True, "step_id": step_id})
        report = mf.ExecutionReport(
            report_id=f"deepresearch-kernel-v2-{step_id}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=list(call.expected_output_refs),
            changed_refs=[*call.expected_output_refs, report_ref, metrics_ref],
            evidence_refs=[ref for ref in call.expected_output_refs if ref.endswith(".json")],
            metrics={"metric_ref": metrics_ref},
        )
        write_json_ref(workspace, report_ref, report.to_dict())
        return mf.WorkerAdapterResult(
            execution_report=report,
            worker_result=mf.WorkerResult(status="completed", execution_report_ref=report_ref),
            metrics={"metric_ref": metrics_ref},
        )

    def _write_source_mapper_outputs(self, workspace: Path, call: mf.PiWorkerCall) -> None:
        request = read_json_ref(workspace, KERNEL_V2_REQUEST_REF, "kernel_v2_request")
        source_packet = _fixture_source_packet(request)
        write_json_ref(workspace, KERNEL_V2_SOURCE_PACKET_REF, source_packet)
        write_text_ref(workspace, KERNEL_V2_EVIDENCE_INDEX_REF, _reference_lines(source_packet))
        write_text_ref(workspace, KERNEL_V2_SOURCE_GAPS_REF, "Fixture mode validates Kernel v2 wiring, not live coverage.\n")
        write_json_ref(workspace, KERNEL_V2_RESEARCH_STATE_REF, _fixture_research_state(source_packet))
        write_json_ref(
            workspace,
            KERNEL_V2_SOURCE_CONTROL_REF,
            {
                "schema_version": "missionforge_deepresearch.kernel_v2.source_control.v1",
                "decision": "ready_for_synthesis",
                "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
                "research_state_ref": KERNEL_V2_RESEARCH_STATE_REF,
                "coverage_note": "Fixture source mapping is complete for wiring tests.",
            },
        )

    def _write_researcher_outputs(self, workspace: Path, call: mf.PiWorkerCall) -> None:
        request = read_json_ref(workspace, KERNEL_V2_REQUEST_REF, "kernel_v2_request")
        source_packet = read_json_ref(workspace, KERNEL_V2_SOURCE_PACKET_REF, "kernel_v2_source_packet")
        write_text_ref(workspace, KERNEL_V2_FINAL_REPORT_REF, _fixture_report(request, source_packet))
        write_text_ref(workspace, KERNEL_V2_EVIDENCE_INDEX_REF, _reference_lines(source_packet))
        write_text_ref(workspace, KERNEL_V2_SOURCE_GAPS_REF, "Fixture mode validates Kernel v2 wiring, not live coverage.\n")
        write_json_ref(workspace, KERNEL_V2_INSIGHT_MAP_REF, _fixture_insight_map(source_packet))
        write_json_ref(workspace, KERNEL_V2_CLAIM_INDEX_REF, _fixture_claim_index(source_packet))
        write_json_ref(workspace, KERNEL_V2_RESEARCH_STATE_REF, _fixture_research_state(source_packet))
        write_json_ref(
            workspace,
            KERNEL_V2_RESEARCHER_CONTROL_REF,
            {
                "schema_version": "missionforge_deepresearch.kernel_v2.researcher_control.v1",
                "decision": "ready_for_review",
                "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
                "final_report_ref": KERNEL_V2_FINAL_REPORT_REF,
                "insight_map_ref": KERNEL_V2_INSIGHT_MAP_REF,
                "research_state_ref": KERNEL_V2_RESEARCH_STATE_REF,
            },
        )

    def _write_reviewer_outputs(self, workspace: Path, call: mf.PiWorkerCall) -> None:
        write_json_ref(
            workspace,
            KERNEL_V2_REVIEWER_OBSERVATION_REF,
            {
                "schema_version": "missionforge_deepresearch.kernel_v2.reviewer_observation.v1",
                "decision": "ready_for_judge",
                "reviewer_report_ref": KERNEL_V2_REVIEWER_OBSERVATION_REF,
                "blocking_gaps": [],
                "next_directive_ref": "",
            },
        )

    def _write_judge_outputs(self, workspace: Path, call: mf.PiWorkerCall) -> None:
        write_json_ref(
            workspace,
            KERNEL_V2_JUDGE_REPORT_REF,
            {
                "schema_version": "missionforge_deepresearch.kernel_v2.judge_report.v1",
                "decision": "accepted",
                "accepted_artifact_refs": [KERNEL_V2_FINAL_REPORT_REF, KERNEL_V2_SOURCE_PACKET_REF],
                "residual_risks": ["Fixture mode does not judge live research quality."],
            },
        )


def _write_kernel_v2_workspace(
    request: AcademicResearchRequest,
    *,
    root: Path,
    run_root: Path,
    contract: Mapping[str, Any],
) -> None:
    write_json_ref(run_root, KERNEL_V2_REQUEST_REF, request.to_dict())
    write_json_ref(run_root, KERNEL_V2_CONTRACT_REF, contract)
    _write_previous_run_inputs(request, root=root, run_root=run_root)
    write_json_ref(run_root, KERNEL_V2_WORKSPACE_POLICY_REF, {"policy_id": "deepresearch-kernel-v2", "root_ref": "."})
    write_json_ref(run_root, KERNEL_V2_OUTPUT_CONTRACT_REF, _output_contract(request))
    write_json_ref(run_root, KERNEL_V2_INITIAL_SOURCE_PACKET_REF, _empty_source_packet(request))
    write_text_ref(run_root, KERNEL_V2_SOURCE_MAPPER_BRIEF_REF, _source_mapper_brief(request))
    write_text_ref(run_root, KERNEL_V2_RESEARCHER_BRIEF_REF, _researcher_brief(request))
    write_text_ref(run_root, KERNEL_V2_REVIEWER_RUBRIC_REF, _reviewer_rubric(request))
    write_text_ref(run_root, KERNEL_V2_JUDGE_RUBRIC_REF, _judge_rubric(request))


def _task_contract(request: AcademicResearchRequest) -> dict[str, Any]:
    profile = research_intensity_profile(request.research_intensity)
    request_payload = request.to_dict()
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2_task_contract.v1",
        "contract_id": f"deepresearch-kernel-v2-{request.request_id}",
        "request_ref": KERNEL_V2_REQUEST_REF,
        "request_payload_hash": mf.stable_json_hash(request_payload),
        "request": request_payload,
        "objective": f"Produce a citation-backed academic deep research report for: {request.topic}",
        "audience": request.audience,
        "language": request.language,
        "research_intensity": profile.intensity.value,
        "research_intensity_guidance": profile.guidance,
        "required_report_sections": research_report_section_specs(request.language),
        "authority": "frozen_kernel_v2_contract",
    }


def _require_adapter(adapter: mf.PiWorkerCallAdapter | None) -> mf.PiWorkerCallAdapter:
    if adapter is None:
        raise mf.ContractValidationError("deepresearch_kernel_v2 requires an explicit PiWorker adapter")
    return adapter


def _write_previous_run_inputs(request: AcademicResearchRequest, *, root: Path, run_root: Path) -> None:
    if not request.previous_run_refs:
        return
    entries = []
    for index, previous_ref in enumerate(request.previous_run_refs, start=1):
        source_path = root / previous_ref
        if not source_path.is_file():
            raise mf.ContractValidationError(f"previous_run_ref does not exist: {previous_ref}")
        staged_ref = f"inputs/previous_runs/{index:03d}-{source_path.name}"
        staged_path = run_root / staged_ref
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(source_path.read_bytes())
        entries.append(
            {
                "previous_run_ref": previous_ref,
                "staged_ref": staged_ref,
            }
        )
    write_json_ref(
        run_root,
        KERNEL_V2_PREVIOUS_RUN_INDEX_REF,
        {
            "schema_version": "missionforge_deepresearch.kernel_v2.previous_run_index.v1",
            "entries": entries,
        },
    )


def _request_input_refs(request: AcademicResearchRequest) -> list[str]:
    refs = list(request.seed_pdf_refs)
    if request.sample_report_ref:
        refs.append(request.sample_report_ref)
    if request.previous_run_refs:
        refs.append(KERNEL_V2_PREVIOUS_RUN_INDEX_REF)
    return _dedupe_refs(refs)


def _source_budget_guidance(request: AcademicResearchRequest, profile: ResearchIntensityProfile) -> str:
    target = request.target_source_count or profile.max_sources
    return (
        f"Source-count budget guidance: aim around {target} source records when the topic needs that scale, "
        "and exceed or undershoot it only with an explicit coverage rationale in `reports/source_gaps.md` "
        "and `state/research_state.json`."
    )


def _optional_input_guidance(request: AcademicResearchRequest) -> list[str]:
    guidance = []
    if request.seed_papers:
        guidance.append(
            "Optional seed papers are frozen in `contract/research_request.json.seed_papers`; use them as starting points, not as required proof."
        )
    input_refs = _request_input_refs(request)
    if input_refs:
        guidance.append(
            "Optional input refs are visible under `inputs`: " + ", ".join(input_refs) + ". "
            "Use them when relevant and record parse/fetch gaps explicitly."
        )
    if request.previous_run_refs:
        guidance.append(
            "Previous run refs are staged through `inputs/previous_run_index.json`; read staged refs from that index rather than reaching outside the run workspace."
        )
    if request.provider_policy == "openalex_enhanced":
        guidance.append(
            "OpenAlex-enhanced policy was requested, but OpenAlex remains optional; use it only if provider capabilities report it enabled."
        )
    return guidance


def _output_contract(request: AcademicResearchRequest) -> dict[str, Any]:
    profile = research_intensity_profile(request.research_intensity)
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2_output_contract.v1",
        "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
        "source_graph_ref": KERNEL_V2_SOURCE_GRAPH_REF,
        "canonical_sources_ref": KERNEL_V2_CANONICAL_SOURCES_REF,
        "final_report_ref": KERNEL_V2_FINAL_REPORT_REF,
        "citation_projected_report_ref": KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
        "citation_registry_ref": KERNEL_V2_CITATION_REGISTRY_REF,
        "insight_map_ref": KERNEL_V2_INSIGHT_MAP_REF,
        "claim_index_ref": KERNEL_V2_CLAIM_INDEX_REF,
        "claim_index_validation_ref": KERNEL_V2_CLAIM_INDEX_VALIDATION_REF,
        "citation_projection_validation_ref": KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
        "research_state_ref": KERNEL_V2_RESEARCH_STATE_REF,
        "min_source_records": profile.min_source_records,
        "min_final_report_chars": profile.min_final_report_chars,
        "research_intensity_guidance": profile.guidance,
        "required_sections": research_report_section_specs(request.language),
        "max_review_rounds": profile.max_review_rounds,
    }


def _source_mapper_brief(request: AcademicResearchRequest) -> str:
    profile = research_intensity_profile(request.research_intensity)
    return "\n".join(
        [
            "# DeepResearch v2 Source Mapper Brief",
            "",
            "You own only the first-pass evidence-mapping phase. Do not draft the final report in this step.",
            "Your goal is to create a durable, useful evidence base that the synthesis researcher can read and turn into a report, then hand off.",
            "This is not the whole research run. Later researcher/reviewer passes can request narrow follow-up source expansion from your artifacts.",
            "Use academic/repo tools when available. Start live academic runs with `academic_provider_capabilities` and record provider availability, missing optional keys, and disabled enhancements before broad search.",
            "Default academic acquisition is no-key. Do not assume OpenAlex is available unless provider capabilities report it as enabled; missing OpenAlex is a source-gap diagnostic, not a task failure.",
            "Batch independent searches, but keep the batch bounded enough to leave time to write artifacts.",
            "Do not keep searching until timeout. After a representative source set exists, write the required artifacts and hand off.",
            "Write the required artifacts before any second broad search wave. If you are tempted to continue searching broadly, record the follow-up targets in `reports/source_gaps.md` and `state/research_state.json` instead.",
            "Once you have enough sources to make synthesis useful, stop expanding and set `ready_for_synthesis`; do not chase the maximum source count in this phase.",
            "If tool failures repeat, context pressure is reported, or a context checkpoint/safe-point appears, stop searching and write the durable artifacts from the evidence already gathered.",
            "Required outputs: `sources/source_packet.json`, `sources/provider_capabilities.json` when academic tools are available, `reports/evidence_index.md`, `reports/source_gaps.md`, `state/research_state.json`, and `state/source_control.json`.",
            "Treat `sources/source_packet.json` as the durable source authority. Include `source_records` with `source_id`, `title`, `source_type`, `year`, `locator`, `evidence_note`, and `evidence_strength` when available.",
            "Use stable source ids like `S1`, `S2`, ... in `sources/source_packet.json`; a mechanical projector will later produce canonical sources, dedupe maps, and citation anchors.",
            "Treat `reports/evidence_index.md` as a compact reading map grouped by research line, not a full report.",
            "Treat `reports/source_gaps.md` as the place to record inaccessible sources, weak evidence classes, and follow-up checks.",
            "Treat `state/research_state.json` as the compact project board and posterior summary. Include `project_phase`, `latest_project_update`, `project_milestones`, `coverage_map`, `next_actions`, `source_count`, `current_synthesis`, and `unresolved_gaps` when possible.",
            "Set `state/source_control.json.decision` to `ready_for_synthesis` once a usable evidence base exists, even if imperfect.",
            "Use `continue` only if one more bounded evidence batch is necessary before any synthesis would be useful.",
            "Use `blocked` only when tools or permissions prevent writing a usable source packet.",
            *_optional_input_guidance(request),
            f"Research intensity: `{profile.intensity.value}`. {profile.guidance}",
            *_source_mapper_intensity_guidance(profile.intensity),
            f"First-pass handoff target: at least {profile.min_source_records} useful source records when feasible.",
            _source_budget_guidance(request, profile),
            "These are source-quality targets and budget guidance, not a fixed acceptance count or permission to exhaust the runtime.",
            f"Topic: {request.topic}",
            f"Audience: {request.audience}",
            f"Language: {request.language}",
        ]
    )


def _source_mapper_max_turns(intensity: ResearchIntensity) -> int:
    try:
        return _SOURCE_MAPPER_RUNTIME_MAX_TURNS[intensity]
    except KeyError as exc:
        raise mf.ContractValidationError(f"unsupported research intensity for source mapper runtime: {intensity}") from exc


def _source_mapper_intensity_guidance(intensity: ResearchIntensity) -> list[str]:
    if intensity is ResearchIntensity.INTENSIVE:
        return [
            "For intensive runs, include repository or documentation evidence when the topic involves software systems.",
            "When tools permit, collect file/path-level evidence targets such as README, docs, examples, tests, configs, source layout, entrypoints, and workflows.",
            "Do not install projects, execute code, run benchmarks, or perform experimental validation.",
            "If repository files cannot be fetched or inspected, record the gap explicitly and downgrade code-level evidence strength.",
        ]
    if intensity is ResearchIntensity.STANDARD:
        return [
            "For standard runs, public metadata, papers, docs, release notes, and repository summaries are sufficient when limits are explicit.",
            "Do not require clone-level or file-by-file code audit.",
        ]
    raise mf.ContractValidationError(f"unsupported research intensity for source mapper brief: {intensity}")


def _researcher_brief(request: AcademicResearchRequest) -> str:
    profile = research_intensity_profile(request.research_intensity)
    return "\n".join(
        [
            "# DeepResearch v2 Researcher Brief",
            "",
            "You own the synthesis and report-writing phase. The source mapper already owns source acquisition.",
            "Use read/write/edit to turn the source packet and evidence index into insight, claim audit, and final report.",
            "Do not run a new broad source-gathering loop in this step. If evidence is insufficient, write a useful evidence-calibrated report with explicit gaps or set `continue` with narrow source targets for the source mapper.",
            "Reserve most of this step for synthesis, writing, and artifact consistency.",
            "Feedback paths are `reviews/reviewer_observation.json` and `judge/judge_report.json` when those files exist.",
            "User intervention snapshots may appear as visible refs ending in `interaction/safe_points/*-user_events.json`. Read them when visible.",
            "Treat user events as timely guidance or interruption signals, not as frozen task authority.",
            "If a user event changes scope, success criteria, audience, or acceptance standards, do not silently rewrite the task. Mark the issue explicitly in `state/researcher_control.json` using `blocked` or explain the needed contract revision.",
            "If a user event is compatible with the frozen contract, incorporate it in the next safe phase and mention how it affected the research state.",
            "Required outputs: `reports/final_report.md`, `reports/evidence_index.md`, `reports/source_gaps.md`, `analysis/insight_map.json`, `claims/claim_index.json`, `state/research_state.json`, and `state/researcher_control.json`.",
            "On every pass, write or update every required output ref, even when only one artifact needed a semantic change.",
            "Treat `state/research_state.json` as the compact user-facing project progress board and posterior summary: source strategy, evidence coverage, current synthesis, confidence notes, unresolved gaps, and next actions with refs.",
            "Do not bury the main intellectual argument in `state/research_state.json`; put thesis, tensions, narrative arc, and reader-value reasoning in `analysis/insight_map.json`.",
            "Include project-progress fields when possible: `project_phase`, `latest_project_update`, `project_milestones`, `coverage_map`, and `next_actions`.",
            "`project_milestones` should be an array of compact objects with `id`, `title`, `status`, `notes`, and optional `evidence_refs`; use statuses such as `pending`, `active`, `done`, `blocked`, or `deferred`.",
            "`coverage_map` should summarize the major research dimensions, evidence state, confidence, and gaps so a TUI can show whether the project is actually converging.",
            "Update `state/research_state.json` after planning, after each meaningful evidence batch, before review handoff, and after repair passes.",
            "Treat `sources/source_packet.json` as the durable source authority. Include `source_records` with `source_id`, `title`, `source_type`, `year`, `locator`, `evidence_note`, and `evidence_strength` when available.",
            "Do not rewrite `sources/source_packet.json` in this step; cite it and reflect any needed source expansion in `state/researcher_control.json`.",
            "Treat `analysis/insight_map.json` as the durable expert-thinking artifact. Use schema_version `missionforge_deepresearch.kernel_v2.insight_map.v1`.",
            "`analysis/insight_map.json` must include `thesis`, `audience_relevance`, `narrative_arc`, `key_insights`, `tensions`, and `evidence_limits`.",
            "Each key insight should include `insight_id`, `claim`, `why_non_obvious`, `supporting_source_ids`, optional `supporting_claim_ids`, optional `counterevidence_source_ids`, `confidence`, `reader_value`, and `report_section_ids`.",
            "Before drafting the final report, form a defensible thesis and identify cross-source tensions or surprises; every major section should support, challenge, or refine that thesis.",
            "Apply the So What test: every major claim should explain why it matters to the audience and what decision, assumption, or follow-up it informs.",
            "Avoid a paper-by-paper or source-by-source catalog. Reorganize evidence around technical mechanisms, disagreements, constraints, and implications.",
            "Match the requested genre. If the user asks for a literature review, write in a neutral, rigorous, comprehensive review style, not a strategic memo or marketing-style narrative.",
            "Avoid sensational or casual headings and phrases unless the user explicitly requested that style. Prefer precise academic labels such as limitations, counterevidence, bottlenecks, open questions, and future directions.",
            "Organize tools and papers under research lines, technical mechanisms, assumptions, and evidence strength. Do not dedicate one major section per tool unless the contract explicitly asks for a tool directory.",
            "Keep scope, method, source strategy, audit map, source gaps, and confidence caveats explicit, but proportionate. They should support the review, not dominate it.",
            "Detailed repository/code-audit maps are evidence artifacts, not default reader-facing sections. Put detailed audit coverage in `reports/evidence_index.md`, `reports/source_gaps.md`, `sources/source_packet.json`, or `state/research_state.json`; keep `reports/final_report.md` to a concise evidence-method summary unless the user explicitly requests a full audit appendix.",
            "In `analysis/insight_map.json.narrative_arc`, make the arc concrete: abstract/key findings -> scope/method -> background/problem -> research lines -> comparative analysis -> limitations/counterevidence/open questions -> trends/future directions.",
            "In the trends/future directions section, distinguish evidence-supported trends from practical implications and hypotheses.",
            "If evidence is mostly metadata, abstract-only, or README-level, downgrade conclusion strength and use attribution language rather than strong causal claims.",
            "Treat `claims/claim_index.json` as the claim-to-evidence audit artifact. Use schema_version `missionforge_deepresearch.kernel_v2.claim_index.v1` and a `claims` array. Each claim should include `claim_id`, `claim`, `supporting_source_ids`, `evidence_strength`, `verification_status`, and `confidence_note`.",
            "Use citations like [S1] for material claims.",
            "Do not hand-author numbered citation anchors; the product citation projector will convert source-id citations to `[cite: N](#ref-N)` and write `citations/citation_registry.json`.",
            "The final report must include all required sections from `product_contract/output_contract.json`, including a References/参考文献 section inside `reports/final_report.md` itself.",
            "Before setting `ready_for_review`, reread the tail of `reports/final_report.md` and ensure it is not truncated.",
            *_optional_input_guidance(request),
            f"Research intensity: `{profile.intensity.value}`. {profile.guidance}",
            *_researcher_intensity_guidance(profile.intensity),
            f"Target at least {profile.min_final_report_chars} characters when source coverage supports it.",
            f"Target at least {profile.min_source_records} useful source records when feasible. {_source_budget_guidance(request, profile)}",
            "These are quality targets, not permission to defer writing. Prefer a reviewable partial synthesis over no artifacts.",
            "If source coverage is weaker than the target, write a useful report anyway, make limitations explicit in `reports/source_gaps.md`, and use `continue` only for a bounded source-mapping request.",
            "Set `state/researcher_control.json.decision` to `ready_for_review` when the workspace is ready for reviewer.",
            "Use `continue` only when another researcher pass is strictly necessary before review; otherwise hand off to reviewer with explicit gaps.",
            "Use `blocked` only when tools or permissions prevent a usable source packet/report.",
            f"Topic: {request.topic}",
            f"Audience: {request.audience}",
            f"Language: {request.language}",
        ]
    )


def _researcher_intensity_guidance(intensity: ResearchIntensity) -> list[str]:
    if intensity is ResearchIntensity.INTENSIVE:
        return [
            "Intensive mode means repository/code-audit-backed research when the topic includes software systems or tools.",
            "When tools permit, inspect repository files directly: README, docs, examples, tests, configs/manifests, scripts, source layout, entrypoints, and workflow/tool definitions.",
            "For each important system, record file/path-level evidence in the source packet or evidence index when available.",
            "Do not put a full repo/code-audit map in the reader-facing final report by default. Record detailed audit coverage in `reports/evidence_index.md`, `reports/source_gaps.md`, `sources/source_packet.json`, or `state/research_state.json`; summarize only the evidence method and confidence in the final report unless the user explicitly asks for an audit appendix.",
            "Classify claims as `code_evidence`, `readme_or_docs_claim`, `paper_or_web_claim`, `inference`, or `not_found` instead of presenting all claims as equally verified.",
            "Do not install projects, execute repository code, run benchmarks, call project CLIs, or require experimental runtime validation.",
            "If repository files cannot be fetched or inspected, say so explicitly in `reports/source_gaps.md` and downgrade code-level claims.",
        ]
    if intensity is ResearchIntensity.STANDARD:
        return [
            "Standard mode means a web, paper, documentation, and repository-metadata survey.",
            "Use public metadata, papers, docs, README pages, release notes, and repository search/fetch results to synthesize the field.",
            "Do not require clone-level or file-by-file code audit for standard mode.",
            "Do not claim implementation-level verification unless specific repository files or paths were inspected.",
        ]
    raise mf.ContractValidationError(f"unsupported research intensity for researcher brief: {intensity}")


def _reviewer_rubric(request: AcademicResearchRequest) -> str:
    profile = research_intensity_profile(request.research_intensity)
    return "\n".join(
        [
            "# DeepResearch v2 Reviewer Rubric",
            "",
            "Review the researcher-owned workspace. Do not rewrite artifacts.",
            "User intervention snapshots may appear as visible refs ending in `interaction/safe_points/*-user_events.json`. Read them when visible.",
            "Treat user events as reviewer context, not as automatic contract changes.",
            "If the user intervention materially changes scope or acceptance criteria, prefer `blocked` or `rejected` with a revision note over silently accepting a changed task.",
            "Return `ready_for_judge`, `revise_report`, `continue`, `blocked`, or `rejected` in the decision field.",
            "Prefer `ready_for_judge` when the report is usable, structurally complete, cited, and explicit about evidence gaps; do not use `continue` merely because deeper research would be valuable.",
            "Use `revise_report` for bounded report defects such as truncation, missing required sections, missing References, citation formatting gaps, incomplete conclusion, weak thesis, thin insight, or narrative mismatch.",
            "Use `continue` only for one narrow, budget-aware research expansion that is necessary before judge handoff; include exact artifacts and source targets in the observation.",
            "Judge the phase artifacts, not the number of turns or the number of tool calls inside a turn.",
            "A multi-tool researcher batch is fine when it advances the posterior and the workspace artifacts stay coherent.",
            "Use `rejected` only when the package is not salvageable under the frozen contract.",
            "Batch material blockers in one pass.",
            "Use `analysis/insight_map.json` as the main review lens for intellectual quality. Check whether the report actually follows its thesis, tensions, narrative arc, and reader-value claims.",
            "Narrative quality check: the report should have a discernible central argument, a progression from problem to evidence to analysis to implication, and counterevidence woven into the argument rather than isolated as a disclaimer.",
            "Insight check: key insights should be non-obvious, cross-source, and useful to the audience. A complete but source-by-source summary should be revised even when citations are valid.",
            "Genre fit check: if the user requested a literature review, require neutral academic tone, comprehensive route coverage, and evidence-calibrated comparison; reject casual slogans or unsupported strategic overreach.",
            "Structure check: if the report is a tool-by-tool or paper-by-paper catalog without synthesis, require revision into research lines, mechanisms, comparison, limitations, and future directions.",
            "Proportion check: source strategy, audit coverage, evidence limitations, and confidence caveats should be explicit but should not dominate the reader-facing report.",
            "Audit placement check: detailed repo/code-audit maps should live in evidence artifacts or source gaps by default; the final report should include only a concise method/confidence summary unless the user requested an audit appendix.",
            "Evidence-conclusion calibration check: when evidence is metadata, abstract-only, README-level, or explicitly weak, require downgraded claim language and visible limits.",
            f"Research intensity: `{profile.intensity.value}`. {profile.guidance}",
            *_reviewer_intensity_guidance(profile.intensity),
            f"Topic: {request.topic}",
        ]
    )


def _reviewer_intensity_guidance(intensity: ResearchIntensity) -> list[str]:
    if intensity is ResearchIntensity.INTENSIVE:
        return [
            "For intensive runs, check whether software-tool claims are backed by repository file/path evidence or explicitly downgraded as gaps.",
            "Do not ask the researcher to install projects, execute code, run benchmarks, or perform experimental validation.",
            "Prefer one bounded repo-audit expansion only when missing file/path evidence blocks the report's central conclusions.",
            "Do not treat parallel retrieval or a longer evidence batch as a defect by itself.",
        ]
    if intensity is ResearchIntensity.STANDARD:
        return [
            "For standard runs, do not block solely because there was no clone-level or file-by-file code audit.",
            "Block only unsupported implementation-level claims, missing citations, missing structure, or undisclosed evidence gaps.",
        ]
    raise mf.ContractValidationError(f"unsupported research intensity for reviewer rubric: {intensity}")


def _judge_rubric(request: AcademicResearchRequest) -> str:
    profile = research_intensity_profile(request.research_intensity)
    return "\n".join(
        [
            "# DeepResearch v2 Judge Rubric",
            "",
            "Independently judge the final artifacts against the frozen contract.",
            "User intervention snapshots may appear as visible refs ending in `interaction/safe_points/*-user_events.json`. Read them when visible.",
            "Do not accept a package that silently follows a user intervention that conflicts with the frozen contract; require a revision instead.",
            "Return `accepted`, `repair`, `revision_required`, or `rejected` in the decision field.",
            "Use `repair` only for bounded same-contract fixes that the researcher can perform without changing the task contract.",
            "Judge the staged package as a whole: report, evidence index, source gaps, claim index, and research state must agree.",
            "Use `analysis/insight_map.json` as the semantic map for the package. Do not accept a report that lacks a defensible thesis, clear audience relevance, cross-source insight, or a coherent argument arc.",
            "Do not accept a report that is structurally complete but reads as a catalog of sources, unless the frozen contract explicitly requested only a bibliography or source inventory.",
            "Do not accept a report that ignores the requested genre. A literature review should be objective, rigorous, comprehensive, and evidence-calibrated, not slogan-heavy or over-personalized to an unknown reader.",
            "The main body should explain the field clearly; method, audit coverage, and source limitations should remain explicit and proportionate.",
            "Do not accept a reader-facing literature review that exposes a full repo/code-audit map as a default body section unless the user explicitly requested an audit appendix.",
            "Do not accept evidence-conclusion mismatch: strong implementation, causal, benchmark, or trend claims need correspondingly strong source, paper, or repo-file evidence; otherwise require repair or revision.",
            f"Research intensity: `{profile.intensity.value}`. {profile.guidance}",
            *_judge_intensity_guidance(profile.intensity),
            f"Audience: {request.audience}",
        ]
    )


def _judge_intensity_guidance(intensity: ResearchIntensity) -> list[str]:
    if intensity is ResearchIntensity.INTENSIVE:
        return [
            "For intensive runs, accept explicit source gaps, but do not accept code-level conclusions that lack repository file/path evidence.",
            "Do not require installation, execution, benchmarks, or experimental reproduction.",
            "Do not infer poor quality from the number of tool calls or from parallel retrieval inside a researcher turn.",
        ]
    if intensity is ResearchIntensity.STANDARD:
        return [
            "For standard runs, accept a strong metadata/web/docs/paper survey when claims are cited and limits are explicit.",
            "Do not require repo/code audit as an acceptance condition for standard mode.",
        ]
    raise mf.ContractValidationError(f"unsupported research intensity for judge rubric: {intensity}")


def _empty_source_packet(request: AcademicResearchRequest) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": request.request_id,
        "source_records": [],
    }


def _fixture_source_packet(request: Mapping[str, Any]) -> dict[str, Any]:
    request_id = str(request["request_id"])
    return {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": request_id,
        "source_records": [
            {
                "source_id": "S1",
                "title": "Fixture survey on compiler autotuning",
                "source_type": "fixture",
                "year": 2025,
                "locator": "https://example.test/compiler-autotuning",
                "evidence_note": "Fixture evidence for Kernel v2 wiring.",
                "evidence_strength": "fixture",
            }
        ],
    }


def _fixture_report(request: Mapping[str, Any], source_packet: Mapping[str, Any]) -> str:
    language = str(request.get("language", "zh"))
    if language.startswith("zh"):
        return (
            "# Kernel v2 DeepResearch Fixture Report\n\n"
            "## 摘要与核心发现\n\n"
            "本夹具报告验证 Kernel v2 的白盒编排边界，并使用夹具来源说明引用链路 [S1]。\n\n"
            "## 范围与方法\n\n"
            "夹具模式只验证控制流和 artifact 边界，不声称完成真实研究。\n\n"
            "## 研究背景与问题定义\n\n"
            "真实运行中该章节由 researcher PiWorker 负责解释研究问题和边界 [S1]。\n\n"
            "## 研究路线与代表性工作\n\n"
            "真实运行中该章节由 researcher PiWorker 负责按研究路线综合，不由 Python 判断语义充分性 [S1]。\n\n"
            "## 比较分析\n\n"
            "| 路线 | 证据 |\n| --- | --- |\n| Kernel v2 fixture | [S1] |\n\n"
            "## 局限、反证与开放问题\n\n"
            "夹具只覆盖 refs、权限、insight map、claim index 和 judge handoff 的结构边界。\n\n"
            "## 趋势与未来方向\n\n"
            "需要 live PiWorker 和授权工具才能生成正式综述。\n\n"
            "## 参考文献\n\n"
            "- [S1] Fixture survey on compiler autotuning. https://example.test/compiler-autotuning\n"
        )
    return (
        "# Kernel v2 DeepResearch Fixture Report\n\n"
        "## Abstract And Key Findings\n\n"
        "This report validates Kernel v2 orchestration boundaries with fixture evidence [S1].\n\n"
        "## Scope And Method\n\n"
        "The fixture source is structural evidence only.\n\n"
        "## Background And Problem Definition\n\n"
        "Live runs explain the field context and problem boundary [S1].\n\n"
        "## Research Lines And Representative Work\n\n"
        "Live runs organize sources by research line rather than by Python semantics [S1].\n\n"
        "## Comparative Analysis\n\n"
        "Fixture mode only checks artifact and permission boundaries.\n\n"
        "## Limitations Counterevidence And Open Questions\n\n"
        "Fixture evidence does not prove live research quality.\n\n"
        "## Trends And Future Directions\n\n"
        "Use live PiWorker mode for expert synthesis.\n\n"
        "## References\n\n"
        "- [S1] Fixture survey on compiler autotuning. https://example.test/compiler-autotuning\n"
    )


def _reference_lines(source_packet: Mapping[str, Any]) -> str:
    lines = []
    for record in source_packet.get("source_records", []):
        lines.append(f"- [{record['source_id']}] {record['title']} ({record.get('locator', '')})")
    return "\n".join(lines) + "\n"


def _fixture_research_state(source_packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2.research_state.v1",
        "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
        "final_report_ref": KERNEL_V2_FINAL_REPORT_REF,
        "evidence_index_ref": KERNEL_V2_EVIDENCE_INDEX_REF,
        "source_gaps_ref": KERNEL_V2_SOURCE_GAPS_REF,
        "insight_map_ref": KERNEL_V2_INSIGHT_MAP_REF,
        "project_phase": "final_package_ready",
        "latest_project_update": "Fixture mode completed the structural research package.",
        "project_milestones": [
            {
                "id": "scope",
                "title": "Scope and output contract",
                "status": "done",
                "notes": "Fixture request and output contract were prepared.",
                "evidence_refs": [KERNEL_V2_OUTPUT_CONTRACT_REF],
            },
            {
                "id": "evidence",
                "title": "Evidence packet",
                "status": "done",
                "notes": "Fixture evidence packet was written.",
                "evidence_refs": [KERNEL_V2_SOURCE_PACKET_REF],
            },
            {
                "id": "synthesis",
                "title": "Report synthesis",
                "status": "done",
                "notes": "Fixture final report and evidence index were written.",
                "evidence_refs": [KERNEL_V2_FINAL_REPORT_REF, KERNEL_V2_EVIDENCE_INDEX_REF],
            },
        ],
        "coverage_map": [
            {
                "dimension": "runtime wiring",
                "status": "covered",
                "confidence": "fixture",
                "gaps": ["Fixture mode does not judge live research quality."],
                "evidence_refs": [KERNEL_V2_SOURCE_PACKET_REF],
            }
        ],
        "next_actions": ["Use live PiWorker mode for semantic research quality."],
        "source_count": len(source_packet.get("source_records", [])),
        "current_synthesis": "Fixture mode validates researcher-owned workspace boundaries.",
        "unresolved_gaps": ["Fixture mode does not judge live research quality."],
    }


def _fixture_insight_map(source_packet: Mapping[str, Any]) -> dict[str, Any]:
    source_ids = [
        str(record.get("source_id"))
        for record in source_packet.get("source_records", [])
        if isinstance(record, Mapping) and record.get("source_id")
    ]
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2.insight_map.v1",
        "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
        "claim_index_ref": KERNEL_V2_CLAIM_INDEX_REF,
        "final_report_ref": KERNEL_V2_FINAL_REPORT_REF,
        "thesis": "Fixture mode only proves DeepResearch Kernel v2 artifact and role boundaries.",
        "audience_relevance": "It gives developers a stable wiring check before live PiWorker research.",
        "narrative_arc": {
            "setup": "Kernel v2 needs refs-first research artifacts.",
            "tension": "Fixture evidence cannot prove live research quality.",
            "resolution": "The fixture validates boundaries while deferring semantic judgment to PiWorker roles.",
            "implications": "Use live PiWorker mode for actual expert synthesis.",
        },
        "key_insights": [
            {
                "insight_id": "I1",
                "claim": "The core runtime can enforce artifact ownership without judging research semantics.",
                "why_non_obvious": "The fixture separates wiring evidence from live research quality.",
                "supporting_source_ids": source_ids[:1],
                "supporting_claim_ids": ["C1"],
                "counterevidence_source_ids": [],
                "confidence": "fixture",
                "reader_value": "Developers can test boundaries without confusing fixture output for research.",
                "report_section_ids": ["abstract_and_key_findings", "research_lines_and_representative_work"],
            }
        ],
        "tensions": [
            {
                "tension_id": "T1",
                "description": "Structural acceptance is useful for tests but insufficient for research quality.",
                "source_ids": source_ids[:1],
                "how_resolved_or_left_open": "Resolved by keeping fixture claims narrow and explicit.",
            }
        ],
        "evidence_limits": ["Fixture evidence is not a live source review."],
    }


def _fixture_claim_index(source_packet: Mapping[str, Any]) -> dict[str, Any]:
    source_ids = [
        str(record.get("source_id"))
        for record in source_packet.get("source_records", [])
        if isinstance(record, Mapping) and record.get("source_id")
    ]
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2.claim_index.v1",
        "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
        "final_report_ref": KERNEL_V2_FINAL_REPORT_REF,
        "claims": [
            {
                "claim_id": "C1",
                "claim": "Fixture mode validates that Kernel v2 records claim-to-source evidence as a separate artifact.",
                "supporting_source_ids": source_ids[:1],
                "evidence_strength": "fixture",
                "verification_status": "fixture_only",
                "confidence_note": "Fixture evidence is structural and does not imply live research quality.",
            }
        ],
    }


def _kernel_v2_max_steps(max_review_rounds: int) -> int:
    return max(4 + (max_review_rounds * 2), 6)


def _write_kernel_v2_source_graph(run_root: Path) -> None:
    if not (run_root / KERNEL_V2_SOURCE_PACKET_REF).is_file():
        return
    source_packet = read_json_ref(run_root, KERNEL_V2_SOURCE_PACKET_REF, "kernel_v2_source_packet")
    projection = project_source_graph(source_packet)
    write_json_ref(run_root, KERNEL_V2_CANONICAL_SOURCES_REF, projection["canonical_sources"])
    write_json_ref(run_root, KERNEL_V2_DEDUPE_MAP_REF, projection["dedupe_map"])
    write_json_ref(run_root, KERNEL_V2_SOURCE_GRAPH_REF, projection["source_graph"])


def _write_kernel_v2_citation_projection(run_root: Path) -> None:
    report_path = run_root / KERNEL_V2_FINAL_REPORT_REF
    if not report_path.is_file():
        return
    if not (run_root / KERNEL_V2_CANONICAL_SOURCES_REF).is_file():
        write_json_ref(
            run_root,
            KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
            {
                "schema_version": CITATION_PROJECTION_VALIDATION_SCHEMA_VERSION,
                "status": "failed",
                "failure_codes": ["missing_canonical_sources"],
            },
        )
        return
    markdown = report_path.read_text(encoding="utf-8")
    canonical_sources = read_json_ref(run_root, KERNEL_V2_CANONICAL_SOURCES_REF, "kernel_v2_canonical_sources")
    projection = project_report_citations(markdown=markdown, canonical_sources_payload=canonical_sources)
    write_text_ref(run_root, KERNEL_V2_CITATION_PROJECTED_REPORT_REF, projection["projected_markdown"])
    write_json_ref(run_root, KERNEL_V2_CITATION_REGISTRY_REF, projection["citation_registry"])
    write_json_ref(run_root, KERNEL_V2_REPORT_CITATION_MAP_REF, projection["report_citation_map"])
    write_json_ref(run_root, KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF, projection["validation"])


def _write_kernel_v2_report_html(run_root: Path) -> str:
    report_path = run_root / KERNEL_V2_CITATION_PROJECTED_REPORT_REF
    if not report_path.is_file():
        report_path = run_root / KERNEL_V2_FINAL_REPORT_REF
    if not report_path.is_file():
        return KERNEL_V2_REPORT_HTML_REF
    markdown = report_path.read_text(encoding="utf-8")
    html = _render_report_html(markdown)
    write_text_ref(run_root, KERNEL_V2_REPORT_HTML_REF, html)
    return KERNEL_V2_REPORT_HTML_REF


def _write_kernel_v2_claim_index_validation(run_root: Path) -> str:
    payload = _kernel_v2_claim_index_validation(run_root)
    write_json_ref(run_root, KERNEL_V2_CLAIM_INDEX_VALIDATION_REF, payload)
    return KERNEL_V2_CLAIM_INDEX_VALIDATION_REF


def _kernel_v2_claim_index_validation(run_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    source_ids: set[str] = set()
    try:
        source_packet = json.loads((run_root / KERNEL_V2_SOURCE_PACKET_REF).read_text(encoding="utf-8"))
        for record in source_packet.get("source_records", []):
            if isinstance(record, Mapping) and isinstance(record.get("source_id"), str):
                source_ids.add(record["source_id"])
    except (OSError, json.JSONDecodeError, AttributeError):
        failures.append("source_packet_unreadable")
    try:
        claim_index = json.loads((run_root / KERNEL_V2_CLAIM_INDEX_REF).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        claim_index = {}
        failures.append("claim_index_unreadable")
    if claim_index.get("schema_version") != "missionforge_deepresearch.kernel_v2.claim_index.v1":
        failures.append("schema_version_invalid")
    claims = claim_index.get("claims")
    if not isinstance(claims, list):
        claims = []
        failures.append("claims_not_list")
    seen_claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            failures.append(f"claim_{index}_not_object")
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            failures.append(f"claim_{index}_missing_claim_id")
        elif claim_id in seen_claim_ids:
            failures.append(f"claim_{claim_id}_duplicate")
        else:
            seen_claim_ids.add(claim_id)
        if not isinstance(claim.get("claim"), str) or not claim.get("claim"):
            failures.append(f"claim_{claim_id or index}_missing_text")
        supporting_source_ids = claim.get("supporting_source_ids")
        if not isinstance(supporting_source_ids, list):
            failures.append(f"claim_{claim_id or index}_supporting_source_ids_not_list")
            continue
        for source_id in supporting_source_ids:
            if not isinstance(source_id, str) or source_id not in source_ids:
                failures.append(f"claim_{claim_id or index}_unknown_source_id")
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2.claim_index_validation.v1",
        "status": "passed" if not failures else "failed",
        "claim_index_ref": KERNEL_V2_CLAIM_INDEX_REF,
        "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
        "failure_codes": failures,
    }


def _render_report_html(markdown: str) -> str:
    body: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            body.append(f"<p>{'<br>'.join(_render_inline_markdown(item) for item in paragraph)}</p>")
            paragraph.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = stripped[level:].strip()
            body.append(f"<h{level}>{escape(text)}</h{level}>")
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            body.append(f"<pre class=\"table-row\">{_render_inline_markdown(stripped)}</pre>")
            continue
        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            body.append(f"<ul><li>{_render_inline_markdown(stripped[2:].strip())}</li></ul>")
            continue
        paragraph.append(stripped)
    flush_paragraph()
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"zh\">",
            "<head>",
            "<meta charset=\"utf-8\">",
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "<title>MissionForge DeepResearch Report</title>",
            "<style>",
            "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:960px;margin:40px auto;padding:0 24px;line-height:1.65;color:#1f2933;background:#fff}",
            "h1,h2,h3{line-height:1.25;margin-top:1.6em} h1{font-size:2rem} h2{border-top:1px solid #d9e2ec;padding-top:1rem}",
            "p{margin:0 0 1rem} pre.table-row{white-space:pre-wrap;background:#f5f7fa;border:1px solid #d9e2ec;padding:6px 8px;margin:0;font-size:.9rem}",
            "ul{margin:.35rem 0 .7rem 1.2rem;padding:0}",
            "</style>",
            "</head>",
            "<body>",
            *body,
            "</body>",
            "</html>",
            "",
        ]
    )


def _render_inline_markdown(text: str) -> str:
    html = escape(text)
    html = re.sub(r"\[cite:\s*(\d+)\]\(#ref-\1\)", r'<a href="#ref-\1">[cite: \1]</a>', html)
    html = re.sub(r"&lt;a id=&quot;(ref-\d+)&quot;&gt;&lt;/a&gt;", r'<a id="\1"></a>', html)
    return html


def _write_kernel_v2_run_status(
    request: AcademicResearchRequest,
    *,
    run_root: Path,
    flow_result: mf.FlowRunResult,
    product_status: str,
) -> str:
    status_payload = _kernel_v2_run_status(
        request,
        flow_result=flow_result,
        product_status=product_status,
        citation_projection_validation=_optional_json_ref(run_root, KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF),
        claim_index_validation=_optional_json_ref(run_root, KERNEL_V2_CLAIM_INDEX_VALIDATION_REF),
        interaction_summary=_kernel_v2_interaction_summary(run_root, flow_result=flow_result),
    )
    write_json_ref(run_root, KERNEL_V2_RUN_STATUS_REF, status_payload)
    return KERNEL_V2_RUN_STATUS_REF


def _kernel_v2_run_status(
    request: AcademicResearchRequest,
    *,
    flow_result: mf.FlowRunResult,
    product_status: str | None = None,
    citation_projection_validation: Mapping[str, Any] | None = None,
    claim_index_validation: Mapping[str, Any] | None = None,
    interaction_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    flow_projected_status = _kernel_v2_projected_status(flow_result)
    status = product_status or flow_projected_status
    last_record = flow_result.step_results[-1].step_record if flow_result.step_results else None
    metadata = dict(last_record.metadata) if last_record is not None else {}
    failure_summary = metadata.get("failure_summary")
    flow_stop_reason = str(flow_result.flow_result.metadata.get("stop_reason") or "")
    interaction_stop_reason = flow_stop_reason if flow_stop_reason.startswith("user_") else ""
    interaction = dict(interaction_summary or {})
    flow_ledger_ref = flow_result.flow_result.ledger_refs[0] if flow_result.flow_result.ledger_refs else "kernel/missing_flow_ledger.jsonl"
    run_events_ref = _flow_metadata_ref(flow_result.flow_result.metadata, "run_events_ref", "kernel/missing_run_events.jsonl")
    run_snapshot_ref = _flow_metadata_ref(flow_result.flow_result.metadata, "run_snapshot_ref", "kernel/missing_run_snapshot.json")
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2.run_status.v1",
        "request_id": request.request_id,
        "status": status,
        "flow_status": flow_result.flow_result.status,
        "flow_projected_status": flow_projected_status,
        "flow_stop_reason": flow_stop_reason,
        "flow_result_ref": flow_result.flow_result_ref,
        "flow_ledger_ref": flow_ledger_ref,
        "run_events_ref": run_events_ref,
        "run_snapshot_ref": run_snapshot_ref,
        "interaction_stop_reason": interaction_stop_reason,
        "pending_user_event_count": interaction.get("pending_user_event_count", 0),
        "last_interaction_snapshot_ref": interaction.get("last_interaction_snapshot_ref", ""),
        "citation_projection_status": str((citation_projection_validation or {}).get("status", "")),
        "citation_projection_failure_codes": _str_list((citation_projection_validation or {}).get("failure_codes", [])),
        "claim_index_validation_status": str((claim_index_validation or {}).get("status", "")),
        "claim_index_validation_failure_codes": _str_list((claim_index_validation or {}).get("failure_codes", [])),
        "blocked_step_id": last_record.step_id if last_record is not None and status.endswith("_blocked") else "",
        "blocker_kind": _blocker_kind(metadata) if last_record is not None and status.endswith("_blocked") else "",
        "failure_summary": _kernel_v2_failure_summary(
            failure_summary,
            product_status=status,
            citation_projection_validation=citation_projection_validation,
            claim_index_validation=claim_index_validation,
        ),
        "final_report_ref": KERNEL_V2_FINAL_REPORT_REF,
        "citation_projected_report_ref": KERNEL_V2_CITATION_PROJECTED_REPORT_REF,
        "report_html_ref": KERNEL_V2_REPORT_HTML_REF,
        "source_packet_ref": KERNEL_V2_SOURCE_PACKET_REF,
        "source_graph_ref": KERNEL_V2_SOURCE_GRAPH_REF,
        "canonical_sources_ref": KERNEL_V2_CANONICAL_SOURCES_REF,
        "citation_registry_ref": KERNEL_V2_CITATION_REGISTRY_REF,
        "insight_map_ref": KERNEL_V2_INSIGHT_MAP_REF,
        "claim_index_ref": KERNEL_V2_CLAIM_INDEX_REF,
        "claim_index_validation_ref": KERNEL_V2_CLAIM_INDEX_VALIDATION_REF,
        "citation_projection_validation_ref": KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
        "usage_summary_ref": KERNEL_V2_USAGE_SUMMARY_REF,
    }


def _kernel_v2_interaction_summary(run_root: Path, *, flow_result: mf.FlowRunResult) -> dict[str, Any]:
    if not flow_result.flow_result.ledger_refs:
        return {}
    ledger_ref = flow_result.flow_result.ledger_refs[0]
    ledger_path = run_root / ledger_ref
    if not ledger_path.is_file():
        return {}
    event_count = 0
    last_snapshot_ref = ""
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("kind") != mf.FlowLedgerEventKind.INTERACTION_RECORDED.value:
            continue
        metadata = event.get("metadata")
        refs = event.get("refs")
        if isinstance(metadata, Mapping):
            count = metadata.get("event_count")
            if isinstance(count, int):
                event_count += count
        if isinstance(refs, list) and refs:
            last_ref = refs[-1]
            if isinstance(last_ref, str):
                last_snapshot_ref = last_ref
    return {
        "pending_user_event_count": event_count,
        "last_interaction_snapshot_ref": last_snapshot_ref,
    }


def _kernel_v2_projected_status(flow_result: mf.FlowRunResult) -> str:
    flow_status = flow_result.flow_result.status
    if flow_status == "accepted":
        return "accepted"
    produced_refs = set(flow_result.flow_result.final_artifact_refs)
    draft_ready = {
        KERNEL_V2_SOURCE_PACKET_REF,
        KERNEL_V2_FINAL_REPORT_REF,
        KERNEL_V2_RESEARCH_STATE_REF,
        KERNEL_V2_SOURCE_CONTROL_REF,
        KERNEL_V2_INSIGHT_MAP_REF,
        KERNEL_V2_RESEARCHER_CONTROL_REF,
    }.issubset(produced_refs)
    if not draft_ready:
        return flow_status
    if flow_result.flow_result.metadata.get("stop_reason") == "unrouted_decision":
        return flow_status
    if flow_status == "blocked" and flow_result.step_results:
        last_step = flow_result.step_results[-1].step_record.step_id
        if last_step == "reviewer":
            return "review_blocked"
        if last_step == "judge":
            return "judge_blocked"
    return flow_status


def _kernel_v2_product_status(run_root: Path, flow_result: mf.FlowRunResult) -> str:
    status = _kernel_v2_projected_status(flow_result)
    if status != "accepted":
        return status
    citation_validation = _optional_json_ref(run_root, KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF)
    claim_validation = _optional_json_ref(run_root, KERNEL_V2_CLAIM_INDEX_VALIDATION_REF)
    if _citation_projection_failed(citation_validation):
        return "failed"
    if _claim_index_validation_failed(claim_validation):
        return "failed"
    if status == "accepted" and (run_root / KERNEL_V2_FINAL_REPORT_REF).is_file() and citation_validation is None:
        return "failed"
    return status


def _citation_projection_failed(validation: Mapping[str, Any] | None) -> bool:
    return validation is not None and validation.get("status") == "failed"


def _claim_index_validation_failed(validation: Mapping[str, Any] | None) -> bool:
    return validation is not None and validation.get("status") == "failed"


def _kernel_v2_failure_summary(
    flow_failure_summary: Any,
    *,
    product_status: str,
    citation_projection_validation: Mapping[str, Any] | None,
    claim_index_validation: Mapping[str, Any] | None,
) -> str:
    if product_status != "failed":
        return flow_failure_summary if isinstance(flow_failure_summary, str) else ""
    if _citation_projection_failed(citation_projection_validation):
        codes = citation_projection_validation.get("failure_codes", [])
        if isinstance(codes, list) and codes:
            return "citation projection validation failed: " + ", ".join(str(item) for item in codes)
        return "citation projection validation failed"
    if _claim_index_validation_failed(claim_index_validation):
        codes = claim_index_validation.get("failure_codes", [])
        if isinstance(codes, list) and codes:
            return "claim index validation failed: " + ", ".join(str(item) for item in codes)
        return "claim index validation failed"
    return flow_failure_summary if isinstance(flow_failure_summary, str) else ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _blocker_kind(metadata: Mapping[str, Any]) -> str:
    if metadata.get("non_retryable_provider_error") is True:
        return "provider"
    failure_summary = metadata.get("failure_summary")
    if isinstance(failure_summary, str) and failure_summary:
        return "runtime"
    return "unknown"


def _kernel_v2_result(
    *,
    request: AcademicResearchRequest,
    run_ref: str,
    run_root: Path,
    contract_hash: str,
    flow_result: mf.FlowRunResult,
    usage_summary_ref: str,
    status_ref: str,
    product_status: str,
) -> DeepResearchKernelV2Result:
    flow = flow_result.flow_result
    flow_ledger_ref = flow.ledger_refs[0] if flow.ledger_refs else "kernel/missing_flow_ledger.jsonl"
    run_events_ref = _flow_metadata_ref(flow.metadata, "run_events_ref", "kernel/missing_run_events.jsonl")
    run_snapshot_ref = _flow_metadata_ref(flow.metadata, "run_snapshot_ref", "kernel/missing_run_snapshot.json")
    return DeepResearchKernelV2Result(
        request_id=request.request_id,
        status=product_status,
        run_workspace_ref=run_ref,
        result_ref=_outer_ref(run_ref, KERNEL_V2_RESULT_REF),
        flow_result_ref=_outer_ref(run_ref, flow_result.flow_result_ref),
        flow_ledger_ref=_outer_ref(run_ref, flow_ledger_ref),
        run_events_ref=_outer_ref(run_ref, run_events_ref),
        run_snapshot_ref=_outer_ref(run_ref, run_snapshot_ref),
        contract_ref=_outer_ref(run_ref, KERNEL_V2_CONTRACT_REF),
        final_report_ref=_outer_ref(run_ref, KERNEL_V2_FINAL_REPORT_REF),
        citation_projected_report_ref=_outer_ref(run_ref, KERNEL_V2_CITATION_PROJECTED_REPORT_REF),
        report_html_ref=_outer_ref(run_ref, KERNEL_V2_REPORT_HTML_REF),
        source_packet_ref=_outer_ref(run_ref, KERNEL_V2_SOURCE_PACKET_REF),
        source_graph_ref=_outer_ref(run_ref, KERNEL_V2_SOURCE_GRAPH_REF),
        canonical_sources_ref=_outer_ref(run_ref, KERNEL_V2_CANONICAL_SOURCES_REF),
        citation_registry_ref=_outer_ref(run_ref, KERNEL_V2_CITATION_REGISTRY_REF),
        insight_map_ref=_outer_ref(run_ref, KERNEL_V2_INSIGHT_MAP_REF),
        claim_index_ref=_outer_ref(run_ref, KERNEL_V2_CLAIM_INDEX_REF),
        reviewer_observation_ref=_outer_ref(run_ref, KERNEL_V2_REVIEWER_OBSERVATION_REF),
        judge_report_ref=_outer_ref(run_ref, KERNEL_V2_JUDGE_REPORT_REF),
        usage_summary_ref=_outer_ref(run_ref, usage_summary_ref),
        run_status_ref=_outer_ref(run_ref, status_ref),
        draft_artifact_refs=[
            _outer_ref(run_ref, KERNEL_V2_FINAL_REPORT_REF),
            _outer_ref(run_ref, KERNEL_V2_CITATION_PROJECTED_REPORT_REF),
            _outer_ref(run_ref, KERNEL_V2_REPORT_HTML_REF),
            _outer_ref(run_ref, KERNEL_V2_EVIDENCE_INDEX_REF),
            _outer_ref(run_ref, KERNEL_V2_SOURCE_GAPS_REF),
        ],
        evidence_refs=[
            _outer_ref(run_ref, ref)
            for ref in _kernel_v2_product_evidence_refs(flow_result, run_root=run_root)
        ],
        metric_refs=[_outer_ref(run_ref, usage_summary_ref)],
        contract_hash=contract_hash,
    )


def _write_kernel_v2_usage_summary(
    request: AcademicResearchRequest,
    *,
    run_root: Path,
    flow_result: mf.FlowRunResult,
) -> str:
    summary = _kernel_v2_usage_summary(request, run_root=run_root, flow_result=flow_result)
    write_json_ref(run_root, KERNEL_V2_USAGE_SUMMARY_REF, summary)
    return KERNEL_V2_USAGE_SUMMARY_REF


def _kernel_v2_usage_summary(
    request: AcademicResearchRequest,
    *,
    run_root: Path,
    flow_result: mf.FlowRunResult,
) -> dict[str, Any]:
    step_summaries: list[dict[str, Any]] = []
    totals = _empty_usage_totals()
    metric_refs: list[str] = []
    for step_record_ref in flow_result.flow_result.step_record_refs:
        try:
            step_record = read_json_ref(run_root, step_record_ref, "kernel_step_record")
        except (OSError, json.JSONDecodeError, mf.ContractValidationError):
            continue
        step_totals = _empty_usage_totals()
        step_metric_refs: list[str] = []
        for metric_ref in step_record.get("metric_refs", []):
            if not isinstance(metric_ref, str) or not metric_ref:
                continue
            step_metric_refs.append(mf.validate_ref(metric_ref, "kernel_v2_usage_summary.step.metric_refs[]"))
            metric_refs.append(metric_ref)
            try:
                metrics = read_json_ref(run_root, metric_ref, "piworker_metrics")
            except (OSError, json.JSONDecodeError, mf.ContractValidationError):
                continue
            _add_usage_metrics(step_totals, metrics)
            _add_usage_metrics(totals, metrics)
        step_summaries.append(
            {
                "step_id": str(step_record.get("step_id", "")),
                "status": str(step_record.get("status", "")),
                "metric_refs": _dedupe_refs(step_metric_refs),
                "usage": _usage_totals_payload(step_totals),
            }
        )
    return {
        "schema_version": "missionforge_deepresearch.kernel_v2_usage_summary.v1",
        "request_id": request.request_id,
        "research_intensity": request.research_intensity.value,
        "status": flow_result.flow_result.status,
        "flow_result_ref": flow_result.flow_result_ref,
        "metric_refs": _dedupe_refs(metric_refs),
        "totals": _usage_totals_payload(totals),
        "steps": step_summaries,
    }


def _empty_usage_totals() -> dict[str, int | float]:
    return {
        "total_tokens": 0,
        "input_tokens": 0,
        "total_input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "uncached_input_tokens": 0,
        "output_tokens": 0,
        "input_cost_usd": 0.0,
        "cached_input_cost_usd": 0.0,
        "cache_write_cost_usd": 0.0,
        "output_cost_usd": 0.0,
        "provider_reported_cost_usd": 0.0,
    }


def _add_usage_metrics(target: dict[str, int | float], metrics: Mapping[str, Any]) -> None:
    input_tokens = _non_negative_int(metrics.get("input_tokens"))
    cached_input_tokens = _non_negative_int(metrics.get("cache_read_tokens"))
    target["total_tokens"] = int(target["total_tokens"]) + _non_negative_int(
        metrics.get("total_tokens", metrics.get("token_count"))
    )
    target["input_tokens"] = int(target["input_tokens"]) + input_tokens
    target["total_input_tokens"] = int(target["total_input_tokens"]) + input_tokens + cached_input_tokens
    target["cached_input_tokens"] = int(target["cached_input_tokens"]) + cached_input_tokens
    target["cache_write_tokens"] = int(target["cache_write_tokens"]) + _non_negative_int(metrics.get("cache_write_tokens"))
    target["uncached_input_tokens"] = int(target["uncached_input_tokens"]) + input_tokens
    target["output_tokens"] = int(target["output_tokens"]) + _non_negative_int(metrics.get("output_tokens"))
    target["input_cost_usd"] = float(target["input_cost_usd"]) + _non_negative_float(metrics.get("input_cost_usd"))
    target["cached_input_cost_usd"] = float(target["cached_input_cost_usd"]) + _non_negative_float(
        metrics.get("cache_read_cost_usd")
    )
    target["cache_write_cost_usd"] = float(target["cache_write_cost_usd"]) + _non_negative_float(
        metrics.get("cache_write_cost_usd")
    )
    target["output_cost_usd"] = float(target["output_cost_usd"]) + _non_negative_float(metrics.get("output_cost_usd"))
    target["provider_reported_cost_usd"] = float(target["provider_reported_cost_usd"]) + _non_negative_float(
        metrics.get("provider_reported_cost_usd")
    )


def _usage_totals_payload(values: Mapping[str, int | float]) -> dict[str, int | float]:
    payload = dict(values)
    for key in (
        "input_cost_usd",
        "cached_input_cost_usd",
        "cache_write_cost_usd",
        "output_cost_usd",
        "provider_reported_cost_usd",
    ):
        payload[key] = round(float(payload.get(key, 0.0)), 12)
    return payload


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def _non_negative_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    return 0.0


def _kernel_v2_product_evidence_refs(flow_result: mf.FlowRunResult, *, run_root: Path) -> list[str]:
    refs: list[str] = [
        KERNEL_V2_SOURCE_PACKET_REF,
        KERNEL_V2_CANONICAL_SOURCES_REF,
        KERNEL_V2_DEDUPE_MAP_REF,
        KERNEL_V2_SOURCE_GRAPH_REF,
        KERNEL_V2_CITATION_REGISTRY_REF,
        KERNEL_V2_REPORT_CITATION_MAP_REF,
        KERNEL_V2_CITATION_PROJECTION_VALIDATION_REF,
        KERNEL_V2_INSIGHT_MAP_REF,
        KERNEL_V2_CLAIM_INDEX_REF,
        KERNEL_V2_CLAIM_INDEX_VALIDATION_REF,
        KERNEL_V2_EVIDENCE_INDEX_REF,
        KERNEL_V2_SOURCE_GAPS_REF,
        KERNEL_V2_RESEARCH_STATE_REF,
        KERNEL_V2_SOURCE_CONTROL_REF,
        KERNEL_V2_RUN_STATUS_REF,
    ]
    for ref in flow_result.flow_result.decision_refs:
        if ref in {
            KERNEL_V2_SOURCE_CONTROL_REF,
            KERNEL_V2_RESEARCHER_CONTROL_REF,
            KERNEL_V2_REVIEWER_OBSERVATION_REF,
            KERNEL_V2_JUDGE_REPORT_REF,
        }:
            refs.append(ref)
    return [ref for ref in _dedupe_refs(refs) if (run_root / ref).is_file()]


def _optional_json_ref(run_root: Path, ref: str) -> dict[str, Any] | None:
    path = run_root / ref
    if not path.is_file():
        return None
    try:
        payload = read_json_ref(run_root, ref, "kernel_v2_optional_json")
    except (OSError, json.JSONDecodeError, mf.ContractValidationError):
        return None
    return payload if isinstance(payload, dict) else None


def _flow_metadata_ref(metadata: Mapping[str, Any], key: str, fallback: str) -> str:
    value = metadata.get(key)
    if isinstance(value, str) and value:
        return mf.validate_ref(value, f"deepresearch_kernel_v2.flow_result.metadata.{key}")
    return mf.validate_ref(fallback, f"deepresearch_kernel_v2.flow_result.metadata.{key}")


def _outer_ref(run_ref: str, inner_ref: str) -> str:
    return mf.validate_ref(f"{run_ref}/{inner_ref}", "deepresearch_kernel_v2.outer_ref")


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = mf.validate_ref(ref, "deepresearch_kernel_v2.ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result
