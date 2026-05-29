from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.runner import MissionResult
from missionforge_skillfoundry import (
    RegistryStatus,
    SkillFoundryRegistry,
    SkillFoundryMissionCompiler,
    evaluate_product_grade,
    register_skill_bundle,
    validate_skill_bundle,
)
from missionforge_skillfoundry.workspace import read_json_ref

from test_product_contract import sample_request
from test_skill_bundle_validators import write_valid_prompt_only_package


class RegistryTests(unittest.TestCase):
    def test_product_grade_report_registers_product_grade(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            validate_skill_bundle(workspace=root, bundle_id="demo-skill")
            evaluate_product_grade(
                workspace=root,
                bundle_id="demo-skill",
                mission_result=MissionResult(mission_id="skillfoundry-demo-skill", status="completed_verified"),
            )

            entry = register_skill_bundle(workspace=root)
            registry = SkillFoundryRegistry.from_dict(read_json_ref(root, "registry/skillfoundry_registry.json", "registry"))

            self.assertEqual(entry.status, RegistryStatus.PRODUCT_GRADE_REGISTERED)
            self.assertEqual(registry.entries[0].status, RegistryStatus.PRODUCT_GRADE_REGISTERED)

    def test_failed_product_grade_registers_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            validate_skill_bundle(workspace=root, bundle_id="demo-skill")
            evaluate_product_grade(
                workspace=root,
                bundle_id="demo-skill",
                mission_result=MissionResult(mission_id="skillfoundry-demo-skill", status="failed"),
            )

            entry = register_skill_bundle(workspace=root)

            self.assertEqual(entry.status, RegistryStatus.CANDIDATE_REGISTERED)


if __name__ == "__main__":
    unittest.main()
