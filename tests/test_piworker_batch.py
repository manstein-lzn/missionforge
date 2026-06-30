from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    ContractValidationError,
    MemoryRefStore,
    PiWorkerCall,
    PiWorkerCallBatch,
    PiWorkerCallBatchResult,
    PiWorkerCallResult,
    PiWorkerCallResultStatus,
    PiWorkerCallRole,
    run_piworker_call_batch,
)
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from missionforge.piworker_batch import _write_json_atomic


HASH_A = "sha256:" + "a" * 64


class PiWorkerBatchTests(unittest.TestCase):
    def test_batch_rejects_duplicate_call_id(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "unique call_id"):
            PiWorkerCallBatch(batch_id="batch1", calls=[_call("call1", "out/a.txt"), _call("call1", "out/b.txt")])

    def test_batch_rejects_duplicate_expected_output_refs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "duplicate expected_output_ref"):
            PiWorkerCallBatch(batch_id="batch1", calls=[_call("call1", "out/a.txt"), _call("call2", "out/a.txt")])

    def test_batch_rejects_same_or_overlapping_writable_refs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "writable_refs overlap"):
            PiWorkerCallBatch(
                batch_id="batch1",
                calls=[
                    _call("call1", "out/a/report.txt", writable_refs=["out"]),
                    _call("call2", "out/b/report.txt", writable_refs=["out"]),
                ],
            )
        with self.assertRaisesRegex(ContractValidationError, "writable_refs overlap"):
            PiWorkerCallBatch(
                batch_id="batch1",
                calls=[
                    _call("call1", "out/a.txt", writable_refs=["out"]),
                    _call("call2", "out/module/b.txt", writable_refs=["out/module"]),
                ],
            )

    def test_batch_rejects_call_ids_that_map_to_same_path_segment(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "unique path segments"):
            PiWorkerCallBatch(
                batch_id="batch1",
                calls=[
                    _call("call/a", "out/a/report.txt", writable_refs=["out/a"]),
                    _call("call_a", "out/b/report.txt", writable_refs=["out/b"]),
                ],
            )

    def test_write_json_atomic_validates_ref_before_store_write(self) -> None:
        store = _RecordingStore()

        with self.assertRaises(ContractValidationError):
            _write_json_atomic(store, "../bad.json", {"status": "bad"})

        self.assertEqual(store.calls, [])

    def test_three_calls_complete_in_distinct_namespaces(self) -> None:
        adapter_factory = _AdapterFactory()
        calls = [
            _call("call-a", "out/a/report.txt", writable_refs=["out/a"]),
            _call("call-b", "out/b/report.txt", writable_refs=["out/b"]),
            _call("call-c", "out/c/report.txt", writable_refs=["out/c"]),
        ]

        with TemporaryDirectory() as tmpdir:
            result = run_piworker_call_batch(
                PiWorkerCallBatch(batch_id="batch1", calls=calls, concurrency=3),
                workspace=tmpdir,
                adapter_factory=adapter_factory,
            )

            self.assertEqual(PiWorkerCallBatchResult.from_dict(result.to_dict()).status, "completed")
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.completed_call_ids, ["call-a", "call-b", "call-c"])
            self.assertEqual(adapter_factory.call_ids, ["call-a", "call-b", "call-c"])
            self.assertEqual(
                result.call_result_refs,
                [
                    "piworker_batches/batch1/calls/call-a/piworker_call_result.json",
                    "piworker_batches/batch1/calls/call-b/piworker_call_result.json",
                    "piworker_batches/batch1/calls/call-c/piworker_call_result.json",
                ],
            )
            for ref in result.call_result_refs:
                self.assertTrue((Path(tmpdir) / ref).is_file())
            self.assertTrue((Path(tmpdir) / "piworker_batches/batch1/batch_spec.json").is_file())
            self.assertTrue((Path(tmpdir) / "piworker_batches/batch1/batch_result.json").is_file())
            self.assertTrue((Path(tmpdir) / "piworker_batches/batch1/calls/call-a/evidence").is_dir())
            self.assertTrue((Path(tmpdir) / "piworker_batches/batch1/calls/call-a/progress.jsonl").is_file())
            self.assertIn("piworker_batches/batch1/calls/call-a/progress.jsonl", result.runtime_refs)

    def test_runtime_exception_is_structured_partial_result(self) -> None:
        adapter_factory = _AdapterFactory(failing_call_id="call-b")
        calls = [
            _call("call-a", "out/a/report.txt", writable_refs=["out/a"]),
            _call("call-b", "out/b/report.txt", writable_refs=["out/b"]),
            _call("call-c", "out/c/report.txt", writable_refs=["out/c"]),
        ]

        with TemporaryDirectory() as tmpdir:
            result = run_piworker_call_batch(
                PiWorkerCallBatch(batch_id="batch1", calls=calls, concurrency=3),
                workspace=tmpdir,
                adapter_factory=adapter_factory,
            )
            failed_result = PiWorkerCallResult.from_dict(
                _read_json(tmpdir, "piworker_batches/batch1/calls/call-b/piworker_call_result.json")
            )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.completed_call_ids, ["call-a", "call-c"])
        self.assertEqual(result.failed_call_ids, ["call-b"])
        self.assertEqual(failed_result.status, PiWorkerCallResultStatus.RUNTIME_ERROR)
        self.assertEqual(failed_result.call_id, "call-b")
        self.assertEqual(failed_result.contract_id, "contract-001")
        self.assertEqual(failed_result.contract_hash, HASH_A)
        self.assertTrue(failed_result.error_ref)

    def test_batch_can_run_entirely_in_memory_store(self) -> None:
        store = MemoryRefStore()
        adapter_factory = _MemoryAdapterFactory()
        calls = [
            _call("call-a", "out/a/report.txt", writable_refs=["out/a"]),
            _call("call-b", "out/b/report.txt", writable_refs=["out/b"]),
            _call("call-c", "out/c/report.txt", writable_refs=["out/c"]),
        ]

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            result = run_piworker_call_batch(
                PiWorkerCallBatch(batch_id="batch1", calls=calls, concurrency=3),
                store=store,
                adapter_factory=adapter_factory,
            )
            after = _snapshot(tmpdir)

        self.assertIs(result.store, store)
        self.assertEqual(before, after)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.completed_call_ids, ["call-a", "call-b", "call-c"])
        self.assertEqual(adapter_factory.call_ids, ["call-a", "call-b", "call-c"])
        self.assertEqual(store.read_json(result.batch_result_ref), result.to_dict())
        for ref in result.call_result_refs:
            self.assertTrue(store.exists(ref))
        self.assertEqual(store.read_text("out/a/report.txt"), "output for call-a\n")

    def test_memory_batch_collects_runtime_exception_in_store(self) -> None:
        store = MemoryRefStore()
        adapter_factory = _AdapterFactory(failing_call_id="call-b")
        calls = [
            _call("call-a", "out/a/report.txt", writable_refs=["out/a"]),
            _call("call-b", "out/b/report.txt", writable_refs=["out/b"]),
        ]

        result = run_piworker_call_batch(
            PiWorkerCallBatch(batch_id="batch1", calls=calls, concurrency=2),
            store=store,
            adapter_factory=adapter_factory,
        )

        self.assertEqual(result.status, "partial")
        failed_ref = "piworker_batches/batch1/calls/call-b/piworker_call_result.json"
        failed_result = PiWorkerCallResult.from_dict(store.read_json(failed_ref))
        self.assertEqual(failed_result.status, PiWorkerCallResultStatus.RUNTIME_ERROR)
        self.assertTrue(store.exists(failed_result.error_ref))
        self.assertTrue(store.exists(failed_result.execution_report_ref))


def _call(call_id: str, output_ref: str, *, writable_refs: list[str] | None = None) -> PiWorkerCall:
    return PiWorkerCall(
        call_id=call_id,
        role=PiWorkerCallRole.EXECUTOR,
        contract_id="contract-001",
        contract_hash=HASH_A,
        contract_ref="contract/task_contract.json",
        objective="Produce output.",
        visible_refs=["contract/task_contract.json"],
        writable_refs=writable_refs or [output_ref.rsplit("/", 1)[0]],
        expected_output_refs=[output_ref],
        permission_manifest_ref="policy/permission_manifest.json",
    )


class _AdapterFactory:
    def __init__(self, failing_call_id: str = "") -> None:
        self.call_ids: list[str] = []
        self.failing_call_id = failing_call_id

    def __call__(self, call: PiWorkerCall) -> "_BatchAdapter":
        self.call_ids.append(call.call_id)
        return _BatchAdapter(fail=call.call_id == self.failing_call_id)


class _BatchAdapter:
    adapter_family = "batch-test"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def run_call(
        self,
        call,
        *,
        workspace=".",
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
        runtime_progress_sink=None,
    ):
        if self.fail:
            raise RuntimeError(f"boom {call.call_id}")
        output_ref = call.expected_output_refs[0]
        report_ref = f"attempts/{call.call_id}/pi_agent_execution_report.json"
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id=f"R-{call.call_id}",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=[output_ref],
                changed_refs=[output_ref, report_ref],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
        )


class _MemoryAdapterFactory:
    def __init__(self) -> None:
        self.call_ids: list[str] = []

    def __call__(self, call: PiWorkerCall) -> "_MemoryBatchAdapter":
        self.call_ids.append(call.call_id)
        return _MemoryBatchAdapter()


class _MemoryBatchAdapter:
    adapter_family = "memory-batch-test"

    def run_call(
        self,
        call,
        *,
        workspace=None,
        store=None,
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
        runtime_progress_sink=None,
    ):
        if store is None:
            raise AssertionError("memory batch adapter requires store")
        output_ref = call.expected_output_refs[0]
        report_ref = f"attempts/{call.call_id}/pi_agent_execution_report.json"
        store.write_text(output_ref, f"output for {call.call_id}\n")
        report = ExecutionReport(
            report_id=f"R-{call.call_id}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[output_ref],
            changed_refs=[output_ref, report_ref],
            evidence_refs=[],
        )
        store.write_json(report_ref, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
        )


class _RecordingStore:
    store_id = "piworker-batch-recording"

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
        raise AssertionError("store should not be called")

    def write_text(self, ref: str, text: str, *, media_type: str = "text/plain", metadata=None):
        self.calls.append(("write_text", ref))
        raise AssertionError("store should not be called")

    def write_json(self, ref: str, value, *, metadata=None):
        self.calls.append(("write_json", ref))
        raise AssertionError("store should not be called")

    def append_jsonl(self, ref: str, item, *, metadata=None):
        self.calls.append(("append_jsonl", ref))
        raise AssertionError("store should not be called")

    def hash_ref(self, ref: str) -> str:
        self.calls.append(("hash_ref", ref))
        return "sha256:" + "0" * 64

    def list_refs(self, prefix: str = "") -> list[str]:
        self.calls.append(("list_refs", prefix))
        return []


def _read_json(root: str, ref: str) -> dict:
    import json

    return json.loads((Path(root) / ref).read_text(encoding="utf-8"))


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


if __name__ == "__main__":
    unittest.main()
