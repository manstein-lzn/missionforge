from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import InMemoryEvidenceStore, ReviewerDecision, VerificationSpec, Verifier
from missionforge.contracts import EvidenceTrustLevel, VerificationStatus


class VerifierTests(unittest.TestCase):
    def test_blocking_executable_failure_returns_failed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = Verifier(workspace=tmpdir).verify(
                VerificationSpec.from_dict(
                    {
                        "validators": [
                            {
                                "validator_id": "V-missing",
                                "constraint_refs": ["C-001"],
                                "type": "file_exists",
                                "inputs": {"path": "missing.txt"},
                            }
                        ]
                    }
                )
            )

            self.assertEqual(result.status, VerificationStatus.FAILED)
            self.assertEqual(result.failed_constraint_ids, ["C-001"])
            self.assertEqual(result.failed_constraints[0].validator_id, "V-missing")
            self.assertTrue(result.evidence_refs)

    def test_delegatable_manual_gate_returns_review_required(self) -> None:
        result = Verifier().verify(
            VerificationSpec.from_dict(
                {
                    "validators": [
                        {
                            "validator_id": "V-review",
                            "constraint_refs": ["C-001"],
                            "type": "manual_acceptance",
                            "mode": "manual",
                            "inputs": {"authority": "reviewer"},
                        }
                    ]
                }
            )
        )

        self.assertEqual(result.status, VerificationStatus.REVIEW_REQUIRED)

    def test_user_authority_gate_returns_human_acceptance_required(self) -> None:
        result = Verifier().verify(
            VerificationSpec.from_dict(
                {
                    "validators": [
                        {
                            "validator_id": "V-user",
                            "constraint_refs": ["C-001"],
                            "type": "manual_acceptance",
                            "mode": "manual",
                            "inputs": {"authority": "user"},
                        }
                    ]
                }
            )
        )

        self.assertEqual(result.status, VerificationStatus.HUMAN_ACCEPTANCE_REQUIRED)

    def test_unsupported_blocking_validator_returns_unsupported_spec(self) -> None:
        result = Verifier().verify(
            VerificationSpec.from_dict(
                {
                    "validators": [
                        {
                            "validator_id": "V-future",
                            "constraint_refs": ["C-001"],
                            "type": "future_validator",
                            "mode": "unsupported",
                        }
                    ]
                }
            )
        )

        self.assertEqual(result.status, VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC)

    def test_advisory_failure_becomes_warning(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = Verifier(workspace=tmpdir).verify(
                VerificationSpec.from_dict(
                    {
                        "validators": [
                            {
                                "validator_id": "V-advisory",
                                "constraint_refs": ["C-001"],
                                "type": "file_exists",
                                "severity": "advisory",
                                "inputs": {"path": "missing.txt"},
                            }
                        ]
                    }
                )
            )

            self.assertEqual(result.status, VerificationStatus.COMPLETED_VERIFIED)
            self.assertEqual(result.failed_constraint_ids, [])
            self.assertTrue(result.warnings)

    def test_current_reviewer_decision_completes_manual_gate(self) -> None:
        verifier = Verifier(contract_hash="sha256:contract", capsule_id="capsule-1", capsule_revision=2)
        decision = ReviewerDecision(
            reviewer_id="reviewer",
            decision="approved",
            contract_hash="sha256:contract",
            capsule_id="capsule-1",
            capsule_revision=2,
            evidence_refs=["evidence/review.json"],
        )
        result = verifier.verify(
            VerificationSpec.from_dict(
                {
                    "validators": [
                        {
                            "validator_id": "V-review",
                            "constraint_refs": ["C-001"],
                            "type": "manual_acceptance",
                            "mode": "manual",
                        }
                    ]
                }
            ),
            reviewer_decision=decision,
        )

        self.assertEqual(result.status, VerificationStatus.COMPLETED_VERIFIED)
        self.assertEqual(result.validator_results[0].evidence_refs, ["evidence/review.json"])

    def test_worker_claim_evidence_cannot_satisfy_required_trust(self) -> None:
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "artifact.txt").write_text("ready", encoding="utf-8")
            store = InMemoryEvidenceStore()
            worker_claim = store.append(
                payload={"claim": "artifact exists"},
                trust_level=EvidenceTrustLevel.UNTRUSTED_WORKER_CLAIM,
                kind="worker_claim",
            )
            result = Verifier(workspace=tmpdir, evidence_store=store).verify(
                VerificationSpec.from_dict(
                    {
                        "validators": [
                            {
                                "validator_id": "V-trust",
                                "constraint_refs": ["C-001"],
                                "type": "file_exists",
                                "inputs": {
                                    "path": "artifact.txt",
                                    "required_evidence_ids": [worker_claim.evidence_id],
                                    "minimum_trust_level": "verifier_result",
                                },
                            }
                        ]
                    }
                )
            )

            self.assertEqual(result.status, VerificationStatus.FAILED)
            self.assertEqual(result.missing_evidence[0].actual_trust_level, "untrusted_worker_claim")


if __name__ == "__main__":
    unittest.main()
