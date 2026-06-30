from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import ContractValidationError, MemoryRefStore, StoreInteractionPort
from missionforge.kernel import (
    Artifact,
    ArtifactRole,
    Flow,
    FlowStop,
    Projection,
    Step,
    StepCompileContext,
    StepStatus,
    inspect_kernel_run,
    run_projection,
    run_flow,
)
from missionforge.piworker_call import PiWorkerCallRole
from missionforge.runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult


class KernelFlowMemoryStoreTests(unittest.TestCase):
    def test_run_flow_routes_and_records_entire_flow_in_memory_store(self) -> None:
        store = MemoryRefStore()
        store.write_json("contract/task_contract.json", {"contract_ref": "contract/task_contract.json"})
        store.write_json("inputs/request.json", {"request_ref": "inputs/request.json"})
        adapter = _MemoryFlowAdapter()
        flow = Flow(
            id="memory-flow",
            steps=[
                Step(
                    id="executor",
                    brief="Write a report and route to judge.",
                    inputs=["contract/task_contract.json", "inputs/request.json"],
                    outputs=["reports/final.md", "decisions/executor.json"],
                    read=["contract", "inputs"],
                    write=["reports", "decisions"],
                    route_on="decisions/executor.json",
                    route_fields=["decision"],
                ),
                Step(
                    id="judge",
                    brief="Judge the report.",
                    inputs=["contract/task_contract.json", "reports/final.md", "decisions/executor.json"],
                    outputs=["judge/decision.json"],
                    read=["contract", "reports", "decisions"],
                    write=["judge"],
                    role=PiWorkerCallRole.JUDGE,
                    route_on="judge/decision.json",
                    route_fields=["decision"],
                ),
            ],
            routes={
                "executor.ready_for_judge": "judge",
                "judge.accepted": FlowStop(status="accepted"),
            },
            artifacts=[
                Artifact("reports/final.md", role=ArtifactRole.OUTPUT, owner="piworker"),
                Artifact("decisions/executor.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("judge/decision.json", role=ArtifactRole.DECISION, owner="piworker"),
            ],
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            result = run_flow(flow, context=_context(), store=store, adapter=adapter)
            after = _snapshot(tmpdir)

        self.assertIs(result.store, store)
        self.assertEqual(before, after)
        self.assertEqual(result.flow_result.status, "accepted")
        self.assertEqual([item.step_record.status for item in result.step_results], [StepStatus.COMPLETED, StepStatus.COMPLETED])
        self.assertEqual(store.read_json(result.flow_result_ref), result.flow_result.to_dict())
        ledger = store.read_jsonl(result.flow_result.ledger_refs[0])
        self.assertEqual(ledger[0]["kind"], "started")
        self.assertEqual(ledger[-1]["kind"], "stopped")
        self.assertEqual(ledger[-1]["status"], "accepted")
        self.assertTrue(store.exists(result.flow_result.metadata["run_events_ref"]))
        self.assertTrue(store.exists(result.flow_result.metadata["run_snapshot_ref"]))
        self.assertEqual(store.read_json("decisions/executor.json")["decision"], "ready_for_judge")
        self.assertEqual(store.read_json("judge/decision.json")["decision"], "accepted")

    def test_inspect_kernel_run_reads_memory_store_records(self) -> None:
        store = MemoryRefStore()
        store.write_json("contract/task_contract.json", {"contract_ref": "contract/task_contract.json"})
        store.write_json("inputs/request.json", {"request_ref": "inputs/request.json"})
        flow = Flow(
            id="memory-flow",
            steps=[
                Step(
                    id="executor",
                    brief="Write a report and route to judge.",
                    inputs=["contract/task_contract.json", "inputs/request.json"],
                    outputs=["reports/final.md", "decisions/executor.json"],
                    read=["contract", "inputs"],
                    write=["reports", "decisions"],
                    route_on="decisions/executor.json",
                    route_fields=["decision"],
                ),
                Step(
                    id="judge",
                    brief="Judge the report.",
                    inputs=["contract/task_contract.json", "reports/final.md", "decisions/executor.json"],
                    outputs=["judge/decision.json"],
                    read=["contract", "reports", "decisions"],
                    write=["judge"],
                    role=PiWorkerCallRole.JUDGE,
                    route_on="judge/decision.json",
                    route_fields=["decision"],
                ),
            ],
            routes={
                "executor.ready_for_judge": "judge",
                "judge.accepted": FlowStop(status="accepted"),
            },
            artifacts=[
                Artifact("reports/final.md", role=ArtifactRole.OUTPUT, owner="piworker"),
                Artifact("decisions/executor.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("judge/decision.json", role=ArtifactRole.DECISION, owner="piworker"),
            ],
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            result = run_flow(flow, context=_context(), store=store, adapter=_MemoryFlowAdapter())
            inspection = inspect_kernel_run(store, result.flow_result_ref)
            after = _snapshot(tmpdir)

        self.assertEqual(before, after)
        self.assertEqual(inspection.status, "accepted")
        self.assertEqual(inspection.snapshot_status, "accepted")
        self.assertEqual(inspection.flow_result_ref, result.flow_result_ref)
        self.assertEqual(inspection.flow_ledger_ref, result.flow_result.ledger_refs[0])
        self.assertEqual(inspection.run_events_ref, result.flow_result.metadata["run_events_ref"])
        self.assertEqual(inspection.run_snapshot_ref, result.flow_result.metadata["run_snapshot_ref"])
        self.assertEqual(inspection.latest_event_kind, "run_stopped")
        self.assertEqual(inspection.ledger_event_count, len(store.read_jsonl(result.flow_result.ledger_refs[0])))
        self.assertEqual([record.step_id for record in inspection.step_records], ["executor", "judge"])
        self.assertEqual(inspection.final_artifact_refs, ["reports/final.md", "decisions/executor.json", "judge/decision.json"])

    def test_run_flow_accepts_store_backed_interaction_port_without_filesystem_writes(self) -> None:
        store = MemoryRefStore()
        store.write_json("contract/task_contract.json", {"contract_ref": "contract/task_contract.json"})
        store.write_json("inputs/request.json", {"request_ref": "inputs/request.json"})
        interaction = StoreInteractionPort(store)
        event = interaction.submit_text(
            "Please stop after this turn.",
            run_id="memory-flow",
            target="executor",
            kind="stop_after_current_turn",
            delivery="after_current_turn",
        )
        flow = Flow(
            id="memory-flow",
            steps=[
                Step(
                    id="executor",
                    brief="Write a report and route to judge.",
                    inputs=["contract/task_contract.json", "inputs/request.json"],
                    outputs=["reports/final.md", "decisions/executor.json"],
                    read=["contract", "inputs"],
                    write=["reports", "decisions"],
                    route_on="decisions/executor.json",
                    route_fields=["decision"],
                ),
                Step(
                    id="judge",
                    brief="Judge the report.",
                    inputs=["contract/task_contract.json", "reports/final.md", "decisions/executor.json"],
                    outputs=["judge/decision.json"],
                    read=["contract", "reports", "decisions"],
                    write=["judge"],
                    role=PiWorkerCallRole.JUDGE,
                    route_on="judge/decision.json",
                    route_fields=["decision"],
                ),
            ],
            routes={
                "executor.ready_for_judge": "judge",
                "judge.accepted": FlowStop(status="accepted"),
            },
            artifacts=[
                Artifact("reports/final.md", role=ArtifactRole.OUTPUT, owner="piworker"),
                Artifact("decisions/executor.json", role=ArtifactRole.DECISION, owner="piworker"),
                Artifact("judge/decision.json", role=ArtifactRole.DECISION, owner="piworker"),
            ],
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            result = run_flow(
                flow,
                context=_context(),
                store=store,
                adapter=_MemoryFlowAdapter(),
                interaction_port=interaction,
            )
            after = _snapshot(tmpdir)

        self.assertEqual(before, after)
        self.assertEqual(result.flow_result.status, "blocked")
        self.assertEqual(result.flow_result.metadata["stop_reason"], "user_stop_after_current_turn_requested")
        self.assertEqual(interaction.read_acks(run_id="memory-flow")[0].event_id, event.event_id)
        self.assertEqual(interaction.pending_user_events(run_id="memory-flow", target="executor"), [])
        self.assertTrue(result.flow_result.metadata["run_snapshot_ref"])
        self.assertTrue(store.exists(result.flow_result.metadata["run_snapshot_ref"]))

    def test_run_projection_with_memory_store_passes_ref_sources_to_projector(self) -> None:
        store = MemoryRefStore()
        store.write_text("reports/final.md", "final report\n")
        seen_sources = []

        def projector(sources, projection):
            seen_sources.append(dict(sources))
            return {"source_ref": sources["reports/final.md"]}

        result = run_projection(
            Projection(output="reports/index.json", from_=["reports/final.md"], projector="index"),
            workspace=store,
            projectors={"index": projector},
        )

        self.assertEqual(seen_sources, [{"reports/final.md": "reports/final.md"}])
        self.assertEqual(store.read_json("reports/index.json"), {"source_ref": "reports/final.md"})
        self.assertEqual(store.read_json(result.record_ref), result.record.to_dict())

    def test_run_projection_validates_refs_before_custom_store_call(self) -> None:
        store = _RecordingStore()

        def projector(sources, projection):
            return {"source_ref": "reports/final.md"}

        with self.assertRaises(ContractValidationError):
            run_projection(
                Projection(output="../outside.json", from_=["reports/final.md"], projector="index"),
                workspace=store,
                projectors={"index": projector},
            )
        with self.assertRaises(ContractValidationError):
            run_projection(
                Projection(output="reports/index.json", from_=["../outside.json"], projector="index"),
                workspace=store,
                projectors={"index": projector},
            )
        self.assertEqual(store.calls, [])

    def test_run_projection_validates_record_ref_before_projector_and_output_write(self) -> None:
        store = MemoryRefStore()
        store.write_text("reports/final.md", "final report\n")
        projector_calls = []

        def projector(sources, projection):
            projector_calls.append(dict(sources))
            return {"source_ref": "reports/final.md"}

        with self.assertRaises(ContractValidationError):
            run_projection(
                Projection(output="reports/index.json", from_=["reports/final.md"], projector="index"),
                workspace=store,
                projectors={"index": projector},
                record_ref="../bad.json",
            )

        self.assertEqual(projector_calls, [])
        self.assertFalse(store.exists("reports/index.json"))


def _context() -> StepCompileContext:
    return StepCompileContext(
        flow_id="memory-flow",
        contract_id="contract-001",
        contract_hash="sha256:" + "a" * 64,
    )


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


class _MemoryFlowAdapter:
    adapter_family = "kernel-memory-flow"

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
    ):
        if store is None:
            raise AssertionError("memory flow adapter requires store")
        if call.call_id.endswith("executor"):
            store.write_text("reports/final.md", "final report\n")
            store.write_json("decisions/executor.json", {"decision": "ready_for_judge"})
            produced = ["reports/final.md", "decisions/executor.json"]
        elif call.call_id.endswith("judge"):
            store.write_json("judge/decision.json", {"decision": "accepted"})
            produced = ["judge/decision.json"]
        else:
            raise AssertionError(f"unexpected call_id: {call.call_id}")
        report_ref = f"attempts/{call.call_id}/pi_agent_execution_report.json"
        report = ExecutionReport(
            report_id=f"R-{call.call_id}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=produced,
            changed_refs=[*produced, report_ref],
            evidence_refs=[],
        )
        store.write_json(report_ref, report.to_dict())
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
        )


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


if __name__ == "__main__":
    unittest.main()
