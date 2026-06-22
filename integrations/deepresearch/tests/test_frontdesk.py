from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.extensions import ExtensionLock
from missionforge.contracts import ContractValidationError
from missionforge_deepresearch.frontdesk import (
    FRONTDESK_APPROVAL_REF,
    FRONTDESK_ASSISTANT_TURN_REF,
    FRONTDESK_CONTROL_REF,
    FRONTDESK_PERMISSION_MANIFEST_REF,
    FRONTDESK_REQUIREMENTS_REF,
    FRONTDESK_RESEARCH_PROJECTION_REF,
    FRONTDESK_SESSION_STATE_REF,
    FrontDeskFixtureAdapter,
    approve_frontdesk_requirements,
    run_deepresearch_frontdesk_turn,
)


class DeepResearchFrontDeskTests(unittest.TestCase):
    def test_frontdesk_turns_progress_from_questions_to_approval_ready(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = run_deepresearch_frontdesk_turn(
                initial_input="我想研究 AI 模型到 FPGA 的编译链路",
                request_id="frontdesk-demo",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
                research_intensity="intensive",
            )
            first_control = _read_json(root, first.control_ref)
            first_turn = _read_json(root, first.assistant_turn_ref)
            first_state = _read_json(root, first.session_state_ref)
            second = run_deepresearch_frontdesk_turn(
                user_message="面向工程选型和文献综述，需要覆盖 MLIR、HLS、Vitis 和开源实现。",
                request_id="frontdesk-demo",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
                research_intensity="intensive",
            )
            requirements = (root / second.requirements_ref).read_text(encoding="utf-8")
            control = _read_json(root, second.control_ref)
            request = approve_frontdesk_requirements(request_id="frontdesk-demo", workspace=root)
            approval_exists = (root / "runs/frontdesk-demo" / FRONTDESK_APPROVAL_REF).exists()

        self.assertEqual(first.status, "needs_user_answer")
        self.assertEqual(first.research_request_ref, "")
        self.assertEqual(first_control["assistant_turn_ref"], FRONTDESK_ASSISTANT_TURN_REF)
        self.assertEqual(first_control["session_state_ref"], FRONTDESK_SESSION_STATE_REF)
        self.assertIn("先不生成正式调研计划", first_turn["message"])
        self.assertGreaterEqual(len(first_turn["questions"]), 2)
        self.assertIn("open_ambiguities", first_state)
        self.assertEqual(second.status, "ready_for_approval")
        self.assertIn("可执行调研题目", requirements)
        self.assertEqual(control["decision"], "ready_for_approval")
        self.assertEqual(request.request_id, "frontdesk-demo")
        self.assertEqual(request.research_intensity.value, "intensive")
        self.assertTrue(approval_exists)

    def test_approval_requires_ready_control(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_deepresearch_frontdesk_turn(
                initial_input="还不清楚的研究想法",
                request_id="frontdesk-not-ready",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
            )

            with self.assertRaisesRegex(ContractValidationError, "not ready"):
                approve_frontdesk_requirements(request_id="frontdesk-not-ready", workspace=root)

    def test_frontdesk_result_uses_outer_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_frontdesk_turn(
                initial_input="研究 deep research 工具",
                request_id="frontdesk-refs",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
            )

        self.assertEqual(result.requirements_ref, "runs/frontdesk-refs/" + FRONTDESK_REQUIREMENTS_REF)
        self.assertEqual(result.control_ref, "runs/frontdesk-refs/" + FRONTDESK_CONTROL_REF)
        self.assertEqual(result.assistant_turn_ref, "runs/frontdesk-refs/" + FRONTDESK_ASSISTANT_TURN_REF)
        self.assertEqual(result.session_state_ref, "runs/frontdesk-refs/" + FRONTDESK_SESSION_STATE_REF)
        self.assertTrue(all(ref.startswith("runs/frontdesk-refs/") for ref in result.evidence_refs))

    def test_frontdesk_live_extension_mode_grants_academic_tools(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_frontdesk_turn(
                initial_input="我想先确认一个 FPGA 编译研究方向是否合理",
                request_id="frontdesk-live",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
                live_extension_mode=True,
                extension_installer=_fake_extension_installer,
            )
            run_root = root / result.run_workspace_ref
            manifest = _read_json(run_root, FRONTDESK_PERMISSION_MANIFEST_REF)
            lock_ref = next(ref.removeprefix(result.run_workspace_ref + "/") for ref in result.evidence_refs if ref.endswith("extension_lock.json"))
            lock = ExtensionLock.from_dict(_read_json(run_root, lock_ref))

        self.assertEqual(result.status, "needs_user_answer")
        self.assertEqual(manifest["network_policy"], "enabled")
        self.assertEqual(manifest["extension_grants"][0]["package"], "local:extensions/pi-academic-sources")
        self.assertEqual(
            manifest["extension_grants"][0]["metadata"]["tool_names"],
            ["academic_search", "academic_fetch", "citation_lookup", "repo_search"],
        )
        self.assertEqual(lock.extensions[0].package, "local:extensions/pi-academic-sources")

    def test_frontdesk_without_live_extension_has_no_tool_grant_or_lock(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = run_deepresearch_frontdesk_turn(
                initial_input="先澄清一个研究方向",
                request_id="frontdesk-no-live",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
            )
            run_root = root / result.run_workspace_ref
            manifest = _read_json(run_root, FRONTDESK_PERMISSION_MANIFEST_REF)

        self.assertEqual(manifest["network_policy"], "disabled")
        self.assertEqual(manifest["extension_grants"], [])
        self.assertFalse(any(ref.endswith("extension_lock.json") for ref in result.evidence_refs))

    def test_frontdesk_accepts_runtime_progress_sink(self) -> None:
        events = []

        class ProgressFixtureAdapter(FrontDeskFixtureAdapter):
            def run_call(self, call, *, runtime_progress_sink=None, **kwargs):
                if runtime_progress_sink is not None:
                    runtime_progress_sink({"message": "frontdesk fixture running", "detail": "progress sink connected"})
                return super().run_call(call, runtime_progress_sink=runtime_progress_sink, **kwargs)

        with TemporaryDirectory() as tmpdir:
            run_deepresearch_frontdesk_turn(
                initial_input="研究一个方向",
                request_id="frontdesk-progress",
                workspace=Path(tmpdir),
                adapter=ProgressFixtureAdapter(),
                runtime_progress_sink=events.append,
            )

        self.assertEqual(events[0]["message"], "frontdesk fixture running")

    def test_approval_rejects_stale_projected_requirements(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_deepresearch_frontdesk_turn(
                initial_input="研究 deep research 工具",
                request_id="frontdesk-stale",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
            )
            result = run_deepresearch_frontdesk_turn(
                user_message="面向工程选型，覆盖工具架构和报告产物。",
                request_id="frontdesk-stale",
                workspace=root,
                adapter=FrontDeskFixtureAdapter(),
            )
            self.assertTrue((root / result.run_workspace_ref / FRONTDESK_RESEARCH_PROJECTION_REF).is_file())
            (root / result.run_workspace_ref / FRONTDESK_REQUIREMENTS_REF).write_text(
                "# DeepResearch 调研需求文档\n\n被用户手动修改但未重新投影。\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractValidationError, "changed after research request projection"):
                approve_frontdesk_requirements(request_id="frontdesk-stale", workspace=root)


def _read_json(root: Path, ref: str):
    return json.loads((root / ref).read_text(encoding="utf-8"))


def _fake_extension_installer(_grant, install_root):
    install_path = install_root / "pi-academic-sources"
    install_path.mkdir(parents=True, exist_ok=True)
    package_json = install_path / "package.json"
    package_json.write_text(
        json.dumps(
            {
                "name": "@missionforge/pi-academic-sources",
                "version": "0.1.0",
                "main": "index.js",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (install_path / "index.js").write_text("module.exports = { tools: [] };\n", encoding="utf-8")
    return {}


if __name__ == "__main__":
    unittest.main()
