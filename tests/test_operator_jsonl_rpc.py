from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.rpc import MissionJSONLRPC
from tests.operator_state_fixtures import seed_operator_run


class OperatorJSONLRPCTests(unittest.TestCase):
    def test_jsonl_rpc_inspect_reuses_cli_command_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            seed_operator_run(root)
            rpc = MissionJSONLRPC(workspace=root)

            inspect_response = rpc.handle_line(
                json.dumps({"id": "2", "type": "inspect", "run": "run-sample-mission"}, sort_keys=True)
            )

            self.assertEqual(inspect_response["id"], "2")
            self.assertTrue(inspect_response["success"])
            self.assertEqual(inspect_response["result"]["data"]["mission_run_id"], "run-sample-mission")

    def test_jsonl_rpc_write_control_maps_to_control_halt(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            seed_operator_run(root)
            rpc = MissionJSONLRPC(workspace=root)

            response = rpc.handle_line(
                json.dumps(
                    {
                        "id": "2",
                        "type": "write_control",
                        "control_type": "halt",
                        "run": "run-sample-mission",
                        "reason": "Pause.",
                    },
                    sort_keys=True,
                )
            )

            self.assertTrue(response["success"])
            self.assertEqual(response["result"]["command"], "control halt")
            self.assertTrue((root / response["result"]["data"]["control_ref"]).exists())

    def test_jsonl_rpc_malformed_request_fails_closed(self) -> None:
        rpc = MissionJSONLRPC()

        response = rpc.handle_line("{not json")
        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "invalid_input")

        response = rpc.handle_line(json.dumps({"id": "1", "type": "unknown"}, sort_keys=True))
        self.assertFalse(response["success"])
        self.assertEqual(response["id"], "1")
        self.assertEqual(response["error"]["code"], "invalid_input")

    def test_jsonl_rpc_handle_lines_returns_stable_json_lines(self) -> None:
        rpc = MissionJSONLRPC()

        lines = rpc.handle_lines([json.dumps({"id": "1", "type": "unknown"}, sort_keys=True)])

        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["id"], "1")


if __name__ == "__main__":
    unittest.main()
