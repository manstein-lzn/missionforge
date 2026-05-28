"""Optional CLI/Python host shell for MissionForge."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping, Sequence

from ..adapters.contracts import AdapterResult
from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..ir import MissionIR
from ..review import ReviewerDecision
from ..runner import MissionResult, MissionRuntime
from ..state import (
    ARTIFACT_HYGIENE_SCHEMA_VERSION,
    SUPPORTED_RESUME_BOUNDARY,
    ArtifactHygieneReport,
    load_mission_run,
    mission_run_id_for,
)


COMMAND_RESULT_SCHEMA_VERSION = "missionforge.command_result.v1"
COMMAND_NAMES = {"run", "inspect", "diagnose", "resume", "control halt", "review record", "validate"}
COMMAND_RESULT_STATUSES = {"completed", "failed", "blocked", "unsupported"}
COMMAND_EXIT_CODE_BY_REASON = {
    "success": 0,
    "invalid_input": 2,
    "missing_state": 3,
    "unsupported_operation": 4,
    "runtime_failure": 5,
    "verification_failed": 6,
    "authority_pending": 7,
    "validation_failed": 8,
}
COMMAND_STATUS_BY_EXIT_REASON = {
    "success": "completed",
    "invalid_input": "failed",
    "missing_state": "failed",
    "unsupported_operation": "unsupported",
    "runtime_failure": "failed",
    "verification_failed": "failed",
    "authority_pending": "blocked",
    "validation_failed": "failed",
}
MISSION_STATUS_EXIT_REASON = {
    "completed_verified": "success",
    "failed": "verification_failed",
    "review_required": "authority_pending",
    "human_acceptance_required": "authority_pending",
    "unsupported_verification_spec": "unsupported_operation",
    "missing_verification_plan": "invalid_input",
    "execution_incomplete": "runtime_failure",
    "invalid_contract": "invalid_input",
}
COMMAND_FORBIDDEN_RAW_FIELDS = {
    "access_token",
    "api_key",
    "artifact_body",
    "body",
    "credential",
    "credentials",
    "id_token",
    "message_body",
    "notes_body",
    "passphrase",
    "password",
    "payload",
    "private_key",
    "prompt",
    "provider_message",
    "provider_messages",
    "raw",
    "raw_body",
    "raw_payload",
    "raw_prompt",
    "raw_transcript",
    "refresh_token",
    "secret",
    "secret_key",
    "stderr",
    "stdout",
    "transcript",
}
COMMAND_FORBIDDEN_KEY_FRAGMENTS = {"credential", "password", "prompt", "secret", "transcript"}
COMMAND_FORBIDDEN_KEY_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_body",
    "_payload",
    "_private_key",
    "_refresh_token",
)


@dataclass(frozen=True)
class MissionCommandError:
    """Structured operator command error."""

    code: str
    message: str
    refs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionCommandError":
        data = _command_mapping(payload, "mission_command_error", {"code", "message", "refs"})
        error = cls(
            code=require_non_empty_str(data.get("code"), "mission_command_error.code"),
            message=require_non_empty_str(data.get("message"), "mission_command_error.message"),
            refs=require_str_list(data.get("refs", []), "mission_command_error.refs"),
        )
        error.validate()
        return error

    def validate(self) -> None:
        reason = require_non_empty_str(self.code, "mission_command_error.code")
        if reason == "success" or reason not in COMMAND_EXIT_CODE_BY_REASON:
            raise ContractValidationError(
                f"mission_command_error.code must be one of {sorted(set(COMMAND_EXIT_CODE_BY_REASON) - {'success'})}"
            )
        require_non_empty_str(self.message, "mission_command_error.message")
        for ref in self.refs:
            validate_ref(ref, "mission_command_error.refs[]")
        assert_refs_only_command_payload({"refs": list(self.refs)}, "mission_command_error")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "code": self.code,
            "message": self.message,
            "refs": list(self.refs),
        }


@dataclass(frozen=True)
class MissionCommandResult:
    """Deterministic refs-only operator command result envelope."""

    command: str
    status: str
    exit_code: int
    data: dict[str, Any] = field(default_factory=dict)
    refs: list[str] = field(default_factory=list)
    error: MissionCommandError | None = None
    schema_version: str = COMMAND_RESULT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionCommandResult":
        data = _command_mapping(
            payload,
            "mission_command_result",
            {"schema_version", "command", "status", "exit_code", "data", "refs", "error"},
        )
        if data.get("schema_version") != COMMAND_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("mission_command_result.schema_version is unsupported")
        error_payload = data.get("error")
        if error_payload is not None and not isinstance(error_payload, Mapping):
            raise ContractValidationError("mission_command_result.error must be null or a mapping")
        result = cls(
            command=require_non_empty_str(data.get("command"), "mission_command_result.command"),
            status=require_non_empty_str(data.get("status"), "mission_command_result.status"),
            exit_code=_require_known_exit_code(data.get("exit_code"), "mission_command_result.exit_code"),
            data=ensure_json_value(
                require_mapping(data.get("data", {}), "mission_command_result.data"),
                "mission_command_result.data",
            ),
            refs=require_str_list(data.get("refs", []), "mission_command_result.refs"),
            error=MissionCommandError.from_dict(error_payload) if isinstance(error_payload, Mapping) else None,
            schema_version=require_non_empty_str(
                data.get("schema_version"),
                "mission_command_result.schema_version",
            ),
        )
        result.validate()
        return result

    @classmethod
    def from_cli_result(cls, command: str, result: "MissionCLIResult") -> "MissionCommandResult":
        """Wrap the existing CLI result without changing CLI execution behavior."""

        result.validate()
        reason = command_exit_reason_for_mission_status(result.status)
        exit_code = command_exit_code(reason)
        error = None
        if exit_code != 0:
            error = MissionCommandError(
                code=reason,
                message=f"Mission status is {result.status}.",
                refs=[result.mission_result_ref],
            )
        command_result = cls(
            command=command,
            status=command_status_for_exit_reason(reason),
            exit_code=exit_code,
            data=result.to_dict(),
            refs=_dedupe_refs([result.mission_result_ref, *result.evidence_refs, *result.artifact_refs]),
            error=error,
        )
        command_result.validate()
        return command_result

    def validate(self) -> None:
        command = require_non_empty_str(self.command, "mission_command_result.command")
        if command not in COMMAND_NAMES:
            raise ContractValidationError(f"mission_command_result.command must be one of {sorted(COMMAND_NAMES)}")
        status = require_non_empty_str(self.status, "mission_command_result.status")
        if status not in COMMAND_RESULT_STATUSES:
            raise ContractValidationError(
                f"mission_command_result.status must be one of {sorted(COMMAND_RESULT_STATUSES)}"
            )
        exit_code = _require_known_exit_code(self.exit_code, "mission_command_result.exit_code")
        expected_status = command_status_for_exit_code(exit_code)
        if status != expected_status:
            raise ContractValidationError(
                f"mission_command_result.status must be {expected_status!r} for exit code {exit_code}"
            )
        if exit_code == 0 and self.error is not None:
            raise ContractValidationError("mission_command_result.error must be null for successful commands")
        if exit_code != 0 and self.error is None:
            raise ContractValidationError("mission_command_result.error is required for nonzero exit codes")
        if self.error is not None:
            self.error.validate()
            if command_exit_code(self.error.code) != exit_code:
                raise ContractValidationError("mission_command_result.error.code does not match exit_code")
        normalized_data = ensure_json_value(
            require_mapping(self.data, "mission_command_result.data"),
            "mission_command_result.data",
        )
        assert_refs_only_command_payload(normalized_data, "mission_command_result.data")
        for ref in self.refs:
            validate_ref(ref, "mission_command_result.refs[]")
        assert_refs_only_command_payload({"refs": list(self.refs)}, "mission_command_result")
        require_non_empty_str(self.schema_version, "mission_command_result.schema_version")
        if self.schema_version != COMMAND_RESULT_SCHEMA_VERSION:
            raise ContractValidationError("mission_command_result.schema_version is unsupported")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "data": ensure_json_value(self.data, "mission_command_result.data"),
            "refs": list(self.refs),
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass(frozen=True)
class MissionCLIResult:
    """Refs-only host-shell result summary."""

    mission_id: str
    status: str
    mission_result_ref: str
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionCLIResult":
        data = require_mapping(payload, "mission_cli_result")
        result = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_cli_result.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_cli_result.status"),
            mission_result_ref=validate_ref(data.get("mission_result_ref"), "mission_cli_result.mission_result_ref"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_cli_result.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_cli_result.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_cli_result.failed_constraint_ids",
            ),
            metrics=ensure_json_value(
                require_mapping(data.get("metrics", {}), "mission_cli_result.metrics"),
                "mission_cli_result.metrics",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_cli_result.mission_id")
        require_non_empty_str(self.status, "mission_cli_result.status")
        validate_ref(self.mission_result_ref, "mission_cli_result.mission_result_ref")
        for ref in self.evidence_refs:
            validate_ref(ref, "mission_cli_result.evidence_refs[]")
        for ref in self.artifact_refs:
            validate_ref(ref, "mission_cli_result.artifact_refs[]")
        require_str_list(self.failed_constraint_ids, "mission_cli_result.failed_constraint_ids")
        ensure_json_value(require_mapping(self.metrics, "mission_cli_result.metrics"), "mission_cli_result.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "status": self.status,
            "mission_result_ref": self.mission_result_ref,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "metrics": ensure_json_value(self.metrics, "mission_cli_result.metrics"),
        }


class MissionCLI:
    """Small host shell around the primary Python MissionRuntime API."""

    adapter_id = "missionforge_cli_shell"

    def __init__(
        self,
        *,
        validate_runner: Callable[[Path], tuple[int, str]] | None = None,
    ) -> None:
        self._validate_runner = validate_runner

    def run_mission_ref(
        self,
        mission_ref: str,
        *,
        workspace: str | Path = ".",
        result_ref: str | None = None,
        max_attempts: int = 1,
    ) -> MissionCLIResult:
        root = Path(workspace).resolve()
        mission_path = _resolve_workspace_ref(root, mission_ref)
        mission = MissionIR.from_dict(json.loads(mission_path.read_text(encoding="utf-8")))
        mission_result = MissionRuntime(workspace=root, max_attempts=max_attempts).run(mission)
        mission_result.validate()

        output_ref = result_ref or f"host_results/{mission_result.mission_id}.mission_result.json"
        _write_json_ref(root, output_ref, mission_result.to_dict())
        cli_result = MissionCLIResult(
            mission_id=mission_result.mission_id,
            status=mission_result.status,
            mission_result_ref=output_ref,
            evidence_refs=list(mission_result.evidence_refs),
            artifact_refs=list(mission_result.artifact_refs),
            failed_constraint_ids=list(mission_result.failed_constraint_ids),
            metrics=dict(mission_result.metrics),
        )
        adapter_result = AdapterResult(
            invocation_id=f"cli-run-{mission_result.mission_id}",
            adapter_id=self.adapter_id,
            status="completed",
            output_refs=[output_ref],
            evidence_refs=list(mission_result.evidence_refs),
            metrics={"artifact_count": len(mission_result.artifact_refs)},
        )
        adapter_result.validate()
        cli_result.validate()
        return cli_result

    def run_command(self, argv: Sequence[str]) -> MissionCommandResult:
        parser = _command_parser()
        args = parser.parse_args(list(argv))
        command = args.command
        if command == "run":
            return self._command_run(args)
        if command == "inspect":
            return self._command_inspect(args)
        if command == "diagnose":
            return self._command_diagnose(args)
        if command == "resume":
            return self._command_resume(args)
        if command == "control" and args.control_command == "halt":
            return self._command_control_halt(args)
        if command == "review" and args.review_command == "record":
            return self._command_review_record(args)
        if command == "validate":
            return self._command_validate(args)
        return _error_result("inspect", "unsupported_operation", f"unsupported command: {command}")

    def run(self, argv: Sequence[str]) -> MissionCLIResult:
        parser = _parser()
        args = parser.parse_args(list(argv))
        return self.run_mission_ref(
            args.mission_ref,
            workspace=args.workspace,
            result_ref=args.result_ref,
            max_attempts=args.max_attempts,
        )

    def _command_run(self, args: argparse.Namespace) -> MissionCommandResult:
        try:
            result = self.run_mission_ref(
                args.mission_ref,
                workspace=args.workspace,
                result_ref=args.result_ref,
                max_attempts=args.max_attempts,
            )
            return MissionCommandResult.from_cli_result("run", result)
        except FileNotFoundError as exc:
            return _error_result("run", "missing_state", str(exc))
        except (json.JSONDecodeError, OSError, ContractValidationError) as exc:
            return _error_result("run", "invalid_input", str(exc))

    def _command_inspect(self, args: argparse.Namespace) -> MissionCommandResult:
        try:
            data, refs = _inspect_run_data(args.workspace, args.run)
            return _success_result("inspect", data=data, refs=refs)
        except FileNotFoundError as exc:
            return _error_result("inspect", "missing_state", str(exc))
        except ContractValidationError as exc:
            reason = "missing_state" if "missing" in str(exc).lower() else "invalid_input"
            return _error_result("inspect", reason, str(exc))

    def _command_diagnose(self, args: argparse.Namespace) -> MissionCommandResult:
        try:
            inspect_data, refs = _inspect_run_data(args.workspace, args.run)
            diagnosis = _diagnose_run(inspect_data)
            data = {
                "mission_run_id": inspect_data["mission_run_id"],
                "mission_id": inspect_data["mission_id"],
                "diagnosis": diagnosis["diagnosis"],
                "operator_action": diagnosis["operator_action"],
                "reason": diagnosis["reason"],
                "status": inspect_data["status"],
                "latest_decision": inspect_data["latest_decision"],
                "next_action": inspect_data["next_action"],
                "refs": refs,
            }
            return _success_result("diagnose", data=data, refs=refs)
        except FileNotFoundError as exc:
            return _error_result("diagnose", "missing_state", str(exc), data={"diagnosis": "missing_state"})
        except ContractValidationError as exc:
            reason = "missing_state" if "missing" in str(exc).lower() else "invalid_input"
            return _error_result("diagnose", reason, str(exc), data={"diagnosis": reason})

    def _command_resume(self, args: argparse.Namespace) -> MissionCommandResult:
        root = Path(args.workspace).resolve()
        try:
            mission = _load_mission_ref(root, args.mission_ref)
            run = load_mission_run(root, args.run)
            expected_run_id = mission_run_id_for(mission.mission_id)
            if run.mission_run_id != expected_run_id:
                raise ContractValidationError("mission ref does not match requested run")
            if run.latest_safe_point is None:
                return _error_result(
                    "resume",
                    "unsupported_operation",
                    "runtime resume requires a latest safe point",
                    refs=[run.attempts_ref, run.artifact_hygiene_ref],
                )
            if run.latest_safe_point.kind != SUPPORTED_RESUME_BOUNDARY:
                return _error_result(
                    "resume",
                    "unsupported_operation",
                    f"unsupported resume boundary: {run.latest_safe_point.kind}",
                    refs=[run.latest_safe_point.savepoint_ref],
                )
            mission_result = MissionRuntime(workspace=root, max_attempts=args.max_attempts).resume(
                mission,
                follow_up_prompt=args.prompt,
            )
            output_ref = args.result_ref or f"host_results/{mission_result.mission_id}.resume_result.json"
            _write_json_ref(root, output_ref, mission_result.to_dict())
            cli_result = MissionCLIResult(
                mission_id=mission_result.mission_id,
                status=mission_result.status,
                mission_result_ref=output_ref,
                evidence_refs=list(mission_result.evidence_refs),
                artifact_refs=list(mission_result.artifact_refs),
                failed_constraint_ids=list(mission_result.failed_constraint_ids),
                metrics=dict(mission_result.metrics),
            )
            return MissionCommandResult.from_cli_result("resume", cli_result)
        except FileNotFoundError as exc:
            return _error_result("resume", "missing_state", str(exc))
        except (json.JSONDecodeError, OSError, ContractValidationError) as exc:
            message = str(exc)
            reason = "unsupported_operation" if "resume" in message.lower() or "boundary" in message.lower() else "invalid_input"
            return _error_result("resume", reason, message)

    def _command_control_halt(self, args: argparse.Namespace) -> MissionCommandResult:
        from ..adapters.observation import ControlRequestWriter

        root = Path(args.workspace).resolve()
        try:
            run = load_mission_run(root, args.run)
            control_id = args.control_id or f"halt-{run.mission_run_id}"
            control_ref = args.control_ref or f"control/{run.mission_run_id}.halt.json"
            result = ControlRequestWriter(workspace=root).write_halt(
                reason=args.reason,
                control_id=control_id,
                control_ref=control_ref,
            )
            data = {
                "mission_run_id": run.mission_run_id,
                **result.to_dict(),
            }
            return _success_result("control halt", data=data, refs=[result.control_ref, run.attempts_ref])
        except FileNotFoundError as exc:
            return _error_result("control halt", "missing_state", str(exc))
        except ContractValidationError as exc:
            reason = "missing_state" if "missing" in str(exc).lower() else "invalid_input"
            return _error_result("control halt", reason, str(exc))

    def _command_review_record(self, args: argparse.Namespace) -> MissionCommandResult:
        root = Path(args.workspace).resolve()
        try:
            run = load_mission_run(root, args.run)
            review_path = _resolve_workspace_ref(root, args.review_ref)
            decision = ReviewerDecision.from_dict(json.loads(review_path.read_text(encoding="utf-8")))
            if decision.decision != args.decision:
                raise ContractValidationError("review command decision does not match review_ref decision")
            contract_hash = require_non_empty_str(run.metrics.get("contract_hash"), "mission_run.metrics.contract_hash")
            _validate_reviewer_decision_fresh(decision, contract_hash=contract_hash)
            record_ref = args.record_ref or f"reviews/{run.mission_run_id}.review_record.json"
            record_payload = {
                "schema_version": "missionforge.review_record.v1",
                "mission_run_id": run.mission_run_id,
                "mission_id": run.mission_id,
                "decision": decision.decision,
                "reviewer_id": decision.reviewer_id,
                "review_ref": args.review_ref,
                "review_record_ref": record_ref,
                "contract_hash": decision.contract_hash,
                "runtime_status": run.status,
                "failed_constraint_ids": list(run.failed_constraint_ids),
                "evidence_refs": list(decision.evidence_refs),
                "verifier_override": False,
            }
            _write_json_ref(root, record_ref, record_payload)
            return _success_result(
                "review record",
                data=record_payload,
                refs=_dedupe_refs([args.review_ref, record_ref, *decision.evidence_refs, run.attempts_ref]),
            )
        except FileNotFoundError as exc:
            return _error_result("review record", "missing_state", str(exc))
        except (json.JSONDecodeError, OSError, ContractValidationError) as exc:
            return _error_result("review record", "invalid_input", str(exc))

    def _command_validate(self, args: argparse.Namespace) -> MissionCommandResult:
        root = Path(args.workspace).resolve()
        script_ref = "scripts/validate.sh"
        log_ref = args.log_ref or "host_results/validation/validate.log"
        try:
            return_code, output = self._run_validation(root)
            _write_text_ref(root, log_ref, output)
            data = {
                "script_ref": script_ref,
                "validation_log_ref": log_ref,
                "return_code": return_code,
                "skip_npm_ci": os.environ.get("MISSIONFORGE_SKIP_NPM_CI") == "1",
            }
            if return_code == 0:
                return _success_result("validate", data=data, refs=[script_ref, log_ref])
            return _error_result(
                "validate",
                "validation_failed",
                f"validation command failed with exit code {return_code}",
                data=data,
                refs=[script_ref, log_ref],
            )
        except FileNotFoundError as exc:
            return _error_result("validate", "missing_state", str(exc), refs=[script_ref])
        except (OSError, ContractValidationError) as exc:
            return _error_result("validate", "validation_failed", str(exc), refs=[script_ref])

    def _run_validation(self, root: Path) -> tuple[int, str]:
        if self._validate_runner is not None:
            return self._validate_runner(root)
        script = root / "scripts/validate.sh"
        if not script.is_file():
            raise FileNotFoundError(str(script))
        completed = subprocess.run(
            [str(script)],
            cwd=root,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return completed.returncode, completed.stdout


def main(argv: Sequence[str] | None = None) -> int:
    """Run the optional CLI shell and print the refs-only command result."""

    args = list(sys.argv[1:] if argv is None else argv)
    cli = MissionCLI()
    if args and args[0].startswith("--") and args[0] not in {"-h", "--help"}:
        result = MissionCommandResult.from_cli_result("run", cli.run(args))
    else:
        result = cli.run_command(args)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return result.exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a MissionForge MissionIR ref through the optional CLI shell.")
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument("--mission-ref", required=True, help="Workspace-relative MissionIR JSON ref.")
    parser.add_argument("--result-ref", default=None, help="Workspace-relative MissionResult output ref.")
    parser.add_argument("--max-attempts", type=int, default=1, help="Runtime max attempts.")
    return parser


def _command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MissionForge operator commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a MissionIR ref.")
    run.add_argument("--workspace", default=".", help="Workspace root.")
    run.add_argument("--mission-ref", required=True, help="Workspace-relative MissionIR JSON ref.")
    run.add_argument("--result-ref", default=None, help="Workspace-relative MissionResult output ref.")
    run.add_argument("--max-attempts", type=int, default=1, help="Runtime max attempts.")
    run.add_argument("--json", action="store_true", help="Emit deterministic JSON.")

    inspect = subparsers.add_parser("inspect", help="Inspect a MissionRun.")
    inspect.add_argument("--workspace", default=".", help="Workspace root.")
    inspect.add_argument("--run", required=True, help="MissionRun id.")
    inspect.add_argument("--json", action="store_true", help="Emit deterministic JSON.")

    diagnose = subparsers.add_parser("diagnose", help="Diagnose a MissionRun.")
    diagnose.add_argument("--workspace", default=".", help="Workspace root.")
    diagnose.add_argument("--run", required=True, help="MissionRun id.")
    diagnose.add_argument("--json", action="store_true", help="Emit deterministic JSON.")

    resume = subparsers.add_parser("resume", help="Resume a MissionRun from the latest safe point.")
    resume.add_argument("--workspace", default=".", help="Workspace root.")
    resume.add_argument("--run", required=True, help="MissionRun id.")
    resume.add_argument("--mission-ref", required=True, help="Workspace-relative MissionIR JSON ref.")
    resume.add_argument("--prompt", default="Resume from the latest completed turn.", help="Follow-up prompt.")
    resume.add_argument("--result-ref", default=None, help="Workspace-relative MissionResult output ref.")
    resume.add_argument("--max-attempts", type=int, default=1, help="Runtime max attempts.")
    resume.add_argument("--json", action="store_true", help="Emit deterministic JSON.")

    control = subparsers.add_parser("control", help="Write explicit control intent.")
    control_subparsers = control.add_subparsers(dest="control_command", required=True)
    halt = control_subparsers.add_parser("halt", help="Write halt control intent.")
    halt.add_argument("--workspace", default=".", help="Workspace root.")
    halt.add_argument("--run", required=True, help="MissionRun id.")
    halt.add_argument("--reason", required=True, help="Halt reason.")
    halt.add_argument("--control-id", default=None, help="Control id.")
    halt.add_argument("--control-ref", default=None, help="Workspace-relative ControlRequest output ref.")
    halt.add_argument("--json", action="store_true", help="Emit deterministic JSON.")

    review = subparsers.add_parser("review", help="Record independent review decisions.")
    review_subparsers = review.add_subparsers(dest="review_command", required=True)
    record = review_subparsers.add_parser("record", help="Record a review decision ref.")
    record.add_argument("--workspace", default=".", help="Workspace root.")
    record.add_argument("--run", required=True, help="MissionRun id.")
    record.add_argument("--decision", required=True, choices=sorted({"approved", "needs_changes", "rejected"}))
    record.add_argument("--review-ref", required=True, help="Workspace-relative ReviewerDecision ref.")
    record.add_argument("--record-ref", default=None, help="Workspace-relative review record output ref.")
    record.add_argument("--json", action="store_true", help="Emit deterministic JSON.")

    validate = subparsers.add_parser("validate", help="Run repository validation.")
    validate.add_argument("--workspace", default=".", help="Repository/workspace root.")
    validate.add_argument("--log-ref", default=None, help="Workspace-relative validation log ref.")
    validate.add_argument("--json", action="store_true", help="Emit deterministic JSON.")
    return parser


def _write_json_ref(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    data = ensure_json_value(require_mapping(payload, ref), ref)
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_text_ref(root: Path, ref: str, text: str) -> None:
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json_ref(root: Path, ref: str) -> dict[str, Any]:
    path = _resolve_workspace_ref(root, ref)
    return require_mapping(json.loads(path.read_text(encoding="utf-8")), ref)


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("MissionCLI ref escapes workspace")
    return path


def _load_mission_ref(root: Path, mission_ref: str) -> MissionIR:
    mission_path = _resolve_workspace_ref(root, mission_ref)
    return MissionIR.from_dict(json.loads(mission_path.read_text(encoding="utf-8")))


def _success_result(command: str, *, data: Mapping[str, Any], refs: list[str] | None = None) -> MissionCommandResult:
    result = MissionCommandResult(
        command=command,
        status=command_status_for_exit_reason("success"),
        exit_code=command_exit_code("success"),
        data=ensure_json_value(require_mapping(data, f"{command}.data"), f"{command}.data"),
        refs=_dedupe_refs(refs or []),
    )
    result.validate()
    return result


def _error_result(
    command: str,
    reason: str,
    message: str,
    *,
    data: Mapping[str, Any] | None = None,
    refs: list[str] | None = None,
) -> MissionCommandResult:
    safe_refs = _dedupe_refs(refs or [])
    result = MissionCommandResult(
        command=command,
        status=command_status_for_exit_reason(reason),
        exit_code=command_exit_code(reason),
        data=ensure_json_value(require_mapping(data or {}, f"{command}.data"), f"{command}.data"),
        refs=safe_refs,
        error=MissionCommandError(code=reason, message=message, refs=safe_refs),
    )
    result.validate()
    return result


def _inspect_run_data(workspace: str | Path, mission_run_id: str) -> tuple[dict[str, Any], list[str]]:
    root = Path(workspace).resolve()
    run = load_mission_run(root, mission_run_id)
    from ..state import load_runtime_attempts
    from ..steering_store import SteeringArtifactStore

    attempts = load_runtime_attempts(root, run.mission_run_id)
    steering_store = SteeringArtifactStore(root)
    steering_refs = steering_store.collect_refs(run.mission_run_id)
    latest_steering_refs = steering_store.latest_refs(run.mission_run_id)
    artifact_hygiene = None
    hygiene_path = _resolve_workspace_ref(root, run.artifact_hygiene_ref)
    if hygiene_path.is_file():
        artifact_hygiene = ArtifactHygieneReport.from_dict(_read_json_ref(root, run.artifact_hygiene_ref)).to_dict()
    data = {
        "mission_run_id": run.mission_run_id,
        "mission_id": run.mission_id,
        "status": run.status,
        "current_attempt": run.current_attempt,
        "latest_work_unit_id": run.latest_work_unit_id,
        "latest_decision": run.latest_decision,
        "next_action": run.next_action,
        "latest_safe_point": run.latest_safe_point.to_dict() if run.latest_safe_point else None,
        "attempt_count": len(attempts),
        "latest_attempt": attempts[-1].to_dict() if attempts else None,
        "failed_constraint_ids": list(run.failed_constraint_ids),
        "artifact_refs": list(run.artifact_refs),
        "evidence_refs": list(run.evidence_refs),
        "attempts_ref": run.attempts_ref,
        "artifact_hygiene_ref": run.artifact_hygiene_ref,
        "artifact_hygiene": artifact_hygiene,
        "steering_refs": list(steering_refs),
        "latest_steering_ref_map": dict(latest_steering_refs),
        "metrics": ensure_json_value(run.metrics, "mission_run.metrics"),
    }
    refs = _dedupe_refs([
        run.attempts_ref,
        run.artifact_hygiene_ref,
        *run.artifact_refs,
        *run.evidence_refs,
        *steering_refs,
    ])
    return data, refs


def _diagnose_run(inspect_data: Mapping[str, Any]) -> dict[str, str]:
    hygiene = inspect_data.get("artifact_hygiene")
    if isinstance(hygiene, Mapping) and hygiene.get("passed") is False:
        return _diagnosis("artifact_hygiene_failed", "inspect_hygiene_report", "artifact hygiene failed")
    status = require_non_empty_str(inspect_data.get("status"), "diagnose.status")
    if status == "completed_verified":
        return _diagnosis("complete", "no_action", "verifier completed")
    if status == "review_required":
        return _diagnosis("review_required", "record_review_decision", "review gate is pending")
    if status == "human_acceptance_required":
        return _diagnosis("human_acceptance_required", "wait_for_human_authority", "human authority is pending")
    if status in {"unsupported_verification_spec", "missing_verification_plan", "invalid_contract"}:
        return _diagnosis("redesign_required", "revise_contract_or_profile", f"runtime status is {status}")

    metrics = require_mapping(inspect_data.get("metrics", {}), "diagnose.metrics")
    if bool(metrics.get("provider_failure_count")):
        return _diagnosis("steering_provider_failure", "inspect_steering_refs", "steering provider failed")
    if bool(metrics.get("rejected_proposal_count")):
        return _diagnosis("steering_proposal_rejected", "inspect_steering_refs", "latest steering proposal was rejected")
    if bool(metrics.get("unsafe_proposal_rejection_count")):
        return _diagnosis("unsafe_steering_proposal_rejected", "inspect_steering_refs", "unsafe steering proposal was rejected")
    if bool(metrics.get("redesign_required")):
        return _diagnosis("redesign_required", "revise_contract_or_profile", "runtime marked redesign_required")

    safe_point = inspect_data.get("latest_safe_point")
    if not isinstance(safe_point, Mapping):
        return _diagnosis("no_resume_safe_point", "inspect_or_redesign", "no latest safe point is available")
    if safe_point.get("kind") != SUPPORTED_RESUME_BOUNDARY:
        return _diagnosis("unsupported_resume_boundary", "inspect_or_redesign", "safe point is not resumable")

    latest_attempt = inspect_data.get("latest_attempt")
    if isinstance(latest_attempt, Mapping):
        attempt_status = latest_attempt.get("status")
        failure_category = latest_attempt.get("failure_category")
        if attempt_status not in {"completed", "cancelled"} or failure_category:
            return _diagnosis("worker_failure", "inspect_latest_attempt_refs", "latest attempt did not complete cleanly")

    if status == "failed":
        if bool(metrics.get("repair_exhausted")):
            return _diagnosis("repair_exhausted", "stop_or_redesign", "repair budget is exhausted")
        return _diagnosis("repairable_verifier_failure", "resume_repair", "verifier failed and repair may be available")

    return _diagnosis("redesign_required", "revise_contract_or_profile", f"no deterministic route for status {status}")


def _diagnosis(code: str, action: str, reason: str) -> dict[str, str]:
    return {
        "diagnosis": code,
        "operator_action": action,
        "reason": reason,
    }


def _validate_reviewer_decision_fresh(decision: ReviewerDecision, *, contract_hash: str) -> None:
    decision.validate()
    if decision.contract_hash != require_non_empty_str(contract_hash, "contract_hash"):
        raise ContractValidationError("reviewer decision is stale for contract_hash")


def command_exit_code(reason: str) -> int:
    """Return the deterministic operator exit code for a command reason."""

    safe_reason = require_non_empty_str(reason, "command_exit_reason")
    if safe_reason not in COMMAND_EXIT_CODE_BY_REASON:
        raise ContractValidationError(f"command_exit_reason must be one of {sorted(COMMAND_EXIT_CODE_BY_REASON)}")
    return COMMAND_EXIT_CODE_BY_REASON[safe_reason]


def command_status_for_exit_reason(reason: str) -> str:
    """Return the command envelope status for an exit reason."""

    safe_reason = require_non_empty_str(reason, "command_exit_reason")
    if safe_reason not in COMMAND_STATUS_BY_EXIT_REASON:
        raise ContractValidationError(f"command_exit_reason must be one of {sorted(COMMAND_STATUS_BY_EXIT_REASON)}")
    return COMMAND_STATUS_BY_EXIT_REASON[safe_reason]


def command_status_for_exit_code(exit_code: int) -> str:
    """Return the command envelope status for an exit code."""

    reason = _exit_reason_for_code(exit_code)
    return command_status_for_exit_reason(reason)


def command_exit_reason_for_mission_status(mission_status: str) -> str:
    """Map a MissionResult status to the operator exit reason taxonomy."""

    status = require_non_empty_str(mission_status, "mission_status")
    if status not in MISSION_STATUS_EXIT_REASON:
        raise ContractValidationError(f"mission_status has no command exit mapping: {status}")
    return MISSION_STATUS_EXIT_REASON[status]


def command_exit_code_for_mission_status(mission_status: str) -> int:
    """Map a MissionResult status to the deterministic operator exit code."""

    return command_exit_code(command_exit_reason_for_mission_status(mission_status))


def assert_refs_only_command_payload(value: Any, field_name: str = "command_payload") -> Any:
    """Reject raw bodies, prompts, transcripts, secrets, and unsafe refs."""

    return assert_refs_only_payload(value, field_name)


def _require_known_exit_code(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be one of {sorted(set(COMMAND_EXIT_CODE_BY_REASON.values()))}")
    if value not in COMMAND_EXIT_CODE_BY_REASON.values():
        raise ContractValidationError(f"{field_name} must be one of {sorted(set(COMMAND_EXIT_CODE_BY_REASON.values()))}")
    return value


def _exit_reason_for_code(exit_code: int) -> str:
    code = _require_known_exit_code(exit_code, "command_exit_code")
    for reason, mapped_code in COMMAND_EXIT_CODE_BY_REASON.items():
        if mapped_code == code:
            return reason
    raise ContractValidationError(f"command_exit_code has no reason mapping: {code}")


def _reject_forbidden_command_fields(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = key.lower()
            if (
                lowered in COMMAND_FORBIDDEN_RAW_FIELDS
                or any(fragment in lowered for fragment in COMMAND_FORBIDDEN_KEY_FRAGMENTS)
                or any(lowered.endswith(suffix) for suffix in COMMAND_FORBIDDEN_KEY_SUFFIXES)
            ):
                raise ContractValidationError(f"{field_name}.{key} is not allowed in command output")
            _reject_forbidden_command_fields(item, f"{field_name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_command_fields(item, f"{field_name}[{index}]")


def _command_mapping(payload: Mapping[str, Any], field_name: str, allowed_keys: set[str]) -> dict[str, Any]:
    data = require_mapping(payload, field_name)
    _reject_forbidden_command_fields(data, field_name)
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unsupported fields: {unknown}")
    return data


def _validate_command_refs(value: Any, field_name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = key.lower()
            item_field = f"{field_name}.{key}"
            if lowered == "refs" or lowered.endswith("_refs"):
                for ref in require_str_list(item, item_field):
                    validate_ref(ref, f"{item_field}[]")
            elif lowered == "ref" or lowered.endswith("_ref"):
                validate_ref(item, item_field)
            else:
                _validate_command_refs(item, item_field)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_command_refs(item, f"{field_name}[{index}]")


def _dedupe_refs(refs: list[str]) -> list[str]:
    deduped: list[str] = []
    for ref in refs:
        safe_ref = validate_ref(ref, "mission_command_result.refs[]")
        if safe_ref not in deduped:
            deduped.append(safe_ref)
    return deduped


if __name__ == "__main__":
    raise SystemExit(main())
