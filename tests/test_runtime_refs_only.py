from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge.ir import MissionIR
from missionforge.runner import MissionResult, MissionRuntime
from tests.test_ir import sample_mission_payload


class RuntimeRefsOnlyTests(unittest.TestCase):
    def test_mission_result_is_refs_only(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        with TemporaryDirectory() as tmpdir:
            result = MissionRuntime(workspace=tmpdir).run(mission)

        payload = result.to_dict()
        payload_text = repr(payload)

        self.assertEqual(MissionResult.from_dict(payload), result)
        self.assertIn("package/SKILL.md", payload["artifact_refs"])
        self.assertNotIn("fake worker artifact", payload_text)
        self.assertNotIn("worker_claims", payload_text)
        self.assertNotIn("raw_conversation", payload_text)


if __name__ == "__main__":
    unittest.main()
