from __future__ import annotations

import unittest

from missionforge import ProposalValidationStatus
from missionforge.contracts import AdaptiveDecision, ContractValidationError
from missionforge.harness import ProposalValidator, WorkUnitCompiler
from missionforge.steering import SteeringProposal


def valid_proposal() -> SteeringProposal:
    return SteeringProposal(
        proposal_id="P-001",
        mission_run_id="run-001",
        iteration=1,
        input_refs=["mission/frozen_contract.json"],
        recommended_route=AdaptiveDecision.CONTINUE,
        proposed_contract={
            "next_objective": "Write deterministic artifact.",
            "allowed_scope": ["attempts/001"],
            "visible_refs": ["mission/frozen_contract.json"],
            "expected_outputs": ["attempts/001/artifact.txt"],
            "exit_criteria": ["Artifact exists."],
            "stop_conditions": ["Halt control is active."],
        },
        rationale="Continue with bounded work.",
        confidence=0.7,
    )


class ProposalValidationTests(unittest.TestCase):
    def validator(self) -> ProposalValidator:
        return ProposalValidator(
            available_refs={"mission/frozen_contract.json"},
            allowed_output_roots=["attempts"],
        )

    def test_valid_proposal_is_accepted_and_compiled(self) -> None:
        proposal = valid_proposal()
        validation = self.validator().validate(proposal)
        work_unit = WorkUnitCompiler(mission_id="mission-001", validator=self.validator()).compile(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.ACCEPTED)
        self.assertEqual(validation.accepted_contract_ref, "work_units/WU-000001.json")
        self.assertEqual(work_unit.expected_outputs, ["attempts/001/artifact.txt"])

    def test_unsafe_path_is_rejected(self) -> None:
        proposal = valid_proposal()
        proposal.proposed_contract["expected_outputs"] = ["../secret.txt"]

        validation = self.validator().validate(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertTrue(any("parent segments" in reason for reason in validation.reasons))

    def test_missing_visible_ref_is_rejected(self) -> None:
        proposal = valid_proposal()
        proposal.proposed_contract["visible_refs"] = ["mission/missing.json"]

        validation = self.validator().validate(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertIn("missing visible ref: mission/missing.json", validation.reasons)

    def test_default_validator_fails_closed_without_boundary_context(self) -> None:
        validation = ProposalValidator().validate(valid_proposal())

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertIn("proposal validator requires explicit available_refs", validation.reasons)
        self.assertIn("proposal validator requires explicit allowed_output_roots", validation.reasons)

    def test_empty_boundary_context_means_no_refs_or_output_authority(self) -> None:
        no_refs = ProposalValidator(available_refs=set(), allowed_output_roots=["attempts"]).validate(valid_proposal())
        no_output_authority = ProposalValidator(
            available_refs={"mission/frozen_contract.json"},
            allowed_output_roots=[],
        ).validate(valid_proposal())

        self.assertEqual(no_refs.status, ProposalValidationStatus.REJECTED)
        self.assertIn("missing visible ref: mission/frozen_contract.json", no_refs.reasons)
        self.assertEqual(no_output_authority.status, ProposalValidationStatus.REJECTED)
        self.assertIn("allowed scope outside frozen authority: attempts/001", no_output_authority.reasons)

    def test_expected_output_outside_allowed_scope_is_rejected(self) -> None:
        proposal = valid_proposal()
        proposal.proposed_contract["expected_outputs"] = ["other/artifact.txt"]

        validation = self.validator().validate(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertIn("expected output outside allowed scope: other/artifact.txt", validation.reasons)

    def test_proposal_cannot_close_mission(self) -> None:
        proposal = valid_proposal()
        proposal = SteeringProposal(
            proposal_id=proposal.proposal_id,
            mission_run_id=proposal.mission_run_id,
            iteration=proposal.iteration,
            input_refs=proposal.input_refs,
            recommended_route=AdaptiveDecision.COMPLETE,
            proposed_contract=proposal.proposed_contract,
        )

        validation = self.validator().validate(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertTrue(any("cannot close a mission" in reason for reason in validation.reasons))

    def test_proposal_cannot_expand_frozen_contract_authority(self) -> None:
        proposal = valid_proposal()
        proposal.proposed_contract["verification"] = {"validators": []}

        validation = self.validator().validate(proposal)

        self.assertEqual(validation.status, ProposalValidationStatus.REJECTED)
        self.assertIn("proposal cannot expand frozen contract authority", validation.reasons)

    def test_compile_rejects_invalid_proposal(self) -> None:
        proposal = valid_proposal()
        proposal.proposed_contract["allowed_scope"] = ["outside"]

        with self.assertRaises(ContractValidationError):
            WorkUnitCompiler(mission_id="mission-001", validator=self.validator()).compile(proposal)


if __name__ == "__main__":
    unittest.main()
