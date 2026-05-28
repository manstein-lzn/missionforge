from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import InMemoryEvidenceStore, ValidatorSpec, run_validator
from missionforge.contracts import ContractValidationError, EvidenceTrustLevel


class ValidatorTests(unittest.TestCase):
    def test_file_exists_validator_records_schema_evidence(self) -> None:
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "artifact.txt").write_text("ready", encoding="utf-8")
            store = InMemoryEvidenceStore()
            result = run_validator(
                ValidatorSpec(
                    validator_id="V-file",
                    constraint_refs=["C-001"],
                    type="file_exists",
                    inputs={"path": "artifact.txt"},
                ),
                workspace=tmpdir,
                evidence_store=store,
            )

            self.assertTrue(result.passed)
            record = store.get(result.evidence_refs[0])
            self.assertEqual(record.evidence_ref.trust_level, EvidenceTrustLevel.SCHEMA_VALIDATION)
            self.assertEqual(record.payload["exists"], True)

    def test_file_contains_and_forbidden_path_validators(self) -> None:
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "artifact.txt").write_text("mission ready", encoding="utf-8")
            store = InMemoryEvidenceStore()

            contains = run_validator(
                ValidatorSpec(
                    validator_id="V-contains",
                    constraint_refs=["C-001"],
                    type="file_contains",
                    inputs={"path": "artifact.txt", "contains": "mission"},
                ),
                workspace=tmpdir,
                evidence_store=store,
            )
            forbidden = run_validator(
                ValidatorSpec(
                    validator_id="V-forbidden",
                    constraint_refs=["C-002"],
                    type="forbidden_path",
                    inputs={"path": "secret.txt"},
                ),
                workspace=tmpdir,
                evidence_store=store,
            )

            self.assertTrue(contains.passed)
            self.assertTrue(forbidden.passed)

    def test_json_field_exists_validator(self) -> None:
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "result.json").write_text(json.dumps({"outer": {"inner": 3}}), encoding="utf-8")

            result = run_validator(
                ValidatorSpec(
                    validator_id="V-json",
                    constraint_refs=["C-001"],
                    type="json_field_exists",
                    inputs={"path": "result.json", "field": "outer.inner"},
                ),
                workspace=tmpdir,
                evidence_store=InMemoryEvidenceStore(),
            )

            self.assertTrue(result.passed)

    def test_artifact_hash_validator(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir, "artifact.txt")
            path.write_text("hash me", encoding="utf-8")
            expected = "sha256:" + hashlib.sha256(b"hash me").hexdigest()

            result = run_validator(
                ValidatorSpec(
                    validator_id="V-hash",
                    constraint_refs=["C-001"],
                    type="artifact_hash",
                    inputs={"path": "artifact.txt", "sha256": expected},
                ),
                workspace=tmpdir,
                evidence_store=InMemoryEvidenceStore(),
            )

            self.assertTrue(result.passed)

    def test_command_validator_records_output_summary_not_truth(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = InMemoryEvidenceStore()
            result = run_validator(
                ValidatorSpec(
                    validator_id="V-command",
                    constraint_refs=["C-001"],
                    type="command",
                    inputs={"command": ["python3", "-c", "print('ok')"]},
                ),
                workspace=tmpdir,
                evidence_store=store,
            )

            self.assertTrue(result.passed)
            record = store.get(result.evidence_refs[0])
            self.assertEqual(record.evidence_ref.trust_level, EvidenceTrustLevel.COMMAND_RESULT)
            self.assertEqual(record.payload["exit_code"], 0)
            self.assertEqual(record.payload["stdout_summary"], "ok\n")

    def test_unsafe_path_is_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            run_validator(
                ValidatorSpec(
                    validator_id="V-unsafe",
                    constraint_refs=["C-001"],
                    type="file_exists",
                    inputs={"path": "../secret.txt"},
                )
            )


if __name__ == "__main__":
    unittest.main()
