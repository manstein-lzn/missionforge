from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    ContractValidationError,
    FileControlPort,
    FileInteractionPort,
    RunEvent,
    RunEventKind,
    RunSnapshot,
    RunSnapshotStatus,
    UserEventKind,
    append_run_event,
    latest_run_snapshot,
    read_run_events,
    read_run_snapshot,
    write_run_snapshot,
)
from missionforge.ref_store import MemoryRefStore


class ObservationTests(unittest.TestCase):
    def test_run_event_round_trips_through_refs_only_jsonl(self) -> None:
        with TemporaryDirectory() as tmpdir:
            event = RunEvent.create(
                event_id="000001-run_started",
                run_id="run-001",
                kind=RunEventKind.RUN_STARTED,
                status="running",
                refs=["contract/task_contract.json"],
                metadata={"flow_execution_id": "001"},
            )
            append_run_event(tmpdir, event)
            events = read_run_events(tmpdir, run_id="run-001")

        self.assertEqual(events, [event])
        self.assertEqual(events[0].to_dict()["kind"], "run_started")

    def test_run_event_round_trips_through_memory_store_without_filesystem_writes(self) -> None:
        store = MemoryRefStore()
        event = RunEvent.create(
            event_id="000001-run_started",
            run_id="run-001",
            kind=RunEventKind.RUN_STARTED,
            status="running",
            refs=["contract/task_contract.json"],
            metadata={"flow_execution_id": "001"},
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            append_run_event(store, event)
            events = read_run_events(store, run_id="run-001")
            after = _snapshot(tmpdir)

        self.assertEqual(before, after)
        self.assertEqual(events, [event])
        self.assertTrue(store.exists("observation/run_events.jsonl"))

    def test_run_event_rejects_raw_metadata(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "raw_transcript"):
            RunEvent.create(
                event_id="000001-run_started",
                run_id="run-001",
                kind=RunEventKind.RUN_STARTED,
                metadata={"raw_transcript": "do not persist raw chat here"},
            )

    def test_file_control_port_uses_interaction_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            interaction = FileInteractionPort(tmpdir)
            control = FileControlPort(interaction)
            events = [
                control.inject_message(run_id="run-001", target="researcher", text="补充一个约束。"),
                control.pause(run_id="run-001"),
                control.cancel(run_id="run-001"),
                control.request_revision(run_id="run-001", text="需要修改合同。"),
                control.resume(run_id="run-001"),
                control.stop_after_current_turn(run_id="run-001"),
                control.force_checkpoint(run_id="run-001"),
            ]
            persisted = interaction.read_user_events(run_id="run-001")

        self.assertEqual(persisted, events)
        self.assertEqual([event.kind for event in persisted], [
            UserEventKind.MESSAGE,
            UserEventKind.PAUSE_REQUEST,
            UserEventKind.CANCEL_REQUEST,
            UserEventKind.CONTRACT_REVISION_REQUEST,
            UserEventKind.RESUME_REQUEST,
            UserEventKind.STOP_AFTER_CURRENT_TURN,
            UserEventKind.CHECKPOINT_REQUEST,
        ])

    def test_latest_snapshot_counts_pending_events_and_persists(self) -> None:
        with TemporaryDirectory() as tmpdir:
            interaction = FileInteractionPort(tmpdir)
            interaction.submit_text("请暂停。", run_id="run-001", target="flow")
            append_run_event(
                tmpdir,
                RunEvent.create(
                    event_id="000001-safe_point_reached",
                    run_id="run-001",
                    kind=RunEventKind.SAFE_POINT_REACHED,
                    status="running",
                    step_id="researcher",
                    refs=["interaction/safe_points/001-researcher-user_events.json"],
                ),
            )
            snapshot = latest_run_snapshot(
                run_id="run-001",
                status=RunSnapshotStatus.RUNNING,
                workspace=tmpdir,
                current_step_id="researcher",
                current_role="executor_piworker",
                interaction_port=interaction,
                target="researcher",
                flow_ledger_ref="kernel/run-001/flow_ledger.jsonl",
                flow_result_ref="kernel/run-001/flow_result.json",
                last_safe_point_ref="interaction/safe_points/001-researcher-user_events.json",
                step_record_refs=["kernel/run-001/steps/researcher/step_record.json"],
                context_projection_refs=["kernel/run-001/steps/researcher/context_projection.json"],
                artifact_refs=["reports/final_report.md"],
            )
            snapshot_ref = write_run_snapshot(tmpdir, snapshot)
            reloaded = read_run_snapshot(tmpdir, snapshot_ref=snapshot_ref)

        self.assertIsInstance(reloaded, RunSnapshot)
        self.assertEqual(reloaded.pending_user_event_count, 1)
        self.assertEqual(reloaded.latest_event_id, "000001-safe_point_reached")
        self.assertEqual(reloaded.current_step_id, "researcher")
        self.assertEqual(reloaded.status, RunSnapshotStatus.RUNNING)

    def test_latest_snapshot_persists_in_memory_store_without_filesystem_writes(self) -> None:
        store = MemoryRefStore()
        append_run_event(
            store,
            RunEvent.create(
                event_id="000001-safe_point_reached",
                run_id="run-001",
                kind=RunEventKind.SAFE_POINT_REACHED,
                status="running",
                step_id="researcher",
                refs=["interaction/safe_points/001-researcher-user_events.json"],
            ),
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            snapshot = latest_run_snapshot(
                run_id="run-001",
                status=RunSnapshotStatus.RUNNING,
                workspace=store,
                current_step_id="researcher",
                current_role="executor_piworker",
                flow_ledger_ref="kernel/run-001/flow_ledger.jsonl",
                flow_result_ref="kernel/run-001/flow_result.json",
                last_safe_point_ref="interaction/safe_points/001-researcher-user_events.json",
                step_record_refs=["kernel/run-001/steps/researcher/step_record.json"],
                context_projection_refs=["kernel/run-001/steps/researcher/context_projection.json"],
                artifact_refs=["reports/final_report.md"],
            )
            snapshot_ref = write_run_snapshot(store, snapshot)
            reloaded = read_run_snapshot(store, snapshot_ref=snapshot_ref)
            after = _snapshot(tmpdir)

        self.assertEqual(before, after)
        self.assertEqual(reloaded.pending_user_event_count, 0)
        self.assertEqual(reloaded.latest_event_id, "000001-safe_point_reached")
        self.assertEqual(reloaded.current_step_id, "researcher")
        self.assertEqual(reloaded.status, RunSnapshotStatus.RUNNING)

    def test_observation_refs_cannot_escape_workspace(self) -> None:
        with TemporaryDirectory() as tmpdir:
            event = RunEvent.create(
                event_id="000001-run_started",
                run_id="run-001",
                kind=RunEventKind.RUN_STARTED,
            )
            with self.assertRaises(ContractValidationError):
                append_run_event(tmpdir, event, events_ref="../outside.jsonl")

    def test_observation_validates_ref_before_custom_store_call(self) -> None:
        store = _RecordingStore()
        event = RunEvent.create(
            event_id="000001-run_started",
            run_id="run-001",
            kind=RunEventKind.RUN_STARTED,
        )

        with self.assertRaises(ContractValidationError):
            append_run_event(store, event, events_ref="../outside.jsonl")
        with self.assertRaises(ContractValidationError):
            read_run_events(store, events_ref="../outside.jsonl")

        self.assertEqual(store.calls, [])


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


class _RecordingStore:
    store_id = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def exists(self, ref: str) -> bool:
        self.calls.append(("exists", ref))
        return False

    def read_jsonl(self, ref: str):
        self.calls.append(("read_jsonl", ref))
        return []

    def append_jsonl(self, ref: str, item, *, metadata=None):
        self.calls.append(("append_jsonl", ref))
        raise AssertionError("store should not be called")

    def read_json(self, ref: str):
        self.calls.append(("read_json", ref))
        return {}

    def write_json(self, ref: str, value, *, metadata=None):
        self.calls.append(("write_json", ref))
        raise AssertionError("store should not be called")


if __name__ == "__main__":
    unittest.main()
