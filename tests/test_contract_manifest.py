from __future__ import annotations

import unittest

from missionforge.freeze import freeze_mission
from missionforge.ir import MissionIR
from tests.test_ir import sample_mission_payload


class ContractManifestTests(unittest.TestCase):
    def test_manifest_records_profile_constraint_and_validator_ids(self) -> None:
        payload = sample_mission_payload()
        payload["verification"]["validators"] = [
            {
                "validator_id": "V-001",
                "constraint_refs": ["C-001"],
                "type": "file_exists",
            }
        ]
        frozen = freeze_mission(MissionIR.from_dict(payload))
        manifest = frozen.manifest

        self.assertEqual(manifest.mission_id, "sample-mission")
        self.assertEqual(manifest.contract_hash, frozen.contract_hash)
        self.assertIn("C-001", manifest.constraint_ids)
        self.assertIn("P-user_provided_evidence_only-C-001", manifest.constraint_ids)
        self.assertEqual(manifest.validator_ids, ["V-001"])
        self.assertTrue(all(item.startswith("sha256:") for item in manifest.profile_hashes))
        self.assertTrue(all(item.startswith("sha256:") for item in manifest.profile_ref_hashes))
        self.assertEqual(frozen.to_dict()["manifest"], manifest.to_dict())


if __name__ == "__main__":
    unittest.main()
