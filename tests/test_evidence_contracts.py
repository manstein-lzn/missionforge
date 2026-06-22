from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError, EvidenceTrustLevel
from missionforge.evidence import ArtifactRef, EvidenceRef, require_trust_for_acceptance, trust_satisfies


class EvidenceContractTests(unittest.TestCase):
    def test_evidence_ref_round_trip(self) -> None:
        evidence = EvidenceRef.from_dict(
            {
                "evidence_id": "E-001",
                "ref": "evidence/schema_check.json",
                "trust_level": "schema_validation",
                "kind": "schema_check",
                "source_refs": ["attempts/001/report.json"],
            }
        )

        self.assertEqual(evidence.trust_level, EvidenceTrustLevel.SCHEMA_VALIDATION)
        self.assertEqual(EvidenceRef.from_dict(evidence.to_dict()), evidence)

    def test_artifact_ref_rejects_unsafe_ref(self) -> None:
        with self.assertRaises(ContractValidationError):
            ArtifactRef.from_dict({"artifact_id": "A-001", "ref": "../secret"})

    def test_worker_claim_does_not_satisfy_schema_validation_trust(self) -> None:
        evidence = EvidenceRef.from_dict(
            {
                "evidence_id": "E-worker",
                "ref": "attempts/001/worker_claim.json",
                "trust_level": "untrusted_worker_claim",
            }
        )

        self.assertFalse(trust_satisfies(evidence.trust_level, EvidenceTrustLevel.SCHEMA_VALIDATION))
        with self.assertRaises(ContractValidationError):
            require_trust_for_acceptance(evidence, EvidenceTrustLevel.SCHEMA_VALIDATION)

    def test_reviewer_decision_satisfies_artifact_ref(self) -> None:
        self.assertTrue(trust_satisfies(EvidenceTrustLevel.REVIEWER_DECISION, EvidenceTrustLevel.ARTIFACT_REF))


if __name__ == "__main__":
    unittest.main()
