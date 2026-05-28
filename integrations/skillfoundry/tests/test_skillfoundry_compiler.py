from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge.freeze import freeze_mission
from missionforge.ir import MissionIR
from missionforge_skillfoundry import SkillFoundryMissionCompiler, SkillFoundrySourceBundle


def sample_bundle() -> SkillFoundrySourceBundle:
    return SkillFoundrySourceBundle.from_dict(
        {
            "bundle_id": "sf-source-001",
            "frontdesk_contract_ref": "frontdesk/task_contract.json",
            "source_manifest_ref": "frontdesk/source_manifest.json",
            "target_package_ref": "package/SKILL.md",
            "allowed_write_scopes": ["package", "attempts"],
            "capability_profile_refs": [
                {
                    "profile_id": "user_provided_evidence_only",
                    "requirements": {},
                },
                {
                    "profile_id": "explicit_output_root",
                    "requirements": {"output_root": "package"},
                },
            ],
            "verification_profile_refs": ["generic_local_verification"],
        }
    )


def write_frontdesk_fixture(root: Path, *, raw_manifest: bool = False) -> None:
    (root / "frontdesk").mkdir(parents=True)
    (root / "frontdesk/task_contract.json").write_text(
        json.dumps(
            {
                "mission_id": "skillfoundry-capability",
                "objective": {
                    "summary": "Build a verified SkillFoundry capability package.",
                    "deliverable_type": "capability_bundle",
                    "success_signals": ["Package validator passes."],
                },
                "constraints": [
                    {
                        "constraint_id": "SF-C-001",
                        "kind": "data_boundary",
                        "priority": "must",
                        "statement": "Use only admitted FrontDesk evidence refs.",
                        "source_refs": ["frontdesk/task_contract.json"],
                        "evidence_obligations": ["package/SKILL.md"],
                        "validator": None,
                        "repair_hints": ["Remove unreferenced product facts."],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    source_manifest = {
        "sources": [
            {
                "artifact_id": "source-001",
                "ref": "frontdesk/sanitized_task.json",
                "artifact_type": "sanitized_source",
            },
            {
                "artifact_id": "source-002",
                "ref": "frontdesk/sanitized_transcript.json",
                "artifact_type": "sanitized_transcript",
            },
        ]
    }
    if raw_manifest:
        source_manifest["sources"].append(
            {
                "artifact_id": "source-raw",
                "ref": "frontdesk/raw_transcript.json",
                "artifact_type": "raw_transcript",
            }
        )
    (root / "frontdesk/source_manifest.json").write_text(
        json.dumps(source_manifest, sort_keys=True),
        encoding="utf-8",
    )
    (root / "frontdesk/sanitized_task.json").write_text(
        json.dumps({"summary_ref": "frontdesk/task_contract.json"}, sort_keys=True),
        encoding="utf-8",
    )
    (root / "frontdesk/sanitized_transcript.json").write_text(
        json.dumps({"sanitized_ref": "frontdesk/task_contract.json"}, sort_keys=True),
        encoding="utf-8",
    )


class SkillFoundryCompilerTests(unittest.TestCase):
    def test_frontdesk_artifacts_compile_to_valid_mission_ir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)

            result = SkillFoundryMissionCompiler().compile(sample_bundle(), workspace=root)
            mission_payload = json.loads((root / result.mission_ir_ref).read_text(encoding="utf-8"))
            mission = MissionIR.from_dict(mission_payload)

            self.assertEqual(mission.mission_id, "skillfoundry-capability")
            self.assertEqual(result.target_package_ref, "package/SKILL.md")
            self.assertEqual(
                [profile.profile_id for profile in mission.capability_profiles],
                ["user_provided_evidence_only", "explicit_output_root"],
            )
            self.assertEqual(mission.outputs["required_artifacts"], ["package/SKILL.md"])
            self.assertIn("frontdesk/sanitized_task.json", mission.inputs["admitted_source_refs"])
            self.assertTrue((root / result.frozen_contract_ref).exists())
            self.assertEqual(result.diagnostic_refs, ["evidence/sf-source-001.skillfoundry_compile_diagnostics.json"])

    def test_generated_mission_ir_freezes_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)
            compiler = SkillFoundryMissionCompiler()

            first = compiler.compile(sample_bundle(), workspace=root)
            second = compiler.compile(sample_bundle(), workspace=root)
            mission = MissionIR.from_dict(json.loads((root / first.mission_ir_ref).read_text(encoding="utf-8")))

            self.assertEqual(first.contract_hash, second.contract_hash)
            self.assertEqual(first.contract_hash, freeze_mission(mission).contract_hash)

    def test_capability_bundle_behavior_uses_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)

            result = SkillFoundryMissionCompiler().compile(sample_bundle(), workspace=root)
            frozen_payload = json.loads((root / result.frozen_contract_ref).read_text(encoding="utf-8"))
            expansions = frozen_payload["expanded_mission"]["profile_expansions"]

            self.assertEqual(
                [item["source_profile_id"] for item in expansions],
                ["user_provided_evidence_only", "explicit_output_root", "generic_local_verification"],
            )
            self.assertIn("P-user_provided_evidence_only-C-001", frozen_payload["manifest"]["constraint_ids"])
            self.assertIn("P-explicit_output_root-C-001", frozen_payload["manifest"]["constraint_ids"])

    def test_compiler_rejects_capability_bundle_without_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)
            bundle_payload = sample_bundle().to_dict()
            bundle_payload["capability_profile_refs"] = []

            with self.assertRaisesRegex(ContractValidationError, "capability_profile_refs"):
                SkillFoundrySourceBundle.from_dict(bundle_payload)

    def test_compile_result_is_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)

            result = SkillFoundryMissionCompiler().compile(sample_bundle(), workspace=root)
            result_text = json.dumps(result.to_dict(), sort_keys=True)

            self.assertIn("missions/sf-source-001.mission.json", result_text)
            self.assertNotIn("Build a verified SkillFoundry capability package", result_text)
            self.assertNotIn("summary_ref", result_text)
            self.assertNotIn("sanitized_ref", result_text)

    def test_raw_transcript_manifest_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root, raw_manifest=True)

            with self.assertRaisesRegex(ContractValidationError, "sanitized source ref"):
                SkillFoundryMissionCompiler().compile(sample_bundle(), workspace=root)

    def test_raw_transcript_payload_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            write_frontdesk_fixture(root)
            manifest_path = root / "frontdesk/source_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["raw_transcript"] = "raw private material"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "sanitized source ref"):
                SkillFoundryMissionCompiler().compile(sample_bundle(), workspace=root)


if __name__ == "__main__":
    unittest.main()
