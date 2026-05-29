from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.ir import MissionIR
from missionforge_skillfoundry import (
    BUNDLE_MANIFEST_SCHEMA_VERSION,
    BundleProfile,
    PROMPT_ONLY_MANIFEST_REQUIRED_KEYS,
    SkillFoundryMissionCompiler,
    SkillFoundryRequest,
    SkillProductContract,
    compile_skillfoundry_bundle,
)

from test_product_contract import code_runtime_request, codexarium_runtime_request, sample_request


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
            self.assertIn("json_field_exists", validator_types)
            self.assertIn("command", validator_types)
            self.assertEqual(
                mission.verification["verification_profiles"],
                [{"profile_id": "generic_local_verification"}],
            )
            self.assertTrue((root / result.frozen_contract_ref).exists())

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


if __name__ == "__main__":
    unittest.main()
