from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import build_run_audit
from missionforge.adapters.cli import MissionCLI
from tests.operator_state_fixtures import seed_operator_run


class RunAuditTests(unittest.TestCase):
    def test_run_audit_reports_refs_only_success_summary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_operator_run(root)

            audit = build_run_audit(root, "run-sample-mission")

            self.assertTrue(audit.passed)
            self.assertEqual(audit.run_ref, "runs/run-sample-mission/mission_run.json")
            self.assertEqual(audit.metric_projection_ref, "runs/run-sample-mission/metrics/projection.json")
            self.assertIn("runs/run-sample-mission/attempts.jsonl", [item["ref"] for item in audit.ref_checks])
            self.assertEqual(audit.missing_refs, [])
            self.assertEqual(audit.stale_refs, [])
            self.assertEqual(audit, audit.from_dict(audit.to_dict()))

    def test_run_audit_flags_missing_current_contract_ref(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_operator_run(root)
            contract_ref = "runs/run-sample-mission/contracts/base/frozen_contract.json"
            (root / contract_ref).unlink()

            audit = build_run_audit(root, "run-sample-mission")

            self.assertFalse(audit.passed)
            self.assertIn(contract_ref, audit.missing_refs)
            self.assertIn(contract_ref, audit.stale_refs)
            self.assertIn("missing_refs_detected", audit.diagnostics)

    def test_run_audit_does_not_embed_artifact_bodies(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_operator_run(root)
            audit = build_run_audit(root, "run-sample-mission")
            audit_json = json.dumps(audit.to_dict(), sort_keys=True)

            for artifact_ref in audit.artifact_refs:
                artifact_text = (root / artifact_ref).read_text(encoding="utf-8")
                if artifact_text.strip():
                    self.assertNotIn(artifact_text, audit_json)

    def test_operator_diagnose_fails_closed_on_stale_refs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_operator_run(root)
            (root / "runs/run-sample-mission/contracts/base/frozen_contract.json").unlink()

            result = MissionCLI().run_command(["diagnose", "--workspace", str(root), "--run", "run-sample-mission"])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["diagnosis"], "stale_or_missing_refs")
            self.assertEqual(result.data["operator_action"], "inspect_run_audit")


if __name__ == "__main__":
    unittest.main()
