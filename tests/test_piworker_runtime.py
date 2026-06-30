from __future__ import annotations

import unittest

from missionforge import MemoryRefStore, PiWorkerCall, PiWorkerCallRole, run_piworker_call
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult


HASH_A = "sha256:" + "a" * 64


class PiWorkerRuntimeTests(unittest.TestCase):
    def test_run_piworker_call_passes_store_to_store_aware_adapter(self) -> None:
        store = MemoryRefStore()
        adapter = _StoreAwareAdapter()

        result = run_piworker_call(_call(), store=store, adapter=adapter, workspace=_NoFilesystemWorkspace())

        self.assertIs(adapter.seen_store, store)
        self.assertEqual(result.output_refs, ["out/report.txt"])
        self.assertEqual(store.read_text("out/report.txt"), "report\n")

    def test_run_piworker_call_does_not_pass_store_to_legacy_adapter(self) -> None:
        store = MemoryRefStore()
        adapter = _LegacyAdapter()

        result = run_piworker_call(_call(), store=store, adapter=adapter, workspace="unused")

        self.assertTrue(adapter.called)
        self.assertEqual(result.output_refs, ["out/report.txt"])


def _call() -> PiWorkerCall:
    return PiWorkerCall(
        call_id="call-001",
        role=PiWorkerCallRole.EXECUTOR,
        contract_id="contract-001",
        contract_hash=HASH_A,
        contract_ref="contract/task_contract.json",
        objective="Produce output.",
        visible_refs=["contract/task_contract.json"],
        writable_refs=["out"],
        expected_output_refs=["out/report.txt"],
        permission_manifest_ref="policy/permission_manifest.json",
    )


class _StoreAwareAdapter:
    adapter_family = "store-aware"

    def __init__(self) -> None:
        self.seen_store = None

    def run_call(
        self,
        call,
        *,
        workspace=".",
        store=None,
        evidence_store=None,
        call_spec=None,
        exit_criteria=None,
        stop_conditions=None,
        extension_lock_ref=None,
    ):
        self.seen_store = store
        store.write_text("out/report.txt", "report\n")
        report = ExecutionReport(
            report_id="R-call-001",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=["out/report.txt"],
            changed_refs=["out/report.txt"],
            evidence_refs=[],
        )
        store.write_json("attempts/call-001/execution_report.json", report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref="attempts/call-001/execution_report.json"),
        )


class _LegacyAdapter:
    adapter_family = "legacy"

    def __init__(self) -> None:
        self.called = False

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
    ):
        self.called = True
        return WorkerAdapterResult(
            execution_report=ExecutionReport(
                report_id="R-call-001",
                call_id=call.call_id,
                status="completed",
                produced_artifacts=["out/report.txt"],
                changed_refs=["out/report.txt"],
                evidence_refs=[],
            ),
            worker_result=WorkerResult(status="completed", execution_report_ref="attempts/call-001/execution_report.json"),
        )


class _NoFilesystemWorkspace:
    def __fspath__(self) -> str:
        raise AssertionError("store-aware adapter must not materialize a filesystem workspace")

    def __str__(self) -> str:
        raise AssertionError("store-aware adapter must not stringify a filesystem workspace")


if __name__ == "__main__":
    unittest.main()
