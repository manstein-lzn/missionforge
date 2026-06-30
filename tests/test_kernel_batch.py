from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError, MemoryRefStore
from missionforge.kernel import (
    KernelValidationError,
    Step,
    StepBatchResult,
    StepCompileContext,
    Toolset,
    run_steps_batch,
)
from missionforge.piworker_call import PiWorkerCallRole
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult


HASH_A = "sha256:" + "a" * 64


class KernelBatchTests(unittest.TestCase):
    def test_run_steps_batch_uses_distinct_context_boundaries(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
            ),
            Step(
                id="billing",
                brief="Analyze billing.",
                inputs=["inputs/billing.txt"],
                outputs=["out/billing/report.txt"],
                read=["inputs"],
                write=["out/billing"],
            ),
        ]
        adapter_factory = _KernelBatchAdapterFactory()

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_text(root, "inputs/auth.txt", "auth\n")
            _write_text(root, "inputs/billing.txt", "billing\n")
            result = run_steps_batch(
                steps,
                context=_context(),
                workspace=root,
                batch_id="analysis",
                concurrency=2,
                adapter_factory=adapter_factory,
            )

        result.validate()
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.completed_step_ids, ["auth", "billing"])
        self.assertEqual(
            result.step_record_refs,
            [
                "kernel/demo-flow/batches/analysis/steps/001-auth/step_record.json",
                "kernel/demo-flow/batches/analysis/steps/002-billing/step_record.json",
            ],
        )
        self.assertEqual(
            sorted(call.call_id for call in adapter_factory.seen_calls),
            ["demo-flow-analysis-001-auth", "demo-flow-analysis-002-billing"],
        )
        context_refs = [step_result.step_record.metadata["context_projection_ref"] for step_result in result.step_results]
        self.assertEqual(len(context_refs), 2)
        self.assertNotEqual(context_refs[0], context_refs[1])
        self.assertIn(context_refs[0], result.runtime_refs)
        self.assertIn(context_refs[1], result.runtime_refs)
        self.assertTrue(context_refs[0].startswith("kernel/demo-flow/batches/analysis/steps/001-auth/"))
        self.assertTrue(context_refs[1].startswith("kernel/demo-flow/batches/analysis/steps/002-billing/"))
        for step_result in result.step_results:
            self.assertIn("context_compile_result_ref", step_result.step_record.metadata)
            self.assertIn("context_turn_boundary_ref", step_result.step_record.metadata)
            self.assertEqual(step_result.compiled.piworker_call.role, PiWorkerCallRole.EXECUTOR)

    def test_run_steps_batch_rejects_shared_adapter_for_concurrent_execution(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
            ),
            Step(
                id="billing",
                brief="Analyze billing.",
                inputs=["inputs/billing.txt"],
                outputs=["out/billing/report.txt"],
                read=["inputs"],
                write=["out/billing"],
            ),
        ]

        with self.assertRaisesRegex(KernelValidationError, "adapter_factory"):
            run_steps_batch(steps, context=_context(), workspace=".", concurrency=2, adapter=_KernelBatchAdapter())

    def test_run_steps_batch_rejects_output_conflicts_before_execution(self) -> None:
        adapter = _KernelBatchAdapter()
        steps = [
            Step(
                id="a",
                brief="A.",
                inputs=["inputs/a.txt"],
                outputs=["out/report.txt"],
                read=["inputs"],
                write=["out"],
            ),
            Step(
                id="b",
                brief="B.",
                inputs=["inputs/b.txt"],
                outputs=["out/report.txt"],
                read=["inputs"],
                write=["out/b"],
            ),
        ]

        with TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(KernelValidationError, "duplicate output ref|write refs overlap"):
                run_steps_batch(steps, context=_context(), workspace=tmpdir, adapter=adapter)

        self.assertEqual(adapter.seen_calls, [])

    def test_run_steps_batch_rejects_parent_child_write_conflicts(self) -> None:
        steps = [
            Step(
                id="a",
                brief="A.",
                inputs=["inputs/a.txt"],
                outputs=["out/a/report.txt"],
                read=["inputs"],
                write=["out"],
            ),
            Step(
                id="b",
                brief="B.",
                inputs=["inputs/b.txt"],
                outputs=["out/b/report.txt"],
                read=["inputs"],
                write=["out/b"],
            ),
        ]

        with self.assertRaisesRegex(KernelValidationError, "write refs overlap"):
            run_steps_batch(steps, context=_context(), workspace=".", adapter=_KernelBatchAdapter())

    def test_run_steps_batch_validates_extension_lock_ref_before_store_writes(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
            )
        ]
        store = MemoryRefStore()

        with self.assertRaises(ContractValidationError):
            run_steps_batch(
                steps,
                context=_context(),
                store=store,
                adapter=_KernelBatchAdapter(),
                extension_lock_ref="../bad.json",
            )

        self.assertEqual(store.list_refs(), [])

    def test_run_steps_batch_validates_extension_install_root_ref_before_store_writes(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
            )
        ]
        store = MemoryRefStore()

        with self.assertRaises(ContractValidationError):
            run_steps_batch(
                steps,
                context=_context(),
                store=store,
                adapter=_KernelBatchAdapter(),
                extension_install_root_ref="../bad",
            )

        self.assertEqual(store.list_refs(), [])

    def test_run_steps_batch_does_not_collect_extension_lock_boundary_error(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
                tools=["read", "write", "academic"],
            )
        ]
        toolsets = {
            "academic": Toolset(
                id="academic",
                package="local:extensions/pi-academic-sources",
                tools=["academic_search"],
                network=True,
            )
        }
        store = MemoryRefStore()

        with self.assertRaises(ContractValidationError):
            run_steps_batch(
                steps,
                context=_context(),
                store=store,
                adapter=_KernelBatchAdapter(),
                toolsets=toolsets,
                extension_lock_ref="compiled/missing_lock.json",
            )

        self.assertEqual(store.list_refs(), [])

    def test_run_steps_batch_requires_filesystem_before_extension_step_writes(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
                tools=["read", "write", "academic"],
            )
        ]
        toolsets = {
            "academic": Toolset(
                id="academic",
                package="local:extensions/pi-academic-sources",
                tools=["academic_search"],
                network=True,
            )
        }
        store = MemoryRefStore()

        with self.assertRaisesRegex(KernelValidationError, "extension locks require an explicit filesystem workspace"):
            run_steps_batch(
                steps,
                context=_context(),
                store=store,
                adapter=_KernelBatchAdapter(),
                toolsets=toolsets,
            )

        self.assertEqual(store.list_refs(), [])

    def test_run_steps_batch_collects_step_runtime_exception(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
            ),
            Step(
                id="billing",
                brief="Analyze billing.",
                inputs=["inputs/billing.txt"],
                outputs=["out/billing/report.txt"],
                read=["inputs"],
                write=["out/billing"],
            ),
        ]
        adapter_factory = _KernelBatchAdapterFactory(failing_call_id="demo-flow-analysis-002-billing")

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_text(root, "inputs/auth.txt", "auth\n")
            _write_text(root, "inputs/billing.txt", "billing\n")
            result = run_steps_batch(
                steps,
                context=_context(),
                workspace=root,
                batch_id="analysis",
                concurrency=2,
                adapter_factory=adapter_factory,
            )

            self.assertEqual(result.status, "partial")
            self.assertEqual(result.completed_step_ids, ["auth"])
            self.assertEqual(result.failed_step_ids, ["billing"])
            self.assertEqual(
                result.step_record_refs,
                [
                    "kernel/demo-flow/batches/analysis/steps/001-auth/step_record.json",
                    "kernel/demo-flow/batches/analysis/steps/002-billing/step_record.json",
                ],
            )
            self.assertEqual(
                result.failure_refs,
                ["kernel/demo-flow/batches/analysis/steps/002-billing/batch_error.json"],
            )
            self.assertTrue((root / result.failure_refs[0]).is_file())

    def test_run_steps_batch_can_run_entirely_in_memory_store(self) -> None:
        steps = [
            Step(
                id="auth",
                brief="Analyze auth.",
                inputs=["inputs/auth.txt"],
                outputs=["out/auth/report.txt"],
                read=["inputs"],
                write=["out/auth"],
            ),
            Step(
                id="billing",
                brief="Analyze billing.",
                inputs=["inputs/billing.txt"],
                outputs=["out/billing/report.txt"],
                read=["inputs"],
                write=["out/billing"],
            ),
        ]
        store = MemoryRefStore()
        store.write_text("inputs/auth.txt", "auth\n")
        store.write_text("inputs/billing.txt", "billing\n")
        adapter_factory = _MemoryKernelBatchAdapterFactory(store)

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            result = run_steps_batch(
                steps,
                context=_context(),
                store=store,
                batch_id="analysis",
                concurrency=2,
                adapter_factory=adapter_factory,
            )
            after = _snapshot(tmpdir)

        self.assertIs(result.store, store)
        self.assertEqual(before, after)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.completed_step_ids, ["auth", "billing"])
        self.assertEqual(store.read_text("out/auth/report.txt"), "output for demo-flow-analysis-001-auth\n")
        self.assertEqual(store.read_text("out/billing/report.txt"), "output for demo-flow-analysis-002-billing\n")
        for ref in result.step_record_refs:
            self.assertTrue(store.exists(ref))


def _context() -> StepCompileContext:
    return StepCompileContext(
        flow_id="demo-flow",
        contract_id="demo-contract",
        contract_hash=HASH_A,
    )


class _KernelBatchAdapter:
    adapter_family = "kernel-batch-test"

    def __init__(self, *, failing_call_id: str = "") -> None:
        self.seen_calls = []
        self.failing_call_id = failing_call_id

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
        self.seen_calls.append(call)
        if call.call_id == self.failing_call_id:
            raise RuntimeError(f"boom {call.call_id}")
        output_ref = call.expected_output_refs[0]
        _write_text(Path(workspace), output_ref, f"output for {call.call_id}\n")
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


class _KernelBatchAdapterFactory:
    def __init__(self, *, failing_call_id: str = "") -> None:
        self.adapters: list[_KernelBatchAdapter] = []
        self.failing_call_id = failing_call_id

    @property
    def seen_calls(self):
        return [call for adapter in self.adapters for call in adapter.seen_calls]

    def __call__(self, step: Step) -> _KernelBatchAdapter:
        call_id = f"demo-flow-analysis-{len(self.adapters) + 1:03d}-{step.id}"
        adapter = _KernelBatchAdapter(
            failing_call_id=call_id if call_id == self.failing_call_id else "",
        )
        self.adapters.append(adapter)
        return adapter


class _MemoryKernelBatchAdapter:
    adapter_family = "kernel-memory-batch-test"

    def __init__(self, store: MemoryRefStore) -> None:
        self.store = store
        self.seen_calls = []

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
        self.seen_calls.append(call)
        active_store = store or self.store
        output_ref = call.expected_output_refs[0]
        active_store.write_text(output_ref, f"output for {call.call_id}\n")
        report_ref = f"attempts/{call.call_id}/pi_agent_execution_report.json"
        report = ExecutionReport(
            report_id=f"R-{call.call_id}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=[output_ref],
            changed_refs=[output_ref, report_ref],
            evidence_refs=[],
        )
        active_store.write_json(report_ref, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
        )


class _MemoryKernelBatchAdapterFactory:
    def __init__(self, store: MemoryRefStore) -> None:
        self.store = store
        self.adapters: list[_MemoryKernelBatchAdapter] = []

    def __call__(self, step: Step) -> _MemoryKernelBatchAdapter:
        adapter = _MemoryKernelBatchAdapter(self.store)
        self.adapters.append(adapter)
        return adapter


def _write_text(root: Path, ref: str, text: str) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


if __name__ == "__main__":
    unittest.main()
