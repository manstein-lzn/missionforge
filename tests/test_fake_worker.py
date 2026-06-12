from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import EvidenceTrustLevel, InMemoryEvidenceStore
from missionforge.fake_worker import FakeWorker
from missionforge.work_unit import WorkUnitContract


class FakeWorkerTests(unittest.TestCase):
    def test_fake_worker_output_is_evidence_not_acceptance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = InMemoryEvidenceStore()
            work_unit = WorkUnitContract(
                work_unit_id="WU-000001",
                mission_id="mission-001",
                iteration=1,
                next_objective="Write deterministic artifact.",
                allowed_scope=["attempts/001"],
                visible_refs=["mission/frozen_contract.json"],
                expected_outputs=["attempts/001/artifact.txt"],
            )

            result = FakeWorker().run(work_unit, workspace=tmpdir, evidence_store=store)

            artifact = Path(tmpdir, "attempts/001/artifact.txt")
            report = Path(tmpdir, result.worker_result.execution_report_ref)
            evidence_record = store.get(result.execution_report.evidence_refs[0])
            self.assertTrue(artifact.exists())
            self.assertTrue(report.exists())
            self.assertEqual(evidence_record.evidence_ref.trust_level, EvidenceTrustLevel.ARTIFACT_REF)
            self.assertNotEqual(evidence_record.evidence_ref.trust_level, EvidenceTrustLevel.VERIFIER_RESULT)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "completed")


if __name__ == "__main__":
    unittest.main()
