from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    ContractValidationError,
    FileRefStore,
    MemoryRefStore,
    RefMaterializationState,
    RefRecord,
    stable_json_hash,
)


class RefStoreTests(unittest.TestCase):
    def test_memory_ref_store_has_no_filesystem_side_effects(self) -> None:
        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            store = MemoryRefStore()

            record = store.write_json(
                "kernel/run/step.json",
                {"b": 2, "a": 1},
                metadata={"source_ref": "inputs/request.json"},
            )
            store.append_jsonl("kernel/run/events.jsonl", {"event_ref": "events/one.json", "kind": "started"})

            self.assertEqual(before, _snapshot(tmpdir))
            self.assertTrue(store.exists("kernel/run/step.json"))
            self.assertEqual(store.read_json("kernel/run/step.json"), {"a": 1, "b": 2})
            self.assertEqual(record.materialization_state, RefMaterializationState.VOLATILE)
            self.assertEqual(record.store_id, "memory")
            self.assertEqual(store.list_refs("kernel/run"), ["kernel/run/events.jsonl", "kernel/run/step.json"])

    def test_json_hash_is_canonical(self) -> None:
        store = MemoryRefStore()

        first = store.write_json("records/a.json", {"b": [2, 1], "a": {"x": True}})
        second = store.write_json("records/b.json", {"a": {"x": True}, "b": [2, 1]})

        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(store.read_bytes("records/a.json"), b'{"a":{"x":true},"b":[2,1]}\n')

    def test_jsonl_append_preserves_records_and_hash(self) -> None:
        store = MemoryRefStore()

        first = store.append_jsonl("events/run.jsonl", {"kind": "started", "event_ref": "events/001.json"})
        second = store.append_jsonl("events/run.jsonl", {"kind": "stopped", "event_ref": "events/002.json"})

        self.assertNotEqual(first.content_hash, second.content_hash)
        self.assertEqual(
            store.read_jsonl("events/run.jsonl"),
            [
                {"event_ref": "events/001.json", "kind": "started"},
                {"event_ref": "events/002.json", "kind": "stopped"},
            ],
        )

    def test_memory_ref_store_supports_concurrent_writes(self) -> None:
        store = MemoryRefStore()

        def write(index: int) -> None:
            store.write_json(f"records/{index:03d}.json", {"record_ref": f"records/{index:03d}.json"})
            store.append_jsonl("events/run.jsonl", {"event_ref": f"events/{index:03d}.json"})

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(50)))

        self.assertEqual(len(store.list_refs("records")), 50)
        self.assertEqual(len(store.read_jsonl("events/run.jsonl")), 50)

    def test_missing_ref_hash_matches_existing_kernel_behavior(self) -> None:
        store = MemoryRefStore()

        self.assertEqual(store.hash_ref("missing/ref.json"), stable_json_hash({"missing_ref": "missing/ref.json"}))

    def test_ref_record_metadata_is_refs_only(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "artifact_body is not allowed"):
            RefRecord.create(
                ref="records/a.json",
                body=b"{}",
                metadata={"artifact_body": "raw body must stay behind refs"},
            )

    def test_memory_ref_store_rejects_invalid_refs_and_non_bytes(self) -> None:
        store = MemoryRefStore()

        with self.assertRaisesRegex(ContractValidationError, "safe relative ref"):
            store.write_bytes("/tmp/outside.json", b"{}")
        with self.assertRaisesRegex(ContractValidationError, "body must be bytes"):
            store.write_bytes("records/a.json", "{}")  # type: ignore[arg-type]

    def test_file_ref_store_requires_explicit_root_and_materializes_only_there(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileRefStore(tmpdir)

            record = store.write_text("reports/final.md", "final report")

            self.assertEqual(record.materialization_state, RefMaterializationState.DURABLE)
            self.assertEqual(store.read_text("reports/final.md"), "final report")
            self.assertEqual((Path(tmpdir) / "reports" / "final.md").read_text(encoding="utf-8"), "final report")
            self.assertEqual(store.list_refs(), ["reports/final.md"])

    def test_file_ref_store_read_operations_do_not_create_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "missing-workspace"
            store = FileRefStore(root)

            self.assertFalse(root.exists())
            self.assertFalse(store.exists("reports/final.md"))
            self.assertEqual(store.list_refs(), [])
            self.assertEqual(store.hash_ref("reports/final.md"), stable_json_hash({"missing_ref": "reports/final.md"}))
            self.assertFalse(root.exists())

    def test_kernel_io_read_helpers_do_not_create_workspace_root(self) -> None:
        from missionforge.kernel.io import hash_ref, list_refs, read_json_ref, ref_exists

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "missing-workspace"

            self.assertFalse(ref_exists(root, "reports/final.md"))
            self.assertEqual(list_refs(root), [])
            self.assertEqual(hash_ref(root, "reports/final.md"), stable_json_hash({"missing_ref": "reports/final.md"}))
            with self.assertRaisesRegex(ContractValidationError, "unknown ref"):
                read_json_ref(root, "reports/final.md")
            self.assertFalse(root.exists())

    def test_kernel_io_validates_refs_before_custom_store_calls(self) -> None:
        from missionforge.kernel.io import read_json_ref, ref_exists, write_json_ref

        store = _RecordingStore()

        with self.assertRaises(ContractValidationError):
            ref_exists(store, "../outside.json")
        with self.assertRaises(ContractValidationError):
            read_json_ref(store, "../outside.json")
        with self.assertRaises(ContractValidationError):
            write_json_ref(store, "../outside.json", {"ok": True})

        self.assertEqual(store.calls, [])

    def test_file_ref_store_rejects_path_escape(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileRefStore(tmpdir)

            with self.assertRaisesRegex(ContractValidationError, "dot, or parent"):
                store.write_text("../outside.txt", "bad")


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


class _RecordingStore:
    store_id = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def exists(self, ref: str) -> bool:
        self.calls.append(("exists", ref))
        return False

    def read_bytes(self, ref: str) -> bytes:
        self.calls.append(("read_bytes", ref))
        return b"{}"

    def read_text(self, ref: str) -> str:
        self.calls.append(("read_text", ref))
        return "{}"

    def read_json(self, ref: str):
        self.calls.append(("read_json", ref))
        return {}

    def read_jsonl(self, ref: str):
        self.calls.append(("read_jsonl", ref))
        return []

    def write_bytes(self, ref: str, body: bytes, *, media_type: str = "application/octet-stream", metadata=None):
        self.calls.append(("write_bytes", ref))
        return RefRecord.create(ref="records/placeholder.json", body=b"{}")

    def write_text(self, ref: str, text: str, *, media_type: str = "text/plain", metadata=None):
        self.calls.append(("write_text", ref))
        return RefRecord.create(ref="records/placeholder.json", body=b"{}")

    def write_json(self, ref: str, value, *, metadata=None):
        self.calls.append(("write_json", ref))
        return RefRecord.create(ref="records/placeholder.json", body=b"{}")

    def append_jsonl(self, ref: str, item, *, metadata=None):
        self.calls.append(("append_jsonl", ref))
        return RefRecord.create(ref="records/placeholder.json", body=b"{}")

    def hash_ref(self, ref: str) -> str:
        self.calls.append(("hash_ref", ref))
        return stable_json_hash({"missing_ref": ref})

    def list_refs(self, prefix: str = "") -> list[str]:
        self.calls.append(("list_refs", prefix))
        return []


if __name__ == "__main__":
    unittest.main()
