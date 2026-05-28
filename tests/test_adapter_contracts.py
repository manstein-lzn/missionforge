from __future__ import annotations

import unittest

from missionforge.adapters.contracts import (
    AdapterBoundary,
    AdapterDiagnostic,
    AdapterInvocation,
    AdapterResult,
)
from missionforge.contracts import ContractValidationError


class AdapterContractTests(unittest.TestCase):
    def test_adapter_boundary_round_trip_and_hash(self) -> None:
        boundary = AdapterBoundary(
            adapter_id="adapter-boundary",
            adapter_type="preflight",
            version="1.0",
            input_contract_refs=["contracts/work_unit.json"],
            output_contract_refs=["contracts/adapter_result.json"],
            capabilities=["refs_only"],
        )

        self.assertEqual(AdapterBoundary.from_dict(boundary.to_dict()), boundary)
        self.assertTrue(boundary.boundary_hash.startswith("sha256:"))

    def test_adapter_invocation_is_refs_only(self) -> None:
        invocation = AdapterInvocation.from_dict(
            {
                "invocation_id": "invoke-001",
                "adapter_id": "adapter-boundary",
                "input_refs": ["work_units/WU-000001.json"],
                "config_refs": ["config/adapter.json"],
                "evidence_refs": ["evidence/E-000001.json"],
            }
        )

        self.assertEqual(AdapterInvocation.from_dict(invocation.to_dict()), invocation)

    def test_adapter_result_round_trip(self) -> None:
        result = AdapterResult(
            invocation_id="invoke-001",
            adapter_id="adapter-boundary",
            status="completed",
            output_refs=["outputs/result.json"],
            evidence_refs=["evidence/E-000001.json"],
            diagnostic_refs=["diagnostics/D-000001.json"],
            metrics={"event_count": 1, "cache": {"hit_count": 0}},
        )

        self.assertEqual(AdapterResult.from_dict(result.to_dict()), result)

    def test_adapter_diagnostic_round_trip(self) -> None:
        diagnostic = AdapterDiagnostic(
            diagnostic_id="D-000001",
            severity="warning",
            message="Adapter fixture warning.",
            evidence_refs=["evidence/E-000001.json"],
        )

        self.assertEqual(AdapterDiagnostic.from_dict(diagnostic.to_dict()), diagnostic)

    def test_raw_payload_fields_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            AdapterResult.from_dict(
                {
                    "invocation_id": "invoke-001",
                    "adapter_id": "adapter-boundary",
                    "status": "completed",
                    "output_refs": ["outputs/result.json"],
                    "raw_payload": {"secret": "body"},
                }
            )

        with self.assertRaises(ContractValidationError):
            AdapterResult.from_dict(
                {
                    "invocation_id": "invoke-001",
                    "adapter_id": "adapter-boundary",
                    "status": "completed",
                    "metrics": {"transcript": "raw chat"},
                }
            )

    def test_secret_shaped_fields_are_rejected_recursively(self) -> None:
        forbidden_metric_payloads = [
            {"api_key": "sk-example"},
            {"access_token": "token"},
            {"password": "secret"},
            {"secret_key": "secret"},
            {"provider": {"refresh_token": "token"}},
            {"provider": {"prompt_text": "raw prompt"}},
        ]

        for metrics in forbidden_metric_payloads:
            with self.subTest(metrics=metrics):
                with self.assertRaises(ContractValidationError):
                    AdapterResult.from_dict(
                        {
                            "invocation_id": "invoke-001",
                            "adapter_id": "adapter-boundary",
                            "status": "completed",
                            "metrics": metrics,
                        }
                    )

    def test_unsafe_refs_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            AdapterInvocation.from_dict(
                {
                    "invocation_id": "invoke-001",
                    "adapter_id": "adapter-boundary",
                    "input_refs": ["../secret"],
                }
            )


if __name__ == "__main__":
    unittest.main()
