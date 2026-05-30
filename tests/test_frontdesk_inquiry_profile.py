from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.frontdesk import (
    CompilerReadiness,
    InquirySlot,
    ProductInquiryProfile,
    SlotRequirement,
    SlotTargetMapping,
    SlotValueType,
)


class FrontDeskInquiryProfileTests(unittest.TestCase):
    def test_round_trip_full_profile(self) -> None:
        profile = _profile()

        restored = ProductInquiryProfile.from_dict(profile.to_dict())

        self.assertEqual(restored.product_id, "example_product")
        self.assertEqual(restored.profile_hash, profile.profile_hash)
        self.assertEqual(restored.slots[0].maps_to[0].target, "example.request.goal")

    def test_rejects_duplicate_slot_ids(self) -> None:
        slot = _slot("goal")
        with self.assertRaises(ContractValidationError):
            ProductInquiryProfile(
                product_id="example_product",
                version="v1",
                display_name="Example",
                slots=[slot, slot],
            ).validate()

    def test_rejects_enum_slot_without_choices(self) -> None:
        with self.assertRaises(ContractValidationError):
            InquirySlot(
                slot_id="mode",
                question="Which mode?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.ENUM,
                maps_to=[SlotTargetMapping(target="example.request.mode")],
            ).validate()

    def test_rejects_unknown_blocking_readiness_slot(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductInquiryProfile(
                product_id="example_product",
                version="v1",
                display_name="Example",
                slots=[_slot("goal")],
                compiler_readiness=CompilerReadiness(blocking_slot_ids=["missing"]),
            ).validate()

    def test_rejects_raw_fields_recursively(self) -> None:
        with self.assertRaises(ContractValidationError):
            InquirySlot(
                slot_id="goal",
                question="What goal?",
                requirement=SlotRequirement.BLOCKING,
                value_type=SlotValueType.FREE_TEXT,
                maps_to=[SlotTargetMapping(target="example.request.goal")],
                default_value={"raw_prompt": "do not store this"},
            ).validate()

    def test_product_specific_ids_are_data_only(self) -> None:
        profile = ProductInquiryProfile(
            product_id="skillfoundry",
            version="v1",
            display_name="SkillFoundry",
            slots=[_slot("goal")],
            compiler_readiness=CompilerReadiness(blocking_slot_ids=["goal"]),
        )

        self.assertEqual(ProductInquiryProfile.from_dict(profile.to_dict()).product_id, "skillfoundry")


def _slot(slot_id: str) -> InquirySlot:
    return InquirySlot(
        slot_id=slot_id,
        question="What is the goal?",
        requirement=SlotRequirement.BLOCKING,
        value_type=SlotValueType.FREE_TEXT,
        maps_to=[SlotTargetMapping(target=f"example.request.{slot_id}")],
    )


def _profile() -> ProductInquiryProfile:
    return ProductInquiryProfile(
        product_id="example_product",
        version="v1",
        display_name="Example Product",
        slots=[_slot("goal")],
        compiler_readiness=CompilerReadiness(blocking_slot_ids=["goal"]),
    )


if __name__ == "__main__":
    unittest.main()
