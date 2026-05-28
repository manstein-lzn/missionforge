from __future__ import annotations

import json
from tempfile import TemporaryDirectory
import unittest

from missionforge import EvidenceRecord, FileEvidenceStore, InMemoryEvidenceStore
from missionforge.contracts import ContractValidationError, EvidenceTrustLevel


class EvidenceLedgerTests(unittest.TestCase):
    def test_in_memory_store_appends_and_snapshots_deterministically(self) -> None:
        store = InMemoryEvidenceStore()
        first = store.append(
            payload={"path": "artifact.txt", "exists": True},
            trust_level=EvidenceTrustLevel.SCHEMA_VALIDATION,
            kind="validator_result",
        )
        second = store.append(
            payload={"exit_code": 0},
            trust_level=EvidenceTrustLevel.COMMAND_RESULT,
            kind="validator_result",
            source_refs=[first.ref],
        )

        snapshot = store.snapshot()

        self.assertEqual(first.evidence_id, "E-000001")
        self.assertEqual(second.evidence_id, "E-000002")
        self.assertTrue(snapshot.ledger_hash.startswith("sha256:"))
        self.assertEqual(snapshot.ledger_hash, store.snapshot().ledger_hash)
        self.assertEqual(store.get(first.evidence_id).payload["exists"], True)

    def test_store_rejects_duplicate_evidence_ids(self) -> None:
        store = InMemoryEvidenceStore()
        store.append(
            evidence_id="E-fixed",
            payload={"ok": True},
            trust_level="schema_validation",
            kind="validator_result",
        )

        with self.assertRaises(ContractValidationError):
            store.append(
                evidence_id="E-fixed",
                payload={"ok": False},
                trust_level="schema_validation",
                kind="validator_result",
            )

    def test_record_rejects_payload_hash_mismatch(self) -> None:
        store = InMemoryEvidenceStore()
        evidence_ref = store.append(payload={"ok": True}, trust_level="schema_validation", kind="validator_result")
        payload = store.get(evidence_ref.evidence_id).to_dict()
        payload["payload"] = {"ok": False}

        with self.assertRaises(ContractValidationError):
            EvidenceRecord.from_dict(payload)

    def test_file_store_is_append_only_and_reloadable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileEvidenceStore(tmpdir)
            evidence_ref = store.append(payload={"ok": True}, trust_level="schema_validation", kind="validator_result")
            files = list(store.snapshot().records)
            reloaded = FileEvidenceStore(tmpdir)

            self.assertEqual(reloaded.get(evidence_ref.evidence_id), files[0])
            self.assertEqual(reloaded.snapshot().ledger_hash, store.snapshot().ledger_hash)
            with open(f"{tmpdir}/{evidence_ref.evidence_id}.json", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["evidence_ref"]["evidence_id"], evidence_ref.evidence_id)


if __name__ == "__main__":
    unittest.main()
