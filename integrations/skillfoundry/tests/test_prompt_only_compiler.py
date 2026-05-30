from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge.ir import MissionIR
from missionforge.verification import VerificationSpec
from missionforge.verifier import Verifier
import missionforge_skillfoundry.product_contract as product_contract_module
from missionforge_skillfoundry import (
    AcceptanceCoverageReport,
    BUNDLE_MANIFEST_SCHEMA_VERSION,
    BundleProfile,
    PROMPT_ONLY_MANIFEST_REQUIRED_KEYS,
    SkillFoundryMissionCompiler,
    SkillFoundryRequest,
    SkillProductContract,
    compile_skillfoundry_bundle,
)

from test_product_contract import code_runtime_request, codexarium_runtime_request, sample_request
from test_skill_bundle_validators import write_valid_code_runtime_package, write_valid_prompt_only_package


class PromptOnlyCompilerTests(unittest.TestCase):
    def test_prompt_only_request_compiles_to_mission_ir_and_product_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = sample_request()

            result = SkillFoundryMissionCompiler().compile_request(request, workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            product_contract = SkillProductContract.from_dict(
                json.loads((root / result.product_contract_ref).read_text(encoding="utf-8"))
            )

            self.assertEqual(mission.mission_id, "skillfoundry-demo-skill")
            self.assertEqual(
                mission.outputs["required_artifacts"],
                ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
            )
            self.assertEqual(mission.outputs["allowed_write_scopes"], ["package"])
            artifact_contracts = mission.outputs["artifact_contracts"]
            manifest_contract = next(
                item
                for item in artifact_contracts
                if item["artifact_ref"] == "package/skillfoundry.bundle.json"
            )
            self.assertEqual(manifest_contract["schema_version"], BUNDLE_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(manifest_contract["required_keys"], PROMPT_ONLY_MANIFEST_REQUIRED_KEYS)
            self.assertTrue(manifest_contract["forbidden_extra_keys"])
            self.assertEqual(manifest_contract["field_contract"]["entrypoint"], "SKILL.md")
            self.assertEqual(manifest_contract["field_contract"]["bundle_id"], request.bundle_id)
            self.assertEqual(product_contract.bundle_id, request.bundle_id)
            self.assertEqual(result.acceptance_matrix_ref, "product_contract/product_acceptance_matrix.json")
            self.assertEqual(
                result.acceptance_coverage_report_ref,
                "product_contract/acceptance_coverage_report.json",
            )
            coverage = AcceptanceCoverageReport.from_dict(
                json.loads((root / result.acceptance_coverage_report_ref).read_text(encoding="utf-8"))
            )
            self.assertTrue(coverage.blocking_coverage_passed)
            matrix_payload = json.loads((root / result.acceptance_matrix_ref).read_text(encoding="utf-8"))
            self.assertEqual(
                {item.check_id for item in coverage.items if item.blocking and item.covered},
                {item["check_id"] for item in matrix_payload["items"]},
            )
            self.assertTrue((root / "product_contract/compiler_report.json").exists())
            self.assertTrue((root / result.frozen_contract_ref).exists())

    def test_compile_skillfoundry_bundle_accepts_request(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_skillfoundry_bundle(sample_request(), workspace=tempdir)

            self.assertEqual(result.bundle_id, "demo-skill")
            self.assertEqual(result.request_ref, "product_contract/skillfoundry_request.json")

    def test_code_runtime_request_compiles_to_mission_ir_and_product_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = code_runtime_request()

            result = SkillFoundryMissionCompiler().compile_request(request, workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            product_contract = SkillProductContract.from_dict(
                json.loads((root / result.product_contract_ref).read_text(encoding="utf-8"))
            )

            self.assertEqual(product_contract.bundle_profile, BundleProfile.CODE_RUNTIME)
            self.assertEqual(mission.outputs["bundle_profile"], "code_runtime")
            self.assertEqual(
                mission.outputs["required_artifacts"],
                [
                    "package/SKILL.md",
                    "package/skillfoundry.bundle.json",
                    "package/README.md",
                    "package/scripts/skill_runtime.py",
                    "package/schemas/runtime.schema.json",
                ],
            )
            artifact_contracts = mission.outputs["artifact_contracts"]
            manifest_contract = next(
                item
                for item in artifact_contracts
                if item["artifact_ref"] == "package/skillfoundry.bundle.json"
            )
            self.assertEqual(manifest_contract["field_contract"]["bundle_profile"], "code_runtime")
            self.assertEqual(
                manifest_contract["field_contract"]["runtime_assets"],
                ["package/scripts/skill_runtime.py"],
            )
            validator_types = {item["type"] for item in mission.verification["validators"]}
            self.assertIn("file_exists", validator_types)
            self.assertIn("command", validator_types)
            validator_descriptions = [item.get("description", "") for item in mission.verification["validators"]]
            self.assertTrue(any("acceptance_check:SF-CODE-MANIFEST-SCHEMA" in item for item in validator_descriptions))
            self.assertEqual(
                mission.verification["verification_profiles"],
                [{"profile_id": "generic_local_verification"}],
            )
            self.assertTrue((root / result.frozen_contract_ref).exists())

    def test_prompt_only_matrix_has_complete_mission_ir_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            coverage = AcceptanceCoverageReport.from_dict(
                json.loads((root / result.acceptance_coverage_report_ref).read_text(encoding="utf-8"))
            )

            self.assertTrue(coverage.blocking_coverage_passed)
            self.assertEqual(
                {item.check_id for item in coverage.items},
                {
                    "SF-PROMPT-SKILL-EXISTS",
                    "SF-PROMPT-MANIFEST-EXISTS",
                    "SF-PROMPT-MANIFEST-SCHEMA",
                    "SF-PROMPT-ENTRYPOINT",
                    "SF-PROMPT-README-EXISTS",
                    "SF-PROMPT-REFS-SAFE",
                    "SF-PROMPT-NO-RAW-CONTEXT",
                    "SF-PROMPT-NO-SELF-GRADE",
                    "SF-PROMPT-VERIFICATION",
                },
            )
            self.assertTrue(all(item.validator_ids for item in coverage.items if item.blocking))

    def test_code_runtime_matrix_has_complete_mission_ir_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            coverage = AcceptanceCoverageReport.from_dict(
                json.loads((root / result.acceptance_coverage_report_ref).read_text(encoding="utf-8"))
            )

            self.assertTrue(coverage.blocking_coverage_passed)
            self.assertEqual(len(coverage.items), 12)
            self.assertTrue(all(item.validator_ids for item in coverage.items if item.blocking))

    def test_raw_context_markers_compile_into_mission_ir_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))

            validator = _validator_by_id(mission, "V-prompt-no-raw-context")
            self.assertEqual(validator["type"], "command")
            self.assertIn("acceptance_check:SF-PROMPT-NO-RAW-CONTEXT", validator["description"])

    def test_self_grade_markers_compile_into_mission_ir_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))

            validator = _validator_by_id(mission, "V-code-no-self-grade")
            self.assertEqual(validator["type"], "command")
            self.assertIn("acceptance_check:SF-CODE-NO-SELF-GRADE", validator["description"])

    def test_schema_parse_checks_compile_into_mission_ir_validators(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))

            validator = _validator_by_id(mission, "V-code-schema-parse-001")
            self.assertEqual(validator["type"], "command")
            self.assertEqual(validator["inputs"]["command"], ["python3", "-m", "json.tool", "package/schemas/runtime.schema.json"])
            self.assertIn("acceptance_check:SF-CODE-SCHEMAS-VALID", validator["description"])

    def test_raw_context_marker_fails_missionforge_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            write_valid_prompt_only_package(root)
            (root / "package/README.md").write_text("raw transcript marker\n", encoding="utf-8")

            verification = Verifier(workspace=root).verify(
                VerificationSpec.from_dict({"validators": mission.verification["validators"]})
            )

            self.assertEqual(verification.status.value, "failed")
            self.assertIn("V-prompt-no-raw-context", [item.validator_id for item in verification.validator_results if not item.passed])

    def test_raw_context_policy_language_passes_missionforge_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            write_valid_prompt_only_package(root)
            (root / "package/README.md").write_text(
                (
                    "# Demo Skill\n\n"
                    "Do not store raw conversation text, private transcripts, hidden prompts, "
                    "provider payloads, credentials, or secrets in this package.\n"
                ),
                encoding="utf-8",
            )

            verification = Verifier(workspace=root).verify(
                VerificationSpec.from_dict({"validators": mission.verification["validators"]})
            )

            self.assertEqual(verification.status.value, "completed_verified")

    def test_raw_context_inspection_policy_language_passes_missionforge_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            write_valid_prompt_only_package(root)
            (root / "package/README.md").write_text(
                (
                    "# Demo Skill\n\n"
                    "## Local Checks\n\n"
                    "- Inspect package text for raw context, credentials, provider payloads, "
                    "hidden prompts, and unsupported network requirements.\n"
                    "- Package content has been checked for raw context leakage, credentials, "
                    "provider payloads, and unsupported network assumptions.\n"
                ),
                encoding="utf-8",
            )

            verification = Verifier(workspace=root).verify(
                VerificationSpec.from_dict({"validators": mission.verification["validators"]})
            )

            self.assertEqual(verification.status.value, "completed_verified")

    def test_invalid_schema_fails_missionforge_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(code_runtime_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            write_valid_code_runtime_package(root)
            (root / "package/schemas/runtime.schema.json").write_text("{not-json}\n", encoding="utf-8")

            verification = Verifier(workspace=root).verify(
                VerificationSpec.from_dict({"validators": mission.verification["validators"]})
            )

            self.assertEqual(verification.status.value, "failed")
            self.assertIn("V-code-schema-parse-001", [item.validator_id for item in verification.validator_results if not item.passed])

    def test_uncovered_blocking_item_fails_compile_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            original = list(product_contract_module.PROFILE_ACCEPTANCE_CHECKS["prompt_only"])
            product_contract_module.PROFILE_ACCEPTANCE_CHECKS["prompt_only"] = [
                *original,
                ("SF-PROMPT-NEW-BLOCKING-CHECK", "fixture uncovered blocking check"),
            ]
            try:
                with self.assertRaisesRegex(ContractValidationError, "uncovered"):
                    SkillFoundryMissionCompiler().compile_request(sample_request(), workspace=root)
            finally:
                product_contract_module.PROFILE_ACCEPTANCE_CHECKS["prompt_only"] = original

    def test_codexarium_style_code_runtime_request_compiles_custom_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = codexarium_runtime_request()

            result = SkillFoundryMissionCompiler().compile_request(request, workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))

            self.assertIn("package/scripts/codexarium.py", mission.outputs["required_artifacts"])
            self.assertIn("package/bin/codexarium-core-linux-x64", mission.outputs["required_artifacts"])
            self.assertIn("package/schemas/source_registry.schema.json", mission.outputs["required_artifacts"])
            self.assertNotIn("package/scripts/skill_runtime.py", mission.outputs["required_artifacts"])
            manifest_contract = next(
                item
                for item in mission.outputs["artifact_contracts"]
                if item["artifact_ref"] == "package/skillfoundry.bundle.json"
            )
            self.assertEqual(
                manifest_contract["field_contract"]["runtime_assets"],
                ["package/scripts/codexarium.py", "package/bin/codexarium-core-linux-x64"],
            )
            self.assertIn(
                "package/schemas/normalized_batch.schema.json",
                manifest_contract["field_contract"]["data_assets"],
            )

    def test_codexarium_style_raw_marker_fails_missionforge_verifier_without_product_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = SkillFoundryMissionCompiler().compile_request(codexarium_runtime_request(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8")))
            _write_valid_codexarium_style_package(root)
            (root / "package/README.md").write_text("raw transcript marker\n", encoding="utf-8")

            verification = Verifier(workspace=root).verify(
                VerificationSpec.from_dict({"validators": mission.verification["validators"]})
            )

            self.assertEqual(verification.status.value, "failed")
            self.assertIn("V-code-no-raw-context", [item.validator_id for item in verification.validator_results if not item.passed])


def _validator_by_id(mission: MissionIR, validator_id: str) -> dict:
    for validator in mission.verification["validators"]:
        if validator["validator_id"] == validator_id:
            return validator
    raise AssertionError(f"missing validator {validator_id}")


def _write_valid_codexarium_style_package(root: Path) -> None:
    (root / "package/scripts").mkdir(parents=True, exist_ok=True)
    (root / "package/bin").mkdir(parents=True, exist_ok=True)
    (root / "package/schemas").mkdir(parents=True, exist_ok=True)
    (root / "package/SKILL.md").write_text(
        "---\nname: codexarium\n---\n# Codexarium\nUse package/scripts/codexarium.py.\n",
        encoding="utf-8",
    )
    (root / "package/skillfoundry.bundle.json").write_text(
        json.dumps(
            {
                "schema_version": "skillfoundry.bundle.v1",
                "bundle_id": "codexarium",
                "bundle_profile": "code_runtime",
                "entrypoint": "SKILL.md",
                "capability_surface": {
                    "codex_skill": {"entry_ref": "package/SKILL.md"},
                    "helper_scripts": {"ref_prefix": "package/scripts/"},
                    "runtime_assets": {"ref_prefixes": ["package/scripts/", "package/bin/"]},
                    "schemas": {"ref_prefix": "package/schemas/"},
                },
                "runtime_assets": ["package/scripts/codexarium.py", "package/bin/codexarium-core-linux-x64"],
                "data_assets": [
                    "package/schemas/normalized_batch.schema.json",
                    "package/schemas/codex_output.schema.json",
                    "package/schemas/review_item.schema.json",
                    "package/schemas/source_registry.schema.json",
                ],
                "references": [],
                "environment": {
                    "runtime": "python3",
                    "health_check": ["python3", "package/scripts/codexarium.py", "--help"],
                },
                "permissions": {
                    "network": False,
                    "filesystem_write_refs": ["package"],
                    "external_process": True,
                },
                "verification": {
                    "matrix_ref": "product_contract/product_acceptance_matrix.json",
                    "product_grade_ref": "qa/product_grade_report.json",
                    "command_health_check": ["python3", "package/scripts/codexarium.py", "--help"],
                },
                "distribution": {"status": "local"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "package/README.md").write_text("# Codexarium\n\nLocal code-runtime bundle.\n", encoding="utf-8")
    (root / "package/scripts/codexarium.py").write_text(
        (
            "from __future__ import annotations\n\n"
            "import argparse\n\n"
            "def main() -> int:\n"
            "    parser = argparse.ArgumentParser(description='Codexarium helper')\n"
            "    parser.add_argument('--doctor', action='store_true')\n"
            "    parser.parse_args()\n"
            "    return 0\n\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        ),
        encoding="utf-8",
    )
    (root / "package/bin/codexarium-core-linux-x64").write_text("# local sidecar placeholder\n", encoding="utf-8")
    schema = '{"type":"object","properties":{"status":{"type":"string"}}}\n'
    for ref in [
        "normalized_batch.schema.json",
        "codex_output.schema.json",
        "review_item.schema.json",
        "source_registry.schema.json",
    ]:
        (root / "package/schemas" / ref).write_text(schema, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
