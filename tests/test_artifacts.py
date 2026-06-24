from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
import unittest

from missionforge import (
    ArtifactMaterializationState,
    ArtifactRecord,
    ArtifactVersionRef,
    ContractValidationError,
    FileArtifactStore,
    InMemoryArtifactStore,
)


class ArtifactTests(unittest.TestCase):
    def test_ref_identity_is_not_filesystem_path_identity(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileArtifactStore(tmpdir)

            record = store.put_text("reports/final.md", "final report")

            self.assertEqual(record.ref, "reports/final.md")
            self.assertEqual(record.version_ref.value, "reports/final.md@v1")
            self.assertEqual(ArtifactVersionRef.from_dict(record.version_ref.to_dict()), record.version_ref)
            self.assertEqual(ArtifactVersionRef.from_value(record.version_ref.value), record.version_ref)
            self.assertNotEqual(record.body_ref, record.ref)
            self.assertNotEqual(store.materialized_path(record).relative_to(tmpdir).as_posix(), record.ref)
            self.assertTrue(store.materialized_path(record).exists())
            self.assertEqual(store.read_bytes("reports/final.md"), b"final report")

    def test_versioned_updates_preserve_previous_versions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileArtifactStore(tmpdir)

            first = store.put_text("state/research_state.json", '{"round": 1}', media_type="application/json")
            second = store.put_text("state/research_state.json", '{"round": 2}', media_type="application/json")

            self.assertEqual(first.version, 1)
            self.assertEqual(second.version, 2)
            self.assertNotEqual(first.body_ref, second.body_ref)
            self.assertEqual(store.latest("state/research_state.json"), second)
            self.assertEqual(store.read_bytes("state/research_state.json", version=1), b'{"round": 1}')
            self.assertEqual(store.read_bytes("state/research_state.json", version=2), b'{"round": 2}')
            self.assertEqual([record.version for record in store.records("state/research_state.json")], [1, 2])

    def test_in_memory_store_is_volatile_and_preserves_versions(self) -> None:
        store = InMemoryArtifactStore()

        first = store.put_text("scratch/plan.txt", "first")
        second = store.put_text("scratch/plan.txt", "second")

        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(first.materialization_state, ArtifactMaterializationState.VOLATILE)
        self.assertEqual(second.materialization_state, ArtifactMaterializationState.VOLATILE)
        self.assertEqual(store.latest("scratch/plan.txt"), second)
        self.assertEqual(store.read_bytes("scratch/plan.txt", version=1), b"first")
        self.assertEqual(store.read_bytes("scratch/plan.txt", version=2), b"second")
        self.assertEqual([record.version for record in store.records("scratch/plan.txt")], [1, 2])

    def test_durable_artifact_survives_reload(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileArtifactStore(tmpdir)
            record = store.put_text(
                "artifacts/final.txt",
                "accepted output",
                source_refs=["inputs/request.json"],
                metadata={"schema_ref": "schemas/output.json"},
            )

            reloaded = FileArtifactStore(tmpdir)

            self.assertEqual(reloaded.get("artifacts/final.txt", version=1), record)
            self.assertEqual(
                reloaded.latest("artifacts/final.txt").materialization_state,
                ArtifactMaterializationState.DURABLE,
            )
            self.assertEqual(reloaded.read_bytes("artifacts/final.txt", version=1), b"accepted output")

    def test_durable_artifact_rejects_corrupt_body(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileArtifactStore(tmpdir)
            record = store.put_text("artifacts/final.txt", "accepted output")

            store.materialized_path(record).write_text("corrupt output", encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "hash mismatch"):
                store.read_bytes("artifacts/final.txt", version=1)
            with self.assertRaisesRegex(ContractValidationError, "hash mismatch"):
                FileArtifactStore(tmpdir)

    def test_failed_file_commit_does_not_poison_next_version(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileArtifactStore(tmpdir)

            with self.assertRaisesRegex(ContractValidationError, "artifact_body is not allowed"):
                store.put_text(
                    "artifacts/final.txt",
                    "bad output",
                    metadata={"artifact_body": "raw output must stay behind refs"},
                )

            self.assertEqual(store.records("artifacts/final.txt"), [])
            self.assertFalse((Path(tmpdir) / ".missionforge" / "artifacts" / "bodies").exists())

            record = store.put_text("artifacts/final.txt", "accepted output")

            self.assertEqual(record.version, 1)
            self.assertEqual(store.read_bytes("artifacts/final.txt", version=1), b"accepted output")

    def test_committed_record_provenance_is_immutable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileArtifactStore(tmpdir)
            source_refs = ["inputs/request.json"]
            metadata = {"schema_refs": ["schemas/output.json"], "nested": {"trace_ref": "traces/trace.json"}}
            first = store.put_text(
                "artifacts/final.txt",
                "accepted output",
                source_refs=source_refs,
                metadata=metadata,
            )

            source_refs.append("inputs/after-commit.json")
            metadata["schema_refs"].append("schemas/after-commit.json")
            metadata["nested"]["trace_ref"] = "traces/after-commit.json"

            self.assertIsInstance(first.metadata, MappingProxyType)
            self.assertEqual(first.source_refs, ("inputs/request.json",))
            self.assertEqual(first.metadata["schema_refs"], ("schemas/output.json",))
            self.assertEqual(first.metadata["nested"]["trace_ref"], "traces/trace.json")
            with self.assertRaises(FrozenInstanceError):
                first.source_refs += ("inputs/mutated.json",)
            with self.assertRaises(TypeError):
                first.metadata["schema_ref"] = "schemas/mutated.json"

            store.put_text("artifacts/final.txt", "accepted output v2")
            reloaded = FileArtifactStore(tmpdir)
            reloaded_first = reloaded.get("artifacts/final.txt", version=1)

            self.assertEqual(reloaded_first.source_refs, ("inputs/request.json",))
            self.assertEqual(reloaded_first.metadata["schema_refs"], ("schemas/output.json",))
            self.assertEqual(reloaded_first.metadata["nested"]["trace_ref"], "traces/trace.json")

    def test_artifact_record_rejects_mismatched_version_ref(self) -> None:
        record = ArtifactRecord.create(
            ref="artifacts/final.txt",
            version=1,
            body=b"accepted output",
            body_ref="storage/artifacts/final/v000001/body",
        )
        payload = record.to_dict()
        payload["version_ref"] = {"ref": "artifacts/final.txt", "version": 2, "value": "artifacts/final.txt@v2"}

        with self.assertRaisesRegex(ContractValidationError, "version_ref does not match"):
            ArtifactRecord.from_dict(payload)

    def test_artifact_record_requires_body_ref(self) -> None:
        record = ArtifactRecord.create(
            ref="artifacts/final.txt",
            version=1,
            body=b"accepted output",
            body_ref="storage/artifacts/final/v000001/body",
        )
        payload = record.to_dict()
        payload.pop("body_ref")

        with self.assertRaisesRegex(ContractValidationError, "artifact_record.body_ref"):
            ArtifactRecord.from_dict(payload)

    def test_artifact_record_requires_version_ref(self) -> None:
        record = ArtifactRecord.create(
            ref="artifacts/final.txt",
            version=1,
            body=b"accepted output",
            body_ref="storage/artifacts/final/v000001/body",
        )
        payload = record.to_dict()
        payload.pop("version_ref")

        with self.assertRaisesRegex(ContractValidationError, "artifact_record.version_ref"):
            ArtifactRecord.from_dict(payload)

    def test_artifact_record_rejects_malformed_source_refs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "artifact_record.source_refs"):
            ArtifactRecord.create(
                ref="artifacts/final.txt",
                version=1,
                body=b"accepted output",
                body_ref="storage/artifacts/final/v000001/body",
                source_refs=["inputs/request.json", ""],
            )

        with self.assertRaisesRegex(ContractValidationError, "artifact_record.source_refs"):
            ArtifactRecord.create(
                ref="artifacts/final.txt",
                version=1,
                body=b"accepted output",
                body_ref="storage/artifacts/final/v000001/body",
                source_refs="inputs/request.json",  # type: ignore[arg-type]
            )

    def test_artifact_record_rejects_malformed_metadata(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "artifact_record.metadata"):
            ArtifactRecord.create(
                ref="artifacts/final.txt",
                version=1,
                body=b"accepted output",
                body_ref="storage/artifacts/final/v000001/body",
                metadata=[],  # type: ignore[arg-type]
            )

    def test_artifact_record_metadata_is_refs_only(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "artifact_body is not allowed"):
            ArtifactRecord.create(
                ref="artifacts/final.txt",
                version=1,
                body=b"accepted output",
                body_ref="storage/artifacts/final/v000001/body",
                metadata={"artifact_body": "raw output must stay behind refs"},
            )


if __name__ == "__main__":
    unittest.main()
