from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.runner import MissionResult
from missionforge_skillfoundry import RegistryStatus, evaluate_product_grade, validate_skill_bundle

from test_product_contract import code_runtime_request, sample_request
from test_skill_bundle_validators import write_valid_code_runtime_package, write_valid_prompt_only_package
from missionforge_skillfoundry import SkillFoundryMissionCompiler
from missionforge_skillfoundry.workspace import write_text_ref


class ProductGradeGateTests(unittest.TestCase):
    def test_product_grade_pass_requires_verifier_and_bundle_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            report = evaluate_product_grade(
                workspace=root,
                bundle_id="demo-skill",
                mission_result=MissionResult(
                    mission_id="skillfoundry-demo-skill",
                    status="completed_verified",
                    evidence_refs=["evidence/verifier.json"],
                    artifact_refs=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
                ),
            )

            self.assertTrue(report.product_grade)
            self.assertEqual(report.recommended_registry_status, RegistryStatus.PRODUCT_GRADE_REGISTERED)
            self.assertEqual(report.findings, [])
            self.assertTrue((root / "qa/product_grade_report.json").exists())

    def test_verifier_failure_blocks_product_grade(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            report = evaluate_product_grade(
                workspace=root,
                bundle_id="demo-skill",
                mission_result=MissionResult(mission_id="skillfoundry-demo-skill", status="failed"),
            )

            self.assertFalse(report.product_grade)
            self.assertEqual(report.recommended_registry_status, RegistryStatus.CANDIDATE_REGISTERED)
            self.assertTrue((root / "qa/product_repair_packet.json").exists())

    def test_bundle_validation_failure_blocks_product_grade(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            write_text_ref(root, "package/README.md", "raw_transcript marker\n")
            validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            report = evaluate_product_grade(
                workspace=root,
                bundle_id="demo-skill",
                mission_result=MissionResult(mission_id="skillfoundry-demo-skill", status="completed_verified"),
            )

            self.assertFalse(report.product_grade)
            self.assertTrue(any("SF-PROMPT-NO-RAW-CONTEXT" in finding.finding_id for finding in report.findings))

    def test_code_runtime_product_grade_pass_requires_verifier_and_bundle_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            write_valid_code_runtime_package(root)
            validate_skill_bundle(workspace=root, bundle_id="code-skill")

            report = evaluate_product_grade(
                workspace=root,
                bundle_id="code-skill",
                mission_result=MissionResult(
                    mission_id="skillfoundry-code-skill",
                    status="completed_verified",
                    evidence_refs=["evidence/verifier.json"],
                    artifact_refs=[
                        "package/SKILL.md",
                        "package/skillfoundry.bundle.json",
                        "package/README.md",
                        "package/scripts/skill_runtime.py",
                        "package/schemas/runtime.schema.json",
                    ],
                ),
            )

            self.assertTrue(report.product_grade)
            self.assertEqual(report.recommended_registry_status, RegistryStatus.PRODUCT_GRADE_REGISTERED)

    def test_product_grade_blocks_contract_package_ref_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            write_valid_code_runtime_package(root)
            (root / "package/scripts/skill_runtime.py").unlink()
            validate_skill_bundle(workspace=root, bundle_id="code-skill")

            report = evaluate_product_grade(
                workspace=root,
                bundle_id="code-skill",
                mission_result=MissionResult(mission_id="skillfoundry-code-skill", status="completed_verified"),
            )

            self.assertFalse(report.product_grade)
            self.assertTrue(any("SF-PG-PACKAGE-REFS-MISMATCH" == finding.finding_id for finding in report.findings))


if __name__ == "__main__":
    unittest.main()
