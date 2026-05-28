from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError, VerificationStatus
from missionforge.verification import VerificationResult, VerificationSpec, ValidatorResult, ValidatorSpec


class VerificationContractTests(unittest.TestCase):
    def test_validator_spec_round_trip(self) -> None:
        validator = ValidatorSpec.from_dict(
            {
                "validator_id": "V-001",
                "constraint_refs": ["C-001"],
                "type": "command",
                "mode": "executable",
                "severity": "blocking",
                "description": "Run tests.",
                "inputs": {"command": ["python3", "-m", "unittest"]},
            }
        )

        self.assertEqual(validator.mode.value, "executable")
        self.assertEqual(ValidatorSpec.from_dict(validator.to_dict()), validator)

    def test_validator_spec_rejects_invalid_mode(self) -> None:
        with self.assertRaises(ContractValidationError):
            ValidatorSpec.from_dict(
                {
                    "validator_id": "V-001",
                    "constraint_refs": ["C-001"],
                    "type": "command",
                    "mode": "magic",
                }
            )

    def test_verification_spec_rejects_duplicate_validator_ids(self) -> None:
        payload = {
            "validators": [
                {"validator_id": "V-001", "constraint_refs": ["C-001"], "type": "file_exists"},
                {"validator_id": "V-001", "constraint_refs": ["C-002"], "type": "command"},
            ]
        }

        with self.assertRaises(ContractValidationError):
            VerificationSpec.from_dict(payload)

    def test_verification_result_round_trip(self) -> None:
        result = VerificationResult(
            status=VerificationStatus.FAILED,
            validator_results=[
                ValidatorResult(
                    validator_id="V-001",
                    passed=False,
                    evidence_refs=["evidence/failure.json"],
                    message="Missing artifact.",
                )
            ],
            evidence_refs=["evidence/failure.json"],
            failed_constraint_ids=["C-001"],
            warnings=["advisory finding"],
        )

        self.assertEqual(VerificationResult.from_dict(result.to_dict()), result)
        self.assertEqual(ValidatorResult.from_dict(result.validator_results[0].to_dict()), result.validator_results[0])


if __name__ == "__main__":
    unittest.main()
