from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import MissionIR, MissionRuntime
from tests.test_ir import sample_mission_payload


class RuntimeRouteTests(unittest.TestCase):
    def test_missing_artifact_routes_to_failed_with_constraint_ids(self) -> None:
        payload = sample_mission_payload()
        payload["outputs"]["required_artifacts"] = ["package/SKILL.md", "package/MISSING.md"]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failed_constraint_ids, ["C-001"])

    def test_manual_gate_routes_to_review_required(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["manual_gates"] = [{"authority": "reviewer", "severity": "blocking"}]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        self.assertEqual(result.status, "review_required")

    def test_unsupported_validator_routes_to_unsupported_verification_spec(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-unsupported",
                "constraint_refs": ["C-001"],
                "type": "file_exists",
                "mode": "unsupported",
                "inputs": {"path": "package/SKILL.md"},
            }
        ]
        mission = MissionIR.from_dict(payload)

        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        self.assertEqual(result.status, "unsupported_verification_spec")


if __name__ == "__main__":
    unittest.main()
