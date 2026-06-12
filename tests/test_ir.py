from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from missionforge import Ref
from missionforge.ir import MissionIR, MissionValidationError
from missionforge.runner import MissionResult, MissionRuntime


def sample_mission_payload() -> dict:
    return {
        "schema_version": "missionforge.mission_ir.v1",
        "mission_id": "sample-mission",
        "objective": {
            "summary": "Build a verified local capability bundle.",
            "deliverable_type": "capability_bundle",
            "success_signals": ["Verifier passes."],
        },
        "inputs": {
            "allowed_sources": ["sources/task_contract.json"],
            "forbidden_sources": ["raw_conversation"],
        },
        "outputs": {
            "required_artifacts": ["package/SKILL.md"],
            "allowed_write_scopes": ["package", "attempts"],
        },
        "constraints": [
            {
                "constraint_id": "C-001",
                "kind": "data_boundary",
                "priority": "must",
                "statement": "Use only user-provided evidence.",
                "source_refs": ["sources/task_contract.json"],
                "evidence_obligations": ["package/SKILL.md"],
                "validator": "static_text_boundary",
                "repair_hints": ["Update the safety section."],
            }
        ],
        "capability_profiles": [
            {
                "profile_id": "user_provided_evidence_only",
                "requirements": {},
            }
        ],
        "verification": {"required_evidence": ["verifier/verification_result.json"]},
        "repair_policy": {"rules": []},
        "budget": {},
        "observability": {},
    }


class MissionIRTests(unittest.TestCase):
    def test_mission_ir_round_trip(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        self.assertEqual(mission.mission_id, "sample-mission")
        self.assertEqual(mission.constraints[0].constraint_id, "C-001")
        self.assertEqual(mission.to_dict()["schema_version"], "missionforge.mission_ir.v1")

    def test_rejects_duplicate_constraints(self) -> None:
        payload = sample_mission_payload()
        payload["constraints"] = [payload["constraints"][0], dict(payload["constraints"][0])]

        with self.assertRaises(MissionValidationError):
            MissionIR.from_dict(payload)

    def test_runtime_accepts_valid_mission(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        self.assertEqual(result.status, "completed_verified")
        self.assertEqual(result.metrics["verification_status"], "completed_verified")

    def test_mission_result_round_trip_and_ref_export(self) -> None:
        result = MissionResult(
            mission_id="sample-mission",
            status="accepted",
            evidence_refs=["evidence/result.json"],
            artifact_refs=["package/SKILL.md"],
            failed_constraint_ids=["C-001"],
            metrics={"constraint_count": 1},
        )

        self.assertEqual(MissionResult.from_dict(result.to_dict()), result)
        self.assertEqual(Ref("evidence/result.json").to_dict(), {"value": "evidence/result.json"})


if __name__ == "__main__":
    unittest.main()
