from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    DEFAULT_PROGRESS_REF,
    ProgressEvent,
    ProgressStreamMount,
    ProgressStreamWriter,
    read_progress_events,
    render_progress_event,
    stream_progress,
)
from missionforge.contracts import ContractValidationError


class ProgressStreamTests(unittest.TestCase):
    def test_progress_mount_round_trips_as_declaration(self) -> None:
        mount = ProgressStreamMount(stream_ref=DEFAULT_PROGRESS_REF)

        self.assertEqual(ProgressStreamMount.from_dict(mount.to_dict()), mount)
        self.assertEqual(mount.to_dict()["stream_ref"], "progress/progress.jsonl")

    def test_writer_appends_and_reader_validates_events(self) -> None:
        with TemporaryDirectory() as tempdir:
            writer = ProgressStreamWriter(tempdir)
            writer.emit(
                stage="source_collection",
                state="running",
                message="正在收集高质量来源。",
                detail="优先覆盖论文、代码仓库和官方资料。",
                progress_hint="2/7",
                refs=["sources/source_packet.json"],
            )

            events = read_progress_events(tempdir, DEFAULT_PROGRESS_REF)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].stage, "source_collection")
            self.assertEqual(events[0].state, "running")
            self.assertEqual(events[0].refs, ["sources/source_packet.json"])
            self.assertIn("正在收集高质量来源。", render_progress_event(events[0]))

    def test_progress_event_rejects_unsafe_refs(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProgressEvent(
                event_id="progress-1",
                stage="bad",
                state="running",
                message="bad",
                created_at="2026-06-16T00:00:00+00:00",
                refs=["../secret.json"],
            ).validate()

    def test_stream_progress_renders_new_events_from_runner(self) -> None:
        with TemporaryDirectory() as tempdir:
            output = RecordingOutput()

            def runner() -> str:
                writer = ProgressStreamWriter(tempdir)
                writer.emit(stage="start", state="running", message="正在启动。", progress_hint="1/2")
                writer.emit(stage="done", state="completed", message="完成。", progress_hint="2/2")
                return "ok"

            result = stream_progress(runner, workspace=tempdir, interval_seconds=0.01, output=output)

            self.assertEqual(result, "ok")
            text = output.text
            self.assertIn("[1/2] 正在启动。", text)
            self.assertIn("[2/2] 完成。", text)
            self.assertTrue((Path(tempdir) / DEFAULT_PROGRESS_REF).is_file())

    def test_stream_progress_skips_events_written_before_watch_started(self) -> None:
        with TemporaryDirectory() as tempdir:
            writer = ProgressStreamWriter(tempdir)
            writer.emit(stage="old", state="completed", message="上一轮。", progress_hint="0/2")
            output = RecordingOutput()

            def runner() -> str:
                live_writer = ProgressStreamWriter(tempdir)
                live_writer.emit(stage="start", state="running", message="本轮启动。", progress_hint="1/2")
                live_writer.emit(stage="done", state="completed", message="本轮完成。", progress_hint="2/2")
                return "ok"

            result = stream_progress(runner, workspace=tempdir, interval_seconds=0.01, output=output)

            self.assertEqual(result, "ok")
            self.assertNotIn("上一轮。", output.text)
            self.assertIn("[1/2] 本轮启动。", output.text)
            self.assertIn("[2/2] 本轮完成。", output.text)
            self.assertEqual(len(read_progress_events(tempdir, DEFAULT_PROGRESS_REF)), 3)


class RecordingOutput:
    def __init__(self) -> None:
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def write(self, value: str) -> None:
        self.parts.append(value)

    def flush(self) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
