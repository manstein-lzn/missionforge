from __future__ import annotations

import unittest

from missionforge.adapters.cli import (
    COMMAND_EXIT_CODE_BY_REASON,
    MissionCommandError,
    MissionCommandResult,
    assert_refs_only_command_payload,
    command_exit_code,
    command_status_for_exit_code,
    command_status_for_exit_reason,
)
from missionforge.contracts import ContractValidationError


class OperatorCLIContractTests(unittest.TestCase):
    def test_command_result_round_trip_for_success(self) -> None:
        result = MissionCommandResult(
            command="inspect",
            status=command_status_for_exit_reason("success"),
            exit_code=command_exit_code("success"),
            data={
                "mission_run_id": "run-sample-mission",
                "mission_run_ref": "runs/run-sample-mission/mission_run.json",
                "evidence_refs": ["evidence/E-000001.json"],
            },
            refs=["runs/run-sample-mission/mission_run.json"],
        )

        self.assertEqual(MissionCommandResult.from_dict(result.to_dict()), result)
        self.assertEqual(result.to_dict()["schema_version"], "missionforge.command_result.v1")
        self.assertIsNone(result.to_dict()["error"])

    def test_command_error_and_result_round_trip_for_failure(self) -> None:
        error = MissionCommandError(
            code="missing_state",
            message="Mission run state is missing.",
            refs=["runs/run-sample-mission/mission_run.json"],
        )
        result = MissionCommandResult(
            command="inspect",
            status=command_status_for_exit_reason("missing_state"),
            exit_code=command_exit_code("missing_state"),
            data={"run_ref": "runs/run-sample-mission/mission_run.json"},
            refs=["runs/run-sample-mission/mission_run.json"],
            error=error,
        )

        self.assertEqual(MissionCommandError.from_dict(error.to_dict()), error)
        self.assertEqual(MissionCommandResult.from_dict(result.to_dict()), result)

    def test_exit_code_mapping_is_deterministic(self) -> None:
        expected = {
            "success": 0,
            "invalid_input": 2,
            "missing_state": 3,
            "unsupported_operation": 4,
            "runtime_failure": 5,
            "verification_failed": 6,
            "authority_pending": 7,
            "validation_failed": 8,
        }

        self.assertEqual(COMMAND_EXIT_CODE_BY_REASON, expected)
        for reason, exit_code in expected.items():
            with self.subTest(reason=reason):
                self.assertEqual(command_exit_code(reason), exit_code)
                self.assertEqual(command_status_for_exit_code(exit_code), command_status_for_exit_reason(reason))

    def test_nonzero_exit_requires_matching_error(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "command must be one of"):
            MissionCommandResult(
                command="rpc",
                status=command_status_for_exit_reason("success"),
                exit_code=command_exit_code("success"),
            ).validate()

        with self.assertRaisesRegex(ContractValidationError, "error is required"):
            MissionCommandResult(
                command="inspect",
                status=command_status_for_exit_reason("missing_state"),
                exit_code=command_exit_code("missing_state"),
            ).validate()

        with self.assertRaisesRegex(ContractValidationError, "must be null"):
            MissionCommandResult(
                command="inspect",
                status=command_status_for_exit_reason("success"),
                exit_code=command_exit_code("success"),
                error=MissionCommandError(code="missing_state", message="No state."),
            ).validate()

        with self.assertRaisesRegex(ContractValidationError, "does not match"):
            MissionCommandResult(
                command="inspect",
                status=command_status_for_exit_reason("missing_state"),
                exit_code=command_exit_code("missing_state"),
                error=MissionCommandError(code="invalid_input", message="Bad input."),
            ).validate()

    def test_command_envelopes_reject_unknown_or_raw_extra_fields(self) -> None:
        valid_error = {
            "code": "missing_state",
            "message": "Mission run state is missing.",
            "refs": ["runs/run-sample-mission/mission_run.json"],
        }
        valid_result = {
            "schema_version": "missionforge.command_result.v1",
            "command": "inspect",
            "status": "failed",
            "exit_code": 3,
            "data": {},
            "refs": ["runs/run-sample-mission/mission_run.json"],
            "error": valid_error,
        }

        with self.assertRaisesRegex(ContractValidationError, "unsupported fields"):
            MissionCommandResult.from_dict({**valid_result, "extra": "ignored"})

        with self.assertRaisesRegex(ContractValidationError, "not allowed"):
            MissionCommandResult.from_dict({**valid_result, "raw_payload": {"body": "raw"}})

        with self.assertRaisesRegex(ContractValidationError, "unsupported fields"):
            MissionCommandError.from_dict({**valid_error, "extra": "ignored"})

        with self.assertRaisesRegex(ContractValidationError, "not allowed"):
            MissionCommandError.from_dict({**valid_error, "raw_transcript": "chat"})

    def test_refs_only_policy_rejects_raw_or_secret_shaped_fields(self) -> None:
        forbidden_payloads = [
            {"raw_payload": {"ok": True}},
            {"body": "artifact contents"},
            {"stdout": "raw stream"},
            {"stderr": "raw stream"},
            {"prompt": "raw prompt"},
            {"provider_messages": [{"role": "user", "content": "hello"}]},
            {"metrics": {"provider": {"api_key": "sk-example"}}},
            {"metrics": {"provider": {"refresh_token": "token"}}},
            {"nested": [{"transcript": "raw chat"}]},
        ]

        for payload in forbidden_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ContractValidationError):
                    assert_refs_only_command_payload(payload)
                with self.assertRaises(ContractValidationError):
                    MissionCommandResult(
                        command="inspect",
                        status=command_status_for_exit_reason("success"),
                        exit_code=command_exit_code("success"),
                        data=payload,
                    ).validate()

    def test_refs_only_policy_validates_ref_shaped_fields(self) -> None:
        assert_refs_only_command_payload(
            {
                "mission_result_ref": "host_results/sample-mission.mission_result.json",
                "evidence_refs": ["evidence/E-000001.json"],
                "latest_safe_point": {
                    "savepoint_ref": "attempts/WU-000001/pi_agent_savepoints.jsonl",
                    "session_ref": "attempts/WU-000001/pi_agent_session.jsonl",
                },
            }
        )

        with self.assertRaises(ContractValidationError):
            assert_refs_only_command_payload({"mission_result_ref": "../secret.json"})

        with self.assertRaises(ContractValidationError):
            assert_refs_only_command_payload({"evidence_refs": ["evidence/E-000001.json", "../secret.json"]})

if __name__ == "__main__":
    unittest.main()
