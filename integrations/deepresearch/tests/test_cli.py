from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from missionforge_deepresearch.cli import main


class CliTests(unittest.TestCase):
    def test_academic_frontdesk_step_and_approved_run_fixture_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as first_print, patch("sys.stderr") as first_stderr:
                first_code = main(
                    [
                        "academic",
                        "frontdesk-step",
                        "--initial-input",
                        "我想调研 AI 模型到 FPGA 的编译框架",
                        "--request-id",
                        "frontdesk-cli-demo",
                        "--workspace",
                        str(root),
                        "--research-intensity",
                        "intensive",
                        "--frontdesk-adapter-mode",
                        "fixture",
                    ]
                )
            with patch("builtins.print") as second_print, patch("sys.stderr") as second_stderr:
                second_code = main(
                    [
                        "academic",
                        "frontdesk-step",
                        "--message",
                        "用于工程选型和文献综述，需要覆盖 MLIR、HLS、Vitis 和开源实现。",
                        "--request-id",
                        "frontdesk-cli-demo",
                        "--workspace",
                        str(root),
                        "--research-intensity",
                        "intensive",
                        "--frontdesk-adapter-mode",
                        "fixture",
                    ]
                )
            with patch("builtins.print") as run_print, patch("sys.stderr") as run_stderr:
                run_code = main(
                    [
                        "academic",
                        "frontdesk-run",
                        "--request-id",
                        "frontdesk-cli-demo",
                        "--workspace",
                        str(root),
                        "--kernel-v2-adapter-mode",
                        "fixture",
                    ]
                )

        first_payload = json.loads(first_print.call_args.args[0])
        second_payload = json.loads(second_print.call_args.args[0])
        run_payload = json.loads(run_print.call_args.args[0])
        first_stderr_output = "".join(call.args[0] for call in first_stderr.write.call_args_list)
        second_stderr_output = "".join(call.args[0] for call in second_stderr.write.call_args_list)
        run_stderr_output = "".join(call.args[0] for call in run_stderr.write.call_args_list)

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        self.assertEqual(run_code, 0)
        self.assertEqual(first_payload["status"], "needs_user_answer")
        self.assertEqual(second_payload["status"], "ready_for_approval")
        self.assertEqual(run_payload["status"], "accepted")
        self.assertIn("FrontDesk：", first_stderr_output)
        self.assertIn("需要你补充", first_stderr_output)
        self.assertIn("requirements:", second_stderr_output)
        self.assertIn("final_report:", run_stderr_output)

    def test_academic_kernel_v2_run_fixture_prints_accepted_result(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock, patch("sys.stderr") as stderr_mock:
                exit_code = main(
                    [
                        "academic",
                        "kernel-v2-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "kernel-v2-cli-demo",
                        "--workspace",
                        str(root),
                        "--kernel-v2-adapter-mode",
                        "fixture",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            stderr_output = "".join(call.args[0] for call in stderr_mock.write.call_args_list)
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(
                payload["result_ref"],
                "runs/kernel-v2-cli-demo/packages/deepresearch_kernel_v2_result.json",
            )
            self.assertTrue((root / payload["result_ref"]).exists())
            self.assertTrue((root / payload["final_report_ref"]).exists())
            self.assertIn("输出文件：", stderr_output)
            self.assertIn(str(root / payload["final_report_ref"]), stderr_output)
            self.assertIn(str(root / payload["usage_summary_ref"]), stderr_output)
            self.assertIn("Token 用量：", stderr_output)
            self.assertIn("cached_input_tokens: 0", stderr_output)

    def test_academic_kernel_v2_run_accepts_seed_paper_and_pdf_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            seed_pdf = root / "inputs/seeds/paper.pdf"
            seed_pdf.parent.mkdir(parents=True, exist_ok=True)
            seed_pdf.write_bytes(b"%PDF-1.4\nfixture\n")

            with patch("builtins.print") as print_mock, patch("sys.stderr"):
                exit_code = main(
                    [
                        "academic",
                        "kernel-v2-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "kernel-v2-cli-seed-demo",
                        "--workspace",
                        str(root),
                        "--seed-paper",
                        "doi:10.1145/1234567.1234568",
                        "--seed-pdf-ref",
                        "inputs/seeds/paper.pdf",
                        "--target-source-count",
                        "80",
                        "--kernel-v2-adapter-mode",
                        "fixture",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            seed_pdf_index = json.loads((root / payload["seed_pdf_index_ref"]).read_text(encoding="utf-8"))
            seed_packet = json.loads((root / payload["seed_source_packet_ref"]).read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertTrue(seed_pdf_index["entries"][0]["available"])
        self.assertEqual(seed_packet["schema_version"], "missionforge_deepresearch.seed_source_packet.v1")
        self.assertEqual(len(seed_packet["source_records"]), 2)

    def test_academic_kernel_v2_run_prints_missing_outputs_for_blocked_result(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "blocked",
                "final_report_ref": "runs/kernel-v2-blocked/reports/final_report.md",
                "source_packet_ref": "runs/kernel-v2-blocked/sources/source_packet.json",
                "result_ref": "runs/kernel-v2-blocked/packages/deepresearch_kernel_v2_result.json",
                "judge_report_ref": "runs/kernel-v2-blocked/judge/judge_report.json",
                "usage_summary_ref": "runs/kernel-v2-blocked/metrics/usage_summary.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "kernel-v2-blocked",
                    "status": "blocked",
                    "final_report_ref": self.final_report_ref,
                    "result_ref": self.result_ref,
                },
            },
        )()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.mf.create_default_piworker_adapter"),
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected),
            patch("builtins.print") as print_mock,
            patch("sys.stderr") as stderr_mock,
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "kernel-v2-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "kernel-v2-blocked",
                    "--workspace",
                    str(root),
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        stderr_output = "".join(call.args[0] for call in stderr_mock.write.call_args_list)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "blocked")
        self.assertNotIn("输出文件：", stderr_output)
        self.assertIn("缺失输出：", stderr_output)
        self.assertIn(str(root / expected.final_report_ref), stderr_output)

    def test_academic_kernel_v2_run_defaults_to_piworker_adapter(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "accepted",
                "result_ref": "runs/kernel-v2-piworker/packages/deepresearch_kernel_v2_result.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "kernel-v2-piworker",
                    "status": "accepted",
                    "result_ref": self.result_ref,
                },
            },
        )()
        adapter = object()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.mf.create_default_piworker_adapter", return_value=adapter) as adapter_mock,
            patch("missionforge_deepresearch.cli.KernelV2FixtureAdapter") as fixture_mock,
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected) as run_mock,
            patch("builtins.print") as print_mock,
            patch("sys.stderr"),
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "kernel-v2-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "kernel-v2-piworker",
                    "--workspace",
                    str(root),
                    "--piworker-provider-config-source",
                    "explicit",
                    "--piworker-base-url",
                    "http://127.0.0.1:12345",
                    "--piworker-max-turns",
                    "7",
                    "--piworker-timeout-seconds",
                    "99",
                    "--piworker-reasoning",
                    "medium",
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        adapter_call = adapter_mock.call_args
        run_call = run_mock.call_args
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["request_id"], "kernel-v2-piworker")
        self.assertEqual(payload["status"], "accepted")
        fixture_mock.assert_not_called()
        self.assertIs(run_call.kwargs["adapter"], adapter)
        self.assertEqual(run_call.kwargs["workspace"], root)
        self.assertFalse(run_call.kwargs["live_extension_mode"])
        self.assertEqual(run_call.args[0].request_id, "kernel-v2-piworker")
        self.assertEqual(adapter_call.args[0].provider_config_source, "explicit")
        self.assertEqual(adapter_call.args[0].metadata["base_url"], "http://127.0.0.1:12345")
        self.assertEqual(adapter_call.args[0].timeout_seconds, 99)
        self.assertEqual(adapter_call.kwargs["environ"]["MISSIONFORGE_PI_AGENT_MAX_TURNS"], "7")
        self.assertEqual(adapter_call.kwargs["environ"]["MISSIONFORGE_PI_AGENT_REASONING"], "medium")

    def test_academic_frontdesk_step_passes_live_extension_mode(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "needs_user_answer",
                "requirements_ref": "runs/frontdesk-live-cli/frontdesk/research_requirements.md",
                "control_ref": "runs/frontdesk-live-cli/frontdesk/frontdesk_control.json",
                "research_request_ref": "",
                "result_ref": "runs/frontdesk-live-cli/frontdesk/frontdesk_result.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.frontdesk_result.v1",
                    "request_id": "frontdesk-live-cli",
                    "status": "needs_user_answer",
                    "result_ref": self.result_ref,
                },
            },
        )()
        adapter = object()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.mf.create_default_piworker_adapter", return_value=adapter),
            patch("missionforge_deepresearch.cli.run_deepresearch_frontdesk_turn", return_value=expected) as run_mock,
            patch("builtins.print") as print_mock,
            patch("sys.stderr"),
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "frontdesk-step",
                    "--initial-input",
                    "研究一个尚未想清楚的问题",
                    "--request-id",
                    "frontdesk-live-cli",
                    "--workspace",
                    str(root),
                    "--live-extension-mode",
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "needs_user_answer")
        self.assertIs(run_mock.call_args.kwargs["adapter"], adapter)
        self.assertTrue(run_mock.call_args.kwargs["live_extension_mode"])

    def test_academic_frontdesk_run_passes_live_extension_mode_to_kernel(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "accepted",
                "result_ref": "runs/frontdesk-run-live/packages/deepresearch_kernel_v2_result.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "frontdesk-run-live",
                    "status": "accepted",
                    "result_ref": self.result_ref,
                },
            },
        )()
        adapter = object()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.mf.create_default_piworker_adapter", return_value=adapter),
            patch("missionforge_deepresearch.cli.approve_frontdesk_requirements") as approve_mock,
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected) as run_mock,
            patch("builtins.print") as print_mock,
            patch("sys.stderr"),
        ):
            root = Path(tempdir)
            approve_mock.return_value = type(
                "Request",
                (),
                {
                    "request_id": "frontdesk-run-live",
                    "topic": "approved topic",
                    "research_intensity": "intensive",
                },
            )()
            exit_code = main(
                [
                    "academic",
                    "frontdesk-run",
                    "--request-id",
                    "frontdesk-run-live",
                    "--workspace",
                    str(root),
                    "--live-extension-mode",
                ]
            )

        payload = json.loads(print_mock.call_args.args[0])
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertIs(run_mock.call_args.kwargs["adapter"], adapter)
        self.assertTrue(run_mock.call_args.kwargs["live_extension_mode"])

    def test_academic_frontdesk_tui_fixture_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            user_input = (
                "我想调研 AI 模型到 FPGA 的编译框架\n"
                "面向工程选型和文献综述，需要覆盖 MLIR、HLS、Vitis 和开源实现。\n"
                "/approve\n"
            )
            with patch("sys.stdin", new=StringIO(user_input)), patch("sys.stdout", new=StringIO()):
                exit_code = main(
                    [
                        "academic",
                        "frontdesk-tui",
                        "--request-id",
                        "frontdesk-tui-cli",
                        "--workspace",
                        str(root),
                        "--frontdesk-adapter-mode",
                        "fixture",
                        "--kernel-v2-adapter-mode",
                        "fixture",
                        "--no-live-extension-mode",
                    ]
                )
                report_exists = (root / "runs/frontdesk-tui-cli/reports/final_report.md").is_file()

        self.assertEqual(exit_code, 0)
        self.assertTrue(report_exists)

    def test_academic_web_console_invokes_read_only_server(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.serve_web_console", return_value=0) as serve_mock,
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "web-console",
                    "--request-id",
                    "web-console-cli",
                    "--workspace",
                    str(root),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "0",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(serve_mock.call_args.kwargs["workspace"], root)
        self.assertEqual(serve_mock.call_args.kwargs["request_id"], "web-console-cli")
        self.assertEqual(serve_mock.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(serve_mock.call_args.kwargs["port"], 0)

    def test_academic_kernel_v2_run_does_not_set_turn_budget_by_default(self) -> None:
        expected = type(
            "Result",
            (),
            {
                "status": "accepted",
                "result_ref": "runs/kernel-v2-no-turn-budget/packages/deepresearch_kernel_v2_result.json",
                "to_dict": lambda self: {
                    "schema_version": "missionforge_deepresearch.kernel_v2_result.v1",
                    "request_id": "kernel-v2-no-turn-budget",
                    "status": "accepted",
                    "result_ref": self.result_ref,
                },
            },
        )()
        adapter = object()

        with (
            tempfile.TemporaryDirectory() as tempdir,
            patch("missionforge_deepresearch.cli.mf.create_default_piworker_adapter", return_value=adapter) as adapter_mock,
            patch("missionforge_deepresearch.cli.run_deepresearch_kernel_v2", return_value=expected),
            patch("builtins.print"),
            patch("sys.stderr"),
        ):
            root = Path(tempdir)
            exit_code = main(
                [
                    "academic",
                    "kernel-v2-run",
                    "--topic",
                    "compiler autotuning survey",
                    "--request-id",
                    "kernel-v2-no-turn-budget",
                    "--workspace",
                    str(root),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertNotIn("MISSIONFORGE_PI_AGENT_MAX_TURNS", adapter_mock.call_args.kwargs["environ"])

    def test_academic_kernel_v2_run_streams_kernel_step_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch("builtins.print") as print_mock, patch("sys.stderr") as stderr_mock:
                exit_code = main(
                    [
                        "academic",
                        "kernel-v2-run",
                        "--topic",
                        "compiler autotuning survey",
                        "--request-id",
                        "kernel-v2-watched",
                        "--workspace",
                        str(root),
                        "--kernel-v2-adapter-mode",
                        "fixture",
                        "--stream-progress",
                        "--progress-interval",
                        "0.01",
                    ]
                )

            payload = json.loads(print_mock.call_args.args[0])
            progress_output = "".join(call.args[0] for call in stderr_mock.write.call_args_list)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertIn("Kernel v2 researcher 正在执行。", progress_output)
        self.assertIn("Kernel v2 reviewer 正在执行。", progress_output)
        self.assertIn("Kernel v2 judge 正在执行。", progress_output)
        self.assertIn("Kernel v2 researcher 路由到 reviewer。", progress_output)
        self.assertIn("Kernel v2 judge 路由到 accepted。", progress_output)
        self.assertIn("调研流程完成。", progress_output)
        self.assertNotIn("compiler autotuning survey", progress_output)


if __name__ == "__main__":
    unittest.main()
