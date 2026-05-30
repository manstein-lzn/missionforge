from __future__ import annotations

import unittest

from missionforge_skillfoundry.frontdesk_context import SkillFoundryInquiryProfile


class SkillFoundryFrontDeskContextTests(unittest.TestCase):
    def test_skillfoundry_inquiry_profile_validates(self) -> None:
        profile = SkillFoundryInquiryProfile()

        self.assertEqual(profile.product_id, "skillfoundry")
        self.assertEqual(
            [slot.slot_id for slot in profile.slots],
            [
                "capability_goal",
                "target_user",
                "trigger_scenarios",
                "non_trigger_scenarios",
                "bundle_profile",
                "required_package_outputs",
                "runtime_assets_required",
                "data_assets_required",
                "privacy_boundary",
                "distribution_boundary",
            ],
        )
        self.assertEqual(
            [risk.risk_id for risk in profile.risk_dimensions],
            [
                "raw_context_leakage",
                "self_grade_claim",
                "runtime_execution",
                "filesystem_write",
                "external_document_ingestion",
            ],
        )
        self.assertEqual(SkillFoundryInquiryProfile().profile_hash, profile.profile_hash)


if __name__ == "__main__":
    unittest.main()
