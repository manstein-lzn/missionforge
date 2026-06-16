"""Single-agent Phase 1 runtime for the DeepResearch integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.contracts import ContractValidationError, stable_json_hash, validate_ref
from missionforge.task_contract import ExtensionGrant
from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallResultStatus, PiWorkerCallRole
from missionforge.piworker_runtime import PiWorkerCallAdapter, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult

from .compiler import (
    EXTENSION_LOCK_REF,
    EXPECTED_WORKER_OUTPUT_REFS,
    MANUAL_REF,
    OUTPUT_CONTRACT_REF,
    PERMISSION_MANIFEST_REF,
    PRODUCT_REQUEST_REF,
    SOURCE_COLLECTION_REPORT_REF,
    SOURCE_PACKET_REF,
    STRUCTURAL_CHECK_POLICY_REF,
    TASK_CONTRACT_REF,
    WORKER_BRIEF_REF,
    WORKSPACE_POLICY_REF,
    compile_deepresearch_academic_task_contract,
    load_deepresearch_task_contract,
)
from .evidence import audit_quality_contract, audit_report_citations, audit_source_packet
from .product_contract import AcademicResearchRequest, DeepResearchRunResult, DeepResearchRunStatus
from .product_contract import research_intensity_profile, research_report_section_specs
from .search_intent import (
    AcademicSearchIntent,
    SEARCH_INTENT_REF,
    generate_search_intent_with_piworker,
)
from .source_collector import (
    AcademicSourceCollectionConfig,
    collect_live_academic_sources,
)
from .workspace import read_json_ref, read_text_ref, ref_is_non_empty_file, write_json_ref, write_text_ref


SOURCE_MODES = {"fixture", "live"}
RESEARCHER_MODES = {"fixture", "piworker"}
SEARCH_INTENT_MODES = {"none", "external", "piworker"}
RESEARCHER_CALL_REF = "attempts/researcher/piworker_call.json"
RESEARCHER_CALL_RESULT_REF = "attempts/researcher/piworker_call_result.json"
RESEARCHER_EXECUTION_REPORT_REF = "attempts/researcher/execution_report.json"
RESEARCHER_METRICS_REF = "attempts/researcher/metrics.json"
STRUCTURAL_CHECK_REPORT_REF = "reports/structural_checks.json"
RUN_RESULT_REF = "packages/deepresearch_run_result.json"
ExtensionInstaller = Callable[[ExtensionGrant, Path], Mapping[str, Any]]


def run_deepresearch_academic_single_agent(
    request: AcademicResearchRequest,
    *,
    workspace: str | Path = ".",
    adapter: PiWorkerCallAdapter | None = None,
    source_mode: str = "fixture",
    researcher_mode: str = "fixture",
    search_intent_mode: str = "none",
    search_queries: list[str] | None = None,
    search_intent_ref: str | None = None,
    source_config: AcademicSourceCollectionConfig | None = None,
    search_intent_adapter: PiWorkerCallAdapter | None = None,
    piworker_config: PiAgentRuntimeConfig | None = None,
    piworker_environ: Mapping[str, str] | None = None,
    live_extension_mode: bool = False,
    extension_installer: ExtensionInstaller | None = None,
) -> DeepResearchRunResult:
    """Run the single-agent academic research baseline."""

    request.validate()
    if source_mode not in SOURCE_MODES:
        raise ContractValidationError(f"deepresearch source_mode must be one of {sorted(SOURCE_MODES)}")
    if researcher_mode not in RESEARCHER_MODES:
        raise ContractValidationError(f"deepresearch researcher_mode must be one of {sorted(RESEARCHER_MODES)}")
    if search_intent_mode not in SEARCH_INTENT_MODES:
        raise ContractValidationError(f"deepresearch search_intent_mode must be one of {sorted(SEARCH_INTENT_MODES)}")
    if source_mode != "live" and (search_intent_mode != "none" or search_queries or search_intent_ref):
        raise ContractValidationError("deepresearch search intent is only supported with source_mode=live")
    root = Path(workspace).resolve()
    preflight_root = root / f"runs/{request.request_id}"
    intensity_profile = research_intensity_profile(request.research_intensity)
    effective_source_config = source_config or AcademicSourceCollectionConfig(
        max_records=intensity_profile.max_sources,
        max_search_queries=intensity_profile.max_search_queries,
    )
    search_intent, search_intent_evidence_refs = _resolve_search_intent(
        request,
        workspace=preflight_root,
        mode=search_intent_mode,
        search_queries=search_queries,
        search_intent_ref=search_intent_ref,
        search_intent_adapter=search_intent_adapter,
        piworker_config=piworker_config,
        piworker_environ=piworker_environ,
    )
    source_collection = None
    if source_mode == "live" and not live_extension_mode:
        source_collection = collect_live_academic_sources(
            request,
            config=effective_source_config,
            search_intent=search_intent,
        )
    compile_result = compile_deepresearch_academic_task_contract(
        request,
        workspace=root,
        source_collection=source_collection,
        search_intent=search_intent,
        live_extension_mode=live_extension_mode or source_mode == "live",
        extension_installer=extension_installer,
    )
    task_contract, _workspace_policy, permission_manifest = load_deepresearch_task_contract(root, compile_result)
    run_root = root / compile_result.run_workspace_ref
    source_packet = read_json_ref(run_root, SOURCE_PACKET_REF, "source_packet")
    worker_extension_lock_ref = (
        _run_relative_ref(compile_result.run_workspace_ref, compile_result.extension_lock_ref)
        if compile_result.extension_lock_ref
        else None
    )
    worker_visible_refs = [
        TASK_CONTRACT_REF,
        WORKSPACE_POLICY_REF,
        PERMISSION_MANIFEST_REF,
        WORKER_BRIEF_REF,
        PRODUCT_REQUEST_REF,
        MANUAL_REF,
        SEARCH_INTENT_REF,
        SOURCE_PACKET_REF,
        SOURCE_COLLECTION_REPORT_REF,
        OUTPUT_CONTRACT_REF,
        STRUCTURAL_CHECK_POLICY_REF,
    ]
    if worker_extension_lock_ref is not None:
        worker_visible_refs.append(worker_extension_lock_ref)
    if compile_result.extension_lock_ref is None and source_mode == "live" and not live_extension_mode:
        raise ContractValidationError("deepresearch live source mode requires an extension lock")
    expected_worker_output_refs = list(EXPECTED_WORKER_OUTPUT_REFS)
    call = PiWorkerCall(
        call_id=f"deepresearch-{request.request_id}-researcher",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id=task_contract.contract_id,
        contract_hash=task_contract.contract_hash,
        contract_ref=TASK_CONTRACT_REF,
        objective=task_contract.objective,
        visible_refs=worker_visible_refs,
        writable_refs=list(permission_manifest.writable_refs),
        expected_output_refs=expected_worker_output_refs,
        permission_manifest_ref=PERMISSION_MANIFEST_REF,
        source_packet_ref=SOURCE_PACKET_REF,
        source_packet_hash=stable_json_hash(source_packet),
        evidence_refs=_dedupe_refs([
            SEARCH_INTENT_REF,
            SOURCE_PACKET_REF,
            SOURCE_COLLECTION_REPORT_REF,
            *([worker_extension_lock_ref] if worker_extension_lock_ref else []),
        ]),
        output_schema_ref=OUTPUT_CONTRACT_REF,
        validation_policy_ref=STRUCTURAL_CHECK_POLICY_REF,
        runtime_budget={
            "max_turns": intensity_profile.researcher_max_turns,
            "timeout_seconds": intensity_profile.piworker_timeout_seconds,
        },
        metadata={
            "phase": "phase1_single_agent",
            "source_mode": source_mode,
            "researcher_mode": researcher_mode,
            "search_intent_mode": search_intent_mode,
            "research_intensity": request.research_intensity.value,
        },
    )
    write_json_ref(run_root, RESEARCHER_CALL_REF, call.to_dict())
    researcher = adapter or _researcher_adapter(researcher_mode, piworker_config, piworker_environ)
    call_result = run_piworker_call(
        call,
        workspace=run_root,
        adapter=researcher,
        result_id=f"{call.call_id}-result",
        extension_lock_ref=worker_extension_lock_ref,
        metadata={
            "phase": "phase1_single_agent",
            "source_mode": source_mode,
            "researcher_mode": researcher_mode,
            "search_intent_mode": search_intent_mode,
        },
    )
    write_json_ref(run_root, RESEARCHER_CALL_RESULT_REF, call_result.to_dict())
    structural = run_structural_checks(
        workspace=run_root,
        expected_refs=expected_worker_output_refs,
        call_result=call_result,
    )
    structural_status = structural["status"]
    status = (
        DeepResearchRunStatus.DRAFT_READY
        if call_result.status is PiWorkerCallResultStatus.COMPLETED and structural_status == "passed"
        else DeepResearchRunStatus.FAILED
    )
    result = DeepResearchRunResult(
        request_id=request.request_id,
        status=status,
        run_workspace_ref=compile_result.run_workspace_ref,
        run_result_ref=_outer_ref(compile_result.run_workspace_ref, RUN_RESULT_REF),
        task_contract_ref=compile_result.task_contract_ref,
        manual_ref=compile_result.manual_ref,
        source_packet_ref=compile_result.source_packet_ref,
        output_contract_ref=compile_result.output_contract_ref,
        researcher_call_ref=_outer_ref(compile_result.run_workspace_ref, RESEARCHER_CALL_REF),
        researcher_call_result_ref=_outer_ref(compile_result.run_workspace_ref, RESEARCHER_CALL_RESULT_REF),
        structural_check_ref=_outer_ref(compile_result.run_workspace_ref, STRUCTURAL_CHECK_REPORT_REF),
        draft_artifact_refs=[_outer_ref(compile_result.run_workspace_ref, ref) for ref in compile_result.expected_draft_refs],
        evidence_refs=_dedupe_refs([
            *[_outer_ref(compile_result.run_workspace_ref, ref) for ref in search_intent_evidence_refs],
            _outer_ref(compile_result.run_workspace_ref, SEARCH_INTENT_REF),
            compile_result.source_packet_ref,
            compile_result.source_collection_report_ref,
            *([compile_result.extension_lock_ref] if compile_result.extension_lock_ref else []),
            _outer_ref(compile_result.run_workspace_ref, call_result.execution_report_ref),
            _outer_ref(compile_result.run_workspace_ref, STRUCTURAL_CHECK_REPORT_REF),
        ]),
        metric_refs=[_outer_ref(compile_result.run_workspace_ref, ref) for ref in call_result.metric_refs],
        contract_hash=task_contract.contract_hash,
    )
    write_json_ref(root, result.run_result_ref, result.to_dict())
    return result


def _resolve_search_intent(
    request: AcademicResearchRequest,
    *,
    workspace: Path,
    mode: str,
    search_queries: list[str] | None,
    search_intent_ref: str | None,
    search_intent_adapter: PiWorkerCallAdapter | None,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> tuple[AcademicSearchIntent | None, list[str]]:
    if mode == "none":
        if search_queries:
            return (
                AcademicSearchIntent.from_queries(
                    request,
                    search_queries,
                    created_by="external",
                    notes=["Search queries were supplied externally."],
                ),
                [],
            )
        return None, []
    if mode == "external":
        if search_queries:
            return (
                AcademicSearchIntent.from_queries(
                    request,
                    search_queries,
                    created_by="external",
                    notes=["Search queries were supplied externally."],
                ),
                [],
            )
        if not search_intent_ref:
            raise ContractValidationError("deepresearch search_intent_mode=external requires search_queries or search_intent_ref")
        intent = AcademicSearchIntent.from_dict(read_json_ref(workspace, search_intent_ref, "academic_search_intent"))
        intent.validate_for_request(request)
        return intent, [search_intent_ref]
    if mode == "piworker":
        adapter = search_intent_adapter or _piworker_adapter(piworker_config, piworker_environ)
        generation = generate_search_intent_with_piworker(
            request,
            workspace=workspace,
            adapter=adapter,
        )
        return generation.search_intent, generation.evidence_refs
    raise ContractValidationError(f"deepresearch search_intent_mode must be one of {sorted(SEARCH_INTENT_MODES)}")


def _researcher_adapter(
    researcher_mode: str,
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallAdapter:
    if researcher_mode == "fixture":
        return FixtureAcademicResearcherAdapter()
    if researcher_mode == "piworker":
        return PiAgentRuntimeAdapter(
            piworker_config or PiAgentRuntimeConfig(provider_mode="live"),
            environ=piworker_environ,
        )
    raise ContractValidationError(f"deepresearch researcher_mode must be one of {sorted(RESEARCHER_MODES)}")


def _piworker_adapter(
    piworker_config: PiAgentRuntimeConfig | None,
    piworker_environ: Mapping[str, str] | None,
) -> PiWorkerCallAdapter:
    return PiAgentRuntimeAdapter(
        piworker_config or PiAgentRuntimeConfig(provider_mode="live"),
        environ=piworker_environ,
    )


def load_deepresearch_run_result(workspace: str | Path, ref: str) -> DeepResearchRunResult:
    """Load a refs-first DeepResearch run result."""

    return DeepResearchRunResult.from_dict(read_json_ref(workspace, ref, "deepresearch_run_result"))


def run_structural_checks(
    *,
    workspace: str | Path,
    expected_refs: list[str],
    call_result: PiWorkerCallResult,
) -> dict[str, Any]:
    """Mechanically verify that expected draft refs exist and are non-empty."""

    checked_refs = [validate_ref(ref, "deepresearch_structural_check.expected_refs[]") for ref in expected_refs]
    missing_or_empty = [ref for ref in checked_refs if not ref_is_non_empty_file(workspace, ref)]
    missing_from_worker_result = sorted(set(checked_refs) - set(call_result.output_refs))
    source_packet_audit = _audit_source_packet_ref(workspace)
    citation_audit = _audit_citation_refs(workspace, source_packet_audit.source_ids)
    quality_audit = _audit_quality_contract_ref(workspace)
    status = (
        "passed"
        if (
            not missing_or_empty
            and not missing_from_worker_result
            and source_packet_audit.passed
            and citation_audit.passed
            and quality_audit.passed
        )
        else "failed"
    )
    report = {
        "schema_version": "missionforge_deepresearch.structural_check_report.v1",
        "status": status,
        "checked_refs": checked_refs,
        "missing_or_empty_refs": missing_or_empty,
        "missing_from_worker_result_refs": missing_from_worker_result,
        "source_packet_audit": source_packet_audit.to_dict(),
        "citation_audit": citation_audit.to_dict(),
        "quality_contract_audit": quality_audit.to_dict(),
        "notes": [
            "Structural checks enforce package shape, citation consistency, and the mechanical high-quality contract.",
            "Structural checks do not rank source importance or judge semantic synthesis quality.",
            "Passing structural checks only permits draft_ready.",
        ],
    }
    write_json_ref(workspace, STRUCTURAL_CHECK_REPORT_REF, report)
    return report


class FixtureAcademicResearcherAdapter:
    """Offline researcher adapter for Phase 1 contract and package tests."""

    adapter_family = "fixture_deepresearch_single_researcher"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: Any | None = None,
        call_spec: Any | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        extension_lock_ref: str | None = None,
    ) -> WorkerAdapterResult:
        call.validate()
        if call.role is not PiWorkerCallRole.EXECUTOR:
            raise ContractValidationError("fixture DeepResearch researcher only supports executor PiWorker calls")
        root = Path(workspace).resolve()
        source_packet = read_json_ref(root, SOURCE_PACKET_REF, "source_packet")
        request = read_json_ref(root, PRODUCT_REQUEST_REF, "research_request")
        source_packet = _ensure_fixture_source_packet(root, request=request, source_packet=source_packet)
        source_ids = [
            str(item.get("source_id"))
            for item in source_packet.get("source_records", [])
            if isinstance(item, dict) and item.get("source_id")
        ]
        _write_fixture_reports(root, request=request, source_packet=source_packet, source_ids=source_ids)
        metrics = {"metric_ref": RESEARCHER_METRICS_REF, "fixture": True, "source_count": len(source_ids)}
        write_json_ref(root, RESEARCHER_METRICS_REF, metrics)
        execution_report = ExecutionReport(
            report_id="deepresearch-fixture-researcher-execution-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=list(call.expected_output_refs),
            changed_refs=[*call.expected_output_refs, RESEARCHER_EXECUTION_REPORT_REF, RESEARCHER_METRICS_REF],
            evidence_refs=[SOURCE_PACKET_REF, "reports/evidence_index.md"],
            worker_claims=["fixture draft package produced"],
            metrics=metrics,
        )
        write_json_ref(root, RESEARCHER_EXECUTION_REPORT_REF, execution_report.to_dict())
        return WorkerAdapterResult(
            execution_report=execution_report,
            worker_result=WorkerResult(status="completed", execution_report_ref=RESEARCHER_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics=metrics,
        )


def _write_fixture_reports(
    root: Path,
    *,
    request: dict[str, Any],
    source_packet: dict[str, Any],
    source_ids: list[str],
) -> None:
    topic = str(request.get("topic", "academic research topic"))
    language = str(request.get("language", "zh"))
    source_mode = str(source_packet.get("mode", "fixture"))
    previous_run_refs = request.get("previous_run_refs", [])
    previous_count = len(previous_run_refs) if isinstance(previous_run_refs, list) else 0
    headings = _section_headings(str(request.get("language", "zh")))
    if language == "zh":
        source_note = (
            "已接入 live source packet；当前 fixture 研究员只验证包结构，不进行真实语义研究。"
            if source_mode == "live"
            else "当前为 fixture source packet，不能证明真实领域覆盖。"
        )
        final_report = (
            f"# {topic} 学术调研草稿\n\n"
            "这是 Phase 1 fixture 研究员生成的结构化草稿，用于验证单 Agent 闭环。\n\n"
            f"## {headings['scope_and_method']}\n\n"
            f"本轮以固定合同和 fixture source packet 验证流程。{source_note}\n\n"
            f"## {headings['evidence_base']}\n\n"
            f"可用 fixture 来源: {_citation_group(source_ids) if source_ids else '无'}。\n\n"
            f"## {headings['major_lines_of_work']}\n\n"
            "Fixture 模式不声称覆盖真实研究线，只保留引用链路验证。\n\n"
            f"## {headings['comparison_matrix']}\n\n"
            "| 主题 | 证据 | 局限 |\n|---|---|---|\n"
            f"| fixture 验证 | {_citation_group(source_ids) if source_ids else '无'} | 不代表真实研究质量 |\n\n"
            f"## {headings['counterevidence_and_failure_modes']}\n\n"
            "主要失败模式是把 fixture 包误读为真实调研结果；本报告明确不作该声明。\n\n"
            f"## {headings['research_delta']}\n\n"
            f"previous_run_refs 数量: {previous_count}。Fixture 模式只验证 delta artifact 必然产出。\n\n"
            f"## {headings['source_gaps']}\n\n"
            "需要 researcher-mode=piworker 和 live tools 才能评估真实覆盖、实时性、引用和 delta。\n\n"
            f"## {headings['references']}\n\n"
            f"{_reference_lines(source_packet)}"
        )
        delta = (
            "# Research Delta\n\n"
            f"previous_run_refs 数量: {previous_count}。\n\n"
            "Fixture 模式只验证 delta artifact 必然产出，不判断真实变化。\n"
        )
        gaps = (
            "# Source Gaps\n\n"
            f"- source_mode: {source_mode}。\n"
            "- 当前为 fixture researcher，不能判断真实调研质量。\n"
            "- 需要 researcher-mode=piworker 才能评估覆盖、实时性、引用和 delta。\n"
        )
    else:
        source_note = (
            "A live source packet is present; the fixture researcher only validates package shape."
            if source_mode == "live"
            else "Fixture source packet cannot prove live domain coverage."
        )
        final_report = (
            f"# Academic Research Draft: {topic}\n\n"
            "This Phase 1 fixture draft validates the single-agent loop.\n\n"
            f"## {headings['scope_and_method']}\n\n"
            f"This run validates the contract and fixture source packet. {source_note}\n\n"
            f"## {headings['evidence_base']}\n\n"
            f"Available fixture sources: {_citation_group(source_ids) if source_ids else 'none'}.\n\n"
            f"## {headings['major_lines_of_work']}\n\n"
            "Fixture mode does not claim real topic coverage; it only preserves the citation path.\n\n"
            f"## {headings['comparison_matrix']}\n\n"
            "| Topic | Evidence | Limitation |\n|---|---|---|\n"
            f"| fixture validation | {_citation_group(source_ids) if source_ids else 'none'} | not a real research-quality claim |\n\n"
            f"## {headings['counterevidence_and_failure_modes']}\n\n"
            "The main failure mode is treating fixture evidence as a real research result; this report does not do that.\n\n"
            f"## {headings['research_delta']}\n\n"
            f"previous_run_refs count: {previous_count}. Fixture mode only verifies delta artifact production.\n\n"
            f"## {headings['source_gaps']}\n\n"
            "Use researcher-mode=piworker with live tools to evaluate real coverage, freshness, citations, and delta.\n\n"
            f"## {headings['references']}\n\n"
            f"{_reference_lines(source_packet)}"
        )
        delta = (
            "# Research Delta\n\n"
            f"previous_run_refs count: {previous_count}.\n\n"
            "Fixture mode only verifies that a delta artifact is produced.\n"
        )
        gaps = (
            "# Source Gaps\n\n"
            f"- source_mode: {source_mode}.\n"
            "- Fixture researcher cannot judge real research quality.\n"
            "- Use researcher-mode=piworker to evaluate coverage, freshness, citations, and delta.\n"
        )
    evidence = "# Evidence Index\n\n" + _reference_lines(source_packet)
    reading_plan = (
        "# Reading Plan\n\n"
        "1. Replace fixture sources with live academic collectors.\n"
        "2. Ask the researcher to expand source coverage and identify missing evidence.\n"
        "3. Compare the MissionForge output with a direct skill-like prompt in Phase 3.\n"
    )
    write_text_ref(root, "reports/final_report.md", final_report)
    write_text_ref(root, "reports/evidence_index.md", evidence)
    write_text_ref(root, "reports/research_delta.md", delta)
    write_text_ref(root, "reports/reading_plan.md", reading_plan)
    write_text_ref(root, "reports/source_gaps.md", gaps)


def _section_headings(language: str) -> dict[str, str]:
    return {section["section_id"]: section["title"] for section in research_report_section_specs(language)}


def _audit_source_packet_ref(workspace: str | Path):
    try:
        return audit_source_packet(read_json_ref(workspace, SOURCE_PACKET_REF, "source_packet"))
    except Exception as exc:
        return audit_source_packet(
            {
                "schema_version": "missionforge_deepresearch.source_packet.v1",
                "source_records": [],
                "error": type(exc).__name__,
            }
        )


def _audit_citation_refs(workspace: str | Path, source_ids: list[str]):
    try:
        final_report_text = read_text_ref(workspace, "reports/final_report.md")
        evidence_index_text = read_text_ref(workspace, "reports/evidence_index.md")
    except Exception as exc:
        return audit_report_citations(
            final_report_text=f"[S999]\n\n## References\n\n- [S999] missing: {type(exc).__name__}",
            evidence_index_text="",
            source_ids=source_ids,
        )
    return audit_report_citations(
        final_report_text=final_report_text,
        evidence_index_text=evidence_index_text,
        source_ids=source_ids,
    )


def _audit_quality_contract_ref(workspace: str | Path):
    try:
        output_contract = read_json_ref(workspace, OUTPUT_CONTRACT_REF, "output_contract")
    except Exception:
        output_contract = None
    try:
        source_packet = read_json_ref(workspace, SOURCE_PACKET_REF, "source_packet")
    except Exception:
        source_packet = {}
    try:
        final_report_text = read_text_ref(workspace, "reports/final_report.md")
    except Exception:
        final_report_text = ""
    return audit_quality_contract(
        output_contract=output_contract,
        source_packet=source_packet,
        final_report_text=final_report_text,
    )


def _ensure_fixture_source_packet(root: Path, *, request: dict[str, Any], source_packet: dict[str, Any]) -> dict[str, Any]:
    records = source_packet.get("source_records", [])
    if isinstance(records, list) and records:
        return source_packet
    updated = dict(source_packet)
    updated["schema_version"] = "missionforge_deepresearch.source_packet.v1"
    updated["request_id"] = str(request.get("request_id", updated.get("request_id", "fixture-request")))
    updated["source_records"] = [
        {
            "source_id": "S1",
            "title": "Fixture source for DeepResearch package validation",
            "source_type": "webpage_fixture",
            "source_ref": SOURCE_PACKET_REF,
            "year": 2024,
            "url": "https://example.invalid/missionforge/fixture/deepresearch",
            "accessed_at": "fixture",
            "evidence_note": "Fixture source used only to validate citation and package shape.",
            "evidence_strength": "fixture",
            "notes": "Fixture source used only to validate citation and package shape.",
        }
    ]
    write_json_ref(root, SOURCE_PACKET_REF, updated)
    return updated


def _citation_group(source_ids: list[str]) -> str:
    if not source_ids:
        return ""
    return "[" + ", ".join(source_ids) + "]"


def _reference_lines(source_packet: Mapping[str, Any]) -> str:
    records = source_packet.get("source_records", [])
    if not isinstance(records, list):
        return ""
    lines: list[str] = []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("source_id", "")).strip()
        title = str(item.get("title", "")).strip()
        locator = _source_locator(item)
        if source_id and title:
            lines.append(f"- [{source_id}] {title}. {locator}".rstrip() + "\n")
    return "".join(lines)


def _source_locator(record: Mapping[str, Any]) -> str:
    for field_name in ("url", "doi", "source_ref", "github_repo", "arxiv_id"):
        value = record.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _outer_ref(run_workspace_ref: str, ref: str) -> str:
    return f"{validate_ref(run_workspace_ref, 'run_workspace_ref')}/{validate_ref(ref, 'run_ref')}"


def _run_relative_ref(run_workspace_ref: str, ref: str) -> str:
    safe_run_ref = validate_ref(run_workspace_ref, "run_workspace_ref")
    safe_ref = validate_ref(ref, "run_ref")
    prefix = f"{safe_run_ref}/"
    if not safe_ref.startswith(prefix):
        raise ContractValidationError(f"ref is not under run workspace: {safe_ref}")
    return safe_ref[len(prefix):]


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "ref")
        if safe_ref not in seen:
            result.append(safe_ref)
            seen.add(safe_ref)
    return result
