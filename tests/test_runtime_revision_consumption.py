from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError, MissionIR, RuntimeEngine
from missionforge.steering_store import SteeringArtifactStore
from tests.revision_repair_helpers import ResumableRevisionWorker, run_and_apply_split_revision
from tests.test_ir import sample_mission_payload


class RuntimeRevisionConsumptionTests(unittest.TestCase):
    def test_resume_uses_active_revised_contract_for_steering_and_state(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            revision = run_and_apply_split_revision(root, mission)

            RuntimeEngine(workspace=root, worker=ResumableRevisionWorker(), steering_mode="proposal", steering_provider=_ContextProvider()).resume(mission)
            run = json.loads((root / "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))
            latest_refs = SteeringArtifactStore(root).latest_refs("run-sample-mission")
            context = json.loads((root / latest_refs["steering_context_ref"]).read_text(encoding="utf-8"))

        self.assertEqual(run["current_contract_ref"], revision.new_contract_ref)
        self.assertEqual(run["current_contract_hash"], revision.new_contract_hash)
        self.assertEqual(context["contract_ref"], revision.new_contract_ref)
        self.assertEqual(context["contract_hash"], revision.new_contract_hash)
        self.assertEqual(context["visible_refs"], [revision.new_contract_ref])

    def test_stale_active_contract_hash_fails_closed_without_appending_attempt(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_and_apply_split_revision(root, mission)
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["current_contract_hash"] = "sha256:stale"
            run_path.write_text(json.dumps(run, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            before_attempts = (root / "runs/run-sample-mission/attempts.jsonl").read_text(encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "active contract hash"):
                RuntimeEngine(workspace=root, worker=ResumableRevisionWorker()).resume(mission)

            after_attempts = (root / "runs/run-sample-mission/attempts.jsonl").read_text(encoding="utf-8")

        self.assertEqual(after_attempts, before_attempts)

    def test_missing_active_contract_ref_fails_closed_without_appending_attempt(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            revision = run_and_apply_split_revision(root, mission)
            run_path = root / "runs/run-sample-mission/mission_run.json"
            before_attempts = (root / "runs/run-sample-mission/attempts.jsonl").read_text(encoding="utf-8")
            (root / revision.new_contract_ref).unlink()

            with self.assertRaisesRegex(ContractValidationError, "active contract ref is missing"):
                RuntimeEngine(workspace=root, worker=ResumableRevisionWorker()).resume(mission)

            after_attempts = (root / "runs/run-sample-mission/attempts.jsonl").read_text(encoding="utf-8")
            run = json.loads(run_path.read_text(encoding="utf-8"))

        self.assertEqual(after_attempts, before_attempts)
        self.assertEqual(run["current_contract_ref"], revision.new_contract_ref)
        self.assertEqual(run["current_contract_hash"], revision.new_contract_hash)


class _ContextProvider:
    def next_proposal(self, context):
        from missionforge import EvidenceTrustLevel, SteeringProposal
        from missionforge.contracts import AdaptiveDecision

        return SteeringProposal(
            proposal_id="proposal-revision-001",
            mission_run_id=context.mission_run_id,
            iteration=context.iteration,
            input_refs=[context.contract_ref],
            recommended_route=AdaptiveDecision.CONTINUE,
            proposed_contract={
                "next_objective": "Continue under revised contract.",
                "allowed_scope": ["package"],
                "visible_refs": [context.contract_ref],
                "expected_outputs": ["package/SKILL.md"],
            },
            source="fake_llm",
            source_refs=[context.contract_ref],
            trust_level=EvidenceTrustLevel.LLM_INTERPRETATION,
        )


if __name__ == "__main__":
    unittest.main()
