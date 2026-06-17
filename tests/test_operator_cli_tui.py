from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.adapters.cli import MissionCLI
from missionforge.tui import build_tui_snapshot, render_tui_snapshot
from tests.operator_state_fixtures import workspace_snapshot


class OperatorCLITuiTests(unittest.TestCase):
    def test_tui_snapshot_is_read_only_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_tui_run(root)
            before = workspace_snapshot(root)

            snapshot = build_tui_snapshot(root, run_ref="runs/demo", event_tail=4)
            rendered = render_tui_snapshot(snapshot, width=100)
            after = workspace_snapshot(root)

            self.assertEqual(before, after)
            self.assertEqual(snapshot.status, "active")
            self.assertIn("runs/demo/attempts/WU-000001/pi_agent_events.jsonl", rendered)
            self.assertIn("reports/final_report.md", rendered)
            self.assertNotIn("Secret raw event body", rendered)
            self.assertNotIn("Full report body", rendered)
            self.assertNotIn("outside.json", rendered)

    def test_tui_command_returns_refs_only_snapshot_summary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_tui_run(root)

            result = MissionCLI().run_command(
                [
                    "tui",
                    "--workspace",
                    str(root),
                    "--run-ref",
                    "runs/demo",
                    "--json",
                    "--event-tail",
                    "4",
                ]
            )
            payload = json.dumps(result.to_dict(), sort_keys=True)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.command, "tui")
            self.assertEqual(result.data["snapshot_status"], "active")
            self.assertEqual(result.data["event_file_count"], 1)
            self.assertEqual(result.data["report_file_count"], 3)
            self.assertEqual(result.data["artifact_file_count"], 2)
            self.assertIn("runs/demo/reports/final_report.md", result.refs)
            self.assertNotIn("Secret raw event body", payload)
            self.assertNotIn("Full report body", payload)
            self.assertNotIn(str(root), payload)
            self.assertNotIn("../outside.json", payload)

    def test_tui_missing_run_ref_is_observable_without_failure(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = MissionCLI().run_command(
                [
                    "tui",
                    "--workspace",
                    tmpdir,
                    "--run-ref",
                    "runs/missing",
                    "--json",
                ]
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.data["snapshot_status"], "missing")
            self.assertEqual(result.data["warning_count"], 1)
            self.assertEqual(result.refs, [])

    def test_tui_rejects_workspace_escape_ref(self) -> None:
        with TemporaryDirectory() as tmpdir:
            result = MissionCLI().run_command(
                [
                    "tui",
                    "--workspace",
                    tmpdir,
                    "--run-ref",
                    "../outside",
                    "--json",
                ]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")

    def test_tui_watch_is_terminal_only_not_machine_command(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_tui_run(root)

            result = MissionCLI().run_command(
                [
                    "tui",
                    "--workspace",
                    str(root),
                    "--run-ref",
                    "runs/demo",
                    "--watch",
                    "--json",
                ]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.error.code if result.error else "", "invalid_input")


def seed_tui_run(root: Path) -> None:
    run = root / "runs/demo"
    write_jsonl(
        run / "attempts/WU-000001/pi_agent_events.jsonl",
        [
            {
                "event_type": "started",
                "status": "running",
                "call_id": "WU-000001",
                "payload": {"body": "Secret raw event body", "output_ref": "runs/demo/reports/final_report.md"},
            },
            {
                "event_type": "completed",
                "status": "completed",
                "call_id": "WU-000001",
                "refs": ["runs/demo/reports/final_report.md", "../outside.json"],
                "payload": {"status": "completed"},
            },
        ],
    )
    write_json(
        run / "attempts/WU-000001/pi_agent_execution_report.json",
        {
            "schema_version": "agent_execution_report.v1",
            "report_id": "R-WU-000001",
            "call_id": "WU-000001",
            "status": "completed",
            "worker_status": "completed",
            "produced_artifact_refs": ["runs/demo/reports/final_report.md"],
            "changed_refs": ["runs/demo/reports/final_report.md"],
            "evidence_refs": ["runs/demo/sources/source_packet.json"],
            "metric_refs": ["runs/demo/attempts/WU-000001/pi_agent_metrics.json"],
            "metrics": {"duration_ms": 1234, "total_tokens": 5678},
        },
    )
    write_json(
        run / "attempts/WU-000001/reports/extension_load_report.json",
        {
            "schema_version": "missionforge_extension_load_report.v1",
            "call_id": "WU-000001",
            "loaded_extensions": [{"grant_id": "web-search"}],
            "rejected_extensions": [],
        },
    )
    write_json(run / "attempts/WU-000001/pi_agent_metrics.json", {"status": "completed", "metrics": {"turn_count": 3}})
    write_text(run / "reports/final_report.md", "# Final\n\nFull report body should not be emitted.\n")
    write_json(run / "sources/source_packet.json", {"status": "completed", "body": "Full report body should stay hidden."})


def write_json(path: Path, payload: dict[str, object]) -> None:
    write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    write_text(path, "".join(json.dumps(record, sort_keys=True) + "\n" for record in records))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
