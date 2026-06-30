from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import MemoryRefStore
from missionforge.kernel import Step, StepCompileContext, StepRunResult, StepStatus, run_step
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult


class KernelMemoryStoreTests(unittest.TestCase):
    def test_run_step_uses_memory_store_without_filesystem_side_effects(self) -> None:
        store = MemoryRefStore()
        store.write_json("contract/task_contract.json", {"contract_ref": "contract/task_contract.json"})
        store.write_json("sources/source_packet.json", {"source_ref": "sources/source_packet.json"})
        adapter = _MemoryStoreAdapter()
        step = Step(
            id="researcher",
            brief="Write a concise report.",
            inputs=["contract/task_contract.json", "sources/source_packet.json"],
            outputs=["reports/final_report.md"],
            read=["contract", "sources"],
            write=["reports"],
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            result = run_step(step, context=_context(), store=store, adapter=adapter)
            after = _snapshot(tmpdir)

        self.assertIsInstance(result, StepRunResult)
        self.assertIs(result.store, store)
        self.assertIs(adapter.seen_store, store)
        self.assertEqual(before, after)
        self.assertEqual(result.step_record.status, StepStatus.COMPLETED)
        self.assertEqual(store.read_json(result.step_spec_ref), step.to_dict())
        self.assertEqual(store.read_json(result.piworker_call_ref), result.compiled.piworker_call.to_dict())
        self.assertEqual(store.read_json(result.piworker_call_result_ref), result.call_result.to_dict())
        self.assertEqual(store.read_json(result.step_record_ref), result.step_record.to_dict())
        self.assertEqual(store.read_text("reports/final_report.md"), "memory adapter artifact\n")
        self.assertTrue(store.exists(result.step_record.metadata["context_projection_ref"]))
        self.assertTrue(store.exists(result.step_record.metadata["context_compile_result_ref"]))
        self.assertIn("sources/source_packet.json", result.step_record.input_hashes)


def _context() -> StepCompileContext:
    return StepCompileContext(
        flow_id="demo-flow",
        contract_id="demo-contract",
        contract_hash="sha256:" + "a" * 64,
    )


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


class _MemoryStoreAdapter:
    adapter_family = "kernel-test-memory-store"

    def __init__(self) -> None:
        self.seen_store = None
        self.seen_workspace = None

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
        self.seen_workspace = workspace
        self.seen_store = store
        if store is None:
            raise AssertionError("memory store adapter requires store")
        output_ref = call.expected_output_refs[0]
        report_ref = "attempts/demo-flow-researcher/pi_agent_execution_report.json"
        metric_ref = "attempts/demo-flow-researcher/pi_agent_metrics.json"
        store.write_text(output_ref, "memory adapter artifact\n")
        report = ExecutionReport(
            report_id="R-demo-flow-researcher",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[output_ref],
            changed_refs=[output_ref, "attempts/demo-flow-researcher/pi_agent_output.json"],
            evidence_refs=["evidence/adapter_event_001.json"],
            metrics={"metric_ref": metric_ref},
        )
        store.write_json(report_ref, report.to_dict())
        store.write_json(metric_ref, {"metric_ref": metric_ref})
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
            event_evidence_refs=["evidence/adapter_event_002.json"],
            metrics={"duration_ms": 1},
        )


if __name__ == "__main__":
    unittest.main()
