from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from missionforge import ContractValidationError
from missionforge.freeze import freeze_mission
from missionforge.ir import MissionIR
from missionforge.revision import MissionRevisionRequest, MissionRevisionWorkflow
from missionforge.revision_store import MissionRevisionStore, apply_mission_revision
from missionforge.runner import MissionRuntime
from missionforge.steering import ContractAdjustmentRequest
from missionforge.state import MissionRun
from tests.test_ir import sample_mission_payload


class MissionRevisionWorkflowTests(unittest.TestCase):
    def test_revision_store_records_revision_on_mission_run(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            MissionRuntime(workspace=root).run(mission)
            store = MissionRevisionStore(root)
            refs = store.refs("run-sample-mission", "revision-000001")
            old_contract = freeze_mission(mission)
            adjustment = ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-001",
                    "mission_run_id": "run-sample-mission",
                    "iteration": 1,
                    "contract_ref": "mission/frozen_contract.json",
                    "requested_change": "split",
                    "reason": "Split work.",
                    "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
                    "authority_required": "harness",
                }
            )
            request = MissionRevisionRequest.from_adjustment(
                adjustment,
                base_contract_ref="mission/frozen_contract.json",
                base_contract_hash=old_contract.contract_hash,
                request_ref=refs["request"],
                revision_id="revision-000001",
            )
            workflow = MissionRevisionWorkflow()
            decision = workflow.decide(request)
            revised_mission, new_contract, revision = workflow.apply(
                mission,
                request,
                decision,
                old_contract=old_contract,
                new_contract_ref=refs["contract"],
                decision_ref=refs["decision"],
            )

            store.write_request(request)
            store.write_decision(decision)
            store.write_contract(request.mission_run_id, request.revision_id, new_contract)
            revision_ref = store.write_revision(revision)
            store.record_on_mission_run("run-sample-mission", revision)
            store.record_on_mission_run("run-sample-mission", revision)
            run = MissionRun.from_dict(json.loads((root / "runs/run-sample-mission/mission_run.json").read_text()))

            self.assertEqual(revised_mission.repair_policy["mission_revisions"][0]["requested_change"], "split")
            self.assertEqual(revision_ref, refs["revision"])
            self.assertEqual(run.current_contract_ref, refs["contract"])
            self.assertEqual(run.current_contract_hash, revision.new_contract_hash)
            self.assertIn(refs["revision"], run.revision_refs)
            self.assertEqual(run.revision_refs.count(refs["revision"]), 1)
            self.assertEqual(store.load_revision("run-sample-mission", "revision-000001"), revision)

    def test_apply_mission_revision_writes_full_durable_transition(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            MissionRuntime(workspace=root).run(mission)
            adjustment = ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-001",
                    "mission_run_id": "run-sample-mission",
                    "iteration": 1,
                    "contract_ref": "runs/run-sample-mission/contracts/base/frozen_contract.json",
                    "requested_change": "split",
                    "reason": "Split work.",
                    "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
                    "authority_required": "harness",
                }
            )

            revision = apply_mission_revision(workspace=root, mission=mission, adjustment=adjustment)
            store = MissionRevisionStore(root)
            run = MissionRun.from_dict(json.loads((root / "runs/run-sample-mission/mission_run.json").read_text()))

            self.assertTrue((root / "runs/run-sample-mission/revisions/revision-000001/mission_ir.json").is_file())
            self.assertEqual(revision.new_mission_ref, "runs/run-sample-mission/revisions/revision-000001/mission_ir.json")
            self.assertEqual(run.current_contract_ref, revision.new_contract_ref)
            self.assertEqual(run.current_contract_hash, revision.new_contract_hash)
            self.assertIn(store.refs("run-sample-mission", "revision-000001")["revision"], run.revision_refs)

    def test_unapproved_apply_mission_revision_does_not_activate_contract(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            MissionRuntime(workspace=root).run(mission)
            run_path = root / "runs/run-sample-mission/mission_run.json"
            before = MissionRun.from_dict(json.loads(run_path.read_text()))
            adjustment = ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-002",
                    "mission_run_id": "run-sample-mission",
                    "iteration": 2,
                    "contract_ref": before.current_contract_ref,
                    "requested_change": "expand",
                    "reason": "Expansion requires review.",
                    "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
                    "authority_required": "reviewer",
                }
            )

            with self.assertRaisesRegex(ContractValidationError, "not approved"):
                apply_mission_revision(workspace=root, mission=mission, adjustment=adjustment)

            after = MissionRun.from_dict(json.loads(run_path.read_text()))

            self.assertEqual(after.current_contract_ref, before.current_contract_ref)
            self.assertEqual(after.current_contract_hash, before.current_contract_hash)
            self.assertEqual(after.revision_refs, before.revision_refs)
            self.assertTrue((root / "runs/run-sample-mission/revisions/revision-000002/request.json").is_file())
            self.assertTrue((root / "runs/run-sample-mission/revisions/revision-000002/decision.json").is_file())
            self.assertFalse((root / "runs/run-sample-mission/revisions/revision-000002/revision.json").exists())

    def test_revision_activation_fails_closed_when_revision_write_fails(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            MissionRuntime(workspace=root).run(mission)
            run_path = root / "runs/run-sample-mission/mission_run.json"
            before = MissionRun.from_dict(json.loads(run_path.read_text()))
            adjustment = ContractAdjustmentRequest.from_dict(
                {
                    "request_id": "adjust-003",
                    "mission_run_id": "run-sample-mission",
                    "iteration": 3,
                    "contract_ref": before.current_contract_ref,
                    "requested_change": "split",
                    "reason": "Split work.",
                    "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
                    "authority_required": "harness",
                }
            )

            with patch.object(
                MissionRevisionStore,
                "write_revision",
                side_effect=ContractValidationError("simulated revision write failure"),
            ):
                with self.assertRaisesRegex(ContractValidationError, "simulated revision write failure"):
                    apply_mission_revision(workspace=root, mission=mission, adjustment=adjustment)

            after = MissionRun.from_dict(json.loads(run_path.read_text()))

            self.assertEqual(after.current_contract_ref, before.current_contract_ref)
            self.assertEqual(after.current_contract_hash, before.current_contract_hash)
            self.assertEqual(after.revision_refs, before.revision_refs)
            self.assertFalse((root / "runs/run-sample-mission/revisions/revision-000003/revision.json").exists())


if __name__ == "__main__":
    unittest.main()
