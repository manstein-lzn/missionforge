from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import missionforge as mf
from missionforge_deepresearch.kernel_v2 import KernelV2FixtureAdapter, run_deepresearch_kernel_v2
from missionforge_deepresearch.product_contract import AcademicResearchRequest
from missionforge_deepresearch.web_console import (
    build_project_snapshot,
    read_project_artifact,
    render_project_dashboard,
    web_console_response,
)


class WebConsoleTests(unittest.TestCase):
    def test_snapshot_reads_existing_project_refs_without_writing_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-console-demo",
                topic="compiler autotuning survey",
            )
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            before_paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())

            snapshot = build_project_snapshot(root, "web-console-demo")
            after_paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())

        self.assertEqual(before_paths, after_paths)
        self.assertEqual(snapshot["schema_version"], "missionforge_deepresearch.web_console.project_snapshot.v1")
        self.assertEqual(snapshot["request_id"], "web-console-demo")
        self.assertEqual(snapshot["run_workspace_ref"], result.run_workspace_ref)
        self.assertTrue(snapshot["project_exists"])
        self.assertEqual(snapshot["project"]["lifecycle"]["phase"], "accepted")
        self.assertEqual(snapshot["project"]["resume_diagnostics"]["status"], "reusable")
        self.assertEqual(snapshot["source_summary"]["source_records"], 1)
        self.assertEqual(snapshot["source_summary"]["canonical_sources"], 1)
        self.assertEqual(snapshot["claim_support"]["overall_status"], "passed")
        self.assertEqual(snapshot["judge"]["decision"], "accepted")
        self.assertEqual(snapshot["report_preview"]["ref"], "reports/final_report.citation_projected.md")
        self.assertIn("Kernel v2 DeepResearch Fixture Report", snapshot["report_preview"]["markdown"])
        artifact_refs = {item["ref"] for item in snapshot["artifacts"] if item["exists"]}
        self.assertIn("state/acceptance_gate.json", artifact_refs)
        self.assertIn("judge/judge_report.json", artifact_refs)

    def test_render_project_dashboard_escapes_report_content_and_links_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-console-escape",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            report_path = root / "runs/web-console-escape/reports/final_report.citation_projected.md"
            report_path.write_text("# Title\n\n<script>alert('x')</script>\n", encoding="utf-8")

            html = render_project_dashboard(build_project_snapshot(root, "web-console-escape"))

        self.assertIn("DeepResearch Project", html)
        self.assertIn("/artifact?ref=state/acceptance_gate.json", html)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert", html)

    def test_read_project_artifact_pretty_prints_json_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-console-artifact",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )

            artifact = read_project_artifact(root, "web-console-artifact", "state/run_status.json")

            with self.assertRaises(mf.ContractValidationError):
                read_project_artifact(root, "web-console-artifact", "../outside.json")

        self.assertEqual(artifact["ref"], "state/run_status.json")
        self.assertFalse(artifact["binary"])
        self.assertIn('"status": "accepted"', artifact["content"])

    def test_web_console_response_exposes_dashboard_and_read_only_project_api(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-console-http",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            dashboard = web_console_response(workspace=root, request_id="web-console-http", path="/")
            project = web_console_response(workspace=root, request_id="web-console-http", path="/api/project")
            artifact = web_console_response(
                workspace=root,
                request_id="web-console-http",
                path="/api/artifact?ref=state/run_status.json",
            )
            blocked = web_console_response(
                workspace=root,
                request_id="web-console-http",
                path="/api/artifact?ref=../outside.json",
            )

        project_payload = json.loads(project.body)
        artifact_payload = json.loads(artifact.body)
        self.assertEqual(dashboard.status, 200)
        self.assertEqual(project.status, 200)
        self.assertEqual(artifact.status, 200)
        self.assertIn("DeepResearch Project", dashboard.body)
        self.assertEqual(project_payload["request_id"], "web-console-http")
        self.assertEqual(project_payload["project"]["lifecycle"]["phase"], "accepted")
        self.assertEqual(artifact_payload["ref"], "state/run_status.json")
        self.assertEqual(blocked.status, 404)


if __name__ == "__main__":
    unittest.main()
