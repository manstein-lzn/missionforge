from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.runner import MissionResult
from missionforge_skillfoundry import SkillFoundryProductReport, run_skillfoundry_bundle_build
from missionforge_skillfoundry.registry import SkillFoundryRegistry
from missionforge_skillfoundry.workspace import read_json_ref

from test_product_contract import code_runtime_request, sample_request
from test_skill_bundle_validators import write_valid_code_runtime_package, write_valid_prompt_only_package


class SkillFoundryRuntimeFacadeTests(unittest.TestCase):
    def test_default_runtime_facade_registers_candidate_when_product_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            report = run_skillfoundry_bundle_build(sample_request(), workspace=root)
            registry = SkillFoundryRegistry.from_dict(read_json_ref(root, "registry/skillfoundry_registry.json", "registry"))

            self.assertEqual(report.final_status, "candidate_registered")
            self.assertEqual(registry.entries[0].status.value, "candidate_registered")
            self.assertTrue((root / "package/SKILL.md").exists())
            self.assertTrue((root / "package/skillfoundry.bundle.json").exists())
            self.assertTrue((root / "package/README.md").exists())
            self.assertTrue((root / "qa/product_repair_packet.json").exists())

    def test_runtime_facade_builds_grades_registers_and_reports_prompt_only_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            report = run_skillfoundry_bundle_build(sample_request(), workspace=root, runtime=_PromptOnlyFixtureRuntime(root))
            registry = SkillFoundryRegistry.from_dict(read_json_ref(root, "registry/skillfoundry_registry.json", "registry"))
            report_payload = SkillFoundryProductReport.from_dict(
                read_json_ref(root, "reports/skillfoundry_product_report.json", "product_report")
            )

            self.assertEqual(report.final_status, "product_grade_registered")
            self.assertEqual(report_payload, report)
            self.assertEqual(registry.entries[0].status.value, "product_grade_registered")
            self.assertTrue((root / "package/SKILL.md").exists())
            self.assertTrue((root / "package/skillfoundry.bundle.json").exists())
            self.assertTrue((root / "package/README.md").exists())
            self.assertTrue((root / "qa/product_grade_report.json").exists())

    def test_runtime_facade_builds_grades_registers_and_reports_code_runtime_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            report = run_skillfoundry_bundle_build(code_runtime_request(), workspace=root, runtime=_CodeRuntimeFixtureRuntime(root))
            registry = SkillFoundryRegistry.from_dict(read_json_ref(root, "registry/skillfoundry_registry.json", "registry"))

            self.assertEqual(report.final_status, "product_grade_registered")
            self.assertEqual(registry.entries[0].status.value, "product_grade_registered")
            self.assertTrue((root / "package/scripts/skill_runtime.py").exists())
            self.assertTrue((root / "package/schemas/runtime.schema.json").exists())
            self.assertTrue((root / "qa/product_grade_report.json").exists())


class _PromptOnlyFixtureRuntime:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, mission):
        write_valid_prompt_only_package(self.root)
        return MissionResult(
            mission_id=mission.mission_id,
            status="completed_verified",
            evidence_refs=["evidence/verifier.json"],
            artifact_refs=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
        )


class _CodeRuntimeFixtureRuntime:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, mission):
        write_valid_code_runtime_package(self.root, bundle_id=mission.mission_id.removeprefix("skillfoundry-"))
        return MissionResult(
            mission_id=mission.mission_id,
            status="completed_verified",
            evidence_refs=["evidence/verifier.json"],
            artifact_refs=[
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
                "package/scripts/skill_runtime.py",
                "package/schemas/runtime.schema.json",
            ],
        )


if __name__ == "__main__":
    unittest.main()
