"""Phase 1 compiler for the single-agent DeepResearch baseline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from missionforge.contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from missionforge.extensions import ExtensionLock, compile_extension_lock, npm_install_extension, write_extension_lock
from missionforge.task_contract import (
    ContractClause,
    ExtensionAdapterMode,
    ExtensionCapability,
    ExtensionGrant,
    NetworkPolicy,
    PermissionManifest,
    TaskContract,
    WorkspacePolicy,
)
from missionforge.task_projection import project_judge_rubric, project_worker_brief

from .product_contract import AcademicResearchRequest, research_intensity_profile
from .search_intent import AcademicSearchIntent, SEARCH_INTENT_REF
from .source_collector import AcademicSourceCollectionResult, SOURCE_COLLECTION_REPORT_REF, fixture_source_collection_report
from .workspace import read_json_ref, write_json_ref, write_text_ref


TASK_CONTRACT_REF = "contract/task_contract.json"
WORKSPACE_POLICY_REF = "policy/workspace_policy.json"
PERMISSION_MANIFEST_REF = "policy/permission_manifest.json"
EXTENSION_LOCK_REF = "compiled/extension_lock.json"
WORKER_BRIEF_REF = "projections/worker_brief.json"
JUDGE_RUBRIC_REF = "projections/judge_rubric.json"
PRODUCT_REQUEST_REF = "product_contract/research_request.json"
OUTPUT_CONTRACT_REF = "product_contract/output_contract.json"
COMPILE_REPORT_REF = "product_contract/compile_report.json"
MANUAL_REF = "manuals/deep_research_academic.md"
SOURCE_PACKET_REF = "sources/source_packet.json"
STRUCTURAL_CHECK_POLICY_REF = "product_contract/structural_check_policy.json"
TASK_COMPILE_RESULT_SCHEMA_VERSION = "missionforge_deepresearch.task_contract_compile_result.v1"
EXPECTED_DRAFT_REFS = [
    "reports/final_report.md",
    "reports/evidence_index.md",
    "reports/research_delta.md",
    "reports/reading_plan.md",
    "reports/source_gaps.md",
]
EXPECTED_WORKER_OUTPUT_REFS = [SOURCE_PACKET_REF, *EXPECTED_DRAFT_REFS]


@dataclass(frozen=True)
class DeepResearchTaskContractCompileResult:
    """Refs emitted by compiling a research request into TaskContract form."""

    request_id: str
    run_workspace_ref: str
    task_contract_ref: str
    workspace_policy_ref: str
    permission_manifest_ref: str
    extension_lock_ref: str | None
    worker_brief_ref: str
    judge_rubric_ref: str
    product_request_ref: str
    manual_ref: str
    source_packet_ref: str
    source_collection_report_ref: str
    output_contract_ref: str
    structural_check_policy_ref: str
    compile_report_ref: str
    expected_draft_refs: list[str] = field(default_factory=lambda: list(EXPECTED_DRAFT_REFS))
    contract_hash: str = ""
    schema_version: str = TASK_COMPILE_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DeepResearchTaskContractCompileResult":
        data = require_mapping(payload, "deepresearch_task_contract_compile_result")
        result = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", TASK_COMPILE_RESULT_SCHEMA_VERSION),
                "deepresearch_task_contract_compile_result.schema_version",
            ),
            request_id=require_non_empty_str(data.get("request_id"), "deepresearch_task_contract_compile_result.request_id"),
            run_workspace_ref=validate_ref(
                data.get("run_workspace_ref"),
                "deepresearch_task_contract_compile_result.run_workspace_ref",
            ),
            task_contract_ref=validate_ref(
                data.get("task_contract_ref"),
                "deepresearch_task_contract_compile_result.task_contract_ref",
            ),
            workspace_policy_ref=validate_ref(
                data.get("workspace_policy_ref"),
                "deepresearch_task_contract_compile_result.workspace_policy_ref",
            ),
            permission_manifest_ref=validate_ref(
                data.get("permission_manifest_ref"),
                "deepresearch_task_contract_compile_result.permission_manifest_ref",
            ),
            extension_lock_ref=_optional_ref(
                data.get("extension_lock_ref"),
                "deepresearch_task_contract_compile_result.extension_lock_ref",
            ),
            worker_brief_ref=validate_ref(
                data.get("worker_brief_ref"),
                "deepresearch_task_contract_compile_result.worker_brief_ref",
            ),
            judge_rubric_ref=validate_ref(
                data.get("judge_rubric_ref"),
                "deepresearch_task_contract_compile_result.judge_rubric_ref",
            ),
            product_request_ref=validate_ref(
                data.get("product_request_ref"),
                "deepresearch_task_contract_compile_result.product_request_ref",
            ),
            manual_ref=validate_ref(data.get("manual_ref"), "deepresearch_task_contract_compile_result.manual_ref"),
            source_packet_ref=validate_ref(
                data.get("source_packet_ref"),
                "deepresearch_task_contract_compile_result.source_packet_ref",
            ),
            source_collection_report_ref=validate_ref(
                data.get("source_collection_report_ref")
                or _run_ref(
                    validate_ref(
                        data.get("run_workspace_ref"),
                        "deepresearch_task_contract_compile_result.run_workspace_ref",
                    ),
                    SOURCE_COLLECTION_REPORT_REF,
                ),
                "deepresearch_task_contract_compile_result.source_collection_report_ref",
            ),
            output_contract_ref=validate_ref(
                data.get("output_contract_ref"),
                "deepresearch_task_contract_compile_result.output_contract_ref",
            ),
            structural_check_policy_ref=validate_ref(
                data.get("structural_check_policy_ref"),
                "deepresearch_task_contract_compile_result.structural_check_policy_ref",
            ),
            compile_report_ref=validate_ref(
                data.get("compile_report_ref"),
                "deepresearch_task_contract_compile_result.compile_report_ref",
            ),
            expected_draft_refs=_ref_list(
                data.get("expected_draft_refs", []),
                "deepresearch_task_contract_compile_result.expected_draft_refs",
            ),
            contract_hash=require_non_empty_str(
                data.get("contract_hash"),
                "deepresearch_task_contract_compile_result.contract_hash",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.schema_version != TASK_COMPILE_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("deepresearch_task_contract_compile_result.schema_version is unsupported")
        require_non_empty_str(self.request_id, "deepresearch_task_contract_compile_result.request_id")
        validate_ref(self.run_workspace_ref, "deepresearch_task_contract_compile_result.run_workspace_ref")
        for field_name in (
            "task_contract_ref",
            "workspace_policy_ref",
            "permission_manifest_ref",
            "worker_brief_ref",
            "judge_rubric_ref",
            "product_request_ref",
            "manual_ref",
            "source_packet_ref",
            "source_collection_report_ref",
            "output_contract_ref",
            "structural_check_policy_ref",
            "compile_report_ref",
        ):
            ref = getattr(self, field_name)
            _validate_ref_under_run_workspace(ref, self.run_workspace_ref, f"deepresearch_task_contract_compile_result.{field_name}")
        if self.extension_lock_ref is not None:
            _validate_ref_under_run_workspace(
                self.extension_lock_ref,
                self.run_workspace_ref,
                "deepresearch_task_contract_compile_result.extension_lock_ref",
            )
        _validate_unique_refs(self.expected_draft_refs, "deepresearch_task_contract_compile_result.expected_draft_refs")
        require_non_empty_str(self.contract_hash, "deepresearch_task_contract_compile_result.contract_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "deepresearch_task_contract_compile_result")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "run_workspace_ref": self.run_workspace_ref,
            "task_contract_ref": self.task_contract_ref,
            "workspace_policy_ref": self.workspace_policy_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "extension_lock_ref": self.extension_lock_ref,
            "worker_brief_ref": self.worker_brief_ref,
            "judge_rubric_ref": self.judge_rubric_ref,
            "product_request_ref": self.product_request_ref,
            "manual_ref": self.manual_ref,
            "source_packet_ref": self.source_packet_ref,
            "source_collection_report_ref": self.source_collection_report_ref,
            "output_contract_ref": self.output_contract_ref,
            "structural_check_policy_ref": self.structural_check_policy_ref,
            "compile_report_ref": self.compile_report_ref,
            "expected_draft_refs": list(self.expected_draft_refs),
            "contract_hash": self.contract_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def compile_deepresearch_academic_task_contract(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    source_collection: AcademicSourceCollectionResult | None = None,
    search_intent: AcademicSearchIntent | None = None,
    live_extension_mode: bool = False,
    extension_installer: Callable[[ExtensionGrant, Path], Mapping[str, Any]] | None = None,
) -> DeepResearchTaskContractCompileResult:
    """Compile an academic research request into MissionForge primitives."""

    request.validate()
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_workspace_ref = f"runs/{request.request_id}"
    source_mode = "live" if (source_collection is not None or live_extension_mode) else "fixture"

    workspace_policy = _workspace_policy(request, run_workspace_ref)
    permission_manifest = _permission_manifest(request, source_mode=source_mode)
    extension_lock = _extension_lock_for_source_mode(
        request,
        workspace=root,
        run_workspace_ref=run_workspace_ref,
        permission_manifest=permission_manifest,
        source_mode=source_mode,
        extension_installer=extension_installer,
    )
    output_contract = _output_contract(request)
    effective_search_intent = (
        search_intent
        or (
            source_collection.search_intent
            if source_collection is not None and source_collection.search_intent is not None
            else None
        )
        or AcademicSearchIntent.from_queries(
            request,
            [request.topic],
            created_by="external",
            notes=["Fixture or no-intent run preserves the original topic only."],
        )
    )
    if live_extension_mode:
        source_packet = _live_extension_source_packet(
            request,
            search_intent=effective_search_intent,
        )
    else:
        source_packet = source_collection.source_packet if source_collection is not None else _fixture_source_packet(request)
    if live_extension_mode:
        source_collection_report = _live_extension_source_collection_report(
            request,
            search_intent=effective_search_intent,
            extension_lock_ref=_run_ref(run_workspace_ref, EXTENSION_LOCK_REF),
            extension_grants=permission_manifest.extension_grants,
        )
    else:
        source_collection_report = (
            source_collection.collection_report
            if source_collection is not None
            else fixture_source_collection_report(request)
        )
    structural_policy = _structural_check_policy()
    task_contract = _task_contract(request, workspace_policy, permission_manifest, source_mode=source_mode)
    worker_brief = project_worker_brief(
        task_contract,
        workspace_policy,
        permission_manifest,
        brief_id=f"deepresearch-{request.request_id}-researcher-brief",
        contract_ref=TASK_CONTRACT_REF,
        completion_report_ref="attempts/researcher/execution_report.json",
    )
    judge_rubric = project_judge_rubric(
        task_contract,
        workspace_policy,
        rubric_id=f"deepresearch-{request.request_id}-judge-rubric",
        contract_ref=TASK_CONTRACT_REF,
        evidence_refs=[SEARCH_INTENT_REF, SOURCE_PACKET_REF, SOURCE_COLLECTION_REPORT_REF],
        hard_check_refs=[],
    )

    write_json_ref(root, _run_ref(run_workspace_ref, PRODUCT_REQUEST_REF), request.to_dict())
    write_text_ref(root, _run_ref(run_workspace_ref, MANUAL_REF), _manual_text(request))
    write_json_ref(root, _run_ref(run_workspace_ref, SEARCH_INTENT_REF), effective_search_intent.to_dict())
    write_json_ref(root, _run_ref(run_workspace_ref, SOURCE_PACKET_REF), source_packet)
    write_json_ref(root, _run_ref(run_workspace_ref, SOURCE_COLLECTION_REPORT_REF), source_collection_report)
    if source_collection is not None:
        for ref, payload in source_collection.source_payloads.items():
            if ref == SEARCH_INTENT_REF:
                continue
            write_json_ref(root, _run_ref(run_workspace_ref, ref), payload)
    write_json_ref(root, _run_ref(run_workspace_ref, OUTPUT_CONTRACT_REF), output_contract)
    write_json_ref(root, _run_ref(run_workspace_ref, STRUCTURAL_CHECK_POLICY_REF), structural_policy)
    write_json_ref(root, _run_ref(run_workspace_ref, TASK_CONTRACT_REF), task_contract.to_dict())
    write_json_ref(root, _run_ref(run_workspace_ref, WORKSPACE_POLICY_REF), workspace_policy.to_dict())
    write_json_ref(root, _run_ref(run_workspace_ref, PERMISSION_MANIFEST_REF), permission_manifest.to_dict())
    if extension_lock is not None:
        write_extension_lock(root / _run_ref(run_workspace_ref, EXTENSION_LOCK_REF), extension_lock)
    write_json_ref(root, _run_ref(run_workspace_ref, WORKER_BRIEF_REF), worker_brief.to_dict())
    write_json_ref(root, _run_ref(run_workspace_ref, JUDGE_RUBRIC_REF), judge_rubric.to_dict())

    result = DeepResearchTaskContractCompileResult(
        request_id=request.request_id,
        run_workspace_ref=run_workspace_ref,
        task_contract_ref=_run_ref(run_workspace_ref, TASK_CONTRACT_REF),
        workspace_policy_ref=_run_ref(run_workspace_ref, WORKSPACE_POLICY_REF),
        permission_manifest_ref=_run_ref(run_workspace_ref, PERMISSION_MANIFEST_REF),
        extension_lock_ref=_run_ref(run_workspace_ref, EXTENSION_LOCK_REF) if extension_lock is not None else None,
        worker_brief_ref=_run_ref(run_workspace_ref, WORKER_BRIEF_REF),
        judge_rubric_ref=_run_ref(run_workspace_ref, JUDGE_RUBRIC_REF),
        product_request_ref=_run_ref(run_workspace_ref, PRODUCT_REQUEST_REF),
        manual_ref=_run_ref(run_workspace_ref, MANUAL_REF),
        source_packet_ref=_run_ref(run_workspace_ref, SOURCE_PACKET_REF),
        source_collection_report_ref=_run_ref(run_workspace_ref, SOURCE_COLLECTION_REPORT_REF),
        output_contract_ref=_run_ref(run_workspace_ref, OUTPUT_CONTRACT_REF),
        structural_check_policy_ref=_run_ref(run_workspace_ref, STRUCTURAL_CHECK_POLICY_REF),
        compile_report_ref=_run_ref(run_workspace_ref, COMPILE_REPORT_REF),
        expected_draft_refs=list(EXPECTED_DRAFT_REFS),
        contract_hash=task_contract.contract_hash,
    )
    write_json_ref(
        root,
        result.compile_report_ref,
        {
            "schema_version": "missionforge_deepresearch.compile_report.v1",
            "request_id": request.request_id,
            "task_contract_ref": result.task_contract_ref,
            "worker_brief_ref": result.worker_brief_ref,
            "manual_ref": result.manual_ref,
            "source_packet_ref": result.source_packet_ref,
            "extension_lock_ref": result.extension_lock_ref,
            "source_collection_report_ref": result.source_collection_report_ref,
            "output_contract_ref": result.output_contract_ref,
            "expected_draft_refs": list(result.expected_draft_refs),
            "contract_hash": result.contract_hash,
            "source_mode": source_mode,
            "research_intensity": request.research_intensity.value,
            "research_intensity_profile": research_intensity_profile(request.research_intensity).to_dict(),
        },
    )
    result.validate()
    return result


def load_deepresearch_task_contract(
    workspace: str | Path,
    result: DeepResearchTaskContractCompileResult,
) -> tuple[TaskContract, WorkspacePolicy, PermissionManifest]:
    """Load compiled TaskContract, WorkspacePolicy, and PermissionManifest refs."""

    result.validate()
    task_contract = TaskContract.from_dict(read_json_ref(workspace, result.task_contract_ref, "task_contract"))
    workspace_policy = WorkspacePolicy.from_dict(read_json_ref(workspace, result.workspace_policy_ref, "workspace_policy"))
    permission_manifest = PermissionManifest.from_dict(
        read_json_ref(workspace, result.permission_manifest_ref, "permission_manifest")
    )
    return task_contract, workspace_policy, permission_manifest


def _task_contract(
    request: AcademicResearchRequest,
    workspace_policy: WorkspacePolicy,
    permission_manifest: PermissionManifest,
    *,
    source_mode: str,
) -> TaskContract:
    intensity_profile = research_intensity_profile(request.research_intensity)
    source_refs = [
        PRODUCT_REQUEST_REF,
        MANUAL_REF,
        SEARCH_INTENT_REF,
        SOURCE_PACKET_REF,
        SOURCE_COLLECTION_REPORT_REF,
        OUTPUT_CONTRACT_REF,
        STRUCTURAL_CHECK_POLICY_REF,
    ]
    if permission_manifest.extension_grants:
        source_refs.append(EXTENSION_LOCK_REF)
    return TaskContract(
        contract_id=f"deepresearch-{request.request_id}-task-contract",
        product_id="deepresearch.academic",
        objective=(
            f"Produce a citation-backed academic deep research report for topic: {request.topic}. "
            "First gather evidence and write sources/source_packet.json with non-empty source_records; "
            "then write report artifacts whose material claims cite those source ids."
        ),
        background=[
            "Phase 1 single-agent DeepResearch baseline.",
            "The researcher owns semantic planning, triage, synthesis, delta analysis, and draft writing.",
            "Search intent is an LLM- or user-authored query plan; live extension tools execute it mechanically.",
            "MissionForge owns refs, workspace, permissions, schemas, and structural checks.",
            f"Research intensity is {request.research_intensity.value}: {intensity_profile.guidance}",
        ],
        users_or_audience=[request.audience],
        required_outputs=[
            ContractClause(
                clause_id="dr-output-000",
                text=(
                    "Write sources/source_packet.json as the first structured evidence sink before report artifacts. "
                    "Every report citation must refer to source ids in this packet."
                ),
                refs=[SOURCE_PACKET_REF],
            ),
            *[
                ContractClause(
                    clause_id=f"dr-output-{index:03d}",
                    text=f"Write the DeepResearch draft artifact at {ref}.",
                    refs=[ref],
                )
                for index, ref in enumerate(EXPECTED_DRAFT_REFS, start=1)
            ],
        ],
        semantic_acceptance=[
            ContractClause(
                clause_id="dr-accept-coverage",
                text=(
                    "The report should cover major lines of work, key papers, code or benchmark evidence, "
                    f"and open gaps at {request.research_intensity.value} intensity."
                ),
                refs=[MANUAL_REF, SEARCH_INTENT_REF, SOURCE_PACKET_REF, SOURCE_COLLECTION_REPORT_REF],
            ),
            ContractClause(
                clause_id="dr-accept-freshness",
                text="The report should distinguish current evidence from stale or historical evidence.",
                refs=[MANUAL_REF, SOURCE_PACKET_REF, SOURCE_COLLECTION_REPORT_REF],
            ),
            ContractClause(
                clause_id="dr-accept-citations",
                text="Material claims should use [S1] citation ids from source_packet.json and include a References section.",
                refs=[MANUAL_REF, SOURCE_PACKET_REF],
            ),
            ContractClause(
                clause_id="dr-accept-delta",
                text="The delta artifact should compare against previous run refs when supplied, or state that this is a baseline.",
                refs=[MANUAL_REF, PRODUCT_REQUEST_REF],
            ),
        ],
        hard_constraints=[
            ContractClause(
                clause_id="dr-hard-no-self-accept",
                text=(
                    "The researcher must not claim final product acceptance. Write a candidate report without "
                    "labeling the title as draft; final acceptance is recorded only by the independent judge/final package."
                ),
                refs=[OUTPUT_CONTRACT_REF],
            ),
            ContractClause(
                clause_id="dr-hard-output-refs",
                text="Write only the expected reports artifacts plus sources/source_packet.json.",
                refs=[OUTPUT_CONTRACT_REF, PERMISSION_MANIFEST_REF],
            ),
            ContractClause(
                clause_id="dr-hard-source-boundary",
                text="Use the visible source packet and previous-run refs as evidence; record gaps instead of inventing support.",
                refs=[SEARCH_INTENT_REF, SOURCE_PACKET_REF, PRODUCT_REQUEST_REF],
            ),
            ContractClause(
                clause_id="dr-hard-evidence-first",
                text=(
                    "Treat sources/source_packet.json as the first deliverable in the work loop: collect evidence, "
                    "record source_records, then synthesize reports against those ids."
                ),
                refs=[SOURCE_PACKET_REF, OUTPUT_CONTRACT_REF],
            ),
        ],
        non_goals=[
            ContractClause(clause_id=f"dr-nongoal-{index:03d}", text=text)
            for index, text in enumerate(request.non_goals, start=1)
        ],
        assumptions=[
            ContractClause(
                clause_id="dr-assumption-source-mode",
                text=f"This run uses {source_mode} source mode.",
            ),
            ContractClause(
                clause_id="dr-assumption-research-intensity",
                text=f"This run uses {request.research_intensity.value} research intensity.",
            )
        ],
        risk_notes=[
            ContractClause(
                clause_id="dr-risk-source-quality",
                text="The researcher must report source coverage gaps instead of inventing unsupported evidence.",
            )
        ],
        workspace_policy_ref=WORKSPACE_POLICY_REF,
        permission_manifest_ref=PERMISSION_MANIFEST_REF,
        judge_rubric_ref=JUDGE_RUBRIC_REF,
        revision_policy={"mode": "explicit_revision_required", "product_id": "deepresearch.academic"},
        source_refs=source_refs,
        product_contract_refs=[OUTPUT_CONTRACT_REF, STRUCTURAL_CHECK_POLICY_REF],
        created_by="missionforge_deepresearch.compiler",
        metadata={
            "phase": "phase1_single_agent",
            "language": request.language,
            "source_mode": source_mode,
            "research_intensity": request.research_intensity.value,
            "live_source_strategy": "pi_extensions" if permission_manifest.extension_grants else "fixture_or_collector",
            "workspace_policy_id": workspace_policy.policy_id,
            "permission_manifest_id": permission_manifest.manifest_id,
        },
    )


def _workspace_policy(request: AcademicResearchRequest, run_workspace_ref: str) -> WorkspacePolicy:
    return WorkspacePolicy(
        policy_id=f"deepresearch-{request.request_id}-workspace",
        workspace_root_ref=run_workspace_ref,
        input_refs=["contract", "policy", "projections", "manuals", "sources", "product_contract", "compiled"],
        artifact_root_refs=["reports", "packages", "compiled"],
        scratch_root_refs=["scratch"],
        denied_refs=["secrets"],
    )


def _permission_manifest(request: AcademicResearchRequest, *, source_mode: str) -> PermissionManifest:
    extension_grants = _live_extension_grants(request) if source_mode == "live" else []
    return PermissionManifest(
        manifest_id=f"deepresearch-{request.request_id}-permissions",
        workspace_policy_ref=WORKSPACE_POLICY_REF,
        readable_refs=["contract", "policy", "projections", "manuals", "sources", "product_contract", "compiled"],
        writable_refs=["reports", SOURCE_PACKET_REF, "attempts", "packages", "ledgers", "compiled"],
        denied_refs=["secrets"],
        allowed_commands=[],
        network_policy=NetworkPolicy.ENABLED if source_mode == "live" else NetworkPolicy.DISABLED,
        env_allowlist=["PATH"] if source_mode == "live" else [],
        extension_grants=extension_grants,
    )


def _live_extension_source_packet(
    request: AcademicResearchRequest,
    *,
    search_intent: AcademicSearchIntent,
) -> dict[str, Any]:
    search_intent.validate_for_request(request)
    return {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": request.request_id,
        "mode": "live",
        "query": request.topic,
        "search_intent_ref": SEARCH_INTENT_REF,
        "search_queries": list(search_intent.queries),
        "previous_run_refs": list(request.previous_run_refs),
        "collection_policy": {
            "source_acquisition": "pi_extensions",
            "query_expansion": "search_intent",
            "ranking_authority": "researcher_piworker",
            "tool_surface": ["web", "code_search"],
        },
        "source_records": [],
        "citation_contract": _citation_contract(),
        "limitations": [
            "Python did not precollect sources for this run.",
            "The researcher should use loaded Pi extensions to gather evidence directly.",
            "Before finishing, the researcher must overwrite this packet with structured source_records.",
        ],
    }


def _live_extension_source_collection_report(
    request: AcademicResearchRequest,
    *,
    search_intent: AcademicSearchIntent,
    extension_lock_ref: str,
    extension_grants: list[ExtensionGrant],
) -> dict[str, Any]:
    search_intent.validate_for_request(request)
    return {
        "schema_version": "missionforge_deepresearch.source_collection_report.v1",
        "request_id": request.request_id,
        "mode": "live",
        "query": request.topic,
        "search_intent_ref": SEARCH_INTENT_REF,
        "search_intent_created_by": search_intent.created_by,
        "search_queries": list(search_intent.queries),
        "search_query_count": len(search_intent.queries),
        "search_query_limit": len(search_intent.queries),
        "retrieved_at": None,
        "provider_reports": [],
        "candidate_count": 0,
        "selected_count": 0,
        "source_packet_ref": "sources/source_packet.json",
        "source_record_refs": [],
        "extension_lock_ref": extension_lock_ref,
        "extension_grant_ids": [grant.grant_id for grant in extension_grants],
        "tool_surface": [grant.capability.value for grant in extension_grants],
        "limitations": [
            "No Python collector was used in the live extension path.",
            "Evidence gathering is delegated to loaded Pi extensions and the researcher worker.",
        ],
    }


def _extension_lock_for_source_mode(
    request: AcademicResearchRequest,
    *,
    workspace: Path,
    run_workspace_ref: str,
    permission_manifest: PermissionManifest,
    source_mode: str,
    extension_installer: Callable[[ExtensionGrant, Path], Mapping[str, Any]] | None = None,
) -> ExtensionLock | None:
    if source_mode != "live":
        return None
    return compile_extension_lock(
        permission_manifest,
        source_permission_manifest_ref=_run_ref(run_workspace_ref, PERMISSION_MANIFEST_REF),
        workspace_root=workspace / run_workspace_ref,
        install_root_ref=".missionforge/extensions",
        mode="install",
        installer=extension_installer or npm_install_extension,
    )


def _live_extension_grants(request: AcademicResearchRequest) -> list[ExtensionGrant]:
    return [
        ExtensionGrant(
            grant_id=f"deepresearch-{request.request_id}-web",
            package="npm:pi-web-access",
            version_spec="0.10.7",
            capability=ExtensionCapability.WEB,
            requires_network=True,
            adapter_mode=ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION,
            metadata={"purpose": "web_search_and_fetch"},
        ),
        ExtensionGrant(
            grant_id=f"deepresearch-{request.request_id}-code-search",
            package="npm:@juicesharp/rpiv-web-tools",
            version_spec="0.1.0",
            capability=ExtensionCapability.CODE_SEARCH,
            requires_network=True,
            adapter_mode=ExtensionAdapterMode.UNTRUSTED_PI_EXTENSION,
            metadata={"purpose": "github_and_repository_search"},
        ),
    ]


def _manual_text(request: AcademicResearchRequest) -> str:
    profile = research_intensity_profile(request.research_intensity)
    return f"""# Academic Deep Research Manual

You are the single researcher for this Phase 1 DeepResearch run.

Research intensity: `{request.research_intensity.value}`.

Intensity guidance:

{profile.guidance}

Own the semantic work:

- clarify the research shape from the frozen task contract;
- inspect the source packet before writing conclusions;
- inspect the search intent and source collection report before judging coverage;
- use live tools when available, then write `sources/source_packet.json` with
  structured `source_records`;
- separate supported claims from gaps;
- compare against previous run refs when present;
- cite source identifiers from `sources/source_packet.json` in material claims;
- write concise artifacts for an R&D audience.

Do not claim final product acceptance. This worker produces candidate report
artifacts for structural checks and independent judging. Do not label the
`reports/final_report.md` title as a draft; acceptance status belongs only in
the judged run result or final package.

Evidence and citation contract:

- Write order matters: produce or update `sources/source_packet.json` before
  writing report artifacts, then cite that packet consistently.
- Source ids must use `S1`, `S2`, ... style identifiers.
- `sources/source_packet.json` must contain non-empty `source_records`.
- Each source record must contain `source_id`, `title`, `source_type`, and at
  least one locator such as `url`, `doi`, `source_ref`, `github_repo`, or
  `arxiv_id`.
- `reports/final_report.md` must cite material claims as `[S1]` or
  `[S1, S2]`.
- `reports/final_report.md` must include a `## References` section listing the
  cited source ids with title and locator.
- `reports/evidence_index.md` must map every source id in
  `sources/source_packet.json` using the same `[S1]` citation marker.
- If evidence is incomplete, keep the source record factual and explain the gap
  in `reports/source_gaps.md`; do not invent missing bibliographic data.
"""


def _output_contract(request: AcademicResearchRequest) -> dict[str, Any]:
    profile = research_intensity_profile(request.research_intensity)
    return {
        "schema_version": "missionforge_deepresearch.output_contract.v1",
        "request_id": request.request_id,
        "status_authority": "draft_ready_after_structural_checks",
        "language": request.language,
        "research_intensity": request.research_intensity.value,
        "research_intensity_profile": profile.to_dict(),
        "expected_draft_refs": list(EXPECTED_DRAFT_REFS),
        "expected_worker_output_refs": list(EXPECTED_WORKER_OUTPUT_REFS),
        "source_packet_ref": SOURCE_PACKET_REF,
        "artifact_write_order": [SOURCE_PACKET_REF, *EXPECTED_DRAFT_REFS],
        "citation_contract": _citation_contract(),
        "notes": [
            "final_report.md is the main user-facing candidate report.",
            "source_packet.json is the first structured evidence sink and should be written before report artifacts.",
            "evidence_index.md maps source identifiers to source refs.",
            "research_delta.md is required even for baseline runs.",
            "source_gaps.md should make missing evidence explicit.",
            "Do not label the final_report.md title as draft; final status is carried by judge/final package artifacts.",
        ],
    }


def _structural_check_policy() -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.structural_check_policy.v1",
        "required_non_empty_refs": list(EXPECTED_DRAFT_REFS),
        "required_source_packet_ref": SOURCE_PACKET_REF,
        "citation_contract": _citation_contract(),
        "status_on_pass": "draft_ready",
    }


def _fixture_source_packet(request: AcademicResearchRequest) -> dict[str, Any]:
    return {
        "schema_version": "missionforge_deepresearch.source_packet.v1",
        "request_id": request.request_id,
        "mode": "fixture",
        "query": request.topic,
        "search_intent_ref": SEARCH_INTENT_REF,
        "search_queries": [request.topic],
        "previous_run_refs": list(request.previous_run_refs),
        "source_records": [
            {
                "source_id": "S1",
                "title": "Survey seed for compiler autotuning",
                "source_type": "paper_index_fixture",
                "source_ref": "sources/fixtures/compiler_autotuning_seed.json",
                "year": 2024,
                "url": "https://example.invalid/missionforge/fixture/compiler-autotuning",
                "notes": "Fixture source used only to validate package shape.",
            },
            {
                "source_id": "S2",
                "title": "Survey seed for kernel generation",
                "source_type": "paper_index_fixture",
                "source_ref": "sources/fixtures/kernel_generation_seed.json",
                "year": 2024,
                "url": "https://example.invalid/missionforge/fixture/kernel-generation",
                "notes": "Fixture source used only to validate package shape.",
            },
            {
                "source_id": "S3",
                "title": "Survey seed for engineering harness practice",
                "source_type": "repository_fixture",
                "source_ref": "sources/fixtures/harness_engineering_seed.json",
                "year": 2024,
                "url": "https://example.invalid/missionforge/fixture/harness-engineering",
                "notes": "Fixture source used only to validate package shape.",
            },
        ],
        "citation_contract": _citation_contract(),
        "limitations": [
            "Fixture mode validates orchestration, not live source coverage.",
            "Live collection is deferred to Phase 2.",
        ],
    }


def _citation_contract() -> dict[str, Any]:
    return {
        "source_id_format": "S[0-9]+",
        "citation_format": "[S1] or [S1, S2]",
        "required_final_report_section": "## References",
        "authority": "source_packet.source_records",
    }


def _run_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"


def _validate_ref_under_run_workspace(ref: str, run_workspace_ref: str, field_name: str) -> None:
    safe_ref = validate_ref(ref, field_name)
    safe_root = validate_ref(run_workspace_ref, "run_workspace_ref")
    if safe_ref != safe_root and not safe_ref.startswith(f"{safe_root}/"):
        raise ContractValidationError(f"{field_name} must be under run_workspace_ref")


def _ref_list(value: Any, field_name: str) -> list[str]:
    return [validate_ref(item, f"{field_name}[]") for item in require_str_list(value, field_name)]


def _validate_unique_refs(values: list[str], field_name: str) -> None:
    refs = _ref_list(values, field_name)
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)
