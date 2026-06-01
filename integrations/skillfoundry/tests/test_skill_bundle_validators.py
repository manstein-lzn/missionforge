from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge_skillfoundry import BundleValidationCheck, SkillBundleManifest, SkillFoundryMissionCompiler, validate_skill_bundle
from missionforge_skillfoundry.product_grade_gate import PRODUCT_GRADE_REPORT_SCHEMA_VERSION, ProductGradeReport

from missionforge_skillfoundry.workspace import write_json_ref, write_text_ref
from test_product_contract import code_runtime_request, sample_request


def write_valid_prompt_only_package(root: Path, *, bundle_id: str = "demo-skill") -> None:
    write_text_ref(
        root,
        "package/SKILL.md",
        "---\nname: demo-skill\n---\n# Demo Skill\nUse this skill to review release notes.\n",
    )
    write_json_ref(root, "package/skillfoundry.bundle.json", SkillBundleManifest.prompt_only(bundle_id).to_dict())
    write_text_ref(root, "package/README.md", "# Demo Skill\n\nLocal prompt-only bundle.\n")


def write_valid_code_runtime_package(root: Path, *, bundle_id: str = "code-skill") -> None:
    write_text_ref(
        root,
        "package/SKILL.md",
        "---\nname: code-skill\n---\n# Code Skill\nUse this skill with package/scripts/skill_runtime.py.\n",
    )
    write_json_ref(
        root,
        "package/skillfoundry.bundle.json",
        SkillBundleManifest.code_runtime(
            bundle_id,
            runtime_assets=["package/scripts/skill_runtime.py"],
            data_assets=["package/schemas/runtime.schema.json"],
        ).to_dict(),
    )
    write_text_ref(root, "package/README.md", "# Code Skill\n\nRun `python3 package/scripts/skill_runtime.py --help`.\n")
    write_text_ref(
        root,
        "package/scripts/skill_runtime.py",
        (
            "from __future__ import annotations\n\n"
            "import argparse\n\n"
            "def main() -> int:\n"
            "    parser = argparse.ArgumentParser(description='Skill runtime helper')\n"
            "    parser.add_argument('--doctor', action='store_true')\n"
            "    parser.parse_args()\n"
            "    return 0\n\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        ),
    )
    write_text_ref(
        root,
        "package/schemas/runtime.schema.json",
        '{"type":"object","properties":{"status":{"type":"string"}},"required":["status"]}\n',
    )


class SkillBundleValidatorTests(unittest.TestCase):
    def test_valid_prompt_only_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertTrue(report.passed)
            self.assertTrue((root / "qa/skill_bundle_validation_report.json").exists())

    def test_missing_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_text_ref(root, "package/SKILL.md", "# Demo\n")
            write_text_ref(root, "package/README.md", "# Demo\n")

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertFalse(report.passed)
            self.assertIn("SF-PROMPT-MANIFEST-EXISTS", [check.check_id for check in report.blocking_failures])

    def test_raw_context_marker_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            write_text_ref(root, "package/README.md", "This contains raw_prompt details.\n")

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertFalse(report.passed)
            self.assertIn("SF-PROMPT-NO-RAW-CONTEXT", [check.check_id for check in report.blocking_failures])

    def test_raw_context_policy_language_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            write_text_ref(
                root,
                "package/README.md",
                (
                    "# Demo Skill\n\n"
                    "Do not store raw conversation text, private transcripts, hidden prompts, "
                    "provider payloads, credentials, or secrets in this package.\n"
                ),
            )

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertTrue(report.passed)

    def test_raw_context_non_trigger_policy_language_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            write_text_ref(
                root,
                "package/SKILL.md",
                (
                    "# Demo Skill\n\n"
                    "## Non-Trigger Conditions\n\n"
                    "Do not activate this skill for:\n\n"
                    "- Tiny factual answers.\n"
                    "- Work that requires a domain specialist.\n"
                    "- Requests to collect credentials, hidden prompts, provider payloads, "
                    "private transcripts, or unrelated local secrets.\n"
                ),
            )

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertTrue(report.passed)

    def test_raw_context_inspection_policy_language_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            write_text_ref(
                root,
                "package/README.md",
                (
                    "# Demo Skill\n\n"
                    "## Local Checks\n\n"
                    "- Inspect package text for raw context, credentials, provider payloads, "
                    "hidden prompts, and unsupported network requirements.\n"
                    "- Package content has been checked for raw context leakage, credentials, "
                    "provider payloads, and unsupported network assumptions.\n"
                ),
            )

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertTrue(report.passed)

    def test_self_product_grade_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            write_valid_prompt_only_package(root)
            write_text_ref(root, "package/SKILL.md", "# Demo\nproduct_grade_registered\n")

            report = validate_skill_bundle(workspace=root, bundle_id="demo-skill")

            self.assertFalse(report.passed)
            self.assertIn("SF-PROMPT-NO-SELF-GRADE", [check.check_id for check in report.blocking_failures])

    def test_valid_code_runtime_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            write_valid_code_runtime_package(root)

            report = validate_skill_bundle(workspace=root, bundle_id="code-skill")

            self.assertTrue(report.passed)
            self.assertIn("package/scripts/skill_runtime.py", report.package_refs)
            self.assertIn("package/schemas/runtime.schema.json", report.package_refs)

    def test_code_runtime_missing_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            write_valid_code_runtime_package(root)
            (root / "package/scripts/skill_runtime.py").unlink()

            report = validate_skill_bundle(workspace=root, bundle_id="code-skill")

            self.assertFalse(report.passed)
            self.assertIn("SF-CODE-RUNTIME-ASSETS-EXIST", [check.check_id for check in report.blocking_failures])

    def test_code_runtime_invalid_schema_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            write_valid_code_runtime_package(root)
            write_text_ref(root, "package/schemas/runtime.schema.json", "{not-json}\n")

            report = validate_skill_bundle(workspace=root, bundle_id="code-skill")

            self.assertFalse(report.passed)
            self.assertIn("SF-CODE-SCHEMAS-VALID", [check.check_id for check in report.blocking_failures])

    def test_code_runtime_self_grade_claim_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            write_valid_code_runtime_package(root)
            write_text_ref(root, "package/SKILL.md", "# Code Skill\nproduct_grade_registered\n")

            report = validate_skill_bundle(workspace=root, bundle_id="code-skill")

            self.assertFalse(report.passed)
            self.assertIn("SF-CODE-NO-SELF-GRADE", [check.check_id for check in report.blocking_failures])

    def test_validation_check_rejects_string_booleans(self) -> None:
        with self.assertRaises(ContractValidationError):
            BundleValidationCheck.from_dict(
                {
                    "check_id": "SF-CHECK",
                    "passed": "false",
                    "message": "Bad boolean.",
                }
            )

        with self.assertRaises(ContractValidationError):
            BundleValidationCheck.from_dict(
                {
                    "check_id": "SF-CHECK",
                    "passed": False,
                    "blocking": "false",
                    "message": "Bad boolean.",
                }
            )

    def test_product_grade_report_rejects_string_boolean(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductGradeReport.from_dict(
                {
                    "schema_version": PRODUCT_GRADE_REPORT_SCHEMA_VERSION,
                    "bundle_id": "demo-skill",
                    "package_refs": ["package/SKILL.md"],
                    "package_hash": "sha256:abc",
                    "verifier_status": "passed",
                    "verifier_refs": ["qa/verifier.json"],
                    "bundle_validation_report_ref": "qa/skill_bundle_validation_report.json",
                    "product_grade": "false",
                    "recommended_registry_status": "product_grade_registered",
                    "outcome_category": "product_grade_registered",
                }
            )


if __name__ == "__main__":
    unittest.main()
