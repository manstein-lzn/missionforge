from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    ControlHalt,
    ControlPoint,
    ControlRequest,
    InMemoryEvidenceStore,
    ProposalValidator,
    WorkUnitCompiler,
    WorkUnitHarness,
)
from missionforge.contracts import ContractValidationError
from missionforge.fake_worker import FakeWorker
from tests.test_proposal_validation import valid_proposal


class ControlRequestTests(unittest.TestCase):
    def test_control_request_round_trip(self) -> None:
        request = ControlRequest(
            control_id="C-halt",
            control_type="halt",
            reason="pause requested",
            evidence_refs=["evidence/control.json"],
        )

        self.assertEqual(ControlRequest.from_dict(request.to_dict()), request)

    def test_unknown_control_type_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            ControlRequest(control_id="C-magic", control_type="magic", reason="nope").validate()

    def test_halt_control_blocks_worker_dispatch_at_safe_point(self) -> None:
        with TemporaryDirectory() as tmpdir:
            control_point = ControlPoint(
                requests=[ControlRequest(control_id="C-halt", control_type="halt", reason="stop now")]
            )
            validator = ProposalValidator(
                available_refs={"mission/frozen_contract.json"},
                allowed_output_roots=["attempts"],
            )
            harness = WorkUnitHarness(
                compiler=WorkUnitCompiler(mission_id="mission-001", validator=validator),
                worker=FakeWorker(),
                evidence_store=InMemoryEvidenceStore(),
                control_point=control_point,
            )

            with self.assertRaises(ControlHalt):
                harness.dispatch(valid_proposal(), workspace=tmpdir)

            self.assertFalse(Path(tmpdir, "attempts/001/artifact.txt").exists())
            self.assertEqual(len(harness.decision_ledger), 1)


if __name__ == "__main__":
    unittest.main()
