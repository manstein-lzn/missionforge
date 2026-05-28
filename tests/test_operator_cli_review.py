from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI
from missionforge.review import ReviewerDecision
from tests.test_operator_cli_run import write_mission


def write_review_decision(
    root: Path,
    *,
    contract_hash: str,
    decision: str = "approved",
    author_role: str = "reviewer",
    ref: str = "reviews/reviewer-decision.json",
) -> str:
    payload = {
        "reviewer_id": "reviewer-001",
        "decision": decision,
        "contract_hash": contract_hash,
        "capsule_id": "unbound",
        "capsule_revision": 1,
        "author_role": author_role,
        "evidence_refs": ["evidence/review.json"],
        "notes": "Reviewer notes must not be copied into command output.",
    }
    if author_role != "worker":
        ReviewerDecision.from_dict(payload)
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return ref


class OperatorCLIReviewTests(unittest.TestCase):
    def test_review_record_validates_and_records_refs_only_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            before = run_path.read_text(encoding="utf-8")
            review_ref = write_review_decision(root, contract_hash=run["metrics"]["contract_hash"])

            result = MissionCLI().run_command(
                [
                    "review",
                    "record",
                    "--workspace",
                    str(root),
                    "--run",
                    "run-sample-mission",
                    "--decision",
                    "approved",
                    "--review-ref",
                    review_ref,
                ]
            )
            after = run_path.read_text(encoding="utf-8")
            record_payload = json.loads((root / result.data["review_record_ref"]).read_text(encoding="utf-8"))
            output = json.dumps(result.to_dict(), sort_keys=True)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.command, "review record")
            self.assertEqual(before, after)
            self.assertEqual(record_payload["review_ref"], review_ref)
            self.assertEqual(record_payload["decision"], "approved")
            self.assertFalse(record_payload["verifier_override"])
            self.assertNotIn("Reviewer notes must not be copied", output)

    def test_review_record_rejects_stale_or_worker_authored_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            stale_ref = write_review_decision(root, contract_hash="sha256:stale", ref="reviews/stale.json")

            result = MissionCLI().run_command(
                [
                    "review",
                    "record",
                    "--workspace",
                    str(root),
                    "--run",
                    "run-sample-mission",
                    "--decision",
                    "approved",
                    "--review-ref",
                    stale_ref,
                ]
            )
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")

            run = json.loads((root / "runs/run-sample-mission/mission_run.json").read_text(encoding="utf-8"))
            worker_ref = write_review_decision(
                root,
                contract_hash=run["metrics"]["contract_hash"],
                author_role="worker",
                ref="reviews/worker.json",
            )
            result = MissionCLI().run_command(
                [
                    "review",
                    "record",
                    "--workspace",
                    str(root),
                    "--run",
                    "run-sample-mission",
                    "--decision",
                    "approved",
                    "--review-ref",
                    worker_ref,
                ]
            )
            self.assertEqual(result.exit_code, 2)
            self.assertIn("worker-authored", result.error.message if result.error else "")

    def test_review_approval_does_not_override_failed_verifier_state(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            mission_ref = write_mission(root)
            MissionCLI().run_command(["run", "--workspace", str(root), "--mission-ref", mission_ref])
            run_path = root / "runs/run-sample-mission/mission_run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["status"] = "failed"
            run["failed_constraint_ids"] = ["C-001"]
            run_path.write_text(json.dumps(run, sort_keys=True), encoding="utf-8")
            review_ref = write_review_decision(root, contract_hash=run["metrics"]["contract_hash"])

            result = MissionCLI().run_command(
                [
                    "review",
                    "record",
                    "--workspace",
                    str(root),
                    "--run",
                    "run-sample-mission",
                    "--decision",
                    "approved",
                    "--review-ref",
                    review_ref,
                ]
            )
            persisted_run = json.loads(run_path.read_text(encoding="utf-8"))

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["runtime_status"], "failed")
            self.assertFalse(result.data["verifier_override"])
            self.assertEqual(persisted_run["status"], "failed")
            self.assertEqual(persisted_run["failed_constraint_ids"], ["C-001"])


if __name__ == "__main__":
    unittest.main()
