from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError
from missionforge.json_store import JsonWorkspaceStore


class JsonStoreBackendTests(unittest.TestCase):
    def test_json_store_reads_and_writes_json_text_and_jsonl(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = JsonWorkspaceStore(tmpdir)

            self.assertEqual(store.write_json("runs/run-1/sample.json", {"b": 2, "a": 1}), "runs/run-1/sample.json")
            self.assertEqual(store.read_json("runs/run-1/sample.json"), {"a": 1, "b": 2})
            self.assertTrue(store.exists("runs/run-1/sample.json"))
            store.write_text("host_results/log.txt", "ok")
            self.assertEqual(store.read_text("host_results/log.txt"), "ok")
            store.write_jsonl("runs/run-1/events.jsonl", [{"event": "one"}])
            store.write_jsonl("runs/run-1/events.jsonl", [{"event": "two"}], append=True)
            self.assertEqual(store.read_jsonl("runs/run-1/events.jsonl"), [{"event": "one"}, {"event": "two"}])

    def test_json_store_rejects_path_escape(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = JsonWorkspaceStore(tmpdir)

            with self.assertRaises(ContractValidationError):
                store.write_json("../outside.json", {"ok": False})


if __name__ == "__main__":
    unittest.main()
