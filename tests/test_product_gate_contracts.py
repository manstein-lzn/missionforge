from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge.product_gate import (
    ProductGateCheck,
    ProductGateFinding,
    ProductGateResult,
    ProductGateSeverity,
    ProductGateSpec,
    ProductGateStatus,
)


class ProductGateContractTests(unittest.TestCase):
    def test_round_trip_spec_and_result(self) -> None:
        spec = ProductGateSpec(
            product_id="product",
            gate_id="product-grade",
            checks=[
                ProductGateCheck(
                    check_id="PRODUCT-SPECIFIC-CHECK",
                    purpose="Opaque product-specific check.",
                    evidence_refs=["evidence/check.json"],
                )
            ],
            source_refs=["product/gate_source.json"],
        )
        result = ProductGateResult(
            product_id="product",
            status=ProductGateStatus.PASSED,
            gate_spec_ref="product/gate.json",
            evidence_refs=["evidence/check.json"],
        )

        self.assertEqual(ProductGateSpec.from_dict(spec.to_dict()).checks[0].check_id, "PRODUCT-SPECIFIC-CHECK")
        self.assertEqual(ProductGateResult.from_dict(result.to_dict()).status, ProductGateStatus.PASSED)

    def test_blocking_finding_prevents_pass(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductGateResult(
                product_id="product",
                status=ProductGateStatus.PRODUCT_GRADE,
                gate_spec_ref="product/gate.json",
                findings=[
                    ProductGateFinding(
                        check_id="PRODUCT-SPECIFIC-CHECK",
                        severity=ProductGateSeverity.BLOCKING,
                        message="Missing required artifact.",
                    )
                ],
            ).validate()

    def test_rejects_raw_provider_payload_fields(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProductGateFinding.from_dict(
                {
                    "check_id": "PRODUCT-SPECIFIC-CHECK",
                    "severity": "blocking",
                    "message": "Bad payload.",
                    "evidence_refs": [],
                    "provider_payload": {"secret": "x"},
                }
            )

    def test_product_check_ids_are_opaque(self) -> None:
        check = ProductGateCheck(
            check_id="SF-CODE-RUNTIME-ASSETS-EXIST",
            purpose="The core must not interpret this id.",
        )

        self.assertEqual(ProductGateCheck.from_dict(check.to_dict()).check_id, "SF-CODE-RUNTIME-ASSETS-EXIST")


if __name__ == "__main__":
    unittest.main()
