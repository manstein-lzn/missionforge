from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import missionforge as mf
from missionforge_deepresearch import kernel_v2 as kernel_v2_module
from missionforge_deepresearch.kernel_v2 import (
    AcademicResearchRequest,
    KernelV2FixtureAdapter,
    build_deepresearch_kernel_v2_flow,
    deepresearch_kernel_v2_flow_run_id,
    run_deepresearch_kernel_v2,
)
from missionforge_deepresearch.product_contract import ResearchIntensity
from missionforge_deepresearch.project_lifecycle import (
    PROJECT_LIFECYCLE_STATE_REF,
    PROJECT_MANIFEST_REF,
    PROJECT_RESUME_DIAGNOSTICS_REF,
    PROJECT_RUN_INDEX_REF,
    ROLE_CONTEXT_PACKAGE_POINTER_REFS,
)


class DeepResearchKernelV2Tests(unittest.TestCase):
    def test_fixture_flow_runs_researcher_reviewer_judge_to_acceptance(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-smoke",
            topic="compiler autotuning",
            audience="R&D compiler team",
            language="zh",
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            payload = _read_json(root, result.result_ref)
            flow_result = _read_json(root, result.flow_result_ref)
            run_root = root / result.run_workspace_ref
            ledger_events = _read_jsonl(root, result.flow_ledger_ref)
            step_records = [_read_json(run_root, ref) for ref in flow_result["step_record_refs"]]
            calls = [_read_json(run_root, record["piworker_call_ref"]) for record in step_records]
            permission_manifests = [_read_json(run_root, record["permission_manifest_ref"]) for record in step_records]
            final_report_exists = (root / result.final_report_ref).is_file()
            citation_projected_report = (root / result.citation_projected_report_ref).read_text(encoding="utf-8")
            report_html_exists = (root / result.report_html_ref).is_file()
            report_html = (root / result.report_html_ref).read_text(encoding="utf-8")
            provider_capabilities = _read_json(root, result.provider_capabilities_ref)
            search_plan = _read_json(root, result.search_plan_ref)
            provider_hits_exists = (root / result.provider_hits_ref).is_file()
            provider_hits = _read_jsonl(root, result.provider_hits_ref)
            source_packet_exists = (root / result.source_packet_ref).is_file()
            source_graph_exists = (root / result.source_graph_ref).is_file()
            canonical_sources = _read_json(root, result.canonical_sources_ref)
            coverage_report = _read_json(root, result.coverage_report_ref)
            citation_registry = _read_json(root, result.citation_registry_ref)
            insight_map_exists = (root / result.insight_map_ref).is_file()
            claim_index_exists = (root / result.claim_index_ref).is_file()
            reviewer_observation_exists = (root / result.reviewer_observation_ref).is_file()
            judge_report_exists = (root / result.judge_report_ref).is_file()
            run_status = _read_json(root, result.run_status_ref)
            research_state = _read_json(root, f"{result.run_workspace_ref}/state/research_state.json")
            project_manifest = _read_json(run_root, PROJECT_MANIFEST_REF)
            lifecycle_state = _read_json(run_root, PROJECT_LIFECYCLE_STATE_REF)
            resume_diagnostics = _read_json(run_root, PROJECT_RESUME_DIAGNOSTICS_REF)
            run_index = _read_json(run_root, PROJECT_RUN_INDEX_REF)
            usage_summary = _read_json(root, result.usage_summary_ref)
            run_events = _read_jsonl(root, result.run_events_ref)
            run_snapshot = _read_json(root, result.run_snapshot_ref)
            researcher_pointer = _read_json(run_root, ROLE_CONTEXT_PACKAGE_POINTER_REFS["researcher"])
            lifecycle_packages = [
                _read_json(run_root, lifecycle_state["latest_source_mapper_context_package_ref"]),
                _read_json(run_root, lifecycle_state["latest_researcher_context_package_ref"]),
                _read_json(run_root, lifecycle_state["latest_reviewer_context_package_ref"]),
                _read_json(run_root, lifecycle_state["latest_judge_context_package_ref"]),
            ]
            wrong_role_restore = mf.evaluate_context_package_ref(
                run_root,
                lifecycle_state["latest_researcher_context_package_ref"],
                expectation=mf.ContextPackageRestoreExpectation(
                    role=mf.PiWorkerCallRole.FRONTDESK_AUTHOR.value,
                    step_id="frontdesk",
                ),
            )

        self.assertEqual(result.status, "accepted")
        self.assertEqual(payload, result.to_dict())
        self.assertEqual(flow_result["status"], "accepted")
        self.assertTrue(result.run_events_ref.startswith(f"{result.run_workspace_ref}/kernel/"))
        self.assertTrue(result.run_snapshot_ref.startswith(f"{result.run_workspace_ref}/kernel/"))
        self.assertEqual(run_events[0]["kind"], "run_started")
        self.assertEqual(run_snapshot["status"], "accepted")
        self.assertEqual(run_snapshot["latest_event_ref"], result.run_events_ref.removeprefix(f"{result.run_workspace_ref}/"))
        self.assertTrue(final_report_exists)
        self.assertIn("[cite: 1](#ref-1)", citation_projected_report)
        self.assertIn('<a id="ref-1"></a>[1]', citation_projected_report)
        self.assertTrue(report_html_exists)
        self.assertIn('<a href="#ref-1">[cite: 1]</a>', report_html)
        self.assertIn('<a id="ref-1"></a>[1]', report_html)
        self.assertEqual(
            provider_capabilities["default_search_provider_ids"],
            ["semantic_scholar", "arxiv", "crossref", "dblp", "pubmed"],
        )
        self.assertEqual(search_plan["schema_version"], "missionforge_deepresearch.search_plan.v1")
        self.assertEqual(search_plan["source_count_budget"]["target_source_count"], 50)
        self.assertEqual(search_plan["source_count_budget"]["reference_source_baseline"], 50)
        self.assertTrue(provider_hits_exists)
        self.assertEqual(provider_hits[0]["schema_version"], "missionforge_deepresearch.provider_hit.v1")
        self.assertEqual(provider_hits[0]["query_id"], "Q1")
        self.assertEqual(coverage_report["schema_version"], "missionforge_deepresearch.coverage_report.v1")
        self.assertEqual(coverage_report["target_source_count"], 50)
        self.assertEqual(coverage_report["source_record_count"], 1)
        self.assertEqual(coverage_report["mechanical_coverage_status"], "below_target")
        self.assertTrue(source_packet_exists)
        self.assertTrue(source_graph_exists)
        self.assertEqual(canonical_sources["sources"][0]["source_id"], "S1")
        self.assertEqual(citation_registry["entries"][0]["source_id"], "S1")
        self.assertTrue(insight_map_exists)
        self.assertTrue(claim_index_exists)
        self.assertTrue(reviewer_observation_exists)
        self.assertTrue(judge_report_exists)
        self.assertEqual(run_status["status"], "accepted")
        self.assertEqual(run_status["search_plan_ref"], "sources/search_plan.json")
        self.assertEqual(run_status["provider_hits_ref"], "sources/provider_hits.jsonl")
        self.assertEqual(run_status["coverage_report_ref"], "sources/coverage_report.json")
        self.assertEqual(run_status["coverage_status"], "below_target")
        self.assertEqual(run_status["source_record_count"], 1)
        self.assertEqual(run_status["target_source_count"], 50)
        self.assertEqual(run_status["flow_result_ref"], result.flow_result_ref.removeprefix(f"{result.run_workspace_ref}/"))
        self.assertEqual(run_status["run_events_ref"], result.run_events_ref.removeprefix(f"{result.run_workspace_ref}/"))
        self.assertEqual(run_status["run_snapshot_ref"], result.run_snapshot_ref.removeprefix(f"{result.run_workspace_ref}/"))
        self.assertEqual(research_state["project_phase"], "final_package_ready")
        self.assertIn("project_milestones", research_state)
        self.assertIn("coverage_map", research_state)
        self.assertEqual(project_manifest["request_id"], "kernel-v2-smoke")
        self.assertEqual(project_manifest["lifecycle_state_ref"], PROJECT_LIFECYCLE_STATE_REF)
        self.assertEqual(lifecycle_state["phase"], "accepted")
        self.assertEqual(lifecycle_state["control_agent"], "frontdesk")
        self.assertEqual(lifecycle_state["current_contract_ref"], "contract/task_contract.json")
        self.assertEqual(lifecycle_state["latest_run_ref"], "packages/deepresearch_kernel_v2_result.json")
        self.assertEqual(lifecycle_state["research_state_ref"], "state/research_state.json")
        self.assertTrue(lifecycle_state["latest_researcher_context_package_ref"].endswith("/context/post_turn/package.json"))
        self.assertEqual(lifecycle_state["resume_diagnostics_ref"], PROJECT_RESUME_DIAGNOSTICS_REF)
        self.assertEqual(lifecycle_state["context_package_pointers"]["researcher"], ROLE_CONTEXT_PACKAGE_POINTER_REFS["researcher"])
        self.assertEqual(resume_diagnostics["status"], "reusable")
        self.assertEqual(resume_diagnostics["role_decisions"]["researcher"]["status"], "reusable")
        self.assertEqual(researcher_pointer["context_package_ref"], lifecycle_state["latest_researcher_context_package_ref"])
        self.assertEqual(wrong_role_restore.status, mf.ContextPackageRestoreStatus.INVALID)
        self.assertIn("role_mismatch", wrong_role_restore.reason_codes)
        self.assertIn("step_id_mismatch", wrong_role_restore.reason_codes)
        self.assertEqual(run_index["runs"][0]["result_ref"], "packages/deepresearch_kernel_v2_result.json")
        self.assertEqual(run_index["runs"][0]["context_packages"]["judge"], lifecycle_state["latest_judge_context_package_ref"])
        self.assertEqual(
            [package["schema_version"] for package in lifecycle_packages],
            ["missionforge.context_package.v1"] * 4,
        )
        self.assertEqual([package["step_id"] for package in lifecycle_packages], ["source_mapper", "researcher", "reviewer", "judge"])
        self.assertEqual([record["step_id"] for record in step_records], ["source_mapper", "researcher", "reviewer", "judge"])
        self.assertEqual([call["role"] for call in calls], ["executor_piworker", "executor_piworker", "executor_piworker", "judge_piworker"])
        self.assertIn("sources/initial_source_packet.json", calls[0]["visible_refs"])
        self.assertNotIn("sources/source_packet.json", calls[0]["visible_refs"])
        self.assertIn("sources/search_plan.json", calls[1]["visible_refs"])
        self.assertIn("sources/provider_hits.jsonl", calls[1]["visible_refs"])
        self.assertIn("sources/coverage_report.json", calls[1]["visible_refs"])
        self.assertIn("sources/source_packet.json", calls[1]["visible_refs"])
        self.assertIn("analysis/insight_map.json", calls[2]["visible_refs"])
        self.assertIn("analysis/insight_map.json", calls[3]["visible_refs"])
        self.assertEqual(calls[0]["writable_refs"], ["sources", "reports", "state"])
        self.assertEqual(calls[1]["writable_refs"], ["reports", "analysis", "claims", "state"])
        self.assertNotIn("exports/final_report.html", calls[0]["expected_output_refs"])
        for call, manifest in zip(calls, permission_manifests):
            for ref in call["visible_refs"]:
                self.assertTrue(_ref_is_under_any(ref, manifest["readable_refs"]), ref)
                self.assertFalse(ref == "kernel" or ref.startswith("kernel/"))
                self.assertFalse(ref == "attempts" or ref.startswith("attempts/"))
        self.assertEqual(result.metric_refs, [f"{result.run_workspace_ref}/metrics/usage_summary.json"])
        self.assertEqual(usage_summary["totals"]["total_tokens"], 0)
        self.assertEqual(usage_summary["totals"]["input_tokens"], 0)
        self.assertEqual(usage_summary["totals"]["cached_input_tokens"], 0)
        self.assertEqual(usage_summary["totals"]["output_tokens"], 0)
        self.assertEqual([step["step_id"] for step in usage_summary["steps"]], ["source_mapper", "researcher", "reviewer", "judge"])
        self.assertFalse(any("/kernel/" in ref or "/attempts/" in ref for ref in result.evidence_refs))
        self.assertIn(f"{result.run_workspace_ref}/sources/search_plan.json", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/sources/provider_hits.jsonl", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/sources/source_packet.json", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/sources/coverage_report.json", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/sources/source_graph.json", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/citations/citation_registry.json", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/analysis/insight_map.json", result.evidence_refs)
        self.assertIn(f"{result.run_workspace_ref}/state/research_state.json", result.evidence_refs)
        self.assertEqual(flow_result["decision_refs"], [
            "state/source_control.json",
            "state/researcher_control.json",
            "reviews/reviewer_observation.json",
            "judge/judge_report.json",
        ])
        self.assertEqual(
            [event["kind"] for event in ledger_events],
            [
                mf.FlowLedgerEventKind.STARTED.value,
                mf.FlowLedgerEventKind.STEP_STARTED.value,
                mf.FlowLedgerEventKind.STEP_RECORDED.value,
                mf.FlowLedgerEventKind.ROUTED.value,
                mf.FlowLedgerEventKind.STEP_STARTED.value,
                mf.FlowLedgerEventKind.STEP_RECORDED.value,
                mf.FlowLedgerEventKind.ROUTED.value,
                mf.FlowLedgerEventKind.STEP_STARTED.value,
                mf.FlowLedgerEventKind.STEP_RECORDED.value,
                mf.FlowLedgerEventKind.ROUTED.value,
                mf.FlowLedgerEventKind.STEP_STARTED.value,
                mf.FlowLedgerEventKind.STEP_RECORDED.value,
                mf.FlowLedgerEventKind.ROUTED.value,
                mf.FlowLedgerEventKind.STOPPED.value,
            ],
        )
        self.assertEqual(ledger_events[-2]["step_id"], "judge")
        self.assertEqual(ledger_events[-2]["route_value"], "accepted")
        self.assertEqual(ledger_events[-2]["route_target"], "accepted")

    def test_runtime_user_intervention_reaches_researcher_safe_point(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-interaction",
            topic="deep research platform survey",
            audience="MissionForge runtime team",
            language="zh",
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_root = root / "runs/kernel-v2-interaction"
            port = mf.FileInteractionPort(run_root)
            event = port.submit_text(
                "请优先关注用户体验和进度可观测性。",
                run_id=deepresearch_kernel_v2_flow_run_id(request.request_id),
                target="flow",
            )
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            flow_result = _read_json(root, result.flow_result_ref)
            step_record = _read_json(root / result.run_workspace_ref, flow_result["step_record_refs"][0])
            call = _read_json(root / result.run_workspace_ref, step_record["piworker_call_ref"])
            snapshot_ref = (
                "kernel/deepresearch-v2-kernel-v2-interaction/runs/"
                "deepresearch-v2-kernel-v2-interaction/executions/001/"
                "interaction/safe_points/001-source_mapper-user_events.json"
            )
            snapshot = _read_json(root / result.run_workspace_ref, snapshot_ref)
            acks = _read_jsonl(root / result.run_workspace_ref, "interaction/user_event_acks.jsonl")
            ledger_events = _read_jsonl(root, result.flow_ledger_ref)

        self.assertIn(snapshot_ref, step_record["input_refs"])
        self.assertIn(snapshot_ref, call["visible_refs"])
        self.assertEqual(snapshot["events"][0]["event_id"], event.event_id)
        self.assertEqual(acks[0]["event_id"], event.event_id)
        self.assertEqual(acks[0]["snapshot_ref"], snapshot_ref)
        self.assertTrue(any(item["kind"] == mf.FlowLedgerEventKind.INTERACTION_RECORDED.value for item in ledger_events))

    def test_pause_intervention_blocks_before_researcher_call(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-pause",
            topic="deep research platform survey",
            audience="MissionForge runtime team",
            language="zh",
        )
        adapter = CountingKernelV2FixtureAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_root = root / "runs/kernel-v2-pause"
            port = mf.FileInteractionPort(run_root)
            port.submit_text(
                "暂停。",
                run_id=deepresearch_kernel_v2_flow_run_id(request.request_id),
                target="flow",
                kind=mf.UserEventKind.PAUSE_REQUEST,
            )
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=adapter,
            )
            flow_result = _read_json(root, result.flow_result_ref)
            run_status = _read_json(root, result.run_status_ref)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(flow_result["metadata"]["stop_reason"], "user_pause_requested")
        self.assertEqual(run_status["interaction_stop_reason"], "user_pause_requested")
        self.assertEqual(run_status["pending_user_event_count"], 1)
        self.assertIn("interaction/safe_points/001-source_mapper-user_events.json", run_status["last_interaction_snapshot_ref"])

    def test_revision_intervention_blocks_without_mutating_frozen_contract(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-revision-request",
            topic="deep research platform survey",
            audience="MissionForge runtime team",
            language="zh",
        )
        adapter = CountingKernelV2FixtureAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_root = root / "runs/kernel-v2-revision-request"
            port = mf.FileInteractionPort(run_root)
            port.submit_text(
                "请把研究范围改成只比较前端产品。",
                run_id=deepresearch_kernel_v2_flow_run_id(request.request_id),
                target="flow",
                kind=mf.UserEventKind.CONTRACT_REVISION_REQUEST,
            )
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=adapter,
            )
            original_contract = _read_json(root, result.contract_ref)
            run_status = _read_json(root, result.run_status_ref)
            flow_result = _read_json(root, result.flow_result_ref)
            snapshot = _read_json(
                run_root,
                "kernel/deepresearch-v2-kernel-v2-revision-request/runs/"
                "deepresearch-v2-kernel-v2-revision-request/executions/001/"
                "interaction/safe_points/001-source_mapper-user_events.json",
            )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(adapter.call_count, 0)
        self.assertEqual(flow_result["metadata"]["stop_reason"], "user_contract_revision_requested")
        self.assertEqual(run_status["interaction_stop_reason"], "user_contract_revision_requested")
        self.assertEqual(original_contract["request"]["topic"], "deep research platform survey")
        self.assertEqual(snapshot["events"][0]["kind"], "contract_revision_request")
        self.assertNotIn("current_revision_ref", original_contract)

    def test_source_mapper_and_researcher_briefs_require_artifacts_before_budget_exhaustion(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-brief",
            topic="deep research platform survey",
            audience="MissionForge runtime team",
            language="zh",
        )

        source_mapper = kernel_v2_module._source_mapper_brief(request)
        brief = kernel_v2_module._researcher_brief(request)

        self.assertIn("first-pass evidence-mapping phase", source_mapper)
        self.assertIn("Do not keep searching until timeout.", source_mapper)
        self.assertIn("representative source set", source_mapper)
        self.assertIn("Write the required artifacts before any second broad search wave.", source_mapper)
        self.assertIn("sources/search_plan.json", source_mapper)
        self.assertIn("academic_search.queries", source_mapper)
        self.assertIn("sources/provider_hits.jsonl", source_mapper)
        self.assertIn("sources/coverage_report.json", source_mapper)
        self.assertIn("100+ candidate records", source_mapper)
        self.assertIn("record the follow-up targets in `sources/coverage_report.json`", source_mapper)
        self.assertIn("context pressure is reported", source_mapper)
        self.assertIn("Source-count budget guidance", source_mapper)
        self.assertIn("not a fixed acceptance count", source_mapper)
        self.assertIn("ready_for_synthesis", source_mapper)
        self.assertIn("sources/source_packet.json", source_mapper)
        self.assertIn("The source mapper already owns source acquisition.", brief)
        self.assertIn("sources/search_plan.json", brief)
        self.assertIn("sources/provider_hits.jsonl", brief)
        self.assertIn("sources/coverage_report.json", brief)
        self.assertIn("write a useful evidence-calibrated report with explicit gaps", brief)
        self.assertIn("Prefer a reviewable partial synthesis over no artifacts.", brief)
        self.assertIn("Do not run a new broad source-gathering loop", brief)
        self.assertIn("user-facing project progress board", brief)
        self.assertIn("project_milestones", brief)
        self.assertIn("analysis/insight_map.json", brief)
        self.assertIn("defensible thesis", brief)
        self.assertIn("So What test", brief)
        self.assertIn("Match the requested genre", brief)
        self.assertIn("literature review", brief)
        self.assertIn("neutral, rigorous, comprehensive review style", brief)
        self.assertIn("tool directory", brief)
        self.assertIn("Avoid sensational or casual headings", brief)

    def test_reviewer_and_judge_rubrics_do_not_penalize_parallel_batches(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-rubric",
            topic="deep research platform survey",
            audience="MissionForge runtime team",
            research_intensity=ResearchIntensity.INTENSIVE,
        )

        reviewer = kernel_v2_module._reviewer_rubric(request)
        judge = kernel_v2_module._judge_rubric(request)

        self.assertIn("Judge the phase artifacts, not the number of turns or the number of tool calls inside a turn.", reviewer)
        self.assertIn("A multi-tool researcher batch is fine", reviewer)
        self.assertIn("Use `analysis/insight_map.json` as the main review lens", reviewer)
        self.assertIn("weak thesis, thin insight, or narrative mismatch", reviewer)
        self.assertIn("Genre fit check", reviewer)
        self.assertIn("Structure check", reviewer)
        self.assertIn("Do not treat parallel retrieval or a longer evidence batch as a defect by itself.", reviewer)
        self.assertIn("Judge the staged package as a whole", judge)
        self.assertIn("Use `analysis/insight_map.json` as the semantic map", judge)
        self.assertIn("evidence-conclusion mismatch", judge)
        self.assertIn("objective, rigorous, comprehensive", judge)
        self.assertIn("Do not infer poor quality from the number of tool calls", judge)

    def test_run_requires_explicit_adapter(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(Exception, "explicit PiWorker adapter"):
                run_deepresearch_kernel_v2(
                    AcademicResearchRequest(request_id="kernel-v2-no-adapter", topic="compiler autotuning"),
                    workspace=Path(tmpdir),
                )

    def test_rerun_does_not_overwrite_worker_owned_source_packet(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-rerun", topic="compiler autotuning")
        first_adapter = KernelV2FixtureAdapter()
        second_adapter = CountingKernelV2FixtureAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=first_adapter,
            )
            source_packet_before = _read_json(root, first.source_packet_ref)
            rerun = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=second_adapter,
            )
            source_packet_after = _read_json(root, rerun.source_packet_ref)
            rerun_flow_result = _read_json(root, rerun.flow_result_ref)
            run_root = root / rerun.run_workspace_ref
            rerun_step_records = [_read_json(run_root, ref) for ref in rerun_flow_result["step_record_refs"]]

        self.assertEqual(source_packet_after, source_packet_before)
        self.assertEqual(second_adapter.call_count, 0)
        self.assertEqual([record["status"] for record in rerun_step_records], ["skipped", "skipped", "skipped", "skipped"])

    def test_flow_shape_keeps_acceptance_on_judge_step(self) -> None:
        flow = build_deepresearch_kernel_v2_flow(
            AcademicResearchRequest(request_id="kernel-v2-flow-shape", topic="compiler autotuning")
        )

        self.assertEqual(flow.routes["judge.accepted"].status, "accepted")
        self.assertEqual(
            [step.id for step in flow.steps],
            ["source_mapper", "researcher", "reviewer", "judge"],
        )
        self.assertEqual(flow.routes["source_mapper.ready_for_synthesis"], "researcher")
        self.assertEqual(flow.routes["reviewer.revise_report"], "researcher")
        self.assertEqual(flow.routes["reviewer.continue"], "source_mapper")
        self.assertEqual(flow.routes["judge.repair"], "researcher")
        self.assertEqual(flow.steps[0].role, mf.PiWorkerCallRole.EXECUTOR)
        self.assertEqual(flow.steps[1].role, mf.PiWorkerCallRole.EXECUTOR)
        self.assertEqual(flow.steps[2].role, mf.PiWorkerCallRole.EXECUTOR)
        self.assertEqual(flow.steps[3].role, mf.PiWorkerCallRole.JUDGE)
        self.assertEqual(flow.steps[0].route_on, "state/source_control.json")
        self.assertEqual(flow.steps[1].route_on, "state/researcher_control.json")
        self.assertEqual(flow.steps[2].route_on, "reviews/reviewer_observation.json")
        self.assertIn(kernel_v2_module.KERNEL_V2_SEARCH_PLAN_REF, flow.steps[0].outputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_PROVIDER_HITS_REF, flow.steps[0].outputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_SOURCE_PACKET_REF, flow.steps[0].outputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_COVERAGE_REPORT_REF, flow.steps[0].outputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_COVERAGE_REPORT_REF, flow.steps[1].inputs)
        self.assertNotIn(kernel_v2_module.KERNEL_V2_FINAL_REPORT_REF, flow.steps[0].outputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_INSIGHT_MAP_REF, flow.steps[1].outputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_INSIGHT_MAP_REF, flow.steps[2].inputs)
        self.assertIn(kernel_v2_module.KERNEL_V2_INSIGHT_MAP_REF, flow.steps[3].inputs)
        self.assertNotIn("analysis", flow.steps[0].write)
        self.assertIn("analysis", flow.steps[1].write)
        self.assertIn("analysis", flow.steps[2].read)
        self.assertIn("analysis", flow.steps[3].read)
        self.assertEqual(flow.steps[0].failure.retries, 0)
        self.assertEqual(flow.steps[1].failure.retries, 0)
        self.assertEqual(flow.steps[0].runtime_budget["max_turns"], 12)
        self.assertFalse(any("max_turns" in step.runtime_budget for step in flow.steps[1:]))
        self.assertTrue(all("timeout_seconds" in step.runtime_budget for step in flow.steps))

    def test_researcher_and_reviewer_cannot_self_accept(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-no-self-accept", topic="compiler autotuning")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            researcher_result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=AcceptingResearcherKernelV2FixtureAdapter(),
            )
            reviewer_result = run_deepresearch_kernel_v2(
                AcademicResearchRequest(request_id="kernel-v2-no-reviewer-accept", topic="compiler autotuning"),
                workspace=root,
                adapter=AcceptingReviewerKernelV2FixtureAdapter(),
            )
            researcher_ledger = _read_jsonl(root, researcher_result.flow_ledger_ref)
            reviewer_ledger = _read_jsonl(root, reviewer_result.flow_ledger_ref)

        self.assertEqual(researcher_result.status, "blocked")
        self.assertEqual(researcher_ledger[-2]["step_id"], "researcher")
        self.assertEqual(researcher_ledger[-2]["route_value"], "accepted")
        self.assertEqual(researcher_ledger[-2]["route_target"], "unrouted")
        self.assertEqual(reviewer_result.status, "blocked")
        self.assertEqual(reviewer_ledger[-2]["step_id"], "reviewer")
        self.assertEqual(reviewer_ledger[-2]["route_value"], "accepted")
        self.assertEqual(reviewer_ledger[-2]["route_target"], "unrouted")

    def test_reviewer_provider_failure_projects_review_blocked(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-review-blocked", topic="compiler autotuning")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=ReviewerProviderBlockedKernelV2Adapter(),
            )
            run_status = _read_json(root, result.run_status_ref)
            final_report_exists = (root / result.final_report_ref).is_file()

        self.assertEqual(result.status, "review_blocked")
        self.assertEqual(run_status["status"], "review_blocked")
        self.assertEqual(run_status["blocked_step_id"], "reviewer")
        self.assertEqual(run_status["blocker_kind"], "provider")
        self.assertTrue(final_report_exists)

    def test_reviewer_can_route_bounded_feedback_back_to_researcher(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-revise", topic="compiler autotuning")
        adapter = RevisingKernelV2FixtureAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=adapter,
            )
            flow_result = _read_json(root, result.flow_result_ref)
            run_root = root / result.run_workspace_ref
            step_records = [_read_json(run_root, ref) for ref in flow_result["step_record_refs"]]
            calls = [_read_json(run_root, record["piworker_call_ref"]) for record in step_records]

        self.assertEqual(result.status, "accepted")
        self.assertEqual(
            [record["step_id"] for record in step_records],
            ["source_mapper", "researcher", "reviewer", "researcher", "reviewer", "judge"],
        )
        self.assertEqual(adapter.reviewer_call_count, 2)
        self.assertEqual(calls[3]["writable_refs"], ["reports", "analysis", "claims", "state"])
        self.assertEqual(flow_result["decision_refs"], [
            "state/source_control.json",
            "state/researcher_control.json",
            "reviews/reviewer_observation.json",
            "judge/judge_report.json",
        ])

    def test_judge_can_route_same_contract_repair_back_to_researcher(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-judge-repair", topic="compiler autotuning")
        adapter = JudgeRepairingKernelV2FixtureAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=adapter,
            )
            flow_result = _read_json(root, result.flow_result_ref)
            run_root = root / result.run_workspace_ref
            step_records = [_read_json(run_root, ref) for ref in flow_result["step_record_refs"]]

        self.assertEqual(result.status, "accepted")
        self.assertEqual(
            [record["step_id"] for record in step_records],
            ["source_mapper", "researcher", "reviewer", "judge", "researcher", "reviewer", "judge"],
        )
        self.assertEqual(adapter.judge_call_count, 2)
        self.assertEqual(flow_result["decision_refs"], [
            "state/source_control.json",
            "state/researcher_control.json",
            "reviews/reviewer_observation.json",
            "judge/judge_report.json",
        ])

    def test_live_extension_mode_compiles_kernel_toolset_lock(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-extension", topic="compiler autotuning")
        adapter = KernelV2FixtureAdapter()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=adapter,
                live_extension_mode=True,
                extension_installer=_fake_extension_installer,
            )
            run_root = root / result.run_workspace_ref
            flow_result = _read_json(root, result.flow_result_ref)
            source_mapper_record = _read_json(run_root, flow_result["step_record_refs"][0])
            researcher_record = _read_json(run_root, flow_result["step_record_refs"][1])
            reviewer_record = _read_json(run_root, flow_result["step_record_refs"][2])
            lock = mf.ExtensionLock.from_dict(_read_json(run_root, source_mapper_record["extension_lock_ref"]))

        self.assertEqual(result.status, "accepted")
        self.assertIsNone(researcher_record["extension_lock_ref"])
        self.assertIsNone(reviewer_record["extension_lock_ref"])
        self.assertEqual(lock.extensions[0].package, "local:extensions/pi-academic-sources")
        self.assertEqual(
            lock.extensions[0].metadata["tool_names"],
            ["academic_provider_capabilities", "academic_search", "academic_fetch", "citation_lookup", "repo_search"],
        )

    def test_kernel_v2_contract_freezes_optional_request_fields(self) -> None:
        request = AcademicResearchRequest.from_dict(
            {
                "request_id": "kernel-v2-contract-fields",
                "topic": "compiler autotuning",
                "seed_papers": [{"kind": "doi", "value": "10.1145/1234567.1234568"}],
                "seed_pdf_refs": ["inputs/seeds/paper.pdf"],
                "sample_report_ref": "inputs/sample_report.md",
                "target_source_count": 100,
                "provider_policy": "openalex_enhanced",
                "previous_run_refs": ["runs/previous/packages/deepresearch_kernel_v2_result.json"],
                "constraints": ["Prefer recent systems papers."],
                "non_goals": ["Do not run benchmarks."],
            }
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            previous_result = root / "runs/previous/packages/deepresearch_kernel_v2_result.json"
            previous_result.parent.mkdir(parents=True, exist_ok=True)
            previous_result.write_text('{"status":"accepted"}\n', encoding="utf-8")
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            contract = _read_json(root, result.contract_ref)
            flow_result = _read_json(root, result.flow_result_ref)
            run_root = root / result.run_workspace_ref
            source_mapper_record = _read_json(run_root, flow_result["step_record_refs"][0])
            source_mapper_call = _read_json(run_root, source_mapper_record["piworker_call_ref"])
            source_mapper_manifest = _read_json(run_root, source_mapper_record["permission_manifest_ref"])
            previous_run_index = _read_json(run_root, kernel_v2_module.KERNEL_V2_PREVIOUS_RUN_INDEX_REF)
            staged_previous_run_exists = (run_root / previous_run_index["entries"][0]["staged_ref"]).is_file()

        self.assertEqual(contract["request"]["seed_pdf_refs"], ["inputs/seeds/paper.pdf"])
        self.assertEqual(contract["request"]["sample_report_ref"], "inputs/sample_report.md")
        self.assertEqual(contract["request"]["target_source_count"], 100)
        self.assertEqual(contract["request"]["provider_policy"], "openalex_enhanced")
        self.assertEqual(contract["request_payload_hash"], mf.stable_json_hash(contract["request"]))
        self.assertIn("inputs/seeds/paper.pdf", source_mapper_call["visible_refs"])
        self.assertIn("inputs/sample_report.md", source_mapper_call["visible_refs"])
        self.assertIn(kernel_v2_module.KERNEL_V2_PREVIOUS_RUN_INDEX_REF, source_mapper_call["visible_refs"])
        self.assertIn("inputs", source_mapper_manifest["readable_refs"])
        self.assertEqual(
            previous_run_index["entries"][0]["previous_run_ref"],
            "runs/previous/packages/deepresearch_kernel_v2_result.json",
        )
        self.assertTrue(staged_previous_run_exists)

    def test_kernel_v2_marks_unknown_report_citation_as_failed(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-bad-citation",
            topic="compiler autotuning",
            audience="R&D compiler team",
            language="zh",
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=BadCitationKernelV2FixtureAdapter(),
            )
            run_status = _read_json(root, result.run_status_ref)
            validation = _read_json(
                root,
                f"{result.run_workspace_ref}/state/citation_projection_validation.json",
            )
            flow_result = _read_json(root, result.flow_result_ref)

        self.assertEqual(flow_result["status"], "accepted")
        self.assertEqual(result.status, "failed")
        self.assertEqual(run_status["status"], "failed")
        self.assertEqual(run_status["citation_projection_status"], "failed")
        self.assertIn("unknown_source_id:S999", validation["failure_codes"])

    def test_kernel_v2_marks_unknown_claim_source_as_failed(self) -> None:
        request = AcademicResearchRequest(
            request_id="kernel-v2-bad-claim",
            topic="compiler autotuning",
            audience="R&D compiler team",
            language="zh",
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=BadClaimKernelV2FixtureAdapter(),
            )
            run_status = _read_json(root, result.run_status_ref)
            validation = _read_json(
                root,
                f"{result.run_workspace_ref}/state/claim_index_validation.json",
            )
            flow_result = _read_json(root, result.flow_result_ref)

        self.assertEqual(flow_result["status"], "accepted")
        self.assertEqual(result.status, "failed")
        self.assertEqual(run_status["status"], "failed")
        self.assertEqual(run_status["claim_index_validation_status"], "failed")
        self.assertIn("claim_C1_unknown_source_id", validation["failure_codes"])

    def test_kernel_v2_intensity_briefs_distinguish_standard_and_intensive(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            standard = run_deepresearch_kernel_v2(
                AcademicResearchRequest(
                    request_id="kernel-v2-standard-brief",
                    topic="deep research tools survey",
                    research_intensity=ResearchIntensity.STANDARD,
                ),
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            intensive = run_deepresearch_kernel_v2(
                AcademicResearchRequest(
                    request_id="kernel-v2-intensive-brief",
                    topic="deep research tools survey",
                    research_intensity=ResearchIntensity.INTENSIVE,
                ),
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            standard_source_mapper = _read_text(
                root,
                f"{standard.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_SOURCE_MAPPER_BRIEF_REF}",
            )
            standard_brief = _read_text(
                root,
                f"{standard.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_RESEARCHER_BRIEF_REF}",
            )
            standard_reviewer = _read_text(
                root,
                f"{standard.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_REVIEWER_RUBRIC_REF}",
            )
            standard_judge = _read_text(
                root,
                f"{standard.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_JUDGE_RUBRIC_REF}",
            )
            intensive_source_mapper = _read_text(
                root,
                f"{intensive.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_SOURCE_MAPPER_BRIEF_REF}",
            )
            intensive_brief = _read_text(
                root,
                f"{intensive.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_RESEARCHER_BRIEF_REF}",
            )
            intensive_reviewer = _read_text(
                root,
                f"{intensive.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_REVIEWER_RUBRIC_REF}",
            )
            intensive_judge = _read_text(
                root,
                f"{intensive.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_JUDGE_RUBRIC_REF}",
            )
            intensive_contract = _read_json(root, intensive.contract_ref)
            intensive_output_contract = _read_json(
                root,
                f"{intensive.run_workspace_ref}/{kernel_v2_module.KERNEL_V2_OUTPUT_CONTRACT_REF}",
            )

        self.assertIn("For standard runs, public metadata, papers, docs", standard_source_mapper)
        self.assertIn("Do not require clone-level or file-by-file code audit", standard_brief)
        self.assertIn("do not block solely because there was no clone-level", standard_reviewer)
        self.assertIn("Do not require repo/code audit as an acceptance condition", standard_judge)
        self.assertNotIn("repository/code-audit-backed research", standard_source_mapper)

        self.assertIn("For intensive runs, include repository or documentation evidence", intensive_source_mapper)
        self.assertIn("README, docs, examples, tests, configs", intensive_source_mapper)
        self.assertIn("Do not install projects, execute code, run benchmarks", intensive_source_mapper)
        self.assertIn("Intensive mode means repository/code-audit-backed research", intensive_brief)
        self.assertIn("file/path evidence", intensive_reviewer)
        self.assertIn("do not accept code-level conclusions that lack repository file/path evidence", intensive_judge)
        self.assertIn("repository/code-audit-backed technical report", intensive_contract["research_intensity_guidance"])
        self.assertEqual(
            intensive_output_contract["research_intensity_guidance"],
            intensive_contract["research_intensity_guidance"],
        )
        self.assertEqual(
            intensive_output_contract["insight_map_ref"],
            kernel_v2_module.KERNEL_V2_INSIGHT_MAP_REF,
        )

    def test_kernel_v2_usage_summary_aggregates_piworker_token_metrics(self) -> None:
        request = AcademicResearchRequest(request_id="kernel-v2-token-summary", topic="compiler autotuning")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=TokenMetricsKernelV2FixtureAdapter(),
            )
            usage = _read_json(root, result.usage_summary_ref)

        self.assertEqual(result.metric_refs, [result.usage_summary_ref])
        self.assertEqual(usage["totals"]["input_tokens"], 800)
        self.assertEqual(usage["totals"]["cached_input_tokens"], 200)
        self.assertEqual(usage["totals"]["uncached_input_tokens"], 800)
        self.assertEqual(usage["totals"]["total_input_tokens"], 1000)
        self.assertEqual(usage["totals"]["output_tokens"], 80)
        self.assertEqual(usage["totals"]["total_tokens"], 880)
        self.assertEqual(usage["totals"]["provider_reported_cost_usd"], 0.008)
        self.assertEqual([step["usage"]["cached_input_tokens"] for step in usage["steps"]], [50, 50, 50, 50])


def _read_json(root: Path, ref: str):
    return json.loads((root / ref).read_text(encoding="utf-8"))


def _read_text(root: Path, ref: str) -> str:
    return (root / ref).read_text(encoding="utf-8")


def _read_jsonl(root: Path, ref: str) -> list[dict]:
    path = root / ref
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ref_is_under_any(ref: str, roots: list[str]) -> bool:
    return any(ref == root or ref.startswith(root + "/") for root in roots)


def _fake_extension_installer(grant, install_root):
    package_name = Path(grant.package.split(":", 1)[1]).name
    install_path = install_root / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "package.json").write_text(
        f'{{"name":"@missionforge/{package_name}","version":"{grant.version_spec}"}}\n',
        encoding="utf-8",
    )
    (install_path / "index.js").write_text("export default function () {}\n", encoding="utf-8")
    return {}


class CountingKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def __init__(self) -> None:
        self.call_count = 0

    def run_call(self, *args, **kwargs):
        self.call_count += 1
        return super().run_call(*args, **kwargs)


class RevisingKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def __init__(self) -> None:
        self.reviewer_call_count = 0

    def _write_reviewer_outputs(self, workspace: Path, call) -> None:
        self.reviewer_call_count += 1
        if self.reviewer_call_count == 1:
            kernel_v2_module.write_json_ref(
                workspace,
                kernel_v2_module.KERNEL_V2_REVIEWER_OBSERVATION_REF,
                {
                    "schema_version": "missionforge_deepresearch.kernel_v2.reviewer_observation.v1",
                    "decision": "revise_report",
                    "reviewer_report_ref": kernel_v2_module.KERNEL_V2_REVIEWER_OBSERVATION_REF,
                    "blocking_gaps": [
                        {
                            "gap_id": "G1",
                            "required_fix": "Add References and repair the truncated ending.",
                        }
                    ],
                    "next_directive_ref": "",
                },
            )
            return
        super()._write_reviewer_outputs(workspace, call)


class JudgeRepairingKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def __init__(self) -> None:
        self.judge_call_count = 0

    def _write_judge_outputs(self, workspace: Path, call) -> None:
        self.judge_call_count += 1
        if self.judge_call_count == 1:
            kernel_v2_module.write_json_ref(
                workspace,
                kernel_v2_module.KERNEL_V2_JUDGE_REPORT_REF,
                {
                    "schema_version": "missionforge_deepresearch.kernel_v2.judge_report.v1",
                    "decision": "repair",
                    "repair_scope": "same_contract",
                    "blocking_gaps": [
                        {
                            "gap_id": "J1",
                            "required_fix": "Apply bounded same-contract repair before acceptance.",
                        }
                    ],
                },
            )
            return
        super()._write_judge_outputs(workspace, call)


class TokenMetricsKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def run_call(self, *args, **kwargs):
        result = super().run_call(*args, **kwargs)
        call = args[0]
        workspace = Path(kwargs.get("workspace", "."))
        step_index = {
            "source_mapper": 1,
            "researcher": 2,
            "reviewer": 3,
            "judge": 4,
        }[str(call.metadata.get("kernel_step_id", ""))]
        metrics_ref = f"attempts/{call.call_id}/metrics.json"
        kernel_v2_module.write_json_ref(
            workspace,
            metrics_ref,
            {
                "total_tokens": 220,
                "input_tokens": 200,
                "output_tokens": 20,
                "cache_read_tokens": 50,
                "cache_write_tokens": step_index,
                "provider_reported_cost_usd": 0.002,
            },
        )
        return result


class BadCitationKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def _write_researcher_outputs(self, workspace: Path, call) -> None:
        super()._write_researcher_outputs(workspace, call)
        report = (workspace / kernel_v2_module.KERNEL_V2_FINAL_REPORT_REF).read_text(encoding="utf-8")
        kernel_v2_module.write_text_ref(
            workspace,
            kernel_v2_module.KERNEL_V2_FINAL_REPORT_REF,
            report.replace("[S1]", "[S999]", 1),
        )


class BadClaimKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def _write_researcher_outputs(self, workspace: Path, call) -> None:
        super()._write_researcher_outputs(workspace, call)
        claim_index = _read_json(workspace, kernel_v2_module.KERNEL_V2_CLAIM_INDEX_REF)
        claim_index["claims"][0]["supporting_source_ids"] = ["S999"]
        kernel_v2_module.write_json_ref(workspace, kernel_v2_module.KERNEL_V2_CLAIM_INDEX_REF, claim_index)


class AcceptingResearcherKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def _write_researcher_outputs(self, workspace: Path, call) -> None:
        super()._write_researcher_outputs(workspace, call)
        payload = _read_json(workspace, kernel_v2_module.KERNEL_V2_RESEARCHER_CONTROL_REF)
        payload["decision"] = "accepted"
        kernel_v2_module.write_json_ref(workspace, kernel_v2_module.KERNEL_V2_RESEARCHER_CONTROL_REF, payload)


class AcceptingReviewerKernelV2FixtureAdapter(KernelV2FixtureAdapter):
    def _write_reviewer_outputs(self, workspace: Path, call) -> None:
        super()._write_reviewer_outputs(workspace, call)
        payload = _read_json(workspace, kernel_v2_module.KERNEL_V2_REVIEWER_OBSERVATION_REF)
        payload["decision"] = "accepted"
        kernel_v2_module.write_json_ref(workspace, kernel_v2_module.KERNEL_V2_REVIEWER_OBSERVATION_REF, payload)


class ReviewerProviderBlockedKernelV2Adapter(KernelV2FixtureAdapter):
    def run_call(self, call, *, workspace: str | Path = ".", **kwargs):
        if str(call.metadata.get("kernel_step_id", "")) != "reviewer":
            return super().run_call(call, workspace=workspace, **kwargs)
        report_ref = f"attempts/{call.call_id}/execution_report.json"
        report = mf.ExecutionReport(
            report_id=f"deepresearch-kernel-v2-{call.call_id}",
            call_id=call.call_id,
            status="failed",
            produced_artifacts=[],
            changed_refs=[report_ref],
            evidence_refs=[],
            metrics={
                "failure_summary": "OpenAI API error (403): 403 余额不足",
                "non_retryable_provider_error": True,
            },
        )
        kernel_v2_module.write_json_ref(workspace, report_ref, report.to_dict())
        return mf.WorkerAdapterResult(
            execution_report=report,
            worker_result=mf.WorkerResult(status="failed", execution_report_ref=report_ref),
        )


if __name__ == "__main__":
    unittest.main()
