from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from missionforge import ContractValidationError
from missionforge.frontdesk.freeze_gate import FrontDeskFreezeGate
from missionforge.frontdesk.schema import FrontDeskFreezeManifest
from tests.test_frontdesk_compiler import sample_frontdesk_artifacts


class FrontDeskFreezeGateTests(unittest.TestCase):
    def test_no_approval_means_no_freeze(self) -> None:
        semantic_lock, brief, profiles, plan, _approval, sources = sample_frontdesk_artifacts()
        with self.assertRaisesRegex(ContractValidationError, "approval"):
            FrontDeskFreezeGate().freeze(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=plan,
                approval=None,
                sanitized_sources=sources,
            )

    def test_freeze_manifest_hash_matches_frozen_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            semantic_lock, brief, profiles, plan, approval, sources = sample_frontdesk_artifacts()
            result = FrontDeskFreezeGate().freeze(
                semantic_lock=semantic_lock,
                mission_brief=brief,
                profile_recommendations=profiles,
                mission_plan=plan,
                approval=approval,
                sanitized_sources=sources,
                workspace=tempdir,
            )
            manifest_payload = json.loads((Path(tempdir) / result.freeze_manifest_ref).read_text(encoding="utf-8"))
            frozen_payload = json.loads((Path(tempdir) / result.frozen_contract_ref).read_text(encoding="utf-8"))
            manifest = FrontDeskFreezeManifest.from_dict(manifest_payload)

            self.assertEqual(manifest.contract_hash, frozen_payload["contract_hash"])
            self.assertEqual(manifest.contract_hash, result.contract_hash)


if __name__ == "__main__":
    unittest.main()
