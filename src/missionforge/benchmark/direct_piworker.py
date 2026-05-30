"""Benchmark-only Direct PiWorker baseline runner and collector."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping, Protocol, Sequence

from ..adapters.pi_agent_provider_config import resolve_pi_agent_provider_environment
from ..contracts import (
    ContractValidationError,
    ensure_json_value,
    require_int_at_least,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..json_store import JsonWorkspaceStore
from ..metrics import MetricEvent, MetricTrustLevel
from .contracts import (
    BenchmarkMode,
    BenchmarkStatus,
    BenchmarkSummary,
    BenchmarkTask,
    BenchmarkTrial,
)


DIRECT_PIWORKER_INPUT_SCHEMA_VERSION = "missionforge.pi_agent_direct_input.v1"
DIRECT_PIWORKER_OUTPUT_SCHEMA_VERSION = "missionforge.pi_agent_direct_output.v1"
DEFAULT_DIRECT_PIWORKER_TIMEOUT_SECONDS = 300
DIRECT_PIWORKER_PROVIDER_MODES = {"faux", "live"}
DIRECT_PIWORKER_PROVIDER_CONFIG_SOURCES = {"env", "codex_current", "explicit"}
DIRECT_PIWORKER_STATUSES = {"completed", "failed", "blocked", "cancelled"}
MAX_CAPTURED_STREAM_CHARS = 4000


@dataclass(frozen=True)
class DirectPiWorkerConfig:
    """Configuration for the benchmark-only Direct PiWorker baseline."""

    command: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_DIRECT_PIWORKER_TIMEOUT_SECONDS
    provider_mode: str = "faux"
    provider_config_source: str = "env"
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        command = self.command or default_direct_piworker_command()
        object.__setattr__(self, "command", tuple(command))
        if not self.command:
            raise ContractValidationError("direct_piworker_config.command must not be empty")
        for part in self.command:
            if not isinstance(part, str) or not part or "\x00" in part:
                raise ContractValidationError("direct_piworker_config.command must contain non-empty strings without NUL bytes")
        require_int_at_least(self.timeout_seconds, "direct_piworker_config.timeout_seconds", 1)
        if self.provider_mode not in DIRECT_PIWORKER_PROVIDER_MODES:
            raise ContractValidationError(
                f"direct_piworker_config.provider_mode must be one of {sorted(DIRECT_PIWORKER_PROVIDER_MODES)}"
            )
        if self.provider_config_source not in DIRECT_PIWORKER_PROVIDER_CONFIG_SOURCES:
            raise ContractValidationError(
                "direct_piworker_config.provider_config_source must be one of "
                f"{sorted(DIRECT_PIWORKER_PROVIDER_CONFIG_SOURCES)}"
            )
        if self.model is not None:
            require_non_empty_str(self.model, "direct_piworker_config.model")
        metadata = ensure_json_value(require_mapping(self.metadata, "direct_piworker_config.metadata"), "direct_piworker_config.metadata")
        _reject_sensitive_metadata(metadata)


@dataclass(frozen=True)
class DirectPiWorkerCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class DirectPiWorkerCommandRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        input_path: Path,
        cwd: Path,
        timeout_seconds: int,
        env: Mapping[str, str],
    ) -> DirectPiWorkerCommandResult:
        """Run the Direct PiWorker benchmark process."""


class SubprocessDirectPiWorkerCommandRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        input_path: Path,
        cwd: Path,
        timeout_seconds: int,
        env: Mapping[str, str],
    ) -> DirectPiWorkerCommandResult:
        child_env = dict(os.environ)
        child_env.update(dict(env))
        build_failure = _prepare_default_direct_command(command, timeout_seconds=timeout_seconds, env=child_env)
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
            return DirectPiWorkerCommandResult(
                returncode=-1,
                stdout=_process_output_text(exc.stdout),
                stderr=_process_output_text(exc.stderr),
                timed_out=True,
            )
        return DirectPiWorkerCommandResult(
            returncode=completed.returncode,
            stdout=_process_output_text(completed.stdout),
            stderr=_process_output_text(completed.stderr),
        )


@dataclass(frozen=True)
class DirectPiWorkerRunResult:
    benchmark_run_id: str
    task_id: str
    seed: int
    status: str
    workspace_ref: str
    produced_artifacts: list[str] = field(default_factory=list)
    changed_refs: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    worker_claims: list[str] = field(default_factory=list)
    input_ref: str = ""
    output_ref: str = ""
    session_ref: str = ""
    events_ref: str = ""
    metrics_ref: str = ""
    duration_ms: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        default_benchmark_run_id: str,
        default_task_id: str,
        default_seed: int,
        default_input_ref: str,
        default_workspace_ref: str,
        default_duration_ms: int,
    ) -> "DirectPiWorkerRunResult":
        data = require_mapping(payload, "direct_piworker_run_result")
        if data.get("schema_version") != DIRECT_PIWORKER_OUTPUT_SCHEMA_VERSION:
            raise ContractValidationError("direct_piworker_run_result.schema_version is unsupported")
        result = cls(
            benchmark_run_id=require_non_empty_str(
                data.get("benchmark_run_id") or default_benchmark_run_id,
                "direct_piworker_run_result.benchmark_run_id",
            ),
            task_id=require_non_empty_str(data.get("task_id") or default_task_id, "direct_piworker_run_result.task_id"),
            seed=require_int_at_least(data.get("seed", default_seed), "direct_piworker_run_result.seed", 0),
            status=require_non_empty_str(data.get("status", "failed"), "direct_piworker_run_result.status"),
            workspace_ref=validate_ref(
                data.get("workspace_ref") or default_workspace_ref,
                "direct_piworker_run_result.workspace_ref",
            ),
            produced_artifacts=require_str_list(
                data.get("produced_artifacts", []),
                "direct_piworker_run_result.produced_artifacts",
            ),
            changed_refs=require_str_list(data.get("changed_refs", []), "direct_piworker_run_result.changed_refs"),
            failures=require_str_list(data.get("failures", []), "direct_piworker_run_result.failures"),
            worker_claims=require_str_list(data.get("worker_claims", []), "direct_piworker_run_result.worker_claims"),
            input_ref=validate_ref(data.get("input_ref") or default_input_ref, "direct_piworker_run_result.input_ref"),
            output_ref=validate_ref(data.get("output_ref"), "direct_piworker_run_result.output_ref"),
            session_ref=validate_ref(data.get("session_ref"), "direct_piworker_run_result.session_ref"),
            events_ref=validate_ref(data.get("events_ref"), "direct_piworker_run_result.events_ref"),
            metrics_ref=validate_ref(data.get("metrics_ref"), "direct_piworker_run_result.metrics_ref"),
            duration_ms=require_int_at_least(
                data.get("duration_ms", default_duration_ms),
                "direct_piworker_run_result.duration_ms",
                0,
            ),
            metrics=ensure_json_value(
                require_mapping(data.get("metrics", {}), "direct_piworker_run_result.metrics"),
                "direct_piworker_run_result.metrics",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.benchmark_run_id, "direct_piworker_run_result.benchmark_run_id")
        require_non_empty_str(self.task_id, "direct_piworker_run_result.task_id")
        require_int_at_least(self.seed, "direct_piworker_run_result.seed", 0)
        if self.status not in DIRECT_PIWORKER_STATUSES:
            raise ContractValidationError(
                f"direct_piworker_run_result.status must be one of {sorted(DIRECT_PIWORKER_STATUSES)}"
            )
        validate_ref(self.workspace_ref, "direct_piworker_run_result.workspace_ref")
        for field_name in ("produced_artifacts", "changed_refs"):
            for ref in getattr(self, field_name):
                validate_ref(ref, f"direct_piworker_run_result.{field_name}[]")
        for field_name in ("input_ref", "output_ref", "session_ref", "events_ref", "metrics_ref"):
            validate_ref(getattr(self, field_name), f"direct_piworker_run_result.{field_name}")
        for field_name in ("failures", "worker_claims"):
            require_str_list(getattr(self, field_name), f"direct_piworker_run_result.{field_name}")
        require_int_at_least(self.duration_ms, "direct_piworker_run_result.duration_ms", 0)
        ensure_json_value(require_mapping(self.metrics, "direct_piworker_run_result.metrics"), "direct_piworker_run_result.metrics")


@dataclass(frozen=True)
class DirectPiWorkerTrialRecord:
    """Refs written by one Direct PiWorker benchmark trial."""

    trial: BenchmarkTrial
    summary: BenchmarkSummary
    metric_event: MetricEvent
    run_result: DirectPiWorkerRunResult
    trial_ref: str
    summary_ref: str
    metric_events_ref: str
    review_packet_ref: str
    direct_input_ref: str
    direct_output_ref: str


class DirectPiWorkerBenchmarkRunner:
    """Run and collect a Direct PiWorker benchmark trial."""

    def __init__(
        self,
        config: DirectPiWorkerConfig | None = None,
        *,
        runner: DirectPiWorkerCommandRunner | None = None,
        environ: Mapping[str, str] | None = None,
        codex_home: str | Path | None = None,
    ) -> None:
        self.config = config or DirectPiWorkerConfig()
        self.runner = runner or SubprocessDirectPiWorkerCommandRunner()
        self.environ = dict(environ) if environ is not None else None
        self.codex_home = codex_home

    def run_trial(
        self,
        *,
        benchmark_run_id: str,
        task: BenchmarkTask,
        seed: int,
        workspace: str | Path = ".",
        started_at: str = "1970-01-01T00:00:00Z",
        completed_at: str = "1970-01-01T00:00:00Z",
    ) -> DirectPiWorkerTrialRecord:
        run_id = _require_id(benchmark_run_id, "direct_piworker.benchmark_run_id")
        require_int_at_least(seed, "direct_piworker.seed", 0)
        task.validate()
        if not task.expected_output_refs:
            raise ContractValidationError("direct_piworker task requires at least one expected output ref")
        root = Path(workspace).resolve()
        root.mkdir(parents=True, exist_ok=True)
        store = JsonWorkspaceStore(root)
        refs = _direct_refs(run_id=run_id, task_id=task.task_id, seed=seed)
        _resolve_workspace_ref(root, refs["workspace"]).mkdir(parents=True, exist_ok=True)
        provider_env = resolve_pi_agent_provider_environment(
            provider_mode=self.config.provider_mode,
            provider_config_source=self.config.provider_config_source,
            model=self.config.model,
            metadata=self.config.metadata,
            environ=self.environ,
            codex_home=self.codex_home,
        )

        input_payload = self._build_input_payload(task=task, seed=seed, refs=refs, run_id=run_id)
        input_path = _resolve_workspace_ref(root, refs["input"])
        _write_json(input_path, input_payload)

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
            run_id=run_id,
            task=task,
            seed=seed,
            refs=refs,
            duration_ms=duration_ms,
            command_result=command_result,
            env=provider_env.env,
        )
        run_result = self._enforce_output_contract(root=root, run_id=run_id, task=task, seed=seed, refs=refs, result=run_result)
        summary = _summary_from_direct_result(task=task, seed=seed, result=run_result, metric_events_ref=refs["metric_events"])
        metric_event = MetricEvent(
            metric_id=f"BM-{task.task_id}-{BenchmarkMode.DIRECT_PIWORKER_CHAT.value}-seed-{seed:04d}",
            mission_run_id=run_id,
            namespace="missionforge.harness",
            source_ref=refs["summary"],
            run_ref=refs["trial"],
            metric_kind="summary",
            values=summary.metric_values(),
            trust_level=MetricTrustLevel.OPERATOR_DIAGNOSTIC.value,
            tags=["benchmark", BenchmarkMode.DIRECT_PIWORKER_CHAT.value],
        )
        metric_event.validate()
        trial = BenchmarkTrial(
            benchmark_run_id=run_id,
            task_id=task.task_id,
            mode=BenchmarkMode.DIRECT_PIWORKER_CHAT,
            seed=seed,
            workspace_ref=refs["workspace"],
            started_at=started_at,
            completed_at=completed_at,
            status=BenchmarkStatus.ACCEPTED if summary.accepted else summary.status,
            artifact_refs=list(summary.artifact_refs),
            metric_events_ref=refs["metric_events"],
            summary_ref=refs["summary"],
            review_packet_ref=refs["review_packet"],
        )
        trial.validate()
        store.write_json(refs["trial"], trial.to_dict())
        store.write_json(refs["summary"], summary.to_dict())
        store.write_jsonl(refs["metric_events"], [metric_event.to_dict()])
        store.write_json(
            refs["review_packet"],
            {
                "schema_version": "missionforge.benchmark_review_packet.v1",
                "task_id": task.task_id,
                "seed": seed,
                "artifact_refs": list(summary.artifact_refs),
                "summary_ref": refs["summary"],
                "metric_events_ref": refs["metric_events"],
                "direct_output_ref": refs["output"],
                "events_ref": refs["events"],
                "metrics_ref": refs["metrics"],
                "session_ref": refs["session"],
            },
        )
        return DirectPiWorkerTrialRecord(
            trial=trial,
            summary=summary,
            metric_event=metric_event,
            run_result=run_result,
            trial_ref=refs["trial"],
            summary_ref=refs["summary"],
            metric_events_ref=refs["metric_events"],
            review_packet_ref=refs["review_packet"],
            direct_input_ref=refs["input"],
            direct_output_ref=refs["output"],
        )

    def _build_input_payload(
        self,
        *,
        task: BenchmarkTask,
        seed: int,
        refs: Mapping[str, str],
        run_id: str,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": DIRECT_PIWORKER_INPUT_SCHEMA_VERSION,
            "benchmark_run_id": run_id,
            "task_id": task.task_id,
            "seed": seed,
            "workspace_root": ".",
            "workspace_ref": refs["workspace"],
            "input_ref": refs["input"],
            "output_ref": refs["output"],
            "session_ref": refs["session"],
            "events_ref": refs["events"],
            "metrics_ref": refs["metrics"],
            "initial_user_text_ref": task.initial_user_text_ref,
            "allowed_source_refs": list(task.allowed_source_refs),
            "expected_output_refs": list(task.expected_output_refs),
            "runtime": {
                "runtime_name": "missionforge.pi_agent_direct_benchmark",
                "timeout_seconds": self.config.timeout_seconds,
                "model": self.config.model,
                "metadata": ensure_json_value(dict(self.config.metadata), "direct_piworker_config.metadata"),
            },
        }
        return ensure_json_value(payload, "direct_piworker_input")

    def _load_or_failure_result(
        self,
        *,
        root: Path,
        run_id: str,
        task: BenchmarkTask,
        seed: int,
        refs: Mapping[str, str],
        duration_ms: int,
        command_result: DirectPiWorkerCommandResult,
        env: Mapping[str, str],
    ) -> DirectPiWorkerRunResult:
        output_path = _resolve_workspace_ref(root, refs["output"])
        if not output_path.is_file():
            return _write_failure_result(
                output_path,
                run_id=run_id,
                task=task,
                seed=seed,
                refs=refs,
                duration_ms=duration_ms,
                command_result=command_result,
                env=env,
                failure=_command_failure(command_result, self.config.timeout_seconds)
                or f"direct piworker output artifact is missing: {refs['output']}",
            )
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ContractValidationError("direct piworker output artifact must be a JSON object")
            result = DirectPiWorkerRunResult.from_dict(
                payload,
                default_benchmark_run_id=run_id,
                default_task_id=task.task_id,
                default_seed=seed,
                default_input_ref=refs["input"],
                default_workspace_ref=refs["workspace"],
                default_duration_ms=duration_ms,
            )
        except Exception as exc:
            return _write_failure_result(
                output_path,
                run_id=run_id,
                task=task,
                seed=seed,
                refs=refs,
                duration_ms=duration_ms,
                command_result=command_result,
                env=env,
                failure=f"direct piworker output artifact is invalid: {exc}",
            )
        failure = _command_failure(command_result, self.config.timeout_seconds)
        if failure is not None and result.status == "completed":
            return _rewrite_failure_result(root, run_id=run_id, task=task, seed=seed, refs=refs, result=result, failure=failure)
        return result

    def _enforce_output_contract(
        self,
        *,
        root: Path,
        run_id: str,
        task: BenchmarkTask,
        seed: int,
        refs: Mapping[str, str],
        result: DirectPiWorkerRunResult,
    ) -> DirectPiWorkerRunResult:
        if result.benchmark_run_id != run_id:
            return _rewrite_failure_result(root, run_id=run_id, task=task, seed=seed, refs=refs, result=result, failure="direct piworker output benchmark_run_id mismatch")
        if result.task_id != task.task_id:
            return _rewrite_failure_result(root, run_id=run_id, task=task, seed=seed, refs=refs, result=result, failure="direct piworker output task_id mismatch")
        if result.seed != seed:
            return _rewrite_failure_result(root, run_id=run_id, task=task, seed=seed, refs=refs, result=result, failure="direct piworker output seed mismatch")
        missing_outputs = [ref for ref in task.expected_output_refs if ref not in result.produced_artifacts]
        missing_files = [
            ref
            for ref in result.produced_artifacts
            if not _resolve_workspace_ref(root, _join_ref(refs["workspace"], ref)).is_file()
        ]
        if result.status == "completed" and (missing_outputs or missing_files):
            failures = [f"expected output was not produced: {ref}" for ref in missing_outputs]
            failures.extend(f"produced artifact is missing on disk: {ref}" for ref in missing_files)
            return _rewrite_failure_result(root, run_id=run_id, task=task, seed=seed, refs=refs, result=result, failure="; ".join(failures))
        return result


def default_direct_piworker_command() -> tuple[str, ...]:
    direct_main = Path(__file__).resolve().parents[3] / "workers" / "pi-agent-runtime" / "dist" / "direct-main.js"
    return ("node", str(direct_main))


def _summary_from_direct_result(
    *,
    task: BenchmarkTask,
    seed: int,
    result: DirectPiWorkerRunResult,
    metric_events_ref: str,
) -> BenchmarkSummary:
    accepted = result.status == "completed" and all(ref in result.produced_artifacts for ref in task.expected_output_refs)
    failure_taxonomy: list[str] = []
    if not accepted:
        failure_taxonomy.append("direct_piworker_failed")
        if any("expected output was not produced" in failure for failure in result.failures):
            failure_taxonomy.append("missing_expected_output")
    duration_ms = result.duration_ms
    return BenchmarkSummary(
        task_id=task.task_id,
        mode=BenchmarkMode.DIRECT_PIWORKER_CHAT,
        seed=seed,
        accepted=accepted,
        status=BenchmarkStatus.ACCEPTED if accepted else BenchmarkStatus.FAILED,
        comparable=True,
        hidden_acceptance_passed=False,
        time_to_first_artifact_ms=_non_negative_metric(result.metrics, "time_to_first_artifact_ms"),
        time_to_accepted_deliverable_ms=duration_ms if accepted else 0,
        wall_duration_ms=duration_ms,
        estimated_cost_usd=_non_negative_number_metric(result.metrics, "provider_reported_cost_usd"),
        provider_reported_cost_usd=_non_negative_number_metric(result.metrics, "provider_reported_cost_usd"),
        total_tokens=_non_negative_metric(result.metrics, "total_tokens", "token_count"),
        input_tokens=_non_negative_metric(result.metrics, "input_tokens"),
        output_tokens=_non_negative_metric(result.metrics, "output_tokens"),
        cache_read_tokens=_non_negative_metric(result.metrics, "cache_read_tokens"),
        cache_write_tokens=_non_negative_metric(result.metrics, "cache_write_tokens"),
        tool_call_count=_non_negative_metric(result.metrics, "tool_call_count"),
        repair_count=0,
        user_turn_count=1,
        clarification_turn_count=0,
        privacy_violation_count=0,
        boundary_violation_count=0,
        defect_leakage_count=0,
        failure_taxonomy=failure_taxonomy,
        artifact_refs=[_join_ref(result.workspace_ref, ref) for ref in result.produced_artifacts],
        metric_events_ref=metric_events_ref,
    )


def _direct_refs(*, run_id: str, task_id: str, seed: int) -> dict[str, str]:
    if seed < 0:
        raise ContractValidationError("direct_piworker.seed must be >= 0")
    root = f"benchmarks/runs/{run_id}/trials/{task_id}/{BenchmarkMode.DIRECT_PIWORKER_CHAT.value}/seed-{seed}"
    return {
        "root": root,
        "workspace": f"{root}/workspace",
        "input": f"{root}/direct_piworker_input.json",
        "output": f"{root}/direct_piworker_output.json",
        "session": f"{root}/direct_piworker_session.jsonl",
        "events": f"{root}/direct_piworker_events.jsonl",
        "metrics": f"{root}/direct_piworker_metrics.json",
        "trial": f"{root}/trial.json",
        "summary": f"{root}/summary.json",
        "metric_events": f"{root}/metric_events.jsonl",
        "review_packet": f"{root}/review_packet.json",
    }


def _prepare_default_direct_command(
    command: Sequence[str],
    *,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> DirectPiWorkerCommandResult | None:
    if len(command) < 2 or command[0] != "node":
        return None
    main_path = Path(command[1])
    if main_path.name != "direct-main.js" or main_path.parent.name != "dist":
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
) -> DirectPiWorkerCommandResult:
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
        return DirectPiWorkerCommandResult(
            returncode=-1,
            stdout=_process_output_text(exc.stdout),
            stderr=_process_output_text(exc.stderr),
            timed_out=True,
        )
    except OSError as exc:
        return DirectPiWorkerCommandResult(returncode=-1, stderr=str(exc))
    return DirectPiWorkerCommandResult(
        returncode=completed.returncode,
        stdout=_process_output_text(completed.stdout),
        stderr=_process_output_text(completed.stderr),
    )


def _write_failure_result(
    output_path: Path,
    *,
    run_id: str,
    task: BenchmarkTask,
    seed: int,
    refs: Mapping[str, str],
    duration_ms: int,
    command_result: DirectPiWorkerCommandResult,
    env: Mapping[str, str],
    failure: str,
) -> DirectPiWorkerRunResult:
    payload = _failure_payload(
        run_id=run_id,
        task=task,
        seed=seed,
        refs=refs,
        duration_ms=duration_ms,
        command_result=command_result,
        env=env,
        failures=[failure],
    )
    _write_json(output_path, payload)
    return DirectPiWorkerRunResult.from_dict(
        payload,
        default_benchmark_run_id=run_id,
        default_task_id=task.task_id,
        default_seed=seed,
        default_input_ref=refs["input"],
        default_workspace_ref=refs["workspace"],
        default_duration_ms=duration_ms,
    )


def _rewrite_failure_result(
    root: Path,
    *,
    run_id: str,
    task: BenchmarkTask,
    seed: int,
    refs: Mapping[str, str],
    result: DirectPiWorkerRunResult,
    failure: str,
) -> DirectPiWorkerRunResult:
    payload = {
        "schema_version": DIRECT_PIWORKER_OUTPUT_SCHEMA_VERSION,
        "benchmark_run_id": run_id,
        "task_id": task.task_id,
        "seed": seed,
        "status": "failed",
        "workspace_ref": refs["workspace"],
        "produced_artifacts": list(result.produced_artifacts),
        "changed_refs": list(result.changed_refs),
        "failures": _dedupe([*result.failures, failure]),
        "worker_claims": list(result.worker_claims),
        "input_ref": refs["input"],
        "output_ref": refs["output"],
        "session_ref": refs["session"],
        "events_ref": refs["events"],
        "metrics_ref": refs["metrics"],
        "duration_ms": result.duration_ms,
        "metrics": dict(result.metrics),
    }
    output_path = _resolve_workspace_ref(root, refs["output"])
    _write_json(output_path, payload)
    return DirectPiWorkerRunResult.from_dict(
        payload,
        default_benchmark_run_id=run_id,
        default_task_id=task.task_id,
        default_seed=seed,
        default_input_ref=refs["input"],
        default_workspace_ref=refs["workspace"],
        default_duration_ms=result.duration_ms,
    )


def _failure_payload(
    *,
    run_id: str,
    task: BenchmarkTask,
    seed: int,
    refs: Mapping[str, str],
    duration_ms: int,
    command_result: DirectPiWorkerCommandResult,
    env: Mapping[str, str],
    failures: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": DIRECT_PIWORKER_OUTPUT_SCHEMA_VERSION,
        "benchmark_run_id": run_id,
        "task_id": task.task_id,
        "seed": seed,
        "status": "failed",
        "workspace_ref": refs["workspace"],
        "produced_artifacts": [],
        "changed_refs": [],
        "failures": [*_redacted_failures(failures, env), *_stream_presence_failures(command_result)],
        "worker_claims": [],
        "input_ref": refs["input"],
        "output_ref": refs["output"],
        "session_ref": refs["session"],
        "events_ref": refs["events"],
        "metrics_ref": refs["metrics"],
        "duration_ms": duration_ms,
        "metrics": {
            "duration_ms": duration_ms,
            "returncode": command_result.returncode,
            "timed_out": command_result.timed_out,
        },
    }


def _command_failure(command_result: DirectPiWorkerCommandResult, timeout_seconds: int) -> str | None:
    if command_result.timed_out:
        return f"direct piworker timed out after {timeout_seconds} seconds"
    if command_result.returncode != 0:
        return f"direct piworker exited with return code {command_result.returncode}"
    return None


def _stream_presence_failures(command_result: DirectPiWorkerCommandResult) -> list[str]:
    result: list[str] = []
    if command_result.stdout:
        result.append(f"stdout: <captured {len(command_result.stdout[:MAX_CAPTURED_STREAM_CHARS])} chars>")
    if command_result.stderr:
        result.append(f"stderr: <captured {len(command_result.stderr[:MAX_CAPTURED_STREAM_CHARS])} chars>")
    return result


def _redacted_failures(failures: list[str], env: Mapping[str, str]) -> list[str]:
    return [_redact_sensitive_text(failure, env) for failure in failures]


def _redact_sensitive_text(text: str, env: Mapping[str, str]) -> str:
    result = _process_output_text(text)
    for key, value in env.items():
        if _is_secret_name(key) and isinstance(value, str) and len(value) >= 4:
            result = result.replace(value, "<redacted>")
    return result


def _reject_sensitive_metadata(value: Any, path: str = "metadata") -> None:
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
                    f"Direct PiWorker metadata must not contain sensitive key {path}.{key_text}; "
                    "use child-process environment variables for secrets"
                )
            _reject_sensitive_metadata(nested, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_metadata(item, f"{path}[{index}]")


def _require_id(value: Any, field_name: str) -> str:
    text = require_non_empty_str(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise ContractValidationError(f"{field_name} must be a safe id, not a path")
    validate_ref(text, field_name)
    return text


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("Direct PiWorker ref escapes workspace")
    return path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    compatible = ensure_json_value(dict(payload), "json_payload")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compatible, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _join_ref(prefix: str, ref: str) -> str:
    safe_prefix = validate_ref(prefix, "ref_prefix")
    safe_ref = validate_ref(ref, "ref")
    return f"{safe_prefix.rstrip('/')}/{safe_ref.lstrip('/')}" if safe_prefix else safe_ref


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


def _is_secret_name(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in ("api_key", "authorization", "password", "secret", "token"))


def _process_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _dedupe(refs: list[str]) -> list[str]:
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
