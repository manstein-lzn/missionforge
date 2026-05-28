from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    DeterministicProposalProvider,
    InMemoryEvidenceStore,
    ProposalValidationStatus,
    ProposalValidator,
    WorkUnitCompiler,
    WorkUnitHarness,
)
from missionforge.fake_worker import FakeWorker
from tests.test_proposal_validation import valid_proposal


class HarnessTests(unittest.TestCase):
    def test_deterministic_provider_returns_proposals_in_order(self) -> None:
        proposal = valid_proposal()
        provider = DeterministicProposalProvider([proposal])

        self.assertEqual(provider.next_proposal(), proposal)

    def test_rejected_proposal_is_recorded_in_decision_ledger(self) -> None:
        proposal = valid_proposal()
        proposal.proposed_contract["visible_refs"] = ["mission/missing.json"]
        validator = ProposalValidator(available_refs={"mission/frozen_contract.json"}, allowed_output_roots=["attempts"])
        harness = WorkUnitHarness(
            compiler=WorkUnitCompiler(mission_id="mission-001", validator=validator),
            worker=FakeWorker(),
            evidence_store=InMemoryEvidenceStore(),
        )

        validation = harness.evaluate(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertEqual(harness.decision_ledger[0].proposal_id, "P-001")
        self.assertEqual(harness.decision_ledger[0].status, ProposalValidationStatus.REJECTED)
        self.assertTrue(harness.decision_ledger[0].reasons)

    def test_valid_proposal_dispatches_fake_worker(self) -> None:
        with TemporaryDirectory() as tmpdir:
            proposal = valid_proposal()
            validator = ProposalValidator(
                available_refs={"mission/frozen_contract.json"},
                allowed_output_roots=["attempts"],
            )
            harness = WorkUnitHarness(
                compiler=WorkUnitCompiler(mission_id="mission-001", validator=validator),
                worker=FakeWorker(),
                evidence_store=InMemoryEvidenceStore(),
            )
            result = harness.dispatch(proposal, workspace=tmpdir)

            self.assertEqual(result.validation.status, ProposalValidationStatus.ACCEPTED)
            self.assertIsNotNone(result.work_unit)
            self.assertIsNotNone(result.execution_report)
            self.assertTrue(Path(tmpdir, "attempts/001/artifact.txt").exists())
            self.assertEqual(harness.decision_ledger[0].accepted_contract_ref, "work_units/WU-000001.json")


if __name__ == "__main__":
    unittest.main()
