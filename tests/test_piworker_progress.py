from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import MemoryRefStore
from missionforge.piworker_progress import PiWorkerProgressBridge, PiWorkerProgressBridgeConfig


class PiWorkerProgressBridgeTests(unittest.TestCase):
    def test_summarizes_streamed_write_without_leaking_content(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            events_ref = "attempts/WU-000001/pi_agent_events.jsonl"
            _append_jsonl(
                root / events_ref,
                {
                    "event_type": "message_update",
                    "payload": {
                        "type": "message_update",
                        "message": {
                            "content": [
                                {
                                    "type": "toolCall",
                                    "name": "write",
                                    "arguments": {
                                        "path": "reports/final_report.md",
                                        "content": "SECRET REPORT BODY",
                                    },
                                }
                            ]
                        },
                    },
                },
            )
            emitted: list[dict] = []
            bridge = PiWorkerProgressBridge(
                workspace=root,
                call_id="WU-000001",
                worker_label="report_writer",
                events_ref=events_ref,
                progress_sink=emitted.append,
                config=PiWorkerProgressBridgeConfig(min_emit_interval_seconds=0, heartbeat_interval_seconds=0),
            )

            bridge.poll_once()

        self.assertEqual(len(emitted), 1)
        self.assertIn("report_writer", emitted[0]["message"])
        self.assertIn("reports/final_report.md", emitted[0]["message"])
        self.assertIn("18 chars", emitted[0]["detail"])
        self.assertEqual(emitted[0]["refs"], ["reports/final_report.md"])
        self.assertNotIn("SECRET REPORT BODY", json.dumps(emitted, ensure_ascii=False))

    def test_summarizes_store_backed_runtime_events_without_filesystem_writes(self) -> None:
        store = MemoryRefStore()
        events_ref = "attempts/WU-000001/pi_agent_events.jsonl"
        store.append_jsonl(
            events_ref,
            {
                "event_type": "message_update",
                "payload": {
                    "type": "message_update",
                    "message": {
                        "content": [
                            {
                                "type": "toolCall",
                                "name": "write",
                                "arguments": {
                                    "path": "reports/final_report.md",
                                    "content": "SECRET REPORT BODY",
                                },
                            }
                        ]
                    },
                },
            },
        )
        emitted: list[dict] = []
        bridge = PiWorkerProgressBridge(
            workspace=store,
            call_id="WU-000001",
            worker_label="report_writer",
            events_ref=events_ref,
            progress_sink=emitted.append,
            config=PiWorkerProgressBridgeConfig(min_emit_interval_seconds=0, heartbeat_interval_seconds=0),
        )

        with TemporaryDirectory() as tempdir:
            before = _snapshot(tempdir)
            bridge.poll_once()
            after = _snapshot(tempdir)

        self.assertEqual(before, after)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["refs"], ["reports/final_report.md"])
        self.assertNotIn("SECRET REPORT BODY", json.dumps(emitted, ensure_ascii=False))

    def test_reports_expected_artifact_when_it_appears(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            artifact_ref = "reports/final_report.md"
            artifact_path = root / artifact_ref
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text("# Report\n\nDone.\n", encoding="utf-8")
            emitted: list[dict] = []
            bridge = PiWorkerProgressBridge(
                workspace=root,
                call_id="WU-000001",
                worker_label="report_writer",
                events_ref="attempts/WU-000001/pi_agent_events.jsonl",
                expected_output_refs=[artifact_ref],
                progress_sink=emitted.append,
                config=PiWorkerProgressBridgeConfig(min_emit_interval_seconds=0, heartbeat_interval_seconds=0),
            )

            bridge.poll_once()

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["refs"], [artifact_ref])
        self.assertIn("wrote artifact", emitted[0]["message"])
        self.assertIn("16B", emitted[0]["detail"])

    def test_reports_store_backed_expected_artifact_when_it_appears(self) -> None:
        store = MemoryRefStore()
        artifact_ref = "reports/final_report.md"
        store.write_text(artifact_ref, "# Report\n\nDone.\n")
        emitted: list[dict] = []
        bridge = PiWorkerProgressBridge(
            workspace=store,
            call_id="WU-000001",
            worker_label="report_writer",
            events_ref="attempts/WU-000001/pi_agent_events.jsonl",
            expected_output_refs=[artifact_ref],
            progress_sink=emitted.append,
            config=PiWorkerProgressBridgeConfig(min_emit_interval_seconds=0, heartbeat_interval_seconds=0),
        )

        with TemporaryDirectory() as tempdir:
            before = _snapshot(tempdir)
            bridge.poll_once()
            after = _snapshot(tempdir)

        self.assertEqual(before, after)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["refs"], [artifact_ref])
        self.assertIn("wrote artifact", emitted[0]["message"])
        self.assertIn("16B", emitted[0]["detail"])


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


if __name__ == "__main__":
    unittest.main()
