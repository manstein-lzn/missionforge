from __future__ import annotations

import unittest

from missionforge import MissionIR, freeze_mission
from tests.test_ir import sample_mission_payload


class FreezeTests(unittest.TestCase):
    def test_freeze_mission_is_stable(self) -> None:
        first = freeze_mission(MissionIR.from_dict(sample_mission_payload()))
        second = freeze_mission(MissionIR.from_dict(sample_mission_payload()))

        self.assertEqual(first.contract_hash, second.contract_hash)
        self.assertEqual(first.manifest.contract_hash, first.contract_hash)
        self.assertTrue(first.contract_hash.startswith("sha256:"))

    def test_contract_relevant_change_changes_hash(self) -> None:
        base = sample_mission_payload()
        changed = sample_mission_payload()
        changed["constraints"][0]["statement"] = "Use only admitted sanitized evidence."

        base_hash = freeze_mission(MissionIR.from_dict(base)).contract_hash
        changed_hash = freeze_mission(MissionIR.from_dict(changed)).contract_hash

        self.assertNotEqual(base_hash, changed_hash)

    def test_capability_profile_requirements_change_hash(self) -> None:
        base = sample_mission_payload()
        changed = sample_mission_payload()
        changed["capability_profiles"][0]["requirements"] = {"output_root": "dist"}

        base_hash = freeze_mission(MissionIR.from_dict(base)).contract_hash
        changed_hash = freeze_mission(MissionIR.from_dict(changed)).contract_hash

        self.assertNotEqual(base_hash, changed_hash)

    def test_dict_key_order_does_not_change_hash(self) -> None:
        payload = sample_mission_payload()
        reordered_constraint = {
            "repair_hints": ["Update the safety section."],
            "validator": "static_text_boundary",
            "evidence_obligations": ["package/SKILL.md"],
            "source_refs": ["frontdesk/task_contract.json"],
            "statement": "Use only user-provided evidence.",
            "priority": "must",
            "kind": "data_boundary",
            "constraint_id": "C-001",
        }
        reordered = sample_mission_payload()
        reordered["constraints"] = [reordered_constraint]

        self.assertEqual(
            freeze_mission(MissionIR.from_dict(payload)).contract_hash,
            freeze_mission(MissionIR.from_dict(reordered)).contract_hash,
        )


if __name__ == "__main__":
    unittest.main()
