from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

from missionforge import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    AgentWorkspace,
    FrontDesk,
    JudgePacket,
    JudgeReport,
    JudgeReportDecision,
)
from missionforge.frontdesk.mission_mapper import MissionIRMapper
from missionforge.frontdesk.schema import ApprovalAuthority
from missionforge.ir import MissionIR
from missionforge_skillfoundry import BundleProfile, SkillBundleManifest, SkillFoundryMissionCompiler, SkillFoundryRequest
from missionforge_skillfoundry.runtime import run_skillfoundry_task_contract_bundle_build
from missionforge_skillfoundry.workspace import read_json_ref
from tests.frontdesk_llm_fixtures import seed_llm_authored_frontdesk_artifacts


CORE_ROOT = Path("src/missionforge")


class SkillFoundryFrontDeskFlowTests(unittest.TestCase):
    def test_frontdesk_authored_refs_compile_to_skillfoundry_mission(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(workspace=root)
            session = frontdesk.start(
                "Build a prompt-only SkillFoundry skill package for release-note review. "
                "The expected package entrypoint is package/SKILL.md.",
                session_id="sf-frontdesk",
            )
            frontdesk.answer(
                session.session_ref,
                "Use sanitized source refs only and verify package/SKILL.md, "
                "package/skillfoundry.bundle.json, and package/README.md.",
            )
            freeze_result = _freeze_seeded_frontdesk(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            )

            request = _request_from_frontdesk(root, freeze_result.mission_ir_ref)
            result = SkillFoundryMissionCompiler().compile_request(request, workspace=root)
            mission = MissionIR.from_dict(read_json_ref(root, result.mission_ir_ref, "mission_ir"))

            self.assertEqual(request.bundle_id, "sf-frontdesk-skill")
            self.assertEqual(result.target_package_ref, "package/SKILL.md")
            self.assertEqual(
                mission.outputs["required_artifacts"],
                ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            )
            self.assertEqual(
                [profile.profile_id for profile in mission.capability_profiles],
                ["user_provided_evidence_only", "explicit_output_root"],
            )
            self.assertEqual(
                mission.verification["verification_profiles"],
                [{"profile_id": "generic_local_verification"}],
            )
            self.assertTrue((root / result.frozen_contract_ref).exists())
            self.assertIn(freeze_result.mission_ir_ref, request.source_refs)

    def test_frontdesk_authored_skillfoundry_request_uses_task_contract_runtime_facade(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(workspace=root)
            session = frontdesk.start(
                "Build a prompt-only SkillFoundry skill package with package/SKILL.md.",
                session_id="sf-runtime-frontdesk",
            )
            freeze_result = _freeze_seeded_frontdesk(
                frontdesk,
                session.session_ref,
                expected_artifacts=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            )
            request = _request_from_frontdesk(root, freeze_result.mission_ir_ref, bundle_id="sf-runtime-skill")

            report = run_skillfoundry_task_contract_bundle_build(
                request,
                workspace=root,
                executor=_PackageFixtureExecutor(),
                judge=_AcceptingJudge(),
            )

            self.assertEqual(report.final_status, "product_grade_registered")
            self.assertTrue((root / "runs/sf-runtime-skill/package/SKILL.md").exists())
            self.assertTrue((root / "reports/skillfoundry_product_report.json").exists())

    def test_frontdesk_mapping_selects_code_runtime_when_runtime_assets_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            frontdesk = FrontDesk(workspace=root)
            session = frontdesk.start(
                "Build a Codex skill with helper scripts, JSON schemas, and local runtime assets.",
                session_id="sf-code-runtime-frontdesk",
            )
            frontdesk.answer(
                session.session_ref,
                "The package must include package/scripts/skill_runtime.py and package/schemas/runtime.schema.json.",
            )
            freeze_result = _freeze_seeded_frontdesk(
                frontdesk,
                session.session_ref,
                expected_artifacts=[
                    "package/SKILL.md",
                    "package/skillfoundry.bundle.json",
                    "package/README.md",
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                ],
            )

            request = _request_from_frontdesk(
                root,
                freeze_result.mission_ir_ref,
                bundle_id="sf-code-runtime-skill",
                bundle_profile=BundleProfile.CODE_RUNTIME,
                extra_expected_outputs=[
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                ],
            )
            result = SkillFoundryMissionCompiler().compile_request(request, workspace=root)
            mission = MissionIR.from_dict(read_json_ref(root, result.mission_ir_ref, "mission_ir"))

            self.assertEqual(request.desired_bundle_profile, BundleProfile.CODE_RUNTIME)
            self.assertEqual(mission.outputs["bundle_profile"], "code_runtime")
            self.assertIn("package/scripts/skill_runtime.py", mission.outputs["required_artifacts"])
            self.assertIn(freeze_result.mission_ir_ref, request.source_refs)

    def test_missionforge_core_has_no_skillfoundry_or_codexarium_product_branches(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_name = alias.name.split(".", 1)[0]
                        if root_name in {"missionforge_skillfoundry", "codexarium"}:
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    root_name = module.split(".", 1)[0]
                    if root_name in {"missionforge_skillfoundry", "codexarium"}:
                        violations.append(f"{path}: from {module} import ...")

        self.assertEqual(violations, [])


def _freeze_seeded_frontdesk(frontdesk: FrontDesk, session_ref: str, *, expected_artifacts: list[str]):
    seed_llm_authored_frontdesk_artifacts(
        frontdesk,
        session_ref,
        expected_artifacts=expected_artifacts,
    )
    frontdesk.review_plan(session_ref, reviewed_by="skillfoundry-dogfood", authority=ApprovalAuthority.USER)
    MissionIRMapper().map(session=frontdesk.load_session(session_ref), workspace=frontdesk.workspace)
    frontdesk.audit(session_ref)
    frontdesk.approve(session_ref, approved_by="skillfoundry-dogfood")
    return frontdesk.freeze(session_ref)


def _request_from_frontdesk(
    root: Path,
    mission_ref: str,
    *,
    bundle_id: str = "sf-frontdesk-skill",
    bundle_profile: BundleProfile = BundleProfile.PROMPT_ONLY,
    extra_expected_outputs: list[str] | None = None,
) -> SkillFoundryRequest:
    mission = MissionIR.from_dict(read_json_ref(root, mission_ref, "frontdesk_mission_ir"))
    expected_outputs = list(mission.outputs.get("required_artifacts", ["package/SKILL.md"]))
    for ref in extra_expected_outputs or []:
        if ref not in expected_outputs:
            expected_outputs.append(ref)
    return SkillFoundryRequest(
        request_id=f"request-{bundle_id}",
        bundle_id=bundle_id,
        desired_capability=mission.objective.summary,
        target_user="codex_user",
        triggers=["When release-note review needs a local prompt-only Codex skill."],
        non_triggers=["When a code runtime or service runtime bundle is required."],
        expected_outputs=expected_outputs,
        must=["Write package files only under package/."],
        must_not=["Do not include raw conversations or provider payloads."],
        privacy_boundaries=["Use sanitized FrontDesk and MissionIR refs only."],
        distribution_boundaries=["Local distribution only."],
        source_refs=[
            mission_ref,
            "frontdesk/semantic_lock.json",
            "frontdesk/mission_brief.json",
            "frontdesk/mission_plan.json",
            "frontdesk/freeze_manifest.json",
        ],
        desired_bundle_profile=bundle_profile,
    )


class _PackageFixtureExecutor:
    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> AgentExecutionReport:
        bundle_id = packet.contract_id.removeprefix("skillfoundry-").removesuffix("-task-contract")
        workspace.write_text("package/SKILL.md", "# Release Notes Review\n\nUse sanitized release-note refs only.\n")
        workspace.write_json("package/skillfoundry.bundle.json", SkillBundleManifest.prompt_only(bundle_id).to_dict())
        workspace.write_text("package/README.md", "# Release Notes Review Skill\n\nLocal prompt-only package.\n")
        workspace.write_text("reports/executor_evidence.md", "package written\n")
        return AgentExecutionReport(
            report_id="skillfoundry-frontdesk-execution-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=AgentExecutionStatus.COMPLETED,
            produced_artifact_refs=[
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
            ],
            changed_refs=[
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
            ],
            evidence_refs=["reports/executor_evidence.md"],
        )


class _AcceptingJudge:
    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: AgentWorkspace,
    ) -> JudgeReport:
        return JudgeReport(
            report_id="skillfoundry-frontdesk-judge-report",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            decision=JudgeReportDecision.ACCEPTED,
            hard_check_status=packet.hard_check_status,
            evidence_refs=list(packet.evidence_refs),
            accepted_artifact_refs=list(packet.artifact_refs),
        )


if __name__ == "__main__":
    unittest.main()
