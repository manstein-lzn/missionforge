from __future__ import annotations

import base64
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import missionforge as mf
from missionforge_deepresearch.kernel_v2 import KernelV2FixtureAdapter, run_deepresearch_kernel_v2
from missionforge_deepresearch.product_contract import AcademicResearchRequest
from missionforge_deepresearch.research_requests import read_current_research_request
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
    def _approve_frontdesk_fixture(self, root: Path, request_id: str) -> None:
        frontdesk_config = WebFrontDeskConfig(
            adapter_factory=FrontDeskFixtureAdapter,
            research_intensity="standard",
            live_extension_mode=False,
        )
        web_console_response(
            workspace=root,
            request_id=request_id,
            method="POST",
            path="/api/frontdesk/message",
            body=json.dumps({"message": "我想调研 Deep Research 工具"}),
            frontdesk_config=frontdesk_config,
        )
        web_console_response(
            workspace=root,
            request_id=request_id,
            method="POST",
            path="/api/frontdesk/message",
            body=json.dumps({"message": "用于产品设计，需要比较成熟产品和开源实现。"}),
            frontdesk_config=frontdesk_config,
        )
        response = web_console_response(
            workspace=root,
            request_id=request_id,
            method="POST",
            path="/api/frontdesk/approve",
            body=json.dumps({}),
        )
        self.assertEqual(response.status, 200)

    def _wait_task_terminal(self, root: Path, request_id: str) -> dict[str, object]:
        task_ref = root / f"runs/{request_id}/web/tasks/current_task.json"
        deadline = 200
        while deadline > 0:
            if task_ref.is_file():
                task_payload = json.loads(task_ref.read_text(encoding="utf-8"))
                if task_payload.get("status") in {"completed", "failed", "interrupted"}:
                    return task_payload
            deadline -= 1
            time.sleep(0.01)
        self.fail(f"task did not reach a terminal state for {request_id}")

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
        self.assertTrue(any(group["group_kind"] == "project" for group in snapshot["progress_timeline_groups"]))
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

    def test_runtime_control_post_appends_interaction_events(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            pause = web_console_response(
                workspace=root,
                request_id="web-runtime-control",
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "pause"}),
            )
            revise = web_console_response(
                workspace=root,
                request_id="web-runtime-control",
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "revise", "text": "需要收紧到产品体验。"}),
            )
            message = web_console_response(
                workspace=root,
                request_id="web-runtime-control",
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "message", "text": "补充关注进度可观测性。"}),
            )
            event_log = root / "runs/web-runtime-control/interaction/user_events.jsonl"
            events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(pause.status, 202)
        self.assertEqual(revise.status, 202)
        self.assertEqual(message.status, 202)
        self.assertEqual(
            [event["kind"] for event in events],
            ["pause_request", "contract_revision_request", "message"],
        )
        self.assertEqual(events[0]["run_id"], "deepresearch-v2-web-runtime-control")
        self.assertEqual(events[0]["target"], "flow")
        self.assertEqual(json.loads(revise.body)["events_ref"], "interaction/user_events.jsonl")

    def test_runtime_control_requires_text_for_revision_and_message(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            revise = web_console_response(
                workspace=root,
                request_id="web-runtime-control-text",
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "revise"}),
            )
            message = web_console_response(
                workspace=root,
                request_id="web-runtime-control-text",
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "message"}),
            )

        self.assertEqual(revise.status, 409)
        self.assertEqual(message.status, 409)
        self.assertIn("revision text is required", json.loads(revise.body)["message"])
        self.assertIn("message text is required", json.loads(message.body)["message"])

    def test_runtime_controls_render_without_exposing_event_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            web_console_response(
                workspace=root,
                request_id="web-runtime-render",
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "message", "text": "SECRET_TOKEN=abc123"}),
            )
            snapshot = build_project_snapshot(root, "web-runtime-render")
            html = render_project_dashboard(snapshot)

        self.assertEqual(snapshot["runtime_events"][0]["kind"], "message")
        self.assertNotIn("text", snapshot["runtime_events"][0])
        self.assertIn("Runtime Controls", html)
        self.assertIn('data-runtime-action="pause"', html)
        self.assertIn('data-runtime-submit="revise"', html)
        self.assertNotIn("SECRET_TOKEN", html)

    def test_lifecycle_action_requires_frontdesk_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            response = web_console_response(
                workspace=root,
                request_id="web-lifecycle-unapproved",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry"}),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("frontdesk/approval.json", payload["message"])

    def test_lifecycle_action_records_retry_without_exposing_reason_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-lifecycle-retry")
            task_ref = root / "runs/web-lifecycle-retry/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-failed",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-lifecycle-retry",
                        "status": "failed",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "2026-01-01T00:00:01Z",
                        "result_ref": "",
                        "error_summary": "RuntimeError: task failed",
                        "lock_ref": "",
                    }
                ),
                encoding="utf-8",
            )
            response = web_console_response(
                workspace=root,
                request_id="web-lifecycle-retry",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry", "text": "SECRET_TOKEN=abc123"}),
            )
            snapshot = build_project_snapshot(root, "web-lifecycle-retry")
            action_ref = root / "runs/web-lifecycle-retry/project/lifecycle/latest_retry_request.json"
            action = json.loads(action_ref.read_text(encoding="utf-8"))
            action_index = root / "runs/web-lifecycle-retry/project/lifecycle_actions.jsonl"
            action_index_exists = action_index.is_file()

        payload = json.loads(response.body)
        self.assertEqual(response.status, 202)
        self.assertEqual(payload["status"], "pending_retry")
        self.assertEqual(action["status"], "pending_retry")
        self.assertEqual(action["source_task_ref"], "web/tasks/current_task.json")
        self.assertTrue(action["reason_ref"].startswith("project/lifecycle/action_text/retry-"))
        self.assertNotIn("SECRET_TOKEN", json.dumps(payload))
        self.assertNotIn("SECRET_TOKEN", json.dumps(snapshot["lifecycle_actions"]))
        self.assertTrue(action_index_exists)

    def test_lifecycle_action_records_revision_request_ref_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-lifecycle-revise")
            request = AcademicResearchRequest(
                request_id="web-lifecycle-revise",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            response = web_console_response(
                workspace=root,
                request_id="web-lifecycle-revise",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "revise", "text": "SECRET_TOKEN=abc123"}),
            )
            snapshot = build_project_snapshot(root, "web-lifecycle-revise")
            action = json.loads(
                (root / "runs/web-lifecycle-revise/project/lifecycle/latest_revise_request.json").read_text(
                    encoding="utf-8"
                )
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 202)
        self.assertEqual(payload["status"], "pending_revision")
        self.assertEqual(action["status"], "pending_revision")
        self.assertEqual(action["source_lifecycle_ref"], "project/lifecycle_state.json")
        self.assertTrue(action["reason_ref"].startswith("project/lifecycle/action_text/revise-"))
        self.assertIn("pending_revision", render_project_dashboard(snapshot))
        self.assertNotIn("SECRET_TOKEN", json.dumps(payload))

    def test_lifecycle_action_recovers_lock_and_then_allows_retry_request(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-lifecycle-recover-lock")
            run_root = root / "runs/web-lifecycle-recover-lock"
            task_ref = run_root / "web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-lifecycle-recover-lock",
                        "status": "running",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "",
                        "result_ref": "",
                        "error_summary": "",
                        "lock_ref": "web/locks/kernel_v2.lock",
                    }
                ),
                encoding="utf-8",
            )
            lock_dir = run_root / "web/locks/kernel_v2.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "lock.json").write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_lock.v1",
                        "lock_ref": "web/locks/kernel_v2.lock",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-lifecycle-recover-lock",
                        "owner_pid": "999999",
                        "owner_thread": "1",
                        "owner_host": "test-host",
                        "acquired_at": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            retry_while_locked = web_console_response(
                workspace=root,
                request_id="web-lifecycle-recover-lock",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry"}),
            )
            recover = web_console_response(
                workspace=root,
                request_id="web-lifecycle-recover-lock",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "recover_lock", "text": "operator approved"}),
            )
            recovered_task = json.loads(task_ref.read_text(encoding="utf-8"))
            lock_dir_exists_after_recovery = lock_dir.exists()
            retry = web_console_response(
                workspace=root,
                request_id="web-lifecycle-recover-lock",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry"}),
            )

        self.assertEqual(retry_while_locked.status, 409)
        self.assertIn("failed or interrupted", json.loads(retry_while_locked.body)["message"])
        self.assertEqual(recover.status, 202)
        self.assertEqual(json.loads(recover.body)["status"], "completed")
        self.assertFalse(lock_dir_exists_after_recovery)
        self.assertEqual(recovered_task["status"], "interrupted")
        self.assertEqual(retry.status, 202)
        self.assertEqual(json.loads(retry.body)["status"], "pending_retry")

    def test_lifecycle_action_does_not_record_revision_while_task_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-lifecycle-revise-locked")
            request = AcademicResearchRequest(
                request_id="web-lifecycle-revise-locked",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            run_root = root / "runs/web-lifecycle-revise-locked"
            task_ref = run_root / "web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-lifecycle-revise-locked",
                        "status": "failed",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "2026-01-01T00:00:01Z",
                        "result_ref": "",
                        "error_summary": "RuntimeError: task failed",
                        "lock_ref": "",
                    }
                ),
                encoding="utf-8",
            )
            lock_dir = run_root / "web/locks/kernel_v2.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "lock.json").write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_lock.v1",
                        "lock_ref": "web/locks/kernel_v2.lock",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-lifecycle-revise-locked",
                        "owner_pid": "999999",
                        "owner_thread": "1",
                        "owner_host": "test-host",
                        "acquired_at": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            response = web_console_response(
                workspace=root,
                request_id="web-lifecycle-revise-locked",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "revise", "text": "需要调整研究范围"}),
            )
            revise_ref = run_root / "project/lifecycle/latest_revise_request.json"

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("active web task", payload["message"])
        self.assertFalse(revise_ref.exists())

    def test_progress_timeline_projects_completed_flow_ledger_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-timeline-flow",
                topic="compiler autotuning survey",
            )
            run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )

            snapshot = build_project_snapshot(root, "web-timeline-flow")
            html = render_project_dashboard(snapshot)

        timeline = snapshot["progress_timeline"]
        self.assertTrue(any(row["source"] == "flow_ledger" and row["stage"] == "source_mapper" for row in timeline))
        self.assertTrue(any(row["source"] == "flow_ledger" and row["stage"] == "judge" for row in timeline))
        self.assertTrue(any(row["source"] == "step_record" and row["state"] == "completed" for row in timeline))
        self.assertTrue(all("source_kind" in row and "source_ref" in row for row in timeline))
        self.assertIn("Progress Timeline", html)
        self.assertIn("flow_ledger", html)

    def test_progress_timeline_degrades_when_flow_ledger_or_step_record_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = AcademicResearchRequest(
                request_id="web-timeline-missing-ledger",
                topic="compiler autotuning survey",
            )
            result = run_deepresearch_kernel_v2(
                request,
                workspace=root,
                adapter=KernelV2FixtureAdapter(),
            )
            run_root = root / result.run_workspace_ref
            flow_result = json.loads((root / result.flow_result_ref).read_text(encoding="utf-8"))
            ledger_ref = flow_result["ledger_refs"][0]
            missing_step_ref = flow_result["step_record_refs"][0]
            (run_root / ledger_ref).unlink()
            (run_root / missing_step_ref).unlink()

            snapshot = build_project_snapshot(root, "web-timeline-missing-ledger")

        timeline = snapshot["progress_timeline"]
        self.assertFalse(any(row["source"] == "flow_ledger" for row in timeline))
        self.assertTrue(
            any(
                row["source"] == "step_record"
                and row["source_ref"] == missing_step_ref
                and row["stage"] == "step"
                for row in timeline
            )
        )

    def test_progress_timeline_does_not_expose_runtime_or_lifecycle_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-timeline-redaction"
            self._approve_frontdesk_fixture(root, request_id)
            task_ref = root / f"runs/{request_id}/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-failed",
                        "task_kind": "kernel_v2_run",
                        "request_id": request_id,
                        "status": "failed",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "2026-01-01T00:00:01Z",
                        "result_ref": "",
                        "error_summary": "RuntimeError: task failed",
                        "lock_ref": "",
                    }
                ),
                encoding="utf-8",
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/runtime/control",
                body=json.dumps({"action": "message", "text": "SECRET_TOKEN=runtime"}),
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry", "text": "SECRET_TOKEN=lifecycle"}),
            )

            snapshot = build_project_snapshot(root, request_id)
            html = render_project_dashboard(snapshot)

        timeline_json = json.dumps(snapshot["progress_timeline"])
        self.assertIn("runtime_control", timeline_json)
        self.assertIn("lifecycle_action", timeline_json)
        self.assertNotIn("SECRET_TOKEN", timeline_json)
        self.assertNotIn("SECRET_TOKEN", html)

    def test_web_research_start_records_sanitized_live_progress_timeline(self) -> None:
        class ProgressFixtureAdapter(KernelV2FixtureAdapter):
            def run_call(self, call, *, runtime_progress_sink=None, **kwargs):
                if runtime_progress_sink is not None:
                    runtime_progress_sink(
                        {
                            "stage": str(call.metadata.get("kernel_step_id", "")),
                            "message": "SECRET_TOKEN=progress",
                            "detail": "SECRET_TOKEN=detail",
                        }
                    )
                return super().run_call(call, runtime_progress_sink=runtime_progress_sink, **kwargs)

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-timeline-live"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: ProgressFixtureAdapter(),
                live_extension_mode=False,
            )
            response = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            self._wait_task_terminal(root, request_id)
            timeline_ref = root / f"runs/{request_id}/web/progress_timeline.jsonl"
            timeline_exists = timeline_ref.is_file()
            timeline_text = timeline_ref.read_text(encoding="utf-8")
            snapshot = build_project_snapshot(root, request_id)

        self.assertEqual(response.status, 202)
        self.assertTrue(timeline_exists)
        self.assertIn("Runtime progress update", timeline_text)
        self.assertIn("flow_ledger", timeline_text)
        self.assertNotIn("SECRET_TOKEN", timeline_text)
        self.assertTrue(any(row["source"] == "runtime_progress" or row["source"] == "kernel_v2" for row in snapshot["progress_timeline"]))

    def test_lifecycle_action_does_not_recover_live_process_lock(self) -> None:
        from missionforge_deepresearch.web_tasks import start_background_task

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-lifecycle-live-lock")
            release = threading.Event()

            def runner() -> object:
                release.wait(5)
                return object()

            task = start_background_task(
                workspace=root,
                request_id="web-lifecycle-live-lock",
                task_kind="kernel_v2_run",
                runner=runner,
            )
            try:
                response = web_console_response(
                    workspace=root,
                    request_id="web-lifecycle-live-lock",
                    method="POST",
                    path="/api/lifecycle/action",
                    body=json.dumps({"action": "recover_lock", "text": "operator approved"}),
                )
                task_during_response = web_console_response(
                    workspace=root,
                    request_id="web-lifecycle-live-lock",
                    method="GET",
                    path="/api/task",
                )
            finally:
                release.set()
                task_ref = root / "runs/web-lifecycle-live-lock/web/tasks/current_task.json"
                deadline = 100
                while deadline > 0:
                    if task_ref.is_file():
                        task_payload = json.loads(task_ref.read_text(encoding="utf-8"))
                        if task_payload["status"] in {"completed", "failed"}:
                            break
                    deadline -= 1
                    time.sleep(0.01)

        payload = json.loads(response.body)
        task_during = json.loads(task_during_response.body)
        self.assertEqual(task["status"], "running")
        self.assertEqual(response.status, 409)
        self.assertIn("live task", payload["message"])
        self.assertEqual(task_during["status"], "running")
        self.assertEqual(task_during["lock_ref"], "web/locks/kernel_v2.lock")

    def test_lifecycle_action_does_not_recover_missing_lock_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-lifecycle-missing-lock")
            task_ref = root / "runs/web-lifecycle-missing-lock/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-lifecycle-missing-lock",
                        "status": "running",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "",
                        "result_ref": "",
                        "error_summary": "",
                        "lock_ref": "web/locks/kernel_v2.lock",
                    }
                ),
                encoding="utf-8",
            )
            response = web_console_response(
                workspace=root,
                request_id="web-lifecycle-missing-lock",
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "recover_lock", "text": "operator approved"}),
            )
            recovery_ref = root / "runs/web-lifecycle-missing-lock/project/lifecycle/latest_lock_recovery_request.json"

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("existing lock", payload["message"])
        self.assertFalse(recovery_ref.exists())

    def test_research_attempt_start_requires_pending_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-attempt-no-retry")
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            response = web_console_response(
                workspace=root,
                request_id="web-attempt-no-retry",
                method="POST",
                path="/api/research/attempt/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            attempt_index_exists = (root / "runs/web-attempt-no-retry/project/attempt_index.json").exists()

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("pending retry request", payload["message"])
        self.assertFalse(attempt_index_exists)

    def test_research_attempt_start_consumes_retry_and_snapshots_previous_outputs(self) -> None:
        class ProgressAttemptFixtureAdapter(KernelV2FixtureAdapter):
            def run_call(self, call, *, runtime_progress_sink=None, **kwargs):
                if runtime_progress_sink is not None:
                    runtime_progress_sink(
                        {
                            "stage": str(call.metadata.get("kernel_step_id", "")),
                            "message": "SECRET_TOKEN=attempt-progress",
                        }
                    )
                return super().run_call(call, runtime_progress_sink=runtime_progress_sink, **kwargs)

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-attempt-retry"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: ProgressAttemptFixtureAdapter(),
                live_extension_mode=False,
            )
            first = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            first_task = self._wait_task_terminal(root, request_id)
            run_root = root / f"runs/{request_id}"
            report_ref = run_root / "reports/final_report.md"
            report_ref.write_text("OLD REPORT MARKER\n", encoding="utf-8")
            task_ref = run_root / "web/tasks/current_task.json"
            failed_task = dict(first_task)
            failed_task.update(
                {
                    "task_id": "kernel_v2_run-failed-for-retry",
                    "task_kind": "kernel_v2_run",
                    "status": "failed",
                    "finished_at": "2026-01-01T00:00:01Z",
                    "result_ref": "",
                    "error_summary": "RuntimeError: task failed",
                    "lock_ref": "",
                }
            )
            task_ref.write_text(json.dumps(failed_task), encoding="utf-8")
            retry = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry", "text": "SECRET_TOKEN=abc123"}),
            )
            attempt_start = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/attempt/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            final_task = self._wait_task_terminal(root, request_id)
            retry_action = json.loads((run_root / "project/lifecycle/latest_retry_request.json").read_text(encoding="utf-8"))
            attempt_index = json.loads((run_root / "project/attempt_index.json").read_text(encoding="utf-8"))
            attempt_ref = attempt_index["latest_attempt_ref"]
            attempt = json.loads((run_root / attempt_ref).read_text(encoding="utf-8"))
            output_manifest = json.loads((run_root / attempt["output_manifest_ref"]).read_text(encoding="utf-8"))
            current_outputs = json.loads((run_root / "project/current_output_pointer.json").read_text(encoding="utf-8"))
            projected_output_ref = next(
                item["output_ref"]
                for item in output_manifest["entries"]
                if item["source_ref"] == "reports/final_report.citation_projected.md"
            )
            projected_source_packet_ref = next(
                item["output_ref"]
                for item in output_manifest["entries"]
                if item["source_ref"] == "sources/source_packet.json"
            )
            projected_canonical_sources_ref = next(
                item["output_ref"]
                for item in output_manifest["entries"]
                if item["source_ref"] == "sources/canonical_sources.json"
            )
            (run_root / "reports/final_report.citation_projected.md").write_text(
                "CORRUPTED STABLE REPORT\n",
                encoding="utf-8",
            )
            (run_root / projected_source_packet_ref).unlink()
            (run_root / projected_canonical_sources_ref).unlink()
            before_snapshot = json.loads((run_root / attempt["before_snapshot_ref"]).read_text(encoding="utf-8"))
            report_snapshot_ref = next(
                item["snapshot_ref"]
                for item in before_snapshot["entries"]
                if item["source_ref"] == "reports/final_report.md"
            )
            report_snapshot_text = (run_root / report_snapshot_ref).read_text(encoding="utf-8")
            snapshot = build_project_snapshot(root, request_id)
            html = render_project_dashboard(snapshot)

        retry_payload = json.loads(retry.body)
        attempt_payload = json.loads(attempt_start.body)
        self.assertEqual(first.status, 202)
        self.assertEqual(retry.status, 202)
        self.assertEqual(attempt_start.status, 202)
        self.assertEqual(retry_payload["status"], "pending_retry")
        self.assertEqual(attempt_payload["status"], "running")
        self.assertEqual(final_task["status"], "completed")
        self.assertEqual(retry_action["status"], "consumed")
        self.assertEqual(retry_action["consumed_by_attempt_ref"], attempt_ref)
        self.assertEqual(attempt["kind"], "retry_attempt")
        self.assertEqual(attempt["status"], "completed")
        self.assertEqual(attempt["base_contract_ref"], "contract/task_contract.json")
        self.assertTrue(attempt["base_contract_hash"].startswith("sha256:"))
        self.assertEqual(attempt["parent_web_task_ref"], "web/tasks/current_task.json")
        self.assertEqual(attempt["source_retry_request_ref"], "project/lifecycle/latest_retry_request.json")
        self.assertEqual(attempt["reason_ref"], retry_action["reason_ref"])
        self.assertEqual(attempt["output_manifest_ref"], current_outputs["output_manifest_ref"])
        self.assertEqual(current_outputs["attempt_ref"], attempt_ref)
        self.assertEqual(snapshot["project"]["current_outputs"]["output_manifest_ref"], attempt["output_manifest_ref"])
        self.assertEqual(snapshot["report_preview"]["ref"], projected_output_ref)
        self.assertIn("Kernel v2 DeepResearch Fixture Report", snapshot["report_preview"]["markdown"])
        self.assertNotIn("CORRUPTED STABLE REPORT", snapshot["report_preview"]["markdown"])
        self.assertEqual(snapshot["source_summary"]["source_records"], 0)
        self.assertEqual(snapshot["source_summary"]["canonical_sources"], 0)
        self.assertIn("OLD REPORT MARKER", report_snapshot_text)
        self.assertEqual(snapshot["project"]["attempt_index"]["attempt_count"], 1)
        current_groups = [
            group
            for group in snapshot["progress_timeline_groups"]
            if group["group_kind"] == "attempt" and group["is_current_output"]
        ]
        self.assertEqual(len(current_groups), 1)
        self.assertEqual(current_groups[0]["attempt_ref"], attempt_ref)
        self.assertEqual(current_groups[0]["output_manifest_ref"], attempt["output_manifest_ref"])
        self.assertTrue(any(row["source"] == "attempt" for row in current_groups[0]["rows"]))
        self.assertTrue(any(row["source"] == "flow_ledger" for row in current_groups[0]["rows"]))
        self.assertTrue(
            any(
                row["source"] == "retry_attempt" and row["source_kind"] == "runtime_progress"
                for row in current_groups[0]["rows"]
            )
        )
        self.assertIn("Start Retry Attempt", html)
        self.assertIn("current output", html)
        self.assertIn(attempt["output_manifest_ref"], html)
        self.assertIn("data-attempt-start=\"retry\"", html)
        self.assertNotIn("SECRET_TOKEN", json.dumps(attempt_payload))
        self.assertNotIn("SECRET_TOKEN", json.dumps(snapshot["lifecycle_actions"]))
        self.assertNotIn("SECRET_TOKEN", json.dumps(snapshot["progress_timeline_groups"]))

    def test_research_attempt_start_is_idempotent_for_consumed_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-attempt-idempotent"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            first_task = self._wait_task_terminal(root, request_id)
            run_root = root / f"runs/{request_id}"
            failed_task = dict(first_task)
            failed_task.update({"status": "failed", "result_ref": "", "error_summary": "RuntimeError: task failed"})
            (run_root / "web/tasks/current_task.json").write_text(json.dumps(failed_task), encoding="utf-8")
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry"}),
            )
            first_attempt = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/attempt/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            self._wait_task_terminal(root, request_id)
            second_attempt = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/attempt/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            attempt_index = json.loads((run_root / "project/attempt_index.json").read_text(encoding="utf-8"))

        first_payload = json.loads(first_attempt.body)
        second_payload = json.loads(second_attempt.body)
        first_attempt_ref = first_payload["action"]["consumed_by_attempt_ref"]
        second_attempt_ref = second_payload["action"]["consumed_by_attempt_ref"]
        self.assertEqual(first_attempt.status, 202)
        self.assertEqual(second_attempt.status, 200)
        self.assertEqual(first_attempt_ref, second_attempt_ref)
        self.assertEqual(attempt_index["latest_attempt_ref"], first_attempt_ref)
        self.assertEqual(len(attempt_index["attempts"]), 1)

    def test_research_attempt_start_rejects_pending_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-attempt-pending-revision"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            self._wait_task_terminal(root, request_id)
            task_ref = root / f"runs/{request_id}/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-failed",
                        "task_kind": "kernel_v2_run",
                        "request_id": request_id,
                        "status": "failed",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "2026-01-01T00:00:01Z",
                        "result_ref": "",
                        "error_summary": "RuntimeError: task failed",
                        "lock_ref": "",
                    }
                ),
                encoding="utf-8",
            )
            retry = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry"}),
            )
            revise = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "revise", "text": "需要调整研究范围"}),
            )
            attempt = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/attempt/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            retry_action = json.loads(
                (root / f"runs/{request_id}/project/lifecycle/latest_retry_request.json").read_text(encoding="utf-8")
            )
            attempt_index_exists = (root / f"runs/{request_id}/project/attempt_index.json").exists()

        payload = json.loads(attempt.body)
        self.assertEqual(retry.status, 202)
        self.assertEqual(revise.status, 202)
        self.assertEqual(attempt.status, 409)
        self.assertIn("pending revision", payload["message"])
        self.assertEqual(retry_action["status"], "pending_retry")
        self.assertFalse(attempt_index_exists)

    def test_research_revision_start_requires_pending_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-revision-no-request"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            response = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/revision/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            revision_index_exists = (root / f"runs/{request_id}/project/revision_index.json").exists()

        payload = json.loads(response.body)
        self.assertEqual(response.status, 409)
        self.assertIn("pending revision request", payload["message"])
        self.assertFalse(revision_index_exists)

    def test_research_revision_start_consumes_revision_and_freezes_revised_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-revision-start"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            self._wait_task_terminal(root, request_id)
            run_root = root / f"runs/{request_id}"
            approval_before = (run_root / "frontdesk/approval.json").read_text(encoding="utf-8")
            old_contract = json.loads((run_root / "contract/task_contract.json").read_text(encoding="utf-8"))
            old_contract_hash = mf.stable_json_hash(old_contract)
            revise = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "revise", "text": "SECRET_TOKEN=abc123 需要把范围调整到 UI 生命周期控制。"}),
            )
            revision_start = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/revision/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            final_task = self._wait_task_terminal(root, request_id)
            second_revision_start = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/revision/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            revise_action = json.loads((run_root / "project/lifecycle/latest_revise_request.json").read_text(encoding="utf-8"))
            revision_index = json.loads((run_root / "project/revision_index.json").read_text(encoding="utf-8"))
            attempt_index = json.loads((run_root / "project/attempt_index.json").read_text(encoding="utf-8"))
            revision_ref = revision_index["latest_revision_ref"]
            attempt_ref = attempt_index["latest_attempt_ref"]
            revision = json.loads((run_root / revision_ref).read_text(encoding="utf-8"))
            attempt = json.loads((run_root / attempt_ref).read_text(encoding="utf-8"))
            revised_request = json.loads((run_root / revision["revised_request_ref"]).read_text(encoding="utf-8"))
            kernel_request = json.loads((run_root / "product_contract/research_request.json").read_text(encoding="utf-8"))
            new_contract = json.loads((run_root / "contract/task_contract.json").read_text(encoding="utf-8"))
            contract_revision_input = json.loads((run_root / "inputs/contract_revision_index.json").read_text(encoding="utf-8"))
            staged_directive_ref = next(
                item["staged_ref"]
                for item in contract_revision_input["entries"]
                if item["contract_revision_ref"].endswith("/revision_directive.md")
            )
            staged_directive_text = (run_root / staged_directive_ref).read_text(encoding="utf-8")
            lifecycle = json.loads((run_root / "project/lifecycle_state.json").read_text(encoding="utf-8"))
            approval_after = (run_root / "frontdesk/approval.json").read_text(encoding="utf-8")
            snapshot = build_project_snapshot(root, request_id)
            html = render_project_dashboard(snapshot)

        revise_payload = json.loads(revise.body)
        start_payload = json.loads(revision_start.body)
        second_start_payload = json.loads(second_revision_start.body)
        self.assertEqual(revise.status, 202)
        self.assertEqual(revision_start.status, 202)
        self.assertEqual(second_revision_start.status, 200)
        self.assertEqual(revise_payload["status"], "pending_revision")
        self.assertEqual(start_payload["status"], "running")
        self.assertEqual(second_start_payload["action"]["consumed_by_revision_ref"], revision_ref)
        self.assertEqual(second_start_payload["action"]["consumed_by_attempt_ref"], attempt_ref)
        self.assertEqual(final_task["status"], "completed")
        self.assertEqual(revise_action["status"], "consumed")
        self.assertEqual(revise_action["consumed_by_revision_ref"], revision_ref)
        self.assertEqual(revise_action["consumed_by_attempt_ref"], attempt_ref)
        self.assertEqual(revision["status"], "completed")
        self.assertEqual(revision["attempt_ref"], attempt_ref)
        self.assertEqual(attempt["kind"], "revision_attempt")
        self.assertEqual(attempt["status"], "completed")
        self.assertEqual(attempt["revision_record_ref"], revision_ref)
        self.assertEqual(revised_request["contract_revision_refs"], kernel_request["contract_revision_refs"])
        self.assertIn(f"runs/{request_id}/{revision_ref}", revised_request["contract_revision_refs"])
        self.assertIn(f"runs/{request_id}/{revision['directive_ref']}", revised_request["contract_revision_refs"])
        self.assertIn("SECRET_TOKEN=abc123", staged_directive_text)
        self.assertNotEqual(old_contract_hash, mf.stable_json_hash(new_contract))
        self.assertEqual(lifecycle["current_revision_ref"], revision_ref)
        self.assertEqual(snapshot["project"]["revision_index"]["revision_count"], 1)
        self.assertEqual(len(revision_index["revisions"]), 1)
        self.assertTrue(any(row["source"] == "contract_revision" for row in snapshot["progress_timeline"]))
        self.assertIn("Start Revision Attempt", html)
        self.assertEqual(approval_before, approval_after)
        self.assertNotIn("SECRET_TOKEN", json.dumps(start_payload))
        self.assertNotIn("SECRET_TOKEN", json.dumps(snapshot["lifecycle_actions"]))
        self.assertNotIn("SECRET_TOKEN", json.dumps(snapshot["progress_timeline"]))

    def test_failed_revision_attempt_keeps_revised_request_as_current_authority(self) -> None:
        class FailingRevisionAdapter(KernelV2FixtureAdapter):
            def run_call(self, call, **kwargs):
                if str(call.metadata.get("kernel_step_id", "")) == "source_mapper":
                    raise RuntimeError("revision provider failed")
                return super().run_call(call, **kwargs)

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-revision-failed-current"
            self._approve_frontdesk_fixture(root, request_id)
            ok_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            failing_config = WebKernelConfig(
                adapter_factory=lambda _intensity: FailingRevisionAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=ok_config,
            )
            self._wait_task_terminal(root, request_id)
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "revise", "text": "失败后也必须保留冻结后的修订合同。"}),
            )
            revision_start = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/revision/start",
                body=json.dumps({}),
                kernel_config=failing_config,
            )
            final_task = self._wait_task_terminal(root, request_id)
            run_root = root / f"runs/{request_id}"
            revision_index = json.loads((run_root / "project/revision_index.json").read_text(encoding="utf-8"))
            revision_ref = revision_index["latest_revision_ref"]
            revision = json.loads((run_root / revision_ref).read_text(encoding="utf-8"))
            lifecycle = json.loads((run_root / "project/lifecycle_state.json").read_text(encoding="utf-8"))
            current_request = read_current_research_request(workspace=root, request_id=request_id)

        self.assertEqual(revision_start.status, 202)
        self.assertEqual(final_task["status"], "failed")
        self.assertEqual(revision["status"], "failed")
        self.assertEqual(lifecycle["current_revision_ref"], revision_ref)
        self.assertIn(f"runs/{request_id}/{revision_ref}", current_request.contract_revision_refs)
        self.assertIn(f"runs/{request_id}/{revision['directive_ref']}", current_request.contract_revision_refs)

    def test_retry_after_completed_revision_preserves_current_revision_lifecycle_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-revision-then-retry"
            self._approve_frontdesk_fixture(root, request_id)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            self._wait_task_terminal(root, request_id)
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "revise", "text": "把研究范围修订到 lifecycle retry 后仍保持合同权威。"}),
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/revision/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            revision_task = self._wait_task_terminal(root, request_id)
            run_root = root / f"runs/{request_id}"
            revision_index = json.loads((run_root / "project/revision_index.json").read_text(encoding="utf-8"))
            revision_ref = revision_index["latest_revision_ref"]
            failed_task = dict(revision_task)
            failed_task.update({"status": "failed", "result_ref": "", "error_summary": "RuntimeError: task failed"})
            (run_root / "web/tasks/current_task.json").write_text(json.dumps(failed_task), encoding="utf-8")
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/lifecycle/action",
                body=json.dumps({"action": "retry"}),
            )
            retry_start = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/attempt/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            retry_task = self._wait_task_terminal(root, request_id)
            lifecycle = json.loads((run_root / "project/lifecycle_state.json").read_text(encoding="utf-8"))
            current_request = read_current_research_request(workspace=root, request_id=request_id)

        self.assertEqual(retry_start.status, 202)
        self.assertEqual(retry_task["status"], "completed")
        self.assertEqual(lifecycle["current_revision_ref"], revision_ref)
        self.assertIn(f"runs/{request_id}/{revision_ref}", current_request.contract_revision_refs)

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
                body=json.dumps({"message": "我想调研 AI 模型到 FPGA 的编译框架 SECRET_TOKEN=frontdesk"}),
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
            snapshot = build_project_snapshot(root, "web-frontdesk-chat")
            html = render_project_dashboard(snapshot)

        first_payload = json.loads(first.body)
        second_payload = json.loads(second.body)
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 200)
        self.assertEqual(first_payload["status"], "needs_user_answer")
        self.assertEqual(second_payload["status"], "ready_for_approval")
        self.assertEqual(second_payload["snapshot"]["frontdesk"]["status"], "ready_for_approval")
        self.assertEqual(len(second_payload["snapshot"]["frontdesk_dialogue"]), 2)
        self.assertNotIn("AI 模型到 FPGA", json.dumps(second_payload["snapshot"], ensure_ascii=False))
        self.assertNotIn("SECRET_TOKEN", json.dumps(second_payload["snapshot"], ensure_ascii=False))
        self.assertNotIn("AI 模型到 FPGA", html)
        self.assertNotIn("SECRET_TOKEN", html)
        self.assertTrue(all("content" not in row for row in second_payload["snapshot"]["frontdesk_dialogue"]))
        self.assertEqual(snapshot["frontdesk_dialogue"][0]["dialogue_ref"], "frontdesk/dialogue.jsonl")
        self.assertTrue(requirements_exists)

    def test_seed_paper_post_updates_preapproval_request_without_snapshot_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-seed-paper"
            config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 seed paper support"}),
                frontdesk_config=config,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于论文综述。"}),
                frontdesk_config=config,
            )
            seed = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/seeds/papers",
                body=json.dumps({"kind": "doi", "value": "10.1145/1234567.1234568", "note": "SECRET_TOKEN=seed"}),
            )
            approve = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )
            snapshot = build_project_snapshot(root, request_id)
            html = render_project_dashboard(snapshot)

        seed_payload = json.loads(seed.body)
        approve_payload = json.loads(approve.body)
        self.assertEqual(seed.status, 202)
        self.assertEqual(seed_payload["seed_paper_count"], 1)
        self.assertEqual(seed_payload["snapshot"]["seeds"]["seed_paper_count"], 1)
        self.assertNotIn("10.1145/1234567.1234568", json.dumps(seed_payload["snapshot"]))
        self.assertNotIn("SECRET_TOKEN", json.dumps(seed_payload["snapshot"]))
        self.assertEqual(approve.status, 200)
        self.assertEqual(approve_payload["research_request"]["seed_papers"][0]["kind"], "doi")
        self.assertEqual(approve_payload["research_request"]["seed_papers"][0]["value"], "10.1145/1234567.1234568")
        self.assertEqual(snapshot["seeds"]["seed_paper_count"], 1)
        self.assertIn("Seed Inputs", html)
        self.assertNotIn("10.1145/1234567.1234568", html)
        self.assertNotIn("SECRET_TOKEN", html)

    def test_seed_pdf_upload_updates_request_and_kernel_seed_index(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-seed-pdf"
            config = WebFrontDeskConfig(
                adapter_factory=FrontDeskFixtureAdapter,
                research_intensity="standard",
                live_extension_mode=False,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "我想调研 PDF seed support"}),
                frontdesk_config=config,
            )
            web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/frontdesk/message",
                body=json.dumps({"message": "用于论文综述。"}),
                frontdesk_config=config,
            )
            pdf_body = base64.b64encode(b"%PDF-1.4\nfixture seed\n").decode("ascii")
            seed = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/seeds/pdfs",
                body=json.dumps({"filename": "seed paper.pdf", "content_base64": pdf_body}),
            )
            approve = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/frontdesk/approve",
                body=json.dumps({}),
            )
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            start = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            self._wait_task_terminal(root, request_id)
            run_root = root / f"runs/{request_id}"
            seed_payload = json.loads(seed.body)
            approve_payload = json.loads(approve.body)
            seed_pdf_ref = seed_payload["seed_pdf_ref"]
            pdf_exists = (run_root / seed_pdf_ref).is_file()
            seed_pdf_index = json.loads((run_root / "inputs/seed_pdf_index.json").read_text(encoding="utf-8"))
            seed_packet = json.loads((run_root / "sources/seed_source_packet.json").read_text(encoding="utf-8"))
            snapshot = build_project_snapshot(root, request_id)
            html = render_project_dashboard(snapshot)

        self.assertEqual(seed.status, 202)
        self.assertEqual(approve.status, 200)
        self.assertEqual(start.status, 202)
        self.assertTrue(pdf_exists)
        self.assertEqual(seed_pdf_ref, "inputs/seeds/001-seed-paper.pdf")
        self.assertEqual(approve_payload["research_request"]["seed_pdf_refs"], [seed_pdf_ref])
        self.assertTrue(seed_pdf_index["entries"][0]["available"])
        self.assertEqual(seed_pdf_index["entries"][0]["original_ref"], seed_pdf_ref)
        self.assertEqual(seed_packet["schema_version"], "missionforge_deepresearch.seed_source_packet.v1")
        self.assertEqual(snapshot["seeds"]["seed_pdf_count"], 1)
        self.assertIn(seed_pdf_ref, snapshot["seeds"]["seed_pdf_refs"])
        self.assertIn("/artifact?ref=inputs/seeds/001-seed-paper.pdf", html)
        self.assertNotIn("fixture seed", json.dumps(snapshot))

    def test_seed_upload_rejects_unsafe_pdf_and_postapproval_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-seed-rejects"
            self._approve_frontdesk_fixture(root, request_id)
            after_approval = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/seeds/papers",
                body=json.dumps({"kind": "doi", "value": "10.1145/1234567.1234568"}),
            )

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request_id = "web-seed-unsafe-pdf"
            unsafe_name = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/seeds/pdfs",
                body=json.dumps({
                    "filename": "../paper.pdf",
                    "content_base64": base64.b64encode(b"%PDF-1.4\n").decode("ascii"),
                }),
            )
            bad_content = web_console_response(
                workspace=root,
                request_id=request_id,
                method="POST",
                path="/api/seeds/pdfs",
                body=json.dumps({
                    "filename": "paper.pdf",
                    "content_base64": base64.b64encode(b"not a pdf").decode("ascii"),
                }),
            )

        self.assertEqual(after_approval.status, 409)
        self.assertIn("explicit revision", json.loads(after_approval.body)["message"])
        self.assertEqual(unsafe_name.status, 409)
        self.assertIn("path separators", json.loads(unsafe_name.body)["message"])
        self.assertEqual(bad_content.status, 409)
        self.assertIn("must be a PDF", json.loads(bad_content.body)["message"])

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
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            self._approve_frontdesk_fixture(root, "web-start-ready")
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
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            self._approve_frontdesk_fixture(root, "web-start-once")
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
            self._approve_frontdesk_fixture(root, "web-start-existing")
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
            self._approve_frontdesk_fixture(root, "web-start-orphan")
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
            self._approve_frontdesk_fixture(root, "web-start-orphan-complete")
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

    def test_task_api_reports_lock_without_exposing_lock_owner_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_root = root / "runs/web-task-lock-sanitize"
            lock_dir = run_root / "web/locks/kernel_v2.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "lock.json").write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_lock.v1",
                        "lock_ref": "web/locks/kernel_v2.lock",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-task-lock-sanitize",
                        "owner_pid": "999999",
                        "owner_thread": "1",
                        "owner_host": "test-host",
                        "acquired_at": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            response = web_console_response(
                workspace=root,
                request_id="web-task-lock-sanitize",
                method="GET",
                path="/api/task",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "locked")
        self.assertEqual(payload["lock_ref"], "web/locks/kernel_v2.lock")
        self.assertNotIn("owner_pid", payload)
        self.assertNotIn("owner_host", payload)

    def test_task_api_does_not_trust_locked_state_without_lock_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            task_ref = root / "runs/web-task-stale-lock/web/tasks/current_task.json"
            task_ref.parent.mkdir(parents=True, exist_ok=True)
            task_ref.write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_state.v1",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-task-stale-lock",
                        "status": "locked",
                        "started_at": "2026-01-01T00:00:00Z",
                        "finished_at": "",
                        "result_ref": "",
                        "error_summary": "run lock is held by another process",
                        "lock_ref": "web/locks/kernel_v2.lock",
                    }
                ),
                encoding="utf-8",
            )

            response = web_console_response(
                workspace=root,
                request_id="web-task-stale-lock",
                method="GET",
                path="/api/task",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "idle")

    def test_task_api_does_not_project_malformed_lock_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_root = root / "runs/web-task-malformed-lock"
            lock_dir = run_root / "web/locks/kernel_v2.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "lock.json").write_text(
                json.dumps(
                    {
                        "schema_version": "wrong",
                        "lock_ref": "web/locks/kernel_v2.lock",
                        "task_id": "SECRET_TASK",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-task-malformed-lock",
                        "acquired_at": "2026-01-01T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            response = web_console_response(
                workspace=root,
                request_id="web-task-malformed-lock",
                method="GET",
                path="/api/task",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "locked")
        self.assertEqual(payload["task_id"], "kernel_v2_run-locked")
        self.assertNotIn("SECRET_TASK", json.dumps(payload))

    def test_research_start_failure_state_does_not_include_secret_exception_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            self._approve_frontdesk_fixture(root, "web-start-failure")
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

    def test_research_start_post_respects_existing_cross_process_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-start-locked")
            run_root = root / "runs/web-start-locked"
            lock_dir = run_root / "web/locks/kernel_v2.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "lock.json").write_text(
                json.dumps(
                    {
                        "schema_version": "missionforge_deepresearch.web_task_lock.v1",
                        "lock_ref": "web/locks/kernel_v2.lock",
                        "task_id": "kernel_v2_run-locked",
                        "task_kind": "kernel_v2_run",
                        "request_id": "web-start-locked",
                        "owner_pid": "999999",
                        "owner_thread": "1",
                        "owner_host": "test-host",
                        "acquired_at": "2026-01-01T00:00:00Z",
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
                    request_id="web-start-locked",
                    method="POST",
                    path="/api/research/start",
                    body=json.dumps({}),
                    kernel_config=kernel_config,
                )

        payload = json.loads(response.body)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "locked")
        self.assertEqual(payload["task"]["lock_ref"], "web/locks/kernel_v2.lock")
        run_mock.assert_not_called()

    def test_research_start_post_allows_one_cross_process_starter(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._approve_frontdesk_fixture(root, "web-start-cross-process")
            result_queue: multiprocessing.Queue[dict[str, object]] = multiprocessing.Queue()
            ready = multiprocessing.Event()
            release = multiprocessing.Event()
            holder = multiprocessing.Process(
                target=_hold_web_start_lock,
                args=(str(root), "web-start-cross-process", result_queue, ready, release),
            )
            holder.start()
            self.assertTrue(ready.wait(5))
            try:
                kernel_config = WebKernelConfig(
                    adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                    live_extension_mode=False,
                )
                with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", Mock()) as run_mock:
                    blocked = web_console_response(
                        workspace=root,
                        request_id="web-start-cross-process",
                        method="POST",
                        path="/api/research/start",
                        body=json.dumps({}),
                        kernel_config=kernel_config,
                    )
                    run_mock.assert_not_called()
            finally:
                release.set()
                holder.join(5)
                if holder.is_alive():
                    holder.terminate()
                    holder.join(5)
            holder_result = result_queue.get(timeout=5)

        blocked_payload = json.loads(blocked.body)
        self.assertEqual(holder.exitcode, 0)
        self.assertEqual(holder_result["status"], "running")
        self.assertEqual(blocked.status, 200)
        self.assertEqual(blocked_payload["status"], "locked")

    def test_research_start_post_releases_cross_process_lock_after_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            self._approve_frontdesk_fixture(root, "web-start-lock-release")
            response = web_console_response(
                workspace=root,
                request_id="web-start-lock-release",
                method="POST",
                path="/api/research/start",
                body=json.dumps({}),
                kernel_config=kernel_config,
            )
            task_ref = root / "runs/web-start-lock-release/web/tasks/current_task.json"
            lock_dir = root / "runs/web-start-lock-release/web/locks/kernel_v2.lock"
            deadline = 100
            while deadline > 0:
                if task_ref.is_file():
                    task_payload = json.loads(task_ref.read_text(encoding="utf-8"))
                    if task_payload["status"] in {"completed", "failed"}:
                        break
                deadline -= 1
                time.sleep(0.01)
            final_task = json.loads(task_ref.read_text(encoding="utf-8"))

        self.assertEqual(response.status, 202)
        self.assertEqual(final_task["status"], "completed")
        self.assertEqual(final_task["lock_ref"], "web/locks/kernel_v2.lock")
        self.assertFalse(lock_dir.exists())

    def test_research_start_post_releases_cross_process_lock_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            kernel_config = WebKernelConfig(
                adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                live_extension_mode=False,
            )
            self._approve_frontdesk_fixture(root, "web-start-lock-failure-release")
            task_ref = root / "runs/web-start-lock-failure-release/web/tasks/current_task.json"
            lock_dir = root / "runs/web-start-lock-failure-release/web/locks/kernel_v2.lock"

            with patch("missionforge_deepresearch.web_actions.run_deepresearch_kernel_v2", side_effect=RuntimeError):
                response = web_console_response(
                    workspace=root,
                    request_id="web-start-lock-failure-release",
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
        self.assertFalse(lock_dir.exists())


def _hold_web_start_lock(
    workspace: str,
    request_id: str,
    result_queue: multiprocessing.Queue[dict[str, object]],
    ready: multiprocessing.Event,
    release: multiprocessing.Event,
) -> None:
    from missionforge_deepresearch.web_tasks import start_background_task

    def runner() -> object:
        ready.set()
        release.wait(5)
        return object()

    state = start_background_task(
        workspace=workspace,
        request_id=request_id,
        task_kind="kernel_v2_run",
        runner=runner,
    )
    result_queue.put({"status": state["status"], "lock_ref": state["lock_ref"]})
    deadline = 500
    while deadline > 0:
        if not release.is_set():
            time.sleep(0.01)
            deadline -= 1
            continue
        time.sleep(0.05)
        break


if __name__ == "__main__":
    unittest.main()
