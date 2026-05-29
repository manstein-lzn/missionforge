from __future__ import annotations

from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from missionforge import JsonWorkspaceStore, MissionIR, MissionRuntime
from tests.test_ir import sample_mission_payload


class RuntimeStoreIntegrationTests(unittest.TestCase):
    def test_json_store_loads_runtime_outputs_without_layout_change(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())

        with TemporaryDirectory() as tmpdir:
            MissionRuntime(workspace=tmpdir).run(mission)
            store = JsonWorkspaceStore(tmpdir)
            run = store.load_mission_run("run-sample-mission")
            attempts = store.load_attempts("run-sample-mission")
            metric_projection = store.read_json("runs/run-sample-mission/metrics/projection.json")

            self.assertEqual(run.attempts_ref, "runs/run-sample-mission/attempts.jsonl")
            self.assertEqual(run.artifact_hygiene_ref, "runs/run-sample-mission/artifact_hygiene.json")
            self.assertEqual(len(attempts), 1)
            self.assertIn("missionforge.runtime", metric_projection["namespaces"])

    def test_runtime_state_writes_route_through_json_workspace_store(self) -> None:
        mission = MissionIR.from_dict(sample_mission_payload())
        original_write_json = JsonWorkspaceStore.write_json
        original_write_jsonl = JsonWorkspaceStore.write_jsonl
        json_refs: list[str] = []
        jsonl_refs: list[str] = []

        def record_json(store: JsonWorkspaceStore, ref: str, payload: dict) -> str:
            json_refs.append(ref)
            return original_write_json(store, ref, payload)

        def record_jsonl(
            store: JsonWorkspaceStore,
            ref: str,
            payloads: list[dict],
            *,
            append: bool = False,
        ) -> str:
            jsonl_refs.append(ref)
            return original_write_jsonl(store, ref, payloads, append=append)

        with TemporaryDirectory() as tmpdir:
            with patch.object(JsonWorkspaceStore, "write_json", autospec=True) as write_json:
                with patch.object(JsonWorkspaceStore, "write_jsonl", autospec=True) as write_jsonl:
                    write_json.side_effect = record_json
                    write_jsonl.side_effect = record_jsonl

                    MissionRuntime(workspace=tmpdir).run(mission)

        self.assertIn("runs/run-sample-mission/mission_run.json", json_refs)
        self.assertIn("runs/run-sample-mission/artifact_hygiene.json", json_refs)
        self.assertIn("runs/run-sample-mission/metrics/projection.json", json_refs)
        self.assertIn("runs/run-sample-mission/attempts.jsonl", jsonl_refs)
        self.assertIn("runs/run-sample-mission/metrics/events.jsonl", jsonl_refs)


if __name__ == "__main__":
    unittest.main()
