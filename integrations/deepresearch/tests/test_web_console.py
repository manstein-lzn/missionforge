from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import missionforge as mf
from missionforge_deepresearch.kernel_v2 import KernelV2FixtureAdapter, run_deepresearch_kernel_v2
from missionforge_deepresearch.product_contract import AcademicResearchRequest
from missionforge_deepresearch.frontdesk import FrontDeskFixtureAdapter
from missionforge_deepresearch.web_console import (
    WebFrontDeskConfig,
    WebKernelConfig,
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

    def test_frontdesk_message_post_requires_server_owned_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            response = web_console_response(
                workspace=root,
                request_id="web-frontdesk-unconfigured",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "研究 AI 编译器"}),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertEqual(payload["message"], "frontdesk_not_configured")

    def test_frontdesk_message_post_runs_frontdesk_turn_and_returns_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="intensive",
                live_extension_mode=False,
            )
            first = web_console_response(
                workspace=root,
                request_id="web-frontdesk-chat",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 AI 模型到 FPGA 的编译框架"}),
                frontdesk_config=config,
            )
            second = web_console_response(
                workspace=root,
                request_id="web-frontdesk-chat",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于工程选型，需要覆盖 MLIR、HLS 和开源实现。"}),
                frontdesk_config=config,
            )
            requirements_exists = (root / "runs/web-frontdesk-chat/frontdesk/research_requirements.md").is_file()

        first_payload = json.loads(first.body)
        second_payload = json.loads(second.body)
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(first_payload["status"], "needs_user_answer")
        self.assertEqual(second_payload["status"], "ready_for_approval")
        self.assertEqual(second_payload["snapshot"]["frontdesk"]["status"], "ready_for_approval")
        self.assertEqual(len(second_payload["snapshot"]["frontdesk_dialogue"]), 2)
        self.assertTrue(requirements_exists)

    def test_frontdesk_approve_post_requires_approval_ready_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            response = web_console_response(
                workspace=root,
                request_id="web-approve-not-ready",
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("frontdesk_control", payload["message"])

    def test_frontdesk_approve_post_approves_without_starting_research_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id="web-approve-ready",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 Deep Research 工具"}),
                frontdesk_config=config,
            )
            web_console_response(
                workspace=root,
                request_id="web-approve-ready",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于产品设计，需要比较成熟产品和开源实现。"}),
                frontdesk_config=config,
            )
            response = web_console_response(
                workspace=root,
                request_id="web-approve-ready",
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )
            research_request_exists = (root / "runs/web-approve-ready/frontdesk/research_request.json").is_file()
            kernel_report_exists = (root / "runs/web-approve-ready/reports/final_report.md").is_file()

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "approved")
        self.assertEqual(payload["research_request"]["request_id"], "web-approve-ready")
        self.assertTrue(research_request_exists)
        self.assertFalse(kernel_report_exists)

    def test_research_start_post_requires_server_owned_kernel_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            response = web_console_response(
                workspace=root,
                request_id="web-start-unconfigured",
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertEqual(payload["message"], "kernel_not_configured")

    def test_research_start_post_runs_kernel_in_background_task(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk_config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-ready",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 Deep Research 工具"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-ready",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于产品设计，需要比较成熟产品和开源实现。"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-ready",
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )
            response = web_console_response(
                workspace=root,
                request_id="web-start-ready",
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            task = json.loads(response.body)["task"]
            task_ref = root / "runs/web-start-ready/web/tasks/current_task.json"
            deadline = 100
            while deadline > 0:
                if task_ref.is_file():
                    task_payload = json.loads(task_ref.read_text(encoding="utf-8"))
                    if task_payload["status"] in {"completed", "failed"}:
                        break
                deadline -= 1
                time.sleep(0.01)
            final_task = json.loads(task_ref.read_text(encoding="utf-8"))
            report_exists = (root / "runs/web-start-ready/reports/final_report.md").is_file()
            task_api = web_console_response(
                workspace=root,
                request_id="web-start-ready",
                method="GET",
                path="/api/task",
            )

        self.assertEqual(response.status, 202)
        self.assertEqual(task["status"], "running")
        self.assertEqual(final_task["status"], "completed")
        self.assertTrue(report_exists)
        self.assertEqual(json.loads(task_api.body)["status"], "completed")

    def test_research_start_post_requires_explicit_frontdesk_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk_config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-unapproved",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 Deep Research 工具"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-unapproved",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于产品设计，需要比较成熟产品和开源实现。"}),
                frontdesk_config=frontdesk_config,
            )

            with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", Mock()) as run_mock:
                response = web_console_response(
                    workspace=root,
                    request_id="web-start-unapproved",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({"adapter_mode": "fixture"}),
                    kernel_config=kernel_config,
                )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("frontdesk/approval.json", payload["message"])
        run_mock.assert_not_called()

    def test_research_start_post_does_not_rerun_completed_task(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk_config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-once",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 Deep Research 工具"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-once",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于产品设计，需要比较成熟产品和开源实现。"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-once",
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )
            first = web_console_response(
                workspace=root,
                request_id="web-start-once",
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            task_ref = root / "runs/web-start-once/web/tasks/current_task.json"
            deadline = 100
            while deadline > 0:
                if task_ref.is_file():
                    task_payload = json.loads(task_ref.read_text(encoding="utf-8"))
                    if task_payload["status"] in {"completed", "failed"}:
                        break
                deadline -= 1
                time.sleep(0.01)
            completed_task = json.loads(task_ref.read_text(encoding="utf-8"))

            with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", Mock()) as run_mock:
                second = web_console_response(
                    workspace=root,
                    request_id="web-start-once",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({}),
                    kernel_config=kernel_config,
                )

        self.assertEqual(first.status, 202)
        self.assertEqual(second.status, 200)
        self.assertEqual(json.loads(second.body)["task"]["task_id"], completed_task["task_id"])
        run_mock.assert_not_called()

    def test_research_start_post_does_not_overwrite_existing_kernel_run(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-start-existing",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )

            with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", Mock()) as run_mock:
                response = web_console_response(
                    workspace=root,
                    request_id="web-start-existing",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({}),
                    kernel_config=kernel_config,
                )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["task"]["result_ref"], "packages/deepresearch_kernel_v2_result.json")
        run_mock.assert_not_called()

    def test_research_start_post_marks_orphan_running_task_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            task_ref = root / "runs/web-start-orphan/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-old",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-start-orphan",
                        "status": "running",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "",
                        "result_ref": "",
                        "error_summary": "",
                    }
                ),
                encoding="utf-8",
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )

            with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", Mock()) as run_mock:
                response = web_console_response(
                    workspace=root,
                    request_id="web-start-orphan",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({}),
                    kernel_config=kernel_config,
                )
                final_task = json.loads(task_ref.read_text(encoding="utf-8"))

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "interrupted")
        self.assertEqual(final_task["status"], "interrupted")
        run_mock.assert_not_called()

    def test_research_start_post_recovers_orphan_running_task_with_existing_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-start-orphan-complete",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            task_ref = root / "runs/web-start-orphan-complete/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-old",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-start-orphan-complete",
                        "status": "running",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "",
                        "result_ref": "",
                        "error_summary": "",
                    }
                ),
                encoding="utf-8",
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )

            with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", Mock()) as run_mock:
                response = web_console_response(
                    workspace=root,
                    request_id="web-start-orphan-complete",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({}),
                    kernel_config=kernel_config,
                )
                final_task = json.loads(task_ref.read_text(encoding="utf-8"))

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(final_task["result_ref"], "packages/deepresearch_kernel_v2_result.json")
        run_mock.assert_not_called()

    def test_task_api_sanitizes_malformed_and_extra_task_state(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            task_ref = root / "runs/web-task-sanitize/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text("{", encoding="utf-8")
            malformed = web_console_response(
                workspace=root,
                request_id="web-task-sanitize",
                method="GET",
                path="/api/task",
            )
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "task-1",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-task-sanitize",
                        "status": "running",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "",
                        "result_ref": "",
                        "error_summary": "",
                        "secret": "should-not-leak",
                    }
                ),
                encoding="utf-8",
            )
            sanitized = web_console_response(
                workspace=root,
                request_id="web-task-sanitize",
                method="GET",
                path="/api/task",
            )

        malformed_payload = json.loads(malformed.body)
        sanitized_payload = json.loads(sanitized.body)
        self.assertEqual(malformed.status, 200)
        self.assertEqual(malformed_payload["status"], "idle")
        self.assertEqual(sanitized_payload["status"], "running")
        self.assertNotIn("secret", sanitized_payload)

    def test_research_start_failure_state_does_not_include_secret_exception_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk_config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-failure",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 Deep Research 工具"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-failure",
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于产品设计，需要比较成熟产品和开源实现。"}),
                frontdesk_config=frontdesk_config,
            )
            web_console_response(
                workspace=root,
                request_id="web-start-failure",
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )
            task_ref = root / "runs/web-start-failure/web/tasks/current_task.json"

            with patch(
                "missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2",
                side_effect=RuntimeError("SECRET_TOKEN=abc123"),
            ):
                response = web_console_response(
                    workspace=root,
                    request_id="web-start-failure",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({}),
                    kernel_config=kernel_config,
                )
                deadline = 100
                while deadline > 0:
                    if task_ref.is_file():
                        task_payload = json.loads(task_ref.read_text(encoding="utf-8"))
                        if task_payload["status"] == "failed":
                            break
                    deadline -= 1
                    time.sleep(0.01)
                final_task = json.loads(task_ref.read_text(encoding="utf-8"))

        self.assertEqual(response.status, 202)
        self.assertEqual(final_task["status"], "failed")
        self.assertEqual(final_task["error_summary"], "RuntimeError: task failed")
        self.assertNotIn("SECRET_TOKEN", json.dumps(final_task))


if __name__ == "__main__":
    unittest.main()
