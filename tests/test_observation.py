from __future__ import annotations

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

    def test_observation_refs_cannot_escape_workspace(self) -> None:
        with TemporaryDirectory() as tmpdir:
            event = RunEvent.create(
                event_id="000001-run_started",
                run_id="run-001",
                kind=RunEventKind.RUN_STARTED,
            )
            with self.assertRaises(ContractValidationError):
                append_run_event(tmpdir, event, events_ref="../outside.jsonl")


if __name__ == "__main__":
    unittest.main()
