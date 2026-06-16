from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from missionforge.piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallRole
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge_deepresearch import (
    DeepResearchRunStatus,
    ResearchIntensity,
    load_deepresearch_run_result,
    research_intensity_profile,
    run_deepresearch_academic_single_agent,
)
from missionforge_deepresearch.runtime import (
    RESEARCHER_EXECUTION_REPORT_REF,
    RESEARCHER_METRICS_REF,
    FixtureAcademicResearcherAdapter,
    run_structural_checks,
)
from missionforge_deepresearch.search_intent import FixtureSearchIntentAdapter, SEARCH_INTENT_CALL_RESULT_REF, SEARCH_INTENT_REF
from missionforge_deepresearch.source_collector import AcademicSourceCollectionResult
from missionforge_deepresearch.workspace import write_json_ref, write_text_ref

from test_product_contract import sample_request


class RuntimeTests(unittest.TestCase):
    def test_single_agent_fixture_run_produces_draft_ready_package(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_single_agent(sample_request(), workspace=root)
            loaded = load_deepresearch_run_result(root, result.run_result_ref)

            self.assertEqual(loaded, result)
            self.assertEqual(result.status, DeepResearchRunStatus.DRAFT_READY)
            self.assertTrue((root / result.run_result_ref).exists())
            self.assertTrue((root / result.researcher_call_ref).exists())
            self.assertTrue((root / result.researcher_call_result_ref).exists())
            self.assertTrue((root / result.structural_check_ref).exists())
            structural = json.loads((root / result.structural_check_ref).read_text(encoding="utf-8"))
            self.assertEqual(structural["source_packet_audit"]["status"], "passed")
            self.assertEqual(structural["citation_audit"]["status"], "passed")
            self.assertIn("sources/source_packet.json", structural["checked_refs"])
            final_report = (root / "runs/npu-compiler-survey/reports/final_report.md").read_text(encoding="utf-8")
            self.assertIn("[S1", final_report)
            self.assertIn("## References", final_report)
            self.assertEqual(
                result.draft_artifact_refs,
                [
                    "runs/npu-compiler-survey/reports/final_report.md",
                    "runs/npu-compiler-survey/reports/evidence_index.md",
                    "runs/npu-compiler-survey/reports/research_delta.md",
                    "runs/npu-compiler-survey/reports/reading_plan.md",
                    "runs/npu-compiler-survey/reports/source_gaps.md",
                ],
            )
            call_payload = (root / result.researcher_call_ref).read_text(encoding="utf-8")
            self.assertIn("executor_piworker", call_payload)
            self.assertNotIn("judge_piworker", call_payload)
            self.assertNotIn("\"accepted\"", (root / result.run_result_ref).read_text(encoding="utf-8"))

    def test_structural_failure_prevents_draft_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_single_agent(
                sample_request(),
                workspace=root,
                adapter=_IncompleteResearcherAdapter(),
            )

            self.assertEqual(result.status, DeepResearchRunStatus.FAILED)
            self.assertFalse((root / "runs/npu-compiler-survey/reports/source_gaps.md").exists())

    def test_live_run_can_generate_search_intent_before_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch_runtime_collector():
                result = run_deepresearch_academic_single_agent(
                    sample_request(),
                    workspace=root,
                    source_mode="live",
                    researcher_mode="fixture",
                    search_intent_mode="piworker",
                    search_intent_adapter=FixtureSearchIntentAdapter(),
                    extension_installer=_fake_extension_installer,
                )

            run_root = root / "runs/npu-compiler-survey"
            self.assertEqual(result.status, DeepResearchRunStatus.DRAFT_READY)
            self.assertTrue((run_root / SEARCH_INTENT_REF).exists())
            self.assertTrue((run_root / SEARCH_INTENT_CALL_RESULT_REF).exists())
            source_packet = (run_root / "sources/source_packet.json").read_text(encoding="utf-8")
            self.assertIn("\"query_expansion\": \"search_intent\"", source_packet)

    def test_live_extension_mode_uses_extension_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            install_root = root / ".missionforge/extensions/node_modules"
            for package_name in ("pi-web-access", "@juicesharp/rpiv-web-tools"):
                install_path = install_root / package_name
                install_path.mkdir(parents=True, exist_ok=True)
                (install_path / "package.json").write_text(f'{{"name":"{package_name}"}}\n', encoding="utf-8")

            with patch_runtime_collector():
                result = run_deepresearch_academic_single_agent(
                    sample_request(),
                    workspace=root,
                    source_mode="live",
                    researcher_mode="fixture",
                    search_intent_mode="piworker",
                    search_intent_adapter=FixtureSearchIntentAdapter(),
                    live_extension_mode=True,
                    extension_installer=_fake_extension_installer,
                )

            run_root = root / "runs/npu-compiler-survey"
            self.assertEqual(result.status, DeepResearchRunStatus.DRAFT_READY)
            self.assertTrue((run_root / "compiled/extension_lock.json").exists())
            source_packet = (run_root / "sources/source_packet.json").read_text(encoding="utf-8")
            self.assertIn("\"source_acquisition\": \"pi_extensions\"", source_packet)
            self.assertEqual(json.loads(source_packet)["collection_policy"]["tool_surface"], ["web", "code_search"])
            self.assertGreater(len(json.loads(source_packet)["source_records"]), 0)
            lock_payload = json.loads((run_root / "compiled/extension_lock.json").read_text(encoding="utf-8"))
            self.assertTrue(lock_payload["extensions"][0]["install_path"].startswith(".missionforge/extensions/"))

    def test_live_researcher_receives_run_relative_extension_lock_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            install_root = root / ".missionforge/extensions/node_modules"
            for package_name in ("pi-web-access", "@juicesharp/rpiv-web-tools"):
                install_path = install_root / package_name
                install_path.mkdir(parents=True, exist_ok=True)
                (install_path / "package.json").write_text(f'{{"name":"{package_name}"}}\n', encoding="utf-8")

            researcher = _CaptureResearcherAdapter()
            with patch_runtime_collector():
                result = run_deepresearch_academic_single_agent(
                    sample_request(),
                    workspace=root,
                    source_mode="live",
                    researcher_mode="fixture",
                    search_intent_mode="piworker",
                    search_intent_adapter=FixtureSearchIntentAdapter(),
                    adapter=researcher,
                    live_extension_mode=True,
                    extension_installer=_fake_extension_installer,
                )

            self.assertEqual(result.status, DeepResearchRunStatus.DRAFT_READY)
            self.assertEqual(researcher.captured_extension_lock_ref, "compiled/extension_lock.json")
            self.assertIn("sources/source_packet.json", researcher.captured_expected_output_refs)

    def test_research_intensity_sets_researcher_runtime_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = sample_request().__class__(
                **{
                    **sample_request().to_dict(),
                    "research_intensity": ResearchIntensity.INTENSIVE.value,
                }
            )
            researcher = _CaptureResearcherAdapter()

            result = run_deepresearch_academic_single_agent(
                request,
                workspace=root,
                adapter=researcher,
            )

            profile = research_intensity_profile(ResearchIntensity.INTENSIVE)
            self.assertEqual(result.status, DeepResearchRunStatus.DRAFT_READY)
            self.assertEqual(researcher.captured_runtime_budget["max_turns"], profile.researcher_max_turns)
            self.assertEqual(researcher.captured_runtime_budget["timeout_seconds"], profile.piworker_timeout_seconds)
            self.assertEqual(researcher.captured_metadata["research_intensity"], "intensive")

    def test_unknown_citation_prevents_draft_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_single_agent(
                sample_request(),
                workspace=root,
                adapter=_BadCitationResearcherAdapter(),
            )

            structural = json.loads((root / result.structural_check_ref).read_text(encoding="utf-8"))
            self.assertEqual(result.status, DeepResearchRunStatus.FAILED)
            self.assertEqual(structural["citation_audit"]["status"], "failed")
            self.assertIn("final_report_unknown_source_ids:S999", structural["citation_audit"]["errors"])

    def test_source_packet_accepts_nested_locator_object(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_json_ref(
                root,
                "sources/source_packet.json",
                {
                    "schema_version": "missionforge_deepresearch.source_packet.v1",
                    "request_id": "nested-locator",
                    "source_records": [
                        {
                            "source_id": "S1",
                            "title": "Nested locator source",
                            "source_type": "paper",
                            "year": 2024,
                            "locator": {
                                "url": "https://arxiv.org/abs/2401.00001",
                                "arxiv_id": "2401.00001",
                            },
                        },
                        {
                            "source_id": "S2",
                            "title": "External source ref source",
                            "source_type": "official_documentation",
                            "source_ref": "https://tvm.apache.org/docs/v0.16.0/how_to/tune_with_autoscheduler/tune_network_cuda.html",
                        }
                    ],
                },
            )
            write_text_ref(
                root,
                "reports/final_report.md",
                (
                    "# Report\n\n"
                    "Claim [S1, S2].\n\n"
                    "## References\n\n"
                    "- [S1] Nested locator source. https://arxiv.org/abs/2401.00001\n"
                    "- [S2] External source ref source. https://tvm.apache.org/docs/v0.16.0/how_to/tune_with_autoscheduler/tune_network_cuda.html\n"
                ),
            )
            write_text_ref(root, "reports/evidence_index.md", "# Evidence Index\n\n- [S1] Nested locator source.\n- [S2] External source ref source.\n")
            write_text_ref(root, "reports/research_delta.md", "# Delta\n\nBaseline.\n")
            write_text_ref(root, "reports/reading_plan.md", "# Reading Plan\n\nRead [S1].\n")
            write_text_ref(root, "reports/source_gaps.md", "# Source Gaps\n\nNone.\n")
            call = PiWorkerCall(
                call_id="nested-locator-call",
                role=PiWorkerCallRole.EXECUTOR,
                contract_id="nested-locator-contract",
                contract_hash="sha256:" + "1" * 64,
                contract_ref="contract/task_contract.json",
                objective="Validate nested locator.",
                writable_refs=["sources", "reports"],
                expected_output_refs=[
                    "sources/source_packet.json",
                    "reports/final_report.md",
                    "reports/evidence_index.md",
                    "reports/research_delta.md",
                    "reports/reading_plan.md",
                    "reports/source_gaps.md",
                ],
            )
            report = ExecutionReport(
                report_id="nested-locator-report",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=list(call.expected_output_refs),
                changed_refs=list(call.expected_output_refs),
            )
            call_result = PiWorkerCallResult.from_worker_adapter_result(
                call,
                WorkerAdapterResult(
                    execution_report=report,
                    worker_result=WorkerResult(status="completed", execution_report_ref="attempts/report.json"),
                ),
            )

            structural = run_structural_checks(
                workspace=root,
                expected_refs=list(call.expected_output_refs),
                call_result=call_result,
            )

            self.assertEqual(structural["status"], "passed")
            self.assertEqual(structural["source_packet_audit"]["status"], "passed")

    def test_result_package_uses_adapter_runtime_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_academic_single_agent(
                sample_request(),
                workspace=root,
                adapter=_RuntimeRefResearcherAdapter(),
            )

            self.assertEqual(result.status, DeepResearchRunStatus.DRAFT_READY)
            self.assertIn(
                "runs/npu-compiler-survey/attempts/runtime-researcher/pi_agent_execution_report.json",
                result.evidence_refs,
            )
            self.assertNotIn("runs/npu-compiler-survey/attempts/researcher/execution_report.json", result.evidence_refs)
            self.assertEqual(
                result.metric_refs,
                ["runs/npu-compiler-survey/attempts/runtime-researcher/pi_agent_metrics.json"],
            )


class _IncompleteResearcherAdapter(FixtureAcademicResearcherAdapter):
    adapter_family = "fixture_incomplete_deepresearch_researcher"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ) -> WorkerAdapterResult:
        if call.role is not PiWorkerCallRole.EXECUTOR:
            raise AssertionError("unexpected role")
        write_text_ref(workspace, "reports/final_report.md", "# Partial Draft\n")
        write_json_ref(workspace, RESEARCHER_METRICS_REF, {"metric_ref": RESEARCHER_METRICS_REF})
        report = ExecutionReport(
            report_id="deepresearch-incomplete-researcher-report",
            call_id=call.call_id,
            status="invalid_output",
            produced_artifacts=["reports/final_report.md"],
            changed_refs=["reports/final_report.md", RESEARCHER_EXECUTION_REPORT_REF, RESEARCHER_METRICS_REF],
            evidence_refs=[],
            metrics={"metric_ref": RESEARCHER_METRICS_REF},
        )
        write_json_ref(workspace, RESEARCHER_EXECUTION_REPORT_REF, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="invalid_output", execution_report_ref=RESEARCHER_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics={"metric_ref": RESEARCHER_METRICS_REF},
        )


class _CaptureResearcherAdapter(FixtureAcademicResearcherAdapter):
    adapter_family = "fixture_capture_deepresearch_researcher"

    def __init__(self) -> None:
        self.captured_extension_lock_ref: str | None = None
        self.captured_expected_output_refs: list[str] = []
        self.captured_runtime_budget: dict[str, object] = {}
        self.captured_metadata: dict[str, object] = {}

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ) -> WorkerAdapterResult:
        self.captured_extension_lock_ref = extension_lock_ref
        self.captured_expected_output_refs = list(call.expected_output_refs)
        self.captured_runtime_budget = dict(call.runtime_budget)
        self.captured_metadata = dict(call.metadata)
        return super().run_call(
            call,
            workspace=workspace,
            evidence_store=evidence_store,
            call_spec=call_spec,
            exit_criteria=exit_criteria,
            stop_conditions=stop_conditions,
            extension_lock_ref=extension_lock_ref,
        )


class _RuntimeRefResearcherAdapter(FixtureAcademicResearcherAdapter):
    adapter_family = "fixture_runtime_ref_deepresearch_researcher"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ) -> WorkerAdapterResult:
        if call.role is not PiWorkerCallRole.EXECUTOR:
            raise AssertionError("unexpected role")
        for ref in call.expected_output_refs:
            if ref == "sources/source_packet.json":
                write_json_ref(
                    workspace,
                    ref,
                    {
                        "schema_version": "missionforge_deepresearch.source_packet.v1",
                        "request_id": "npu-compiler-survey",
                        "source_records": [
                            {
                                "source_id": "S1",
                                "title": "Runtime ref fixture source",
                                "source_type": "webpage_fixture",
                                "source_ref": "sources/source_packet.json",
                            }
                        ],
                    },
                )
            elif ref == "reports/final_report.md":
                write_text_ref(workspace, ref, "# Artifact\n\nClaim [S1].\n\n## References\n\n- [S1] Runtime ref fixture source. sources/source_packet.json\n")
            elif ref == "reports/evidence_index.md":
                write_text_ref(workspace, ref, "# Evidence Index\n\n- [S1] Runtime ref fixture source. sources/source_packet.json\n")
            else:
                write_text_ref(workspace, ref, f"# Artifact\n\n{ref}\n")
        report_ref = "attempts/runtime-researcher/pi_agent_execution_report.json"
        metrics_ref = "attempts/runtime-researcher/pi_agent_metrics.json"
        write_json_ref(workspace, metrics_ref, {"metric_ref": metrics_ref})
        report = ExecutionReport(
            report_id="runtime-ref-researcher-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=list(call.expected_output_refs),
            changed_refs=[*call.expected_output_refs, report_ref, metrics_ref],
            evidence_refs=["sources/source_packet.json"],
            metrics={"metric_ref": metrics_ref},
        )
        write_json_ref(workspace, report_ref, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
            event_evidence_refs=[],
            metrics={"metric_ref": metrics_ref},
        )


class _BadCitationResearcherAdapter(FixtureAcademicResearcherAdapter):
    adapter_family = "fixture_bad_citation_deepresearch_researcher"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ) -> WorkerAdapterResult:
        if call.role is not PiWorkerCallRole.EXECUTOR:
            raise AssertionError("unexpected role")
        write_json_ref(
            workspace,
            "sources/source_packet.json",
            {
                "schema_version": "missionforge_deepresearch.source_packet.v1",
                "request_id": "npu-compiler-survey",
                "source_records": [
                    {
                        "source_id": "S1",
                        "title": "Known fixture source",
                        "source_type": "webpage_fixture",
                        "source_ref": "sources/source_packet.json",
                    }
                ],
            },
        )
        write_text_ref(workspace, "reports/final_report.md", "# Bad Citation\n\nUnsupported claim [S999].\n\n## References\n\n- [S999] Unknown source.\n")
        write_text_ref(workspace, "reports/evidence_index.md", "# Evidence Index\n\n- [S1] Known fixture source.\n")
        write_text_ref(workspace, "reports/research_delta.md", "# Delta\n\nBaseline.\n")
        write_text_ref(workspace, "reports/reading_plan.md", "# Reading Plan\n\nRead [S1].\n")
        write_text_ref(workspace, "reports/source_gaps.md", "# Source Gaps\n\nUnknown citation.\n")
        write_json_ref(workspace, RESEARCHER_METRICS_REF, {"metric_ref": RESEARCHER_METRICS_REF})
        report = ExecutionReport(
            report_id="bad-citation-researcher-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=list(call.expected_output_refs),
            changed_refs=[*call.expected_output_refs, RESEARCHER_EXECUTION_REPORT_REF, RESEARCHER_METRICS_REF],
            evidence_refs=["sources/source_packet.json", "reports/evidence_index.md"],
            metrics={"metric_ref": RESEARCHER_METRICS_REF},
        )
        write_json_ref(workspace, RESEARCHER_EXECUTION_REPORT_REF, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=RESEARCHER_EXECUTION_REPORT_REF),
            event_evidence_refs=[],
            metrics={"metric_ref": RESEARCHER_METRICS_REF},
        )


def patch_runtime_collector():
    return patch("missionforge_deepresearch.runtime.collect_live_academic_sources", _fake_collect_live_sources)


def _fake_collect_live_sources(request, *, config=None, search_intent=None):
    if search_intent is None:
        raise AssertionError("expected search intent")
    record = {
        "source_id": "S001",
        "title": "Fixture live source",
        "source_type": "academic_index_work",
        "source_ref": "sources/live/S001.json",
        "provider": "fixture",
        "query": search_intent.queries[0],
        "url": "https://example.test/source",
        "doi": "",
        "publication_year": 2025,
        "published": "2025-01-01",
        "authors": ["Ada Researcher"],
        "venue": "Fixture Venue",
        "citation_count": 1,
        "abstract": "Fixture live source.",
    }
    return AcademicSourceCollectionResult(
        source_packet={
            "schema_version": "missionforge_deepresearch.source_packet.v1",
            "request_id": request.request_id,
            "mode": "live",
            "query": request.topic,
            "search_intent_ref": SEARCH_INTENT_REF,
            "search_queries": list(search_intent.queries),
            "previous_run_refs": list(request.previous_run_refs),
            "collection_policy": {"query_expansion": "search_intent"},
            "source_records": [record],
            "limitations": [],
        },
        source_payloads={
            SEARCH_INTENT_REF: search_intent.to_dict(),
            "sources/live/S001.json": {
                "schema_version": "missionforge_deepresearch.live_source_record.v1",
                "source_id": "S001",
                "request_id": request.request_id,
                "query": search_intent.queries[0],
                "provider": "fixture",
                "source_record": record,
                "raw_provider_payload": {},
            },
        },
        collection_report={
            "schema_version": "missionforge_deepresearch.source_collection_report.v1",
            "request_id": request.request_id,
            "mode": "live",
            "query": request.topic,
            "search_intent_ref": SEARCH_INTENT_REF,
            "search_queries": list(search_intent.queries),
            "provider_reports": [],
            "candidate_count": 1,
            "selected_count": 1,
            "source_packet_ref": "sources/source_packet.json",
            "source_record_refs": ["sources/live/S001.json"],
        },
        search_intent=search_intent,
    )


def _fake_extension_installer(grant, install_root):
    package_name = grant.package.split(":", 1)[1]
    install_path = install_root / "node_modules" / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "package.json").write_text(
        f'{{"name":"{package_name}","version":"{grant.version_spec}"}}\n',
        encoding="utf-8",
    )
    return {}


if __name__ == "__main__":
    unittest.main()
