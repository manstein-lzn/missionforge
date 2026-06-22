from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.contracts import ContractValidationError
from missionforge.interaction import (
    ACKS_REF,
    USER_EVENTS_REF,
    AgentEvent,
    AgentEventKind,
    FileInteractionPort,
    InteractionDelivery,
    UserEventKind,
)


class InteractionTests(unittest.TestCase):
    def test_file_interaction_port_projects_and_acknowledges_user_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            port = FileInteractionPort(root)
            event = port.submit_text(
                "等一下，范围改成近三年。",
                run_id="run-001",
                target="researcher",
                kind=UserEventKind.CORRECTION,
                delivery=InteractionDelivery.NEXT_SAFE_POINT,
            )
            ref = port.write_pending_projection(
                run_id="run-001",
                target="researcher",
                step_id="researcher",
                ref="interaction/safe_points/001-researcher-user_events.json",
            )
            projection = json.loads((root / ref).read_text(encoding="utf-8"))
            port.acknowledge([event], consumed_by="001-researcher")
            empty_ref = port.write_pending_projection(
                run_id="run-001",
                target="researcher",
                step_id="researcher",
                ref="interaction/safe_points/002-researcher-user_events.json",
            )
            empty_projection = json.loads((root / empty_ref).read_text(encoding="utf-8"))
            user_events_exists = (root / USER_EVENTS_REF).is_file()
            acks_exists = (root / ACKS_REF).is_file()

        self.assertEqual(projection["event_count"], 1)
        self.assertEqual(projection["events"][0]["text"], "等一下，范围改成近三年。")
        self.assertIn("not task authority", projection["authority_note"])
        self.assertTrue(user_events_exists)
        self.assertTrue(acks_exists)
        self.assertEqual(empty_projection["event_count"], 0)

    def test_agent_events_are_separate_from_user_events(self) -> None:
        with TemporaryDirectory() as tmpdir:
            port = FileInteractionPort(tmpdir)
            event = port.emit_agent_event(
                AgentEvent.create(
                    run_id="run-001",
                    source="frontdesk",
                    kind=AgentEventKind.QUESTION,
                    text="你希望这份研究服务什么决策？",
                )
            )
            events = port.read_agent_events(run_id="run-001")

        self.assertEqual(events, [event])
        self.assertEqual(events[0].source, "frontdesk")

    def test_interaction_refs_cannot_escape_workspace(self) -> None:
        with TemporaryDirectory() as tmpdir:
            port = FileInteractionPort(tmpdir)
            with self.assertRaises(ContractValidationError):
                port.write_pending_projection(
                    run_id="run-001",
                    target="researcher",
                    ref="../outside.json",
                )

    def test_user_event_metadata_is_refs_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            port = FileInteractionPort(tmpdir)
            with self.assertRaises(ContractValidationError):
                port.submit_text(
                    "补充一个方向。",
                    run_id="run-001",
                    target="researcher",
                    metadata={"raw_transcript": "must not enter metadata"},
                )


if __name__ == "__main__":
    unittest.main()
