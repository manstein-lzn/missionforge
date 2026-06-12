from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import ProposalValidationStatus
from missionforge.contracts import AdaptiveDecision
from missionforge.steering import DecisionLedgerEntry, SteeringContext, SteeringProposal
from missionforge.steering_store import SteeringArtifactStore


class ControlledSteeringStoreTests(unittest.TestCase):
    def test_store_writes_and_collects_run_local_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = SteeringArtifactStore(tmpdir)
            context = SteeringContext(
                mission_run_id="run-mission-001",
                mission_id="mission-001",
                iteration=1,
                contract_ref="mission/frozen_contract.json",
                contract_hash="sha256:abc",
                mission_run_ref="runs/run-mission-001/mission_run.json",
                artifact_hygiene_ref="runs/run-mission-001/artifact_hygiene.json",
                allowed_output_roots=["package"],
                visible_refs=["mission/frozen_contract.json"],
                safe_summary="Initial dispatch.",
            )
            proposal = SteeringProposal(
                proposal_id="proposal-001",
                mission_run_id="run-mission-001",
                iteration=1,
                input_refs=["mission/frozen_contract.json"],
                recommended_route=AdaptiveDecision.CONTINUE,
                proposed_contract={
                    "next_objective": "Write artifact.",
                    "allowed_scope": ["package"],
                    "visible_refs": ["mission/frozen_contract.json"],
                    "expected_outputs": ["package/SKILL.md"],
                },
            )

            context_ref = store.write_context(context)
            proposal_ref = store.write_proposal(proposal)
            ledger_ref = store.append_decision(
                mission_run_id="run-mission-001",
                iteration=1,
                decision=DecisionLedgerEntry(
                    entry_id="D-000001",
                    proposal_id="proposal-001",
                    status=ProposalValidationStatus.ACCEPTED,
                    accepted_contract_ref="work_units/WU-000001.json",
                ),
            )

            refs = store.collect_refs("run-mission-001")
            latest = store.latest_refs("run-mission-001")

            self.assertTrue(Path(tmpdir, context_ref).is_file())
            self.assertTrue(Path(tmpdir, proposal_ref).is_file())
            self.assertTrue(Path(tmpdir, ledger_ref).is_file())
            self.assertIn(context_ref, refs)
            self.assertIn(proposal_ref, refs)
            self.assertEqual(latest["steering_context_ref"], context_ref)
            self.assertEqual(latest["latest_steering_proposal_ref"], proposal_ref)
            self.assertEqual(latest["decision_ledger_ref"], ledger_ref)


if __name__ == "__main__":
    unittest.main()
