from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from missionforge_deepresearch.kernel_v2 import run_deepresearch_kernel_v2
from missionforge_deepresearch.kernel_v2 import KernelV2FixtureAdapter
from missionforge_deepresearch.frontdesk import FrontDeskFixtureAdapter
from missionforge_deepresearch.tui import FrontDeskTuiConfig, _kernel_observer_rows, _print_kernel_view, run_frontdesk_tui
from missionforge.adapters.cli import MissionRunView


class FrontDeskTuiTests(unittest.TestCase):
    def test_kernel_view_helpers_render_optional_observer_fields(self) -> None:
        view = MissionRunView(
            flow_id="flow",
            run_id="run",
            status="running",
            flow_result_ref="runs/demo/flow_result.json",
            contract_ref="contracts/demo.json",
            contract_hash="abc123",
            latest_event_age_seconds=42,
            last_safe_point_step_id="step-12",
            last_safe_point_status="stable",
            last_safe_point_details={"ref": "state/safe_point.json"},
            usage_totals={
                "input_tokens": 11,
                "cached_input_tokens": 2,
                "output_tokens": 7,
                "total_tokens": 20,
            },
            context_pressure={"percent": "0.82", "remaining_tokens": 128},
            tool_activity_refs=["state/tool_activity.json", "metrics/tool_usage.json"],
        )

        rows = _kernel_observer_rows(view)
        output = StringIO()
        _print_kernel_view(output, view)
        rendered = output.getvalue()

        self.assertIn(("usage_totals", "input_tokens=11, cached_input_tokens=2, output_tokens=7, total_tokens=20"), rows)
        self.assertIn(("context_pressure", "0.82, remaining_tokens=128"), rows)
        self.assertIn(("latest_event_age", "42s"), rows)
        self.assertIn(("tool_activity_refs", "state/tool_activity.json, metrics/tool_usage.json"), rows)
        self.assertIn(("safe_point_details", "ref=state/safe_point.json, step_id=step-12, status=stable"), rows)
        self.assertIn("usage_totals: input_tokens=11, cached_input_tokens=2, output_tokens=7, total_tokens=20", rendered)
        self.assertIn("context_pressure: 0.82, remaining_tokens=128", rendered)
        self.assertIn("latest_event_age: 42s", rendered)
        self.assertIn("tool_activity_refs: state/tool_activity.json", rendered)
        self.assertIn("safe_point_details: ref=state/safe_point.json, step_id=step-12, status=stable", rendered)

    def test_kernel_view_helpers_ignore_absent_optional_fields(self) -> None:
        view = MissionRunView(
            flow_id="flow",
            run_id="run",
            status="running",
            flow_result_ref="runs/demo/flow_result.json",
            contract_ref="contracts/demo.json",
            contract_hash="abc123",
        )

        rows = _kernel_observer_rows(view)
        output = StringIO()
        _print_kernel_view(output, view)
        rendered = output.getvalue()

        self.assertEqual(rows, [])
        self.assertIn("Kernel 状态", rendered)
        self.assertNotIn("usage_totals:", rendered)
        self.assertNotIn("context_pressure:", rendered)
        self.assertNotIn("latest_event_age:", rendered)
        self.assertNotIn("tool_activity_refs:", rendered)
        self.assertNotIn("safe_point_details:", rendered)

    def test_tui_runs_chat_to_approval_and_research(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = StringIO(
                "\n".join(
                    [
                        "我想调研 AI 模型到 FPGA 的编译链路",
                        "面向工程选型和文献综述，需要覆盖 MLIR、HLS、Vitis 和开源实现。",
                        "/approve",
                    ]
                )
                + "\n"
            )
            outputs = StringIO()
            exit_code = run_frontdesk_tui(
                config=FrontDeskTuiConfig(
                    request_id="tui-demo",
                    workspace=root,
                    research_intensity="intensive",
                    live_extension_mode=False,
                ),
                frontdesk_adapter=FrontDeskFixtureAdapter(),
                kernel_adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                input_stream=inputs,
                output_stream=outputs,
            )
            output = outputs.getvalue()
            report_exists = (root / "runs/tui-demo/reports/final_report.md").is_file()

        self.assertEqual(exit_code, 0)
        self.assertIn("MissionForge DeepResearch", output)
        self.assertIn("命令：/show 查看需求", output)
        self.assertIn("[FrontDesk] status: needs_user_answer", output)
        self.assertIn("我先不生成正式调研计划", output)
        self.assertIn("FrontDesk 需要你补充", output)
        self.assertIn("[FrontDesk] status: ready_for_approval", output)
        self.assertIn("[DeepResearch] status: accepted", output)
        self.assertIn("项目推进看板", output)
        self.assertIn("Kernel 状态", output)
        self.assertIn("flow_result", output)
        self.assertIn("里程碑", output)
        self.assertIn("覆盖面", output)
        self.assertIn("输出文件", output)
        self.assertTrue(report_exists)

    def test_tui_can_show_requirements_before_exit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = StringIO("研究 deep research 工具\n/show\n/quit\n")
            outputs = StringIO()
            exit_code = run_frontdesk_tui(
                config=FrontDeskTuiConfig(
                    request_id="tui-show",
                    workspace=root,
                    live_extension_mode=False,
                ),
                frontdesk_adapter=FrontDeskFixtureAdapter(),
                kernel_adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                input_stream=inputs,
                output_stream=outputs,
            )
            output = outputs.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("research_requirements.md", output)
        self.assertIn("DeepResearch 调研需求文档", output)

    def test_tui_records_runtime_user_intervention_after_approval(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inputs = StringIO(
                "\n".join(
                    [
                        "我想调研 Deep Research 平台",
                        "用于产品设计，需要比较成熟产品和开源实现。",
                        "/approve",
                        "请额外关注用户体验和进度可观测性。",
                    ]
                )
                + "\n"
            )
            outputs = StringIO()

            def _run_after_listener_starts(request):
                event_log_ref = root / "runs/tui-runtime-input/interaction/user_events.jsonl"
                deadline = time.monotonic() + 1.0
                while not event_log_ref.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                return run_deepresearch_kernel_v2(
                    request,
                    workspace=root,
                    adapter=KernelV2FixtureAdapter(),
                    live_extension_mode=False,
                )

            exit_code = run_frontdesk_tui(
                config=FrontDeskTuiConfig(
                    request_id="tui-runtime-input",
                    workspace=root,
                    research_intensity="standard",
                    live_extension_mode=False,
                ),
                frontdesk_adapter=FrontDeskFixtureAdapter(),
                kernel_adapter_factory=lambda _intensity: KernelV2FixtureAdapter(),
                input_stream=inputs,
                output_stream=outputs,
                progress_runner=_run_after_listener_starts,
            )
            event_log_ref = root / "runs/tui-runtime-input/interaction/user_events.jsonl"
            event_log_exists = event_log_ref.is_file()
            event_log = event_log_ref.read_text(encoding="utf-8")
            events = [json.loads(line) for line in event_log.splitlines() if line.strip()]
            output = outputs.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertTrue(event_log_exists)
        self.assertEqual(events[0]["kind"], "message")
        self.assertEqual(events[0]["run_id"], "deepresearch-v2-tui-runtime-input")
        self.assertEqual(events[0]["target"], "flow")
        self.assertIn("请额外关注用户体验和进度可观测性。", events[0]["text"])
        self.assertIn("已记录用户插入", output)


if __name__ == "__main__":
    unittest.main()
