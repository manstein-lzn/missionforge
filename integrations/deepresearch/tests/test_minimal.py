from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult

from missionforge_deepresearch import (
    MinimalFixtureResearcherAdapter,
    MinimalFixtureReviewerAdapter,
    run_deepresearch_minimal,
    run_deepresearch_minimal_loop,
)
from missionforge_deepresearch.minimal import (
    MINIMAL_EXECUTION_REPORT_REF,
    MINIMAL_EXTENSION_LOCK_REF,
    MINIMAL_REPORT_REFS,
    MINIMAL_SOURCE_PACKET_REF,
)
from missionforge_deepresearch.workspace import read_json_ref, write_json_ref, write_text_ref

from test_product_contract import sample_request


class MinimalDeepResearchTests(unittest.TestCase):
    def test_minimal_fixture_run_produces_draft_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_minimal(
                sample_request(),
                workspace=root,
                adapter=MinimalFixtureResearcherAdapter(),
            )

            self.assertEqual(result.status, "draft_ready")
            self.assertEqual(result.worker_status, "completed")
            self.assertEqual(result.boundary_status, "passed")
            self.assertTrue((root / result.result_ref).exists())
            self.assertTrue((root / result.final_report_ref).exists())
            boundary = json.loads((root / result.boundary_validation_ref).read_text(encoding="utf-8"))
            self.assertEqual(boundary["status"], "passed")
            payload = json.loads((root / result.result_ref).read_text(encoding="utf-8"))
            self.assertEqual(payload["check_ref"], payload["boundary_validation_ref"])
            report = (root / result.final_report_ref).read_text(encoding="utf-8")
            self.assertIn("## 对比矩阵", report)
            self.assertIn("[S1]", report)

    def test_boundary_warnings_do_not_override_completed_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_minimal(
                sample_request(),
                workspace=root,
                adapter=IncompleteEvidenceIndexAdapter(),
            )

            self.assertEqual(result.status, "draft_ready")
            self.assertEqual(result.worker_status, "completed")
            self.assertEqual(result.boundary_status, "passed_with_warnings")
            boundary = json.loads((root / result.boundary_validation_ref).read_text(encoding="utf-8"))
            self.assertEqual(boundary["blocking_errors"], [])
            self.assertIn("evidence_index_missing_source_ids:S2", boundary["warnings"])

    def test_live_extension_mode_compiles_and_passes_extension_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            researcher = CaptureMinimalResearcherAdapter()

            result = run_deepresearch_minimal(
                sample_request(),
                workspace=root,
                adapter=researcher,
                live_extension_mode=True,
                extension_installer=fake_extension_installer,
            )

            run_root = root / result.run_workspace_ref
            self.assertEqual(result.status, "draft_ready")
            self.assertEqual(result.extension_lock_ref, f"{result.run_workspace_ref}/{MINIMAL_EXTENSION_LOCK_REF}")
            self.assertEqual(researcher.captured_extension_lock_ref, MINIMAL_EXTENSION_LOCK_REF)
            self.assertTrue((run_root / MINIMAL_EXTENSION_LOCK_REF).exists())
            lock_payload = json.loads((run_root / MINIMAL_EXTENSION_LOCK_REF).read_text(encoding="utf-8"))
            self.assertEqual(len(lock_payload["extensions"]), 3)
            self.assertIn(
                "local:extensions/pi-academic-sources",
                [entry["package"] for entry in lock_payload["extensions"]],
            )

    def test_minimal_loop_fixture_accepts_after_review(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = run_deepresearch_minimal_loop(
                sample_request(),
                workspace=root,
                researcher_adapter=MinimalFixtureResearcherAdapter(),
                reviewer_adapter=MinimalFixtureReviewerAdapter("accepted"),
                review_rounds=1,
            )

            self.assertEqual(result.status, "accepted")
            self.assertEqual(result.review_decision, "accepted")
            self.assertEqual(result.review_round_count, 1)
            self.assertEqual(len(result.review_decision_refs), 1)
            self.assertTrue((root / result.result_ref).exists())
            decision = json.loads((root / result.review_decision_refs[0]).read_text(encoding="utf-8"))
            self.assertEqual(decision["decision"], "accepted")


class IncompleteEvidenceIndexAdapter:
    adapter_family = "fixture_incomplete_evidence_index"

    def run_call(self, call, *, workspace=".", **_kwargs):
        request = read_json_ref(workspace, "product_contract/research_request.json", "research_request")
        source_packet = {
            "schema_version": "missionforge_deepresearch.source_packet.v1",
            "request_id": str(request["request_id"]),
            "source_records": [
                {
                    "source_id": "S1",
                    "title": "First source",
                    "source_type": "fixture",
                    "locator": "https://example.test/first",
                },
                {
                    "source_id": "S2",
                    "title": "Second source",
                    "source_type": "fixture",
                    "locator": "https://example.test/second",
                },
            ],
        }
        write_json_ref(workspace, MINIMAL_SOURCE_PACKET_REF, source_packet)
        write_text_ref(
            workspace,
            "reports/final_report.md",
            "# Report\n\n## 范围与方法\n\nClaim [S1, S2].\n\n## 参考文献\n\n- [S1] First source. https://example.test/first\n- [S2] Second source. https://example.test/second\n",
        )
        write_text_ref(workspace, "reports/evidence_index.md", "- [S1] Evidence note.\n")
        write_text_ref(workspace, "reports/source_gaps.md", "Missing complete evidence index coverage.\n")
        report = ExecutionReport(
            report_id="incomplete-evidence-index-report",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS],
            changed_refs=[MINIMAL_SOURCE_PACKET_REF, *MINIMAL_REPORT_REFS, MINIMAL_EXECUTION_REPORT_REF],
            evidence_refs=[MINIMAL_SOURCE_PACKET_REF, "reports/evidence_index.md"],
            metrics={},
        )
        write_json_ref(workspace, MINIMAL_EXECUTION_REPORT_REF, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=MINIMAL_EXECUTION_REPORT_REF),
            metrics={},
        )


class CaptureMinimalResearcherAdapter(MinimalFixtureResearcherAdapter):
    def __init__(self) -> None:
        self.captured_extension_lock_ref: str | None = None

    def run_call(self, call, *, extension_lock_ref=None, **kwargs):
        self.captured_extension_lock_ref = extension_lock_ref
        return super().run_call(call, extension_lock_ref=extension_lock_ref, **kwargs)


def fake_extension_installer(grant, install_root):
    if grant.package.startswith("local:"):
        package_name = Path(grant.package.split(":", 1)[1]).name
        install_path = install_root / package_name
        install_path.mkdir(parents=True, exist_ok=True)
        (install_path / "package.json").write_text(
            f'{{"name":"@missionforge/{package_name}","version":"{grant.version_spec}"}}\n',
            encoding="utf-8",
        )
        (install_path / "index.js").write_text("export default function () {}\n", encoding="utf-8")
        return {}
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
