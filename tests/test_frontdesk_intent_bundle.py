from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.frontdesk import (
    FrontDeskIntentBundle,
    IntentBundleReadiness,
    IntentGenericRefs,
    ProductContextSnapshot,
    SlotValue,
    SlotValueStatus,
)


class FrontDeskIntentBundleTests(unittest.TestCase):
    def test_round_trip_generic_bundle(self) -> None:
        bundle = FrontDeskIntentBundle(
            session_id="fd",
            intent_bundle_ref="frontdesk/intent_bundle.json",
            generic_refs=IntentGenericRefs(
                session_ref="frontdesk/session.json",
                mission_brief_ref="frontdesk/mission_brief.json",
            ),
            readiness=IntentBundleReadiness.GENERIC_COMPILE_ONLY,
        )

        restored = FrontDeskIntentBundle.from_dict(bundle.to_dict())

        self.assertEqual(restored.session_id, "fd")
        self.assertEqual(restored.readiness, IntentBundleReadiness.GENERIC_COMPILE_ONLY)
        self.assertEqual(restored.bundle_hash, bundle.bundle_hash)

    def test_ready_bundle_requires_no_blocking_missing_slots(self) -> None:
        with self.assertRaises(ContractValidationError):
            FrontDeskIntentBundle(
                session_id="fd",
                intent_bundle_ref="frontdesk/intent_bundle.json",
                generic_refs=IntentGenericRefs(),
                product_context=ProductContextSnapshot(product_id="product", display_name="Product"),
                missing_blocking_slots=["privacy_boundary"],
                readiness=IntentBundleReadiness.READY_FOR_PRODUCT_COMPILE,
            ).validate()

    def test_missing_blocking_slot_cannot_have_confirmed_value(self) -> None:
        with self.assertRaises(ContractValidationError):
            FrontDeskIntentBundle(
                session_id="fd",
                intent_bundle_ref="frontdesk/intent_bundle.json",
                generic_refs=IntentGenericRefs(),
                slot_values=[
                    SlotValue(
                        slot_id="goal",
                        status=SlotValueStatus.CONFIRMED,
                        value="Build the thing.",
                        source_refs=["frontdesk/mission_brief.json"],
                    )
                ],
                missing_blocking_slots=["goal"],
                readiness=IntentBundleReadiness.NEEDS_CLARIFICATION,
                clarification_questions=["What is the goal?"],
            ).validate()

    def test_profile_hash_must_be_sha256(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductContextSnapshot(
                product_id="product",
                display_name="Product",
                profile_hash="not-a-hash",
            ).validate()

    def test_rejects_raw_payload_fields(self) -> None:
        with self.assertRaises(ContractValidationError):
            SlotValue(
                slot_id="goal",
                status=SlotValueStatus.INFERRED,
                value={"transcript": "not allowed"},
                source_refs=["frontdesk/mission_brief.json"],
            ).validate()


if __name__ == "__main__":
    unittest.main()
