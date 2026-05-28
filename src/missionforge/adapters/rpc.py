"""Optional refs-only JSONL RPC adapter for MissionForge operator commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..contracts import ContractValidationError, ensure_json_value, require_mapping, require_non_empty_str
from .cli import MissionCLI, MissionCommandError, assert_refs_only_command_payload


class MissionJSONLRPC:
    """Headless JSONL request/response adapter over MissionCLI commands."""

    def __init__(self, *, cli: MissionCLI | None = None, workspace: str | Path = ".") -> None:
        self.cli = cli or MissionCLI()
        self.workspace = str(Path(workspace))

    def handle_line(self, line: str) -> dict[str, Any]:
        request_id: str | None = None
        try:
            request = require_mapping(json.loads(line), "mission_jsonl_rpc.request")
            request_id = require_non_empty_str(request.get("id"), "mission_jsonl_rpc.request.id")
            request_type = require_non_empty_str(request.get("type"), "mission_jsonl_rpc.request.type")
            argv = _argv_for_request(request, default_workspace=self.workspace)
            result = self.cli.run_command(argv)
            response = {
                "id": request_id,
                "type": "response",
                "command": result.command,
                "success": result.exit_code == 0,
                "result": result.to_dict(),
            }
            assert_refs_only_command_payload(response, "mission_jsonl_rpc.response")
            return response
        except (json.JSONDecodeError, ContractValidationError, KeyError, TypeError) as exc:
            error = MissionCommandError(code="invalid_input", message=str(exc), refs=[])
            response = {
                "id": request_id,
                "type": "response",
                "success": False,
                "error": error.to_dict(),
            }
            assert_refs_only_command_payload(response, "mission_jsonl_rpc.response")
            return response

    def handle_lines(self, lines: Iterable[str]) -> list[str]:
        return [json.dumps(self.handle_line(line), sort_keys=True) for line in lines]


def _argv_for_request(request: Mapping[str, Any], *, default_workspace: str) -> list[str]:
    request_type = require_non_empty_str(request.get("type"), "mission_jsonl_rpc.request.type")
    workspace = require_non_empty_str(request.get("workspace", default_workspace), "mission_jsonl_rpc.request.workspace")

    if request_type == "run":
        return ["run", "--workspace", workspace, "--mission-ref", _required(request, "mission_ref")]
    if request_type == "inspect":
        return ["inspect", "--workspace", workspace, "--run", _required(request, "run")]
    if request_type == "diagnose":
        return ["diagnose", "--workspace", workspace, "--run", _required(request, "run")]
    if request_type == "resume":
        argv = [
            "resume",
            "--workspace",
            workspace,
            "--run",
            _required(request, "run"),
            "--mission-ref",
            _required(request, "mission_ref"),
        ]
        prompt = request.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            argv.extend(["--prompt", prompt.strip()])
        return argv
    if request_type in {"write_control", "control_halt"}:
        control_type = require_non_empty_str(request.get("control_type", "halt"), "mission_jsonl_rpc.request.control_type")
        if control_type != "halt":
            raise ContractValidationError("mission_jsonl_rpc.request.control_type must be halt")
        return [
            "control",
            "halt",
            "--workspace",
            workspace,
            "--run",
            _required(request, "run"),
            "--reason",
            _required(request, "reason"),
        ]
    if request_type == "review_record":
        return [
            "review",
            "record",
            "--workspace",
            workspace,
            "--run",
            _required(request, "run"),
            "--decision",
            _required(request, "decision"),
            "--review-ref",
            _required(request, "review_ref"),
        ]
    if request_type == "validate":
        return ["validate", "--workspace", workspace]
    raise ContractValidationError(f"unsupported JSONL RPC request type: {request_type}")


def _required(request: Mapping[str, Any], key: str) -> str:
    value = require_non_empty_str(request.get(key), f"mission_jsonl_rpc.request.{key}")
    ensure_json_value(value, f"mission_jsonl_rpc.request.{key}")
    return value
