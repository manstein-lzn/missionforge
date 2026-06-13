from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.observation import ControlRequestWriter, MissionRunView, read_control_request
from missionforge.contracts import EvidenceTrustLevel
from missionforge.evidence_store import InMemoryEvidenceStore
from missionforge.runtime_results import MissionResult


def sample_result() -> MissionResult:
    return MissionResult(
        mission_id="sample-mission",
        status="completed_verified",
        evidence_refs=["evidence/E-000001.json"],
        artifact_refs=["package/SKILL.md"],
        failed_constraint_ids=[],
        metrics={"verification_status": "completed_verified"},
    )


class HostObservationAdapterTests(unittest.TestCase):
    def test_mission_run_view_is_read_only_summary(self) -> None:
        result = sample_result()
        before = result.to_dict()
        store = InMemoryEvidenceStore()
        store.append(
            payload={"kind": "verification_summary"},
            trust_level=EvidenceTrustLevel.VERIFIER_RESULT,
            kind="verification_result",
        )

        view = MissionRunView.from_result(result, evidence_snapshot=store.snapshot())

        self.assertEqual(result.to_dict(), before)
        self.assertEqual(view.mission_id, "sample-mission")
        self.assertEqual(view.status, "completed_verified")
        self.assertEqual(view.evidence_record_count, 1)
        self.assertEqual(MissionRunView.from_dict(view.to_dict()), view)

    def test_control_writer_writes_explicit_halt_intent_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            write_result = ControlRequestWriter(workspace=root).write_halt(
                reason="Operator requested pause.",
                control_id="halt-review",
                evidence_refs=["evidence/E-000001.json"],
            )
            request = read_control_request(workspace=root, control_ref=write_result.control_ref)
            payload = json.loads((root / write_result.control_ref).read_text(encoding="utf-8"))

            self.assertEqual(write_result.control_ref, "control/halt-review.json")
            self.assertEqual(write_result.control_type, "halt")
            self.assertTrue(write_result.active)
            self.assertEqual(request.reason, "Operator requested pause.")
            self.assertEqual(payload["control_type"], "halt")
            self.assertFalse((root / "host_results").exists())


if __name__ == "__main__":
    unittest.main()
