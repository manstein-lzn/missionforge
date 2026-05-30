from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.product_integration import (
    ProductClarificationQuestion,
    ProductCompileResult,
    ProductCompileStatus,
)


class ProductIntegrationContractTests(unittest.TestCase):
    def test_compile_result_round_trip(self) -> None:
        result = ProductCompileResult(
            product_id="product",
            status=ProductCompileStatus.COMPILED,
            intent_bundle_ref="frontdesk/intent_bundle.json",
            product_request_ref="product/request.json",
            product_contract_ref="product/contract.json",
            mission_ir_ref="missions/product.mission.json",
            frozen_contract_ref="missions/product.frozen_contract.json",
            product_gate_spec_ref="product/gate.json",
            evidence_refs=["evidence/product_compile.json"],
        )

        restored = ProductCompileResult.from_dict(result.to_dict())

        self.assertEqual(restored.status, ProductCompileStatus.COMPILED)
        self.assertEqual(restored.artifact_refs.mission_ir_ref, "missions/product.mission.json")

    def test_compiled_status_requires_mission_ref(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductCompileResult(
                product_id="product",
                status=ProductCompileStatus.COMPILED,
                intent_bundle_ref="frontdesk/intent_bundle.json",
            ).validate()

    def test_clarification_status_requires_missing_slots_or_questions(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductCompileResult(
                product_id="product",
                status=ProductCompileStatus.NEEDS_CLARIFICATION,
                intent_bundle_ref="frontdesk/intent_bundle.json",
            ).validate()

    def test_clarification_request_projection(self) -> None:
        result = ProductCompileResult(
            product_id="product",
            status=ProductCompileStatus.NEEDS_CLARIFICATION,
            intent_bundle_ref="frontdesk/intent_bundle.json",
            missing_slot_ids=["privacy_boundary"],
            clarification_questions=[
                ProductClarificationQuestion(
                    question_id="q-privacy",
                    slot_id="privacy_boundary",
                    question="What privacy boundary applies?",
                    source_refs=["frontdesk/intent_bundle.json"],
                )
            ],
        )

        request = result.clarification_request

        self.assertIsNotNone(request)
        self.assertEqual(request.missing_slot_ids, ["privacy_boundary"] if request else [])

    def test_rejects_unsafe_refs_and_raw_fields(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductCompileResult(
                product_id="product",
                status=ProductCompileStatus.COMPILED,
                intent_bundle_ref="../frontdesk/intent_bundle.json",
                mission_ir_ref="missions/product.mission.json",
            ).validate()
        with self.assertRaises(ContractValidationError):
            ProductClarificationQuestion.from_dict(
                {
                    "question_id": "q",
                    "slot_id": "slot",
                    "question": "Clarify?",
                    "source_refs": ["frontdesk/intent_bundle.json"],
                    "raw_prompt": "bad",
                }
            )


if __name__ == "__main__":
    unittest.main()
