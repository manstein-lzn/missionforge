"""Dedicated PI Agent runtime worker adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
from typing import Any, Mapping, Protocol, Sequence

from ..agent_packets import (
    AgentExecutionPacket,
    AgentExecutionReport,
    AgentExecutionStatus,
    JudgePacket,
    JudgeReport,
    validate_judge_report_for_packet,
)
from ..adapters.contracts import AdapterResult
from ..contracts import (
    ContractValidationError,
    EvidenceTrustLevel,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from ..evidence_store import EvidenceLedger, InMemoryEvidenceStore
from ..piworker_call import PiWorkerCall, PiWorkerCallResult
from ..runtime_results import ExecutionReport, WorkerAdapterResult, WorkerResult
from ..runtime_control import CapabilityGrant, SandboxMode, SandboxProfile, create_capability_grant
from ..task_contract import PermissionManifest
from .pi_agent_provider_config import resolve_pi_agent_provider_environment


PI_AGENT_INPUT_SCHEMA_VERSION = "missionforge.pi_agent_runtime_input.v1"
PI_AGENT_OUTPUT_SCHEMA_VERSION = "missionforge.pi_agent_runtime_output.v1"
DEFAULT_PI_AGENT_TIMEOUT_SECONDS = 300
MAX_CAPTURED_STREAM_CHARS = 4000

PI_AGENT_PROVIDER_MODES = {"faux", "live"}
PI_AGENT_PROVIDER_CONFIG_SOURCES = {"env", "codex_current", "explicit"}
PI_AGENT_STATUSES = {"completed", "failed", "blocked", "cancelled"}
PI_AGENT_VERIFICATION_STATUSES = {"passed", "failed", "not_run", "review_required"}
PI_AGENT_REPAIR_MODES = {"none", "follow_up"}
PI_AGENT_RESUME_MODES = {"none", "follow_up"}
SAFE_WORKER_CLAIM_RE = re.compile(r"^([a-z][a-z0-9_.-]*):length=[0-9]+$")
SAFE_WORKER_CLAIM_NAMES = {"assistant_final_text_present", "worker_claim_present"}


@dataclass(frozen=True)
class PiAgentCallSpec:
    """Minimal sidecar execution spec projected from PiWorkerCall."""

    call_id: str
    mission_id: str
    iteration: int
    next_objective: str
    allowed_scope: list[str] = field(default_factory=list)
    visible_refs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    exit_criteria: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)

    @classmethod
    def from_call(
        cls,
        call: PiWorkerCall,
        *,
        iteration: int = 1,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
    ) -> "PiAgentCallSpec":
        call.validate()
        call_spec = cls(
            call_id=call.call_id,
            mission_id=call.contract_id,
            iteration=require_int_at_least(iteration, "pi_agent_call_spec.iteration", 1),
            next_objective=call.objective,
            allowed_scope=list(call.writable_refs),
            visible_refs=_dedupe_refs(
                [
                    *call.visible_refs,
                    *([call.permission_manifest_ref] if call.permission_manifest_ref else []),
                ]
            ),
            expected_outputs=list(call.expected_output_refs),
            exit_criteria=exit_criteria or ["Write all expected output refs through the PiWorker runtime."],
            stop_conditions=stop_conditions or ["Stop if the PiWorker runtime reports failed or blocked."],
        )
        call_spec.validate()
        return call_spec

    def validate(self) -> None:
        require_non_empty_str(self.call_id, "pi_agent_call_spec.call_id")
        require_non_empty_str(self.mission_id, "pi_agent_call_spec.mission_id")
        require_int_at_least(self.iteration, "pi_agent_call_spec.iteration", 1)
        require_non_empty_str(self.next_objective, "pi_agent_call_spec.next_objective")
        _validate_ref_list(self.allowed_scope, "pi_agent_call_spec.allowed_scope")
        _validate_ref_list(self.visible_refs, "pi_agent_call_spec.visible_refs")
        _validate_ref_list(self.expected_outputs, "pi_agent_call_spec.expected_outputs")
        require_str_list(self.exit_criteria, "pi_agent_call_spec.exit_criteria")
        require_str_list(self.stop_conditions, "pi_agent_call_spec.stop_conditions")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "call_id": self.call_id,
            "mission_id": self.mission_id,
            "iteration": self.iteration,
            "next_objective": self.next_objective,
            "allowed_scope": list(self.allowed_scope),
            "visible_refs": list(self.visible_refs),
            "expected_outputs": list(self.expected_outputs),
            "exit_criteria": list(self.exit_criteria),
            "stop_conditions": list(self.stop_conditions),
        }


@dataclass(frozen=True)
class PiAgentRuntimeInput:
    """Direct MissionForge input spec for the Pi Agent runtime sidecar."""

    piworker_call: PiWorkerCall
    input_ref: str
    output_ref: str
    session_ref: str
    events_ref: str
    metrics_ref: str
    savepoints_ref: str
    attempt_dir_ref: str
    permission_manifest: Mapping[str, Any]
    capability_grant: Mapping[str, Any]
    sandbox_profile: Mapping[str, Any]
    call_spec: PiAgentCallSpec
    config: "PiAgentRuntimeConfig"
    schema_version: str = PI_AGENT_INPUT_SCHEMA_VERSION

    @classmethod
    def from_call(
        cls,
        call: PiWorkerCall,
        *,
        refs: Mapping[str, str],
        permission_manifest: Mapping[str, Any],
        config: "PiAgentRuntimeConfig",
        call_spec: PiAgentCallSpec | None = None,
        capability_grant: Mapping[str, Any] | None = None,
        sandbox_profile: Mapping[str, Any] | None = None,
    ) -> "PiAgentRuntimeInput":
        call.validate()
        spec = call_spec or PiAgentCallSpec.from_call(call)
        spec.validate()
        if capability_grant is None or sandbox_profile is None:
            generated_grant, generated_profile = _runtime_authority_payloads(
                call,
                refs=refs,
                permission_manifest=permission_manifest,
                timeout_seconds=config.timeout_seconds,
            )
            capability_grant = capability_grant or generated_grant
            sandbox_profile = sandbox_profile or generated_profile
        runtime_input = cls(
            piworker_call=call,
            input_ref=validate_ref(refs["input"], "pi_agent_runtime_input.input_ref"),
            output_ref=validate_ref(refs["output"], "pi_agent_runtime_input.output_ref"),
            session_ref=validate_ref(refs["session"], "pi_agent_runtime_input.session_ref"),
            events_ref=validate_ref(refs["events"], "pi_agent_runtime_input.events_ref"),
            metrics_ref=validate_ref(refs["metrics"], "pi_agent_runtime_input.metrics_ref"),
            savepoints_ref=validate_ref(refs["savepoints"], "pi_agent_runtime_input.savepoints_ref"),
            attempt_dir_ref=validate_ref(refs["attempt_dir"], "pi_agent_runtime_input.attempt_dir_ref"),
            permission_manifest=permission_manifest,
            capability_grant=capability_grant,
            sandbox_profile=sandbox_profile,
            call_spec=spec,
            config=config,
        )
        runtime_input.validate()
        return runtime_input

    def validate(self) -> None:
        if self.schema_version != PI_AGENT_INPUT_SCHEMA_VERSION:
            raise ContractValidationError(f"unsupported pi_agent_runtime_input.schema_version: {self.schema_version}")
        self.piworker_call.validate()
        self.call_spec.validate()
        _validate_call_spec_for_call(self.call_spec, self.piworker_call)
        for field_name in (
            "input_ref",
            "output_ref",
            "session_ref",
            "events_ref",
            "metrics_ref",
            "savepoints_ref",
            "attempt_dir_ref",
        ):
            validate_ref(getattr(self, field_name), f"pi_agent_runtime_input.{field_name}")
        ensure_json_value(
            require_mapping(self.permission_manifest, "pi_agent_runtime_input.permission_manifest"),
            "pi_agent_runtime_input.permission_manifest",
        )
        ensure_json_value(
            require_mapping(self.capability_grant, "pi_agent_runtime_input.capability_grant"),
            "pi_agent_runtime_input.capability_grant",
        )
        ensure_json_value(
            require_mapping(self.sandbox_profile, "pi_agent_runtime_input.sandbox_profile"),
            "pi_agent_runtime_input.sandbox_profile",
        )
        _validate_runtime_authority(
            call=self.piworker_call,
            permission_manifest=PermissionManifest.from_dict(self.permission_manifest),
            capability_grant=CapabilityGrant.from_dict(self.capability_grant),
            sandbox_profile=SandboxProfile.from_dict(self.sandbox_profile),
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "call_id": self.piworker_call.call_id,
            "mission_id": self.piworker_call.contract_id,
            "iteration": self.call_spec.iteration,
            "workspace_root": ".",
            "attempt_dir_ref": self.attempt_dir_ref,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "session_ref": self.session_ref,
            "events_ref": self.events_ref,
            "metrics_ref": self.metrics_ref,
            "savepoints_ref": self.savepoints_ref,
            "piworker_call": self.piworker_call.to_dict(),
            "call_spec": self.call_spec.to_dict(),
            "permission_manifest": ensure_json_value(
                dict(self.permission_manifest),
                "pi_agent_runtime_input.permission_manifest",
            ),
            "capability_grant": ensure_json_value(
                dict(self.capability_grant),
                "pi_agent_runtime_input.capability_grant",
            ),
            "sandbox_profile": ensure_json_value(
                dict(self.sandbox_profile),
                "pi_agent_runtime_input.sandbox_profile",
            ),
            "runtime": {
                "runtime_name": self.config.runtime_name,
                "timeout_seconds": self.config.timeout_seconds,
                "model": self.config.model,
                "metadata": ensure_json_value(dict(self.config.metadata), "pi_agent_config.metadata"),
            },
            "repair": {
                "mode": self.config.repair_mode,
                "verifier_failures": list(self.config.verifier_failures),
                "failed_constraints": list(self.config.failed_constraints),
                "previous_output_ref": self.config.previous_output_ref,
                "repair_prompt": self.config.repair_prompt,
            },
            "resume": {
                "mode": self.config.resume_mode,
                "boundary": self.config.resume_boundary,
                "savepoint_ref": self.config.resume_savepoint_ref,
                "session_ref": self.config.resume_session_ref,
                "events_ref": self.config.resume_events_ref,
                "resume_prompt": self.config.resume_prompt,
            },
        }
        return ensure_json_value(payload, "pi_agent_runtime_input")


@dataclass(frozen=True)
class PiAgentRuntimeConfig:
    """Configuration for the single production PI Agent runtime."""

    command: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_PI_AGENT_TIMEOUT_SECONDS
    provider_mode: str = "faux"
    provider_config_source: str = "env"
    runtime_name: str = "missionforge.pi_agent_runtime"
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    repair_mode: str = "none"
    verifier_failures: tuple[str, ...] = ()
    failed_constraints: tuple[str, ...] = ()
    previous_output_ref: str | None = None
    repair_prompt: str | None = None
    resume_mode: str = "none"
    resume_boundary: str | None = None
    resume_savepoint_ref: str | None = None
    resume_session_ref: str | None = None
    resume_events_ref: str | None = None
    resume_prompt: str | None = None

    def __post_init__(self) -> None:
        command = self.command or default_pi_agent_runtime_command()
        object.__setattr__(self, "command", tuple(command))
        if not self.command:
            raise ContractValidationError("pi_agent_config.command must not be empty")
        for part in self.command:
            if not isinstance(part, str) or not part or "\x00" in part:
                raise ContractValidationError("pi_agent_config.command must contain non-empty strings without NUL bytes")
        require_int_at_least(self.timeout_seconds, "pi_agent_config.timeout_seconds", 1)
        if self.provider_mode not in PI_AGENT_PROVIDER_MODES:
            raise ContractValidationError(f"pi_agent_config.provider_mode must be one of {sorted(PI_AGENT_PROVIDER_MODES)}")
        if self.provider_config_source not in PI_AGENT_PROVIDER_CONFIG_SOURCES:
            raise ContractValidationError(
                f"pi_agent_config.provider_config_source must be one of {sorted(PI_AGENT_PROVIDER_CONFIG_SOURCES)}"
            )
        require_non_empty_str(self.runtime_name, "pi_agent_config.runtime_name")
        if self.model is not None:
            require_non_empty_str(self.model, "pi_agent_config.model")
        metadata = ensure_json_value(require_mapping(self.metadata, "pi_agent_config.metadata"), "pi_agent_config.metadata")
        _reject_sensitive_runtime_metadata(metadata)
        if self.repair_mode not in PI_AGENT_REPAIR_MODES:
            raise ContractValidationError(f"pi_agent_config.repair_mode must be one of {sorted(PI_AGENT_REPAIR_MODES)}")
        object.__setattr__(
            self,
            "verifier_failures",
            tuple(require_str_list(list(self.verifier_failures), "pi_agent_config.verifier_failures")),
        )
        object.__setattr__(
            self,
            "failed_constraints",
            tuple(require_str_list(list(self.failed_constraints), "pi_agent_config.failed_constraints")),
        )
        if self.previous_output_ref is not None:
            validate_ref(self.previous_output_ref, "pi_agent_config.previous_output_ref")
        if self.repair_prompt is not None:
            require_non_empty_str(self.repair_prompt, "pi_agent_config.repair_prompt")
        if self.repair_mode == "follow_up":
            if not self.verifier_failures and not self.failed_constraints:
                raise ContractValidationError("pi_agent_config follow_up repair requires verifier failures or failed constraints")
            if not self.previous_output_ref:
                raise ContractValidationError("pi_agent_config follow_up repair requires previous_output_ref")
            if not self.repair_prompt:
                raise ContractValidationError("pi_agent_config follow_up repair requires repair_prompt")
        if self.resume_mode not in PI_AGENT_RESUME_MODES:
            raise ContractValidationError(f"pi_agent_config.resume_mode must be one of {sorted(PI_AGENT_RESUME_MODES)}")
        for field_name in ("resume_savepoint_ref", "resume_session_ref", "resume_events_ref"):
            value = getattr(self, field_name)
            if value is not None:
                validate_ref(value, f"pi_agent_config.{field_name}")
        if self.resume_mode == "follow_up":
            if self.resume_boundary != "after_completed_turn":
                raise ContractValidationError("pi_agent_config resume follow_up requires after_completed_turn boundary")
            if not self.resume_savepoint_ref or not self.resume_session_ref or not self.resume_events_ref:
                raise ContractValidationError("pi_agent_config resume follow_up requires savepoint/session/events refs")
            if not self.resume_prompt:
                raise ContractValidationError("pi_agent_config resume follow_up requires resume_prompt")


@dataclass(frozen=True)
class PiAgentCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class PiAgentCommandRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        input_path: Path,
        cwd: Path,
        timeout_seconds: int,
        env: Mapping[str, str],
    ) -> PiAgentCommandResult:
        """Run the PI Agent runtime process."""
        ...


class SubprocessPiAgentCommandRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        input_path: Path,
        cwd: Path,
        timeout_seconds: int,
        env: Mapping[str, str],
    ) -> PiAgentCommandResult:
        child_env = dict(os.environ)
        child_env.update(dict(env))
        build_failure = _prepare_default_runtime_command(command, timeout_seconds=timeout_seconds, env=child_env)
        if build_failure is not None:
            return build_failure
        try:
            completed = subprocess.run(
                [*command, str(input_path)],
                cwd=cwd,
                timeout=timeout_seconds,
                text=True,
                capture_output=True,
                check=False,
                env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            return PiAgentCommandResult(
                returncode=-1,
                stdout=_process_output_text(exc.stdout),
                stderr=_process_output_text(exc.stderr),
                timed_out=True,
            )
        return PiAgentCommandResult(
            returncode=completed.returncode,
            stdout=_process_output_text(completed.stdout),
            stderr=_process_output_text(completed.stderr),
        )


@dataclass(frozen=True)
class PiAgentRunResult:
    call_id: str
    status: str
    produced_artifacts: list[str] = field(default_factory=list)
    changed_refs: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    worker_claims: list[str] = field(default_factory=list)
    verifier_evidence: list[str] = field(default_factory=list)
    new_unknowns: list[str] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    verification_status: str = "not_run"
    input_ref: str = ""
    output_ref: str = ""
    session_ref: str = ""
    events_ref: str = ""
    metrics_ref: str = ""
    savepoints_ref: str = ""
    duration_ms: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        default_call_id: str,
        default_input_ref: str,
        default_duration_ms: int,
    ) -> "PiAgentRunResult":
        data = require_mapping(payload, "pi_agent_run_result")
        if data.get("schema_version") != PI_AGENT_OUTPUT_SCHEMA_VERSION:
            raise ContractValidationError("pi_agent_run_result.schema_version is unsupported")
        result = cls(
            call_id=require_non_empty_str(
                data.get("call_id") or default_call_id,
                "pi_agent_run_result.call_id",
            ),
            status=require_non_empty_str(data.get("status", "failed"), "pi_agent_run_result.status"),
            produced_artifacts=require_str_list(data.get("produced_artifacts", []), "pi_agent_run_result.produced_artifacts"),
            changed_refs=require_str_list(data.get("changed_refs", []), "pi_agent_run_result.changed_refs"),
            commands_run=require_str_list(data.get("commands_run", []), "pi_agent_run_result.commands_run"),
            tests_run=require_str_list(data.get("tests_run", []), "pi_agent_run_result.tests_run"),
            failures=require_str_list(data.get("failures", []), "pi_agent_run_result.failures"),
            worker_claims=_summarized_worker_claims(
                require_str_list(data.get("worker_claims", []), "pi_agent_run_result.worker_claims")
            ),
            verifier_evidence=require_str_list(data.get("verifier_evidence", []), "pi_agent_run_result.verifier_evidence"),
            new_unknowns=require_str_list(data.get("new_unknowns", []), "pi_agent_run_result.new_unknowns"),
            recommended_next_steps=require_str_list(
                data.get("recommended_next_steps", []),
                "pi_agent_run_result.recommended_next_steps",
            ),
            verification_status=require_non_empty_str(
                data.get("verification_status", "not_run"),
                "pi_agent_run_result.verification_status",
            ),
            input_ref=validate_ref(data.get("input_ref") or default_input_ref, "pi_agent_run_result.input_ref"),
            output_ref=validate_ref(data.get("output_ref"), "pi_agent_run_result.output_ref"),
            session_ref=validate_ref(data.get("session_ref"), "pi_agent_run_result.session_ref"),
            events_ref=validate_ref(data.get("events_ref"), "pi_agent_run_result.events_ref"),
            metrics_ref=validate_ref(data.get("metrics_ref"), "pi_agent_run_result.metrics_ref"),
            savepoints_ref=validate_ref(data.get("savepoints_ref"), "pi_agent_run_result.savepoints_ref"),
            duration_ms=require_int_at_least(
                data.get("duration_ms", default_duration_ms),
                "pi_agent_run_result.duration_ms",
                0,
            ),
            metrics=ensure_json_value(require_mapping(data.get("metrics", {}), "pi_agent_run_result.metrics"), "pi_agent_run_result.metrics"),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.call_id, "pi_agent_run_result.call_id")
        if self.status not in PI_AGENT_STATUSES:
            raise ContractValidationError(f"pi_agent_run_result.status must be one of {sorted(PI_AGENT_STATUSES)}")
        if self.verification_status not in PI_AGENT_VERIFICATION_STATUSES:
            raise ContractValidationError(
                f"pi_agent_run_result.verification_status must be one of {sorted(PI_AGENT_VERIFICATION_STATUSES)}"
            )
        for field_name in ("produced_artifacts", "changed_refs", "verifier_evidence", "new_unknowns"):
            for ref in getattr(self, field_name):
                validate_ref(ref, f"pi_agent_run_result.{field_name}[]")
        for field_name in ("input_ref", "output_ref", "session_ref", "events_ref", "metrics_ref", "savepoints_ref"):
            validate_ref(getattr(self, field_name), f"pi_agent_run_result.{field_name}")
        for field_name in ("commands_run", "tests_run", "failures", "worker_claims", "recommended_next_steps"):
            require_str_list(getattr(self, field_name), f"pi_agent_run_result.{field_name}")
        require_int_at_least(self.duration_ms, "pi_agent_run_result.duration_ms", 0)
        ensure_json_value(require_mapping(self.metrics, "pi_agent_run_result.metrics"), "pi_agent_run_result.metrics")


@dataclass(frozen=True)
class PiAgentExecutorNode:
    """AgenticFlow executor node backed by the dedicated PI Agent runtime adapter."""

    workspace_root: str | Path
    adapter: "PiAgentRuntimeAdapter" = field(default_factory=lambda: PiAgentRuntimeAdapter())

    def execute(
        self,
        packet: AgentExecutionPacket,
        *,
        packet_ref: str,
        workspace: object,
    ) -> AgentExecutionReport:
        packet.validate()
        root = _agent_node_workspace_root(workspace, fallback=self.workspace_root)
        call = PiWorkerCall.from_execution_packet(packet, packet_ref=packet_ref)
        result = self.adapter.run_call(
            call,
            workspace=root,
            evidence_store=InMemoryEvidenceStore(),
            exit_criteria=["Write all expected artifact refs and report through PI Agent runtime."],
            stop_conditions=["Stop if the PI Agent runtime reports failed or blocked."],
        )
        call_result = PiWorkerCallResult.from_worker_adapter_result(call, result)
        call_result_ref = _piworker_call_result_ref(call.call_id)
        _write_json(_resolve_workspace_ref(root, call_result_ref), call_result.to_dict())
        evidence_projection_ref = _piworker_call_result_projection_ref(call.call_id)
        metrics_projection_ref = _piworker_metrics_projection_ref(call.call_id)
        _write_json(
            _resolve_workspace_ref(root, evidence_projection_ref),
            _piworker_call_result_projection_payload(call_result, source_call_result_ref=call_result_ref),
        )
        _write_json(
            _resolve_workspace_ref(root, metrics_projection_ref),
            _piworker_metrics_projection_payload(call_result, result.execution_report),
        )
        work_report = result.execution_report
        status = _agent_execution_status(work_report.status)
        packet_hash = stable_json_hash(packet.to_dict())
        runtime_owned_refs = _pi_agent_runtime_owned_refs(call.call_id)
        report = AgentExecutionReport(
            report_id=f"agent-{work_report.report_id}",
            packet_id=packet.packet_id,
            packet_ref=packet_ref,
            packet_hash=packet_hash,
            contract_id=packet.contract_id,
            contract_hash=packet.contract_hash,
            contract_ref=packet.contract_ref,
            status=status,
            produced_artifact_refs=list(work_report.produced_artifacts),
            changed_refs=_dedupe_refs([ref for ref in work_report.changed_refs if ref not in runtime_owned_refs]),
            evidence_refs=[evidence_projection_ref],
            metric_refs=[metrics_projection_ref],
        )
        report.validate()
        return report


@dataclass(frozen=True)
class PiAgentJudgeNode:
    """AgenticFlow judge node backed by the dedicated PI Agent runtime adapter."""

    workspace_root: str | Path
    adapter: "PiAgentRuntimeAdapter" = field(default_factory=lambda: PiAgentRuntimeAdapter())

    def judge(
        self,
        packet: JudgePacket,
        *,
        packet_ref: str,
        workspace: object,
    ) -> JudgeReport:
        packet.validate()
        root = _agent_node_workspace_root(workspace, fallback=self.workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        packet_path = _resolve_workspace_ref(root, packet_ref)
        _write_json(packet_path, packet.to_dict())
        packet_hash = stable_json_hash(packet.to_dict())
        spec_ref = _judge_node_spec_ref(packet.packet_id)
        _write_json(
            _resolve_workspace_ref(root, spec_ref),
            _judge_node_spec_payload(packet=packet, packet_ref=packet_ref, packet_hash=packet_hash),
        )
        call = PiWorkerCall.from_judge_packet(
            packet,
            packet_ref=packet_ref,
            spec_ref=spec_ref,
            packet_hash=packet_hash,
        )
        result = self.adapter.run_call(
            call,
            workspace=root,
            evidence_store=InMemoryEvidenceStore(),
            exit_criteria=["JudgeReport JSON exists and matches the judge packet."],
            stop_conditions=["Do not modify executor artifacts, contract refs, packets, hard checks, or evidence refs."],
        )
        call_result = PiWorkerCallResult.from_worker_adapter_result(call, result)
        _write_json(_resolve_workspace_ref(root, _piworker_call_result_ref(call.call_id)), call_result.to_dict())
        work_report = result.execution_report
        if work_report.status != "completed":
            raise ContractValidationError("pi-agent judge node did not complete successfully")
        report_path = _resolve_workspace_ref(root, packet.report_ref)
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ContractValidationError("judge report artifact must be a JSON object")
            judge_report = JudgeReport.from_dict(payload)
        except ContractValidationError:
            raise
        except Exception as exc:
            raise ContractValidationError(f"judge report artifact is invalid: {exc}") from exc
        if judge_report.packet_hash is None:
            judge_report = replace(judge_report, packet_hash=packet_hash)
        validate_judge_report_for_packet(
            judge_report,
            packet,
            packet_ref=packet_ref,
            packet_hash=packet_hash,
        )
        return judge_report


class PiAgentRuntimeAdapter:
    """Invoke the dedicated PI Agent runtime and normalize refs-only evidence."""

    adapter_id = "pi_agent_runtime"
    adapter_family = "piworker"

    def __init__(
        self,
        config: PiAgentRuntimeConfig | None = None,
        *,
        runner: PiAgentCommandRunner | None = None,
        environ: Mapping[str, str] | None = None,
        codex_home: str | Path | None = None,
    ) -> None:
        self.config = config or PiAgentRuntimeConfig()
        self.runner = runner or SubprocessPiAgentCommandRunner()
        self.environ = dict(environ) if environ is not None else None
        self.codex_home = codex_home

    def with_repair(
        self,
        *,
        verifier_failures: Sequence[str],
        failed_constraints: Sequence[str],
        previous_output_ref: str,
        repair_prompt: str,
    ) -> "PiAgentRuntimeAdapter":
        """Clone this adapter for a verifier-driven repair follow-up."""

        repair_config = PiAgentRuntimeConfig(
            command=self.config.command,
            timeout_seconds=self.config.timeout_seconds,
            provider_mode=self.config.provider_mode,
            provider_config_source=self.config.provider_config_source,
            runtime_name=self.config.runtime_name,
            model=self.config.model,
            metadata=self.config.metadata,
            repair_mode="follow_up",
            verifier_failures=tuple(verifier_failures),
            failed_constraints=tuple(failed_constraints),
            previous_output_ref=previous_output_ref,
            repair_prompt=repair_prompt,
        )
        return PiAgentRuntimeAdapter(
            repair_config,
            runner=self.runner,
            environ=self.environ,
            codex_home=self.codex_home,
        )

    def with_resume(
        self,
        *,
        savepoint_ref: str,
        session_ref: str,
        events_ref: str,
        follow_up_prompt: str,
    ) -> "PiAgentRuntimeAdapter":
        """Clone this adapter for a completed-turn resume follow-up."""

        resume_config = PiAgentRuntimeConfig(
            command=self.config.command,
            timeout_seconds=self.config.timeout_seconds,
            provider_mode=self.config.provider_mode,
            provider_config_source=self.config.provider_config_source,
            runtime_name=self.config.runtime_name,
            model=self.config.model,
            metadata=self.config.metadata,
            repair_mode=self.config.repair_mode,
            verifier_failures=self.config.verifier_failures,
            failed_constraints=self.config.failed_constraints,
            previous_output_ref=self.config.previous_output_ref,
            repair_prompt=self.config.repair_prompt,
            resume_mode="follow_up",
            resume_boundary="after_completed_turn",
            resume_savepoint_ref=savepoint_ref,
            resume_session_ref=session_ref,
            resume_events_ref=events_ref,
            resume_prompt=follow_up_prompt,
        )
        return PiAgentRuntimeAdapter(
            resume_config,
            runner=self.runner,
            environ=self.environ,
            codex_home=self.codex_home,
        )

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
        call_spec: PiAgentCallSpec | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
    ) -> WorkerAdapterResult:
        call.validate()
        spec = call_spec or PiAgentCallSpec.from_call(
            call,
            exit_criteria=exit_criteria,
            stop_conditions=stop_conditions,
        )
        spec.validate()
        _validate_call_spec_for_call(spec, call)
        if not spec.expected_outputs:
            raise ContractValidationError("PiAgentRuntimeAdapter requires at least one expected output")
        _reject_outputs_outside_scope(spec)

        store = evidence_store or InMemoryEvidenceStore()
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        refs = _pi_agent_refs(spec.call_id)
        _resolve_workspace_ref(root, refs["attempt_dir"]).mkdir(parents=True, exist_ok=True)
        provider_env = resolve_pi_agent_provider_environment(
            provider_mode=self.config.provider_mode,
            provider_config_source=self.config.provider_config_source,
            model=self.config.model,
            metadata=self.config.metadata,
            environ=self.environ,
            codex_home=self.codex_home,
        )

        input_payload = self._build_input_payload(call, spec, refs)
        _write_json(_resolve_workspace_ref(root, refs["workspace_policy"]), _runtime_workspace_policy_payload(spec, refs))
        _write_json(_resolve_workspace_ref(root, refs["permission_manifest"]), input_payload["permission_manifest"])  # type: ignore[index]
        _write_json(_resolve_workspace_ref(root, refs["sandbox_profile"]), input_payload["sandbox_profile"])  # type: ignore[index]
        input_path = _resolve_workspace_ref(root, refs["input"])
        _write_json(input_path, input_payload)
        event_refs = [
            _record_adapter_event(
                store,
                event_type="invocation_started",
                call_id=spec.call_id,
                payload={
                    "input_ref": refs["input"],
                    "provider_mode": self.config.provider_mode,
                    "provider_config_source": provider_env.source,
                    "provider_env": _non_secret_env(provider_env.env),
                    "provider_secret_present": _has_secret_env(provider_env.env),
                },
                source_refs=[refs["input"]],
            )
        ]

        started = time.monotonic()
        command_result = self.runner.run(
            self.config.command,
            input_path=input_path,
            cwd=root,
            timeout_seconds=self.config.timeout_seconds,
            env=provider_env.env,
        )
        duration_ms = _duration_ms(started)

        run_result = self._load_or_failure_result(
            root=root,
            spec=spec,
            refs=refs,
            duration_ms=duration_ms,
            command_result=command_result,
            env=provider_env.env,
        )
        run_result = self._enforce_output_contract(root=root, spec=spec, refs=refs, result=run_result)

        event_refs.append(
            _record_adapter_event(
                store,
                event_type="invocation_completed" if run_result.status == "completed" else "invocation_failed",
                call_id=spec.call_id,
                payload={
                    "status": run_result.status,
                    "returncode": command_result.returncode,
                    "timed_out": command_result.timed_out,
                    "stdout": _redacted_stream(command_result.stdout, provider_env.env),
                    "stderr": _redacted_stream(command_result.stderr, provider_env.env),
                    "output_ref": run_result.output_ref,
                    "session_ref": run_result.session_ref,
                    "events_ref": run_result.events_ref,
                    "metrics_ref": run_result.metrics_ref,
                    "savepoints_ref": run_result.savepoints_ref,
                },
                source_refs=[refs["input"], run_result.output_ref],
                trust_level=EvidenceTrustLevel.COMMAND_RESULT,
            )
        )
        event_refs.append(
            _record_adapter_event(
                store,
                event_type="metrics_recorded",
                call_id=spec.call_id,
                payload={
                    "metrics_ref": run_result.metrics_ref,
                    "savepoints_ref": run_result.savepoints_ref,
                    "duration_ms": run_result.duration_ms,
                    "produced_artifact_count": len(run_result.produced_artifacts),
                    "provider_mode": self.config.provider_mode,
                },
                source_refs=[run_result.metrics_ref],
            )
        )

        report_ref = refs["report"]
        report_status = "completed" if run_result.status == "completed" else "failed"
        report = ExecutionReport(
            report_id=f"R-{spec.call_id}",
            call_id=spec.call_id,
            status=report_status,
            produced_artifacts=list(run_result.produced_artifacts),
            changed_refs=_dedupe_refs([
                *run_result.changed_refs,
                refs["output"],
                refs["session"],
                refs["events"],
                refs["metrics"],
                refs["savepoints"],
            ]),
            evidence_refs=_dedupe_refs(event_refs),
            worker_claims=list(run_result.worker_claims),
            metrics={
                "adapter_id": self.adapter_id,
                "adapter_result_status": report_status,
                "duration_ms": run_result.duration_ms,
                "returncode": command_result.returncode,
                "timed_out": command_result.timed_out,
                "provider_mode": self.config.provider_mode,
                "provider_config_source": provider_env.source,
                "model": self.config.model,
                "tool_call_count": _non_negative_metric(run_result.metrics, "tool_call_count", "tool_calls"),
                "token_count": _non_negative_metric(run_result.metrics, "total_tokens", "token_count"),
                "total_tokens": _non_negative_metric(run_result.metrics, "total_tokens", "token_count"),
                "input_tokens": _non_negative_metric(run_result.metrics, "input_tokens"),
                "output_tokens": _non_negative_metric(run_result.metrics, "output_tokens"),
                "cache_read_tokens": _non_negative_metric(run_result.metrics, "cache_read_tokens"),
                "cache_write_tokens": _non_negative_metric(run_result.metrics, "cache_write_tokens"),
                "input_cost_usd": _non_negative_number_metric(run_result.metrics, "input_cost_usd"),
                "output_cost_usd": _non_negative_number_metric(run_result.metrics, "output_cost_usd"),
                "cache_read_cost_usd": _non_negative_number_metric(run_result.metrics, "cache_read_cost_usd"),
                "cache_write_cost_usd": _non_negative_number_metric(run_result.metrics, "cache_write_cost_usd"),
                "provider_reported_cost_usd": _non_negative_number_metric(run_result.metrics, "provider_reported_cost_usd"),
                "tool_error_count": _non_negative_metric(run_result.metrics, "tool_error_count"),
                "tool_latency_ms_total": _non_negative_metric(run_result.metrics, "tool_latency_ms_total"),
                "command_count": _non_negative_metric(run_result.metrics, "command_count"),
                "test_command_count": _non_negative_metric(run_result.metrics, "test_command_count"),
                "command_failure_count": _non_negative_metric(run_result.metrics, "command_failure_count"),
                "time_to_first_tool_ms": _non_negative_metric(run_result.metrics, "time_to_first_tool_ms"),
                "time_to_first_artifact_ms": _non_negative_metric(run_result.metrics, "time_to_first_artifact_ms"),
                "input_ref": refs["input"],
                "output_ref": run_result.output_ref,
                "metrics_ref": run_result.metrics_ref,
                "savepoints_ref": run_result.savepoints_ref,
            },
        )
        _write_json(_resolve_workspace_ref(root, report_ref), report.to_dict())

        adapter_result = AdapterResult(
            invocation_id=f"invoke-{spec.call_id}",
            adapter_id=self.adapter_id,
            status=report_status,
            output_refs=_dedupe_refs([report_ref, refs["input"], run_result.output_ref, run_result.savepoints_ref, *run_result.produced_artifacts]),
            evidence_refs=list(report.evidence_refs),
            metrics={
                "duration_ms": run_result.duration_ms,
                "returncode": command_result.returncode,
                "timed_out": command_result.timed_out,
                "provider_mode": self.config.provider_mode,
            },
        )
        adapter_result.validate()

        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status=report_status, execution_report_ref=report_ref),
            event_evidence_refs=list(event_refs),
            metrics=dict(adapter_result.metrics),
        )

    def _build_input_payload(
        self,
        call: PiWorkerCall,
        call_spec: PiAgentCallSpec,
        refs: Mapping[str, str],
    ) -> dict[str, Any]:
        permission_manifest = _permission_manifest_payload(call_spec, workspace_policy_ref=refs["workspace_policy"])
        runtime_input = PiAgentRuntimeInput.from_call(
            call,
            refs=refs,
            permission_manifest=permission_manifest,
            config=self.config,
            call_spec=call_spec,
        )
        return runtime_input.to_dict()

    def _load_or_failure_result(
        self,
        *,
        root: Path,
        spec: PiAgentCallSpec,
        refs: Mapping[str, str],
        duration_ms: int,
        command_result: PiAgentCommandResult,
        env: Mapping[str, str],
    ) -> PiAgentRunResult:
        failure = _command_failure(command_result, self.config.timeout_seconds)
        output_path = _resolve_workspace_ref(root, refs["output"])
        if failure is not None:
            return _write_failure_result(output_path, spec=spec, refs=refs, duration_ms=duration_ms, command_result=command_result, env=env, failure=failure)
        if not output_path.is_file():
            return _write_failure_result(output_path, spec=spec, refs=refs, duration_ms=duration_ms, command_result=command_result, env=env, failure=f"pi-agent-runtime output artifact is missing: {refs['output']}")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ContractValidationError("pi-agent-runtime output artifact must be a JSON object")
            return PiAgentRunResult.from_dict(
                payload,
                default_call_id=spec.call_id,
                default_input_ref=refs["input"],
                default_duration_ms=duration_ms,
            )
        except Exception as exc:
            return _write_failure_result(output_path, spec=spec, refs=refs, duration_ms=duration_ms, command_result=command_result, env=env, failure=f"pi-agent-runtime output artifact is invalid: {exc}")

    def _enforce_output_contract(
        self,
        *,
        root: Path,
        spec: PiAgentCallSpec,
        refs: Mapping[str, str],
        result: PiAgentRunResult,
    ) -> PiAgentRunResult:
        if result.call_id != spec.call_id:
            return _rewrite_contract_failure(root, spec=spec, refs=refs, result=result, failure=f"pi-agent-runtime output call_id mismatch: {result.call_id}")
        for ref in result.produced_artifacts:
            if not any(_is_within(ref, scope) for scope in spec.allowed_scope):
                return _rewrite_contract_failure(root, spec=spec, refs=refs, result=result, failure=f"pi-agent-runtime produced artifact outside allowed scope: {ref}")
        missing_outputs = [ref for ref in spec.expected_outputs if ref not in result.produced_artifacts]
        missing_files = [ref for ref in result.produced_artifacts if not _resolve_workspace_ref(root, ref).is_file()]
        if result.status == "completed" and (missing_outputs or missing_files):
            failures = [f"expected output was not produced: {ref}" for ref in missing_outputs]
            failures.extend(f"produced artifact is missing on disk: {ref}" for ref in missing_files)
            return _rewrite_contract_failure(root, spec=spec, refs=refs, result=result, failure="; ".join(failures))
        if result.status in {"completed", "cancelled"} and not _resolve_workspace_ref(root, result.savepoints_ref).is_file():
            return _rewrite_contract_failure(
                root,
                spec=spec,
                refs=refs,
                result=result,
                failure=f"pi-agent-runtime savepoint artifact is missing: {result.savepoints_ref}",
            )
        return result


def default_pi_agent_runtime_command() -> tuple[str, ...]:
    runtime_main = Path(__file__).resolve().parents[3] / "workers" / "pi-agent-runtime" / "dist" / "main.js"
    return ("node", str(runtime_main))


def _prepare_default_runtime_command(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> PiAgentCommandResult | None:
    if len(command) < 2 or command[0] != "node":
        return None
    main_path = Path(command[1])
    if main_path.name != "main.js" or main_path.parent.name != "dist":
        return None
    if main_path.is_file():
        return None
    package_dir = main_path.parent.parent
    if not (package_dir / "package.json").is_file():
        return None
    install = _run_setup_command(("npm", "install"), cwd=package_dir, timeout_seconds=timeout_seconds, env=env)
    if install.returncode != 0 or install.timed_out:
        return install
    build = _run_setup_command(("npm", "run", "build"), cwd=package_dir, timeout_seconds=timeout_seconds, env=env)
    if build.returncode != 0 or build.timed_out:
        return build
    return None


def _run_setup_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> PiAgentCommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            timeout=timeout_seconds,
            text=True,
            capture_output=True,
            check=False,
            env=dict(env),
        )
    except subprocess.TimeoutExpired as exc:
        return PiAgentCommandResult(
            returncode=-1,
            stdout=_process_output_text(exc.stdout),
            stderr=_process_output_text(exc.stderr),
            timed_out=True,
        )
    except OSError as exc:
        return PiAgentCommandResult(returncode=-1, stderr=str(exc))
    return PiAgentCommandResult(
        returncode=completed.returncode,
        stdout=_process_output_text(completed.stdout),
        stderr=_process_output_text(completed.stderr),
    )


def _write_failure_result(
    output_path: Path,
    *,
    spec: PiAgentCallSpec,
    refs: Mapping[str, str],
    duration_ms: int,
    command_result: PiAgentCommandResult,
    env: Mapping[str, str],
    failure: str,
) -> PiAgentRunResult:
    payload = _failure_payload(
        spec=spec,
        refs=refs,
        duration_ms=duration_ms,
        command_result=command_result,
        env=env,
        failures=[failure],
    )
    _write_json(output_path, payload)
    return PiAgentRunResult.from_dict(
        payload,
        default_call_id=spec.call_id,
        default_input_ref=refs["input"],
        default_duration_ms=duration_ms,
    )


def _rewrite_contract_failure(
    root: Path,
    *,
    spec: PiAgentCallSpec,
    refs: Mapping[str, str],
    result: PiAgentRunResult,
    failure: str,
) -> PiAgentRunResult:
    payload = {
        "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
        "call_id": spec.call_id,
        "status": "failed",
        "produced_artifacts": list(result.produced_artifacts),
        "changed_refs": _dedupe_refs([*result.changed_refs, refs["output"], refs["savepoints"]]),
        "commands_run": list(result.commands_run),
        "tests_run": list(result.tests_run),
        "failures": _dedupe_refs([*result.failures, failure]),
        "worker_claims": list(result.worker_claims),
        "verifier_evidence": _dedupe_refs([*result.verifier_evidence, refs["output"], refs["savepoints"]]),
        "new_unknowns": _dedupe_refs([*result.new_unknowns, *spec.expected_outputs]),
        "recommended_next_steps": ["Inspect PI Agent runtime output spec failure before retrying."],
        "verification_status": "failed",
        "input_ref": refs["input"],
        "output_ref": refs["output"],
        "session_ref": refs["session"],
        "events_ref": refs["events"],
        "metrics_ref": refs["metrics"],
        "savepoints_ref": refs["savepoints"],
        "duration_ms": result.duration_ms,
        "metrics": dict(result.metrics),
    }
    output_path = _resolve_workspace_ref(root, refs["output"])
    _write_json(output_path, payload)
    return PiAgentRunResult.from_dict(
        payload,
        default_call_id=spec.call_id,
        default_input_ref=refs["input"],
        default_duration_ms=result.duration_ms,
    )


def _failure_payload(
    *,
    spec: PiAgentCallSpec,
    refs: Mapping[str, str],
    duration_ms: int,
    command_result: PiAgentCommandResult,
    env: Mapping[str, str],
    failures: list[str],
) -> dict[str, Any]:
    stream_failures = [
        *_prefixed_stream_lines("stdout", command_result.stdout, env),
        *_prefixed_stream_lines("stderr", command_result.stderr, env),
    ]
    return {
        "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
        "call_id": spec.call_id,
        "status": "failed",
        "produced_artifacts": [],
        "changed_refs": [refs["output"], refs["savepoints"]],
        "commands_run": [_format_command([])],
        "tests_run": [],
        "failures": [*failures, *stream_failures],
        "worker_claims": [],
        "verifier_evidence": [refs["output"], refs["savepoints"]],
        "new_unknowns": list(spec.expected_outputs),
        "recommended_next_steps": ["Inspect PI Agent runtime failure before retrying."],
        "verification_status": "failed",
        "input_ref": refs["input"],
        "output_ref": refs["output"],
        "session_ref": refs["session"],
        "events_ref": refs["events"],
        "metrics_ref": refs["metrics"],
        "savepoints_ref": refs["savepoints"],
        "duration_ms": duration_ms,
        "metrics": {
            "duration_ms": duration_ms,
            "returncode": command_result.returncode,
            "timed_out": command_result.timed_out,
        },
    }


def _record_adapter_event(
    store: EvidenceLedger,
    *,
    event_type: str,
    call_id: str,
    payload: Mapping[str, Any],
    source_refs: list[str] | None = None,
    trust_level: EvidenceTrustLevel = EvidenceTrustLevel.ARTIFACT_REF,
) -> str:
    event_payload = {
        "call_id": call_id,
        "event_type": event_type,
        **ensure_json_value(require_mapping(payload, "pi_agent_adapter_event.payload"), "pi_agent_adapter_event.payload"),
    }
    evidence_ref = store.append(
        payload=event_payload,
        trust_level=trust_level,
        kind="pi_agent_runtime_event",
        source_refs=source_refs,
    )
    return evidence_ref.evidence_id


def _judge_node_spec_ref(packet_id: str) -> str:
    safe_packet_id = require_non_empty_str(packet_id, "judge_packet.packet_id")
    return f"attempts/{safe_packet_id}/judge_node_spec.json"


def _piworker_call_result_ref(call_id: str) -> str:
    safe_call_id = require_non_empty_str(call_id, "piworker_call.call_id")
    return f"attempts/{safe_call_id}/piworker_call_result.json"


def _piworker_call_result_projection_ref(call_id: str) -> str:
    safe_call_id = require_non_empty_str(call_id, "piworker_call.call_id")
    return f"reports/piworker_runtime/{safe_call_id}/call_result_projection.json"


def _piworker_metrics_projection_ref(call_id: str) -> str:
    safe_call_id = require_non_empty_str(call_id, "piworker_call.call_id")
    return f"reports/piworker_runtime/{safe_call_id}/metrics_projection.json"


def _pi_agent_runtime_owned_refs(call_id: str) -> set[str]:
    refs = _pi_agent_refs(call_id)
    return {
        refs["input"],
        refs["output"],
        refs["session"],
        refs["events"],
        refs["metrics"],
        refs["savepoints"],
        refs["report"],
        _piworker_call_result_ref(call_id),
    }


def _piworker_call_result_projection_payload(
    call_result: PiWorkerCallResult,
    *,
    source_call_result_ref: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": "missionforge.piworker_call_result_projection.v1",
        "call_id": call_result.call_id,
        "role": call_result.role.value,
        "contract_id": call_result.contract_id,
        "contract_hash": call_result.contract_hash,
        "contract_ref": call_result.contract_ref,
        "status": call_result.status.value,
        "source_call_result_ref": validate_ref(source_call_result_ref, "piworker_call_result_projection.source_call_result_ref"),
        "source_call_result_hash": stable_json_hash(call_result.to_dict()),
        "execution_report_ref": call_result.execution_report_ref,
        "output_refs": list(call_result.output_refs),
        "runtime_refs": list(call_result.runtime_refs),
        "evidence_refs": list(call_result.evidence_refs),
        "metric_refs": list(call_result.metric_refs),
        "validation_report_ref": call_result.validation_report_ref,
        "error_ref": call_result.error_ref,
    }
    return ensure_json_value(payload, "piworker_call_result_projection")


def _piworker_metrics_projection_payload(
    call_result: PiWorkerCallResult,
    report: ExecutionReport,
) -> dict[str, Any]:
    metrics = report.metrics
    payload = {
        "schema_version": "missionforge.piworker_metrics_projection.v1",
        "call_id": call_result.call_id,
        "role": call_result.role.value,
        "status": call_result.status.value,
        "execution_report_ref": call_result.execution_report_ref,
        "metric_refs": list(call_result.metric_refs),
        "duration_ms": _non_negative_metric(metrics, "duration_ms"),
        "returncode": _non_negative_metric(metrics, "returncode"),
        "timed_out": bool(metrics.get("timed_out", False)),
        "provider_mode": metrics.get("provider_mode"),
        "provider_config_source": metrics.get("provider_config_source"),
        "model": metrics.get("model"),
        "tool_call_count": _non_negative_metric(metrics, "tool_call_count"),
        "token_count": _non_negative_metric(metrics, "token_count", "total_tokens"),
        "total_tokens": _non_negative_metric(metrics, "total_tokens", "token_count"),
        "input_tokens": _non_negative_metric(metrics, "input_tokens"),
        "output_tokens": _non_negative_metric(metrics, "output_tokens"),
        "cache_read_tokens": _non_negative_metric(metrics, "cache_read_tokens"),
        "cache_write_tokens": _non_negative_metric(metrics, "cache_write_tokens"),
        "input_cost_usd": _non_negative_number_metric(metrics, "input_cost_usd"),
        "output_cost_usd": _non_negative_number_metric(metrics, "output_cost_usd"),
        "cache_read_cost_usd": _non_negative_number_metric(metrics, "cache_read_cost_usd"),
        "cache_write_cost_usd": _non_negative_number_metric(metrics, "cache_write_cost_usd"),
        "provider_reported_cost_usd": _non_negative_number_metric(metrics, "provider_reported_cost_usd"),
        "tool_error_count": _non_negative_metric(metrics, "tool_error_count"),
        "tool_latency_ms_total": _non_negative_metric(metrics, "tool_latency_ms_total"),
        "command_count": _non_negative_metric(metrics, "command_count"),
        "test_command_count": _non_negative_metric(metrics, "test_command_count"),
        "command_failure_count": _non_negative_metric(metrics, "command_failure_count"),
        "time_to_first_tool_ms": _non_negative_metric(metrics, "time_to_first_tool_ms"),
        "time_to_first_artifact_ms": _non_negative_metric(metrics, "time_to_first_artifact_ms"),
    }
    return ensure_json_value(payload, "piworker_metrics_projection")


def _judge_node_spec_payload(*, packet: JudgePacket, packet_ref: str, packet_hash: str) -> dict[str, Any]:
    return {
        "schema_version": "missionforge.pi_agent_judge_node_spec.v1",
        "role": "judge_piworker",
        "packet_ref": validate_ref(packet_ref, "judge_node_spec.packet_ref"),
        "packet_hash": packet_hash,
        "report_ref": packet.report_ref,
        "contract_ref": packet.contract_ref,
        "judge_rubric_ref": packet.judge_rubric_ref,
        "execution_packet_ref": packet.execution_packet_ref,
        "execution_report_ref": packet.execution_report_ref,
        "hard_check_status": packet.hard_check_status.value,
        "artifact_refs": list(packet.artifact_refs),
        "evidence_refs": list(packet.evidence_refs),
        "hard_check_refs": list(packet.hard_check_refs),
        "rules": [
            "Read the judge packet, judge rubric, execution report, hard checks, evidence refs, and artifact refs before deciding.",
            "Do not edit executor artifacts, contracts, packets, evidence refs, or hard-check refs.",
            "Write exactly one JudgeReport JSON object at report_ref.",
            "rationale_refs is for judge-authored rationale artifacts only; use [] if you do not write one.",
            "Do not put contract, rubric, packet, execution report, hard-check, evidence, or artifact refs in rationale_refs.",
            "If you write rationale, write it only to reports/judge_rationale.md.",
            "Use accepted only when execution and artifacts satisfy the judge rubric and hard_check_status is passed.",
            "Use rejected when execution or artifacts are not acceptable and no same-contract repair is appropriate.",
            "Use repair only for same-contract implementation gaps and include repair_brief_ref.",
            "Use revision_required only when the contract itself must change and include revision_request_ref.",
        ],
        "judge_authored_optional_refs": {
            "rationale_ref": "reports/judge_rationale.md",
            "repair_brief_ref": "projections/repair_brief.json",
            "revision_request_ref": "revisions/request.json",
        },
        "judge_report_schema": {
            "schema_version": "judge_report.v1",
            "role": "judge_piworker",
            "required_fields": [
                "report_id",
                "schema_version",
                "role",
                "packet_id",
                "packet_ref",
                "packet_hash",
                "contract_id",
                "contract_hash",
                "contract_ref",
                "decision",
                "hard_check_status",
                "rationale_refs",
                "evidence_refs",
                "accepted_artifact_refs",
            ],
        },
    }


def _agent_execution_status(status: str) -> AgentExecutionStatus:
    if status == "completed":
        return AgentExecutionStatus.COMPLETED
    if status == "blocked":
        return AgentExecutionStatus.BLOCKED
    return AgentExecutionStatus.FAILED


def _agent_node_workspace_root(workspace: object, *, fallback: str | Path) -> Path:
    active_workspace = getattr(workspace, "workspace", workspace)
    workspace_root_path = getattr(active_workspace, "workspace_root_path", None)
    if workspace_root_path is not None:
        return Path(workspace_root_path).resolve()
    return Path(fallback).resolve()


def _pi_agent_refs(call_id: str) -> dict[str, str]:
    safe_call_id = require_non_empty_str(call_id, "call_id")
    attempt_dir = f"attempts/{safe_call_id}"
    return {
        "attempt_dir": attempt_dir,
        "input": f"{attempt_dir}/pi_agent_input.json",
        "output": f"{attempt_dir}/pi_agent_output.json",
        "session": f"{attempt_dir}/pi_agent_session.jsonl",
        "events": f"{attempt_dir}/pi_agent_events.jsonl",
        "metrics": f"{attempt_dir}/pi_agent_metrics.json",
        "savepoints": f"{attempt_dir}/pi_agent_savepoints.jsonl",
        "workspace_policy": f"{attempt_dir}/runtime_workspace_policy.json",
        "permission_manifest": f"{attempt_dir}/runtime_permission_manifest.json",
        "sandbox_profile": f"{attempt_dir}/sandbox_profile.json",
        "workspace_view": f"{attempt_dir}/workspace_view",
        "report": f"{attempt_dir}/pi_agent_execution_report.json",
    }


def _reject_outputs_outside_scope(spec: PiAgentCallSpec) -> None:
    for output_ref in spec.expected_outputs:
        if not any(_is_within(output_ref, scope) for scope in spec.allowed_scope):
            raise ContractValidationError(f"PI Agent runtime output outside allowed scope: {output_ref}")


def _permission_manifest_payload(spec: PiAgentCallSpec, *, workspace_policy_ref: str | None = None) -> dict[str, Any]:
    readable_refs = _dedupe_refs([
        *spec.visible_refs,
        *spec.allowed_scope,
        *[_parent_ref(ref) for ref in spec.expected_outputs],
    ])
    return {
        "manifest_id": f"{spec.call_id}-pi-runtime-permissions",
        "schema_version": "permission_manifest.v1",
        "workspace_policy_ref": workspace_policy_ref,
        "readable_refs": readable_refs,
        "writable_refs": _dedupe_refs(list(spec.allowed_scope)),
        "denied_refs": [],
        "allowed_commands": [],
        "network_policy": "disabled",
        "env_allowlist": [],
        "secret_ref": None,
        "unsupported_hard_policies": [],
    }


def _runtime_workspace_policy_payload(spec: PiAgentCallSpec, refs: Mapping[str, str]) -> dict[str, Any]:
    return {
        "policy_id": f"{spec.call_id}-pi-runtime-workspace-policy",
        "schema_version": "workspace_policy.v1",
        "workspace_root_ref": validate_ref(refs["workspace_view"], "pi_agent_refs.workspace_view"),
        "input_refs": _dedupe_refs(list(spec.visible_refs)),
        "artifact_root_refs": _dedupe_refs(list(spec.allowed_scope)),
        "scratch_root_refs": [validate_ref(refs["attempt_dir"], "pi_agent_refs.attempt_dir")],
        "denied_refs": [],
    }


def _runtime_authority_payloads(
    call: PiWorkerCall,
    *,
    refs: Mapping[str, str],
    permission_manifest: Mapping[str, Any],
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = PermissionManifest.from_dict(permission_manifest)
    workspace_policy_ref = manifest.workspace_policy_ref or validate_ref(
        refs["workspace_policy"],
        "pi_agent_refs.workspace_policy",
    )
    permission_manifest_ref = validate_ref(refs["permission_manifest"], "pi_agent_refs.permission_manifest")
    sandbox_profile = SandboxProfile(
        profile_id=f"{call.call_id}-pi-runtime-sandbox",
        mode=SandboxMode.BUBBLEWRAP,
        workspace_root_ref=validate_ref(refs["workspace_view"], "pi_agent_refs.workspace_view"),
        readable_refs=list(manifest.readable_refs),
        writable_refs=list(manifest.writable_refs),
        denied_refs=list(manifest.denied_refs),
        network_enabled=manifest.network_policy.value == "enabled",
        env_allowlist=list(manifest.env_allowlist),
        command_allowlist=list(manifest.allowed_commands),
        resource_budget={"timeout_seconds": timeout_seconds},
    )
    now = datetime.now(timezone.utc)
    grant = create_capability_grant(
        grant_id=f"{call.call_id}-pi-runtime-grant",
        role=call.role.value,
        contract_hash=call.contract_hash,
        workspace_policy_ref=workspace_policy_ref,
        permission_manifest_ref=permission_manifest_ref,
        workspace_view_ref=sandbox_profile.workspace_root_ref,
        sandbox_profile_ref=validate_ref(refs["sandbox_profile"], "pi_agent_refs.sandbox_profile"),
        issued_by="missionforge.pi_agent_runtime_adapter",
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=max(timeout_seconds, 1) + 60)).isoformat(),
        metadata={
            "call_id": call.call_id,
            "runtime": "missionforge.pi_agent_runtime",
            "source_permission_manifest_ref": call.permission_manifest_ref,
        },
    )
    return grant.to_dict(), sandbox_profile.to_dict()


def _validate_runtime_authority(
    *,
    call: PiWorkerCall,
    permission_manifest: PermissionManifest,
    capability_grant: CapabilityGrant,
    sandbox_profile: SandboxProfile,
) -> None:
    if capability_grant.role != call.role.value:
        raise ContractValidationError("capability_grant.role must match PiWorkerCall role")
    if capability_grant.contract_hash != call.contract_hash:
        raise ContractValidationError("capability_grant.contract_hash must match PiWorkerCall contract_hash")
    if capability_grant.workspace_view_ref != sandbox_profile.workspace_root_ref:
        raise ContractValidationError("capability_grant.workspace_view_ref must match sandbox_profile.workspace_root_ref")
    if capability_grant.revoked_at is not None:
        raise ContractValidationError("capability_grant must not be revoked")
    if not capability_grant.is_active():
        raise ContractValidationError("capability_grant must be active")
    _require_same_refs(sandbox_profile.readable_refs, permission_manifest.readable_refs, "sandbox_profile.readable_refs")
    _require_same_refs(sandbox_profile.writable_refs, permission_manifest.writable_refs, "sandbox_profile.writable_refs")
    _require_same_refs(sandbox_profile.denied_refs, permission_manifest.denied_refs, "sandbox_profile.denied_refs")
    if sandbox_profile.command_allowlist != permission_manifest.allowed_commands:
        raise ContractValidationError("sandbox_profile.command_allowlist must match permission_manifest.allowed_commands")
    if sandbox_profile.env_allowlist != permission_manifest.env_allowlist:
        raise ContractValidationError("sandbox_profile.env_allowlist must match permission_manifest.env_allowlist")
    expected_network_enabled = permission_manifest.network_policy.value == "enabled"
    if sandbox_profile.network_enabled != expected_network_enabled:
        raise ContractValidationError("sandbox_profile.network_enabled must match permission_manifest.network_policy")


def _validate_call_spec_for_call(spec: PiAgentCallSpec, call: PiWorkerCall) -> None:
    if spec.call_id != call.call_id:
        raise ContractValidationError("pi_agent_call_spec id must match PiWorkerCall call_id")
    if spec.mission_id != call.contract_id:
        raise ContractValidationError("pi_agent_call_spec mission must match PiWorkerCall contract_id")
    expected_visible_refs = _dedupe_refs(
        [
            *call.visible_refs,
            *([call.permission_manifest_ref] if call.permission_manifest_ref else []),
        ]
    )
    _require_same_refs(spec.visible_refs, expected_visible_refs, "pi_agent_call_spec.visible_refs")
    _require_same_refs(spec.allowed_scope, call.writable_refs, "pi_agent_call_spec.allowed_scope")
    _require_same_refs(spec.expected_outputs, call.expected_output_refs, "pi_agent_call_spec.expected_outputs")


def _require_same_refs(actual: list[str], expected: list[str], field_name: str) -> None:
    _validate_ref_list(actual, field_name)
    _validate_ref_list(expected, field_name)
    if set(actual) != set(expected):
        raise ContractValidationError(f"{field_name} must match PiWorkerCall refs")


def _validate_ref_list(values: list[str], field_name: str) -> None:
    require_str_list(values, field_name)
    for ref in values:
        validate_ref(ref, f"{field_name}[]")


def _parent_ref(ref: str) -> str:
    safe_ref = validate_ref(ref, "ref")
    parts = safe_ref.split("/")
    if len(parts) == 1:
        return safe_ref
    return "/".join(parts[:-1])


def _is_within(ref: str, scope: str) -> bool:
    safe_ref = validate_ref(ref, "ref")
    safe_scope = validate_ref(scope, "scope")
    return safe_ref == safe_scope or safe_ref.startswith(f"{safe_scope}/")


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("PI Agent runtime ref escapes workspace")
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    compatible = ensure_json_value(dict(payload), "json_payload")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compatible, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _command_failure(command_result: PiAgentCommandResult, timeout_seconds: int) -> str | None:
    if command_result.timed_out:
        return f"pi-agent-runtime timed out after {timeout_seconds} seconds"
    if command_result.returncode != 0:
        return f"pi-agent-runtime exited with return code {command_result.returncode}"
    return None


def _reject_sensitive_runtime_metadata(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            normalized = key_text.lower().replace("-", "_")
            if normalized in {
                "api_key",
                "apikey",
                "authorization",
                "auth",
                "bearer",
                "token",
                "access_token",
                "refresh_token",
                "secret",
                "client_secret",
                "password",
            }:
                raise ContractValidationError(
                    f"PI Agent runtime metadata must not contain sensitive key {path}.{key_text}; "
                    "use child-process environment variables for secrets"
                )
            _reject_sensitive_runtime_metadata(nested, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_runtime_metadata(item, f"{path}[{index}]")


def _redacted_stream(text: str, env: Mapping[str, str]) -> str:
    redacted = _redact_sensitive_text(text, env)
    if len(redacted) <= MAX_CAPTURED_STREAM_CHARS:
        return redacted
    return redacted[:MAX_CAPTURED_STREAM_CHARS] + "\n[truncated]"


def _redact_sensitive_text(text: str, env: Mapping[str, str]) -> str:
    result = _process_output_text(text)
    for key, value in env.items():
        if _is_secret_name(key) and isinstance(value, str) and len(value) >= 4:
            result = result.replace(value, "<redacted>")
    result = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s'\"\\]+", r"\1<redacted>", result)
    result = re.sub(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,'\"\\]+", r"\1<redacted>", result)
    return result


def _prefixed_stream_lines(stream_name: str, text: str, env: Mapping[str, str]) -> list[str]:
    if not text:
        return [f"{stream_name}: <empty>"]
    return [f"{stream_name}: {line}" for line in _redacted_stream(text, env).splitlines()]


def _is_secret_name(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in ("api_key", "authorization", "password", "secret", "token"))


def _non_secret_env(env: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in env.items() if not _is_secret_name(key)}


def _has_secret_env(env: Mapping[str, str]) -> bool:
    return any(_is_secret_name(key) and bool(value) for key, value in env.items())


def _process_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _summarized_worker_claims(claims: Sequence[str]) -> list[str]:
    result: list[str] = []
    for claim in claims:
        match = SAFE_WORKER_CLAIM_RE.fullmatch(claim)
        if match and match.group(1) in SAFE_WORKER_CLAIM_NAMES:
            result.append(claim)
        else:
            result.append(f"worker_claim_present:length={len(claim.strip())}")
    return result


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _format_command(command: Sequence[str]) -> str:
    if not command:
        return "<pi-agent-runtime command>"
    return shlex.join(list(command))


def _non_negative_metric(metrics: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return 0


def _non_negative_number_metric(metrics: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return float(value)
    return 0.0


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, str) or not ref:
            continue
        if ref in seen:
            continue
        result.append(ref)
        seen.add(ref)
    return result
