"""Packaged PI Agent runtime discovery and preflight checks.

MissionForge ships the PiAgent execution surface with the Python package, but
runtime preparation must stay explicit and writable-location scoped. Importing
MissionForge must never run npm, create caches, or mutate the caller's cwd.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from .contracts import ContractValidationError, require_non_empty_str


PI_AGENT_RUNTIME_VERSION = "0.1.0"
PI_AGENT_RUNTIME_ENV = "MISSIONFORGE_PI_AGENT_RUNTIME"
PI_AGENT_RUNTIME_HOME_ENV = "MISSIONFORGE_RUNTIME_HOME"
PI_AGENT_RUNTIME_CACHE_ENV = "MISSIONFORGE_PI_AGENT_RUNTIME_CACHE"
PI_AGENT_RUNTIME_NODE_ENV = "MISSIONFORGE_NODE"
PI_AGENT_RUNTIME_NPM_ENV = "MISSIONFORGE_NPM"
PI_AGENT_RUNTIME_BWRAP_ENV = "MISSIONFORGE_BWRAP_PATH"


class PiAgentRuntimeCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PiAgentRuntimeOptions:
    """Opaque options for the package-provided PiAgent PiWorker runtime."""

    command: Sequence[str] = ()
    timeout_seconds: int = 300
    provider_mode: str = "faux"
    provider_config_source: str = "codex_current"
    runtime_name: str = "missionforge.pi_agent_runtime"
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    repair_mode: str = "none"
    verifier_failures: Sequence[str] = ()
    failed_constraints: Sequence[str] = ()
    previous_output_ref: str | None = None
    repair_prompt: str | None = None
    resume_mode: str = "none"
    resume_boundary: str | None = None
    resume_savepoint_ref: str | None = None
    resume_session_ref: str | None = None
    resume_events_ref: str | None = None
    resume_checkpoint_refs: Sequence[str] = ()
    resume_summary_artifact_refs: Sequence[str] = ()
    resume_prompt: str | None = None
    context_large_observation_bytes: int = 8 * 1024
    context_soft_compact_ratio: float = 0.8
    context_hard_compact_ratio: float = 0.9
    context_cache_aware: bool = True
    long_memory_packet_ref: str | None = None

    def to_adapter_kwargs(self) -> dict[str, Any]:
        """Return constructor kwargs for the default adapter's internal config."""

        return {
            "command": tuple(self.command),
            "timeout_seconds": self.timeout_seconds,
            "provider_mode": self.provider_mode,
            "provider_config_source": self.provider_config_source,
            "runtime_name": self.runtime_name,
            "model": self.model,
            "metadata": dict(self.metadata),
            "repair_mode": self.repair_mode,
            "verifier_failures": tuple(self.verifier_failures),
            "failed_constraints": tuple(self.failed_constraints),
            "previous_output_ref": self.previous_output_ref,
            "repair_prompt": self.repair_prompt,
            "resume_mode": self.resume_mode,
            "resume_boundary": self.resume_boundary,
            "resume_savepoint_ref": self.resume_savepoint_ref,
            "resume_session_ref": self.resume_session_ref,
            "resume_events_ref": self.resume_events_ref,
            "resume_checkpoint_refs": tuple(self.resume_checkpoint_refs),
            "resume_summary_artifact_refs": tuple(self.resume_summary_artifact_refs),
            "resume_prompt": self.resume_prompt,
            "context_large_observation_bytes": self.context_large_observation_bytes,
            "context_soft_compact_ratio": self.context_soft_compact_ratio,
            "context_hard_compact_ratio": self.context_hard_compact_ratio,
            "context_cache_aware": self.context_cache_aware,
            "long_memory_packet_ref": self.long_memory_packet_ref,
        }


def create_piagent_runtime_config(**kwargs: object) -> PiAgentRuntimeOptions:
    """Create opaque options for MissionForge's default PiAgent runtime."""

    return PiAgentRuntimeOptions(**kwargs)


@dataclass(frozen=True)
class PiAgentRuntimeCapability:
    """One host capability required by a runtime feature."""

    name: str
    status: PiAgentRuntimeCapabilityStatus
    detail: str
    path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "path": self.path,
        }


@dataclass(frozen=True)
class PiAgentRuntimePreflightReport:
    """Host readiness report for the bundled PiAgent runtime."""

    runtime_dir: Path
    command: tuple[str, ...]
    capabilities: tuple[PiAgentRuntimeCapability, ...]
    sandbox_linux_enabled: bool
    platform_system: str = field(default_factory=platform.system)
    runtime_version: str = PI_AGENT_RUNTIME_VERSION

    @property
    def available(self) -> bool:
        return all(item.status == PiAgentRuntimeCapabilityStatus.AVAILABLE for item in self.capabilities)

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(
            f"{item.name}: {item.detail}"
            for item in self.capabilities
            if item.status == PiAgentRuntimeCapabilityStatus.UNAVAILABLE
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "runtime_version": self.runtime_version,
            "runtime_dir": str(self.runtime_dir),
            "command": list(self.command),
            "platform_system": self.platform_system,
            "sandbox_linux_enabled": self.sandbox_linux_enabled,
            "available": self.available,
            "capabilities": [item.to_dict() for item in self.capabilities],
            "failures": list(self.failures),
        }


def default_pi_agent_runtime_command(*, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return the package-provided default runtime command.

    The path may point to a development checkout, an explicit runtime override,
    or the package asset tree. It does not create runtime caches.
    """

    runtime_dir = find_pi_agent_runtime_dir(env=env)
    return (node_executable(env=env), str(runtime_dir / "dist" / "main.js"))


def find_pi_agent_runtime_dir(*, env: Mapping[str, str] | None = None) -> Path:
    """Find the best available PI Agent runtime asset directory."""

    effective_env = env or os.environ
    override = effective_env.get(PI_AGENT_RUNTIME_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        _validate_runtime_asset_dir(path, source=PI_AGENT_RUNTIME_ENV)
        return path

    development_runtime = Path(__file__).resolve().parents[2] / "workers" / "pi-agent-runtime"
    if _is_runtime_asset_dir(development_runtime):
        return development_runtime

    bundled_runtime = Path(__file__).resolve().parent / "_bundled" / "pi_agent_runtime"
    _validate_runtime_asset_dir(bundled_runtime, source="missionforge package")
    return bundled_runtime


def prepare_pi_agent_runtime(
    runtime_dir: str | Path,
    *,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int = 300,
) -> PiAgentRuntimePreflightReport:
    """Ensure the runtime can be executed from a writable runtime home.

    Development checkouts can run in place. Package assets are copied to a
    MissionForge-owned cache before npm installs dependencies so site-packages
    stays immutable and user cwd stays untouched.
    """

    effective_env = dict(os.environ)
    if env is not None:
        effective_env.update(dict(env))
    source_dir = Path(runtime_dir).expanduser().resolve()
    _validate_runtime_asset_dir(source_dir, source="pi_agent_runtime")
    target_dir = _materialized_runtime_dir(source_dir, env=effective_env)
    if target_dir != source_dir:
        _copy_runtime_assets(source_dir, target_dir)
    if not _has_node_modules(target_dir):
        npm = npm_executable(env=effective_env)
        if npm is None:
            return _with_failure(
                preflight_pi_agent_runtime(target_dir, env=effective_env),
                PiAgentRuntimeCapability(
                    name="npm",
                    status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
                    detail="npm is required to install bundled PiAgent runtime dependencies",
                    path=None,
                ),
            )
        install = _run_setup_command(
            (npm, "ci", "--ignore-scripts"),
            cwd=target_dir,
            timeout_seconds=timeout_seconds,
            env=effective_env,
        )
        if install.returncode != 0 or install.timed_out:
            return _with_failure(
                preflight_pi_agent_runtime(target_dir, env=effective_env),
                PiAgentRuntimeCapability(
                    name="npm_ci",
                    status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
                    detail=_setup_failure_detail("npm ci --ignore-scripts", install),
                    path=npm,
                ),
            )
    if not (target_dir / "dist" / "main.js").is_file():
        report = preflight_pi_agent_runtime(target_dir, env=effective_env)
        npm = npm_executable(env=effective_env)
        if npm is None:
            return _with_failure(
                report,
                PiAgentRuntimeCapability(
                    name="npm",
                    status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
                    detail="npm is required to build bundled PiAgent runtime assets",
                    path=None,
                ),
            )
        build = _run_setup_command(
            (npm, "run", "build"),
            cwd=target_dir,
            timeout_seconds=timeout_seconds,
            env=effective_env,
        )
        if build.returncode != 0 or build.timed_out:
            return _with_failure(
                report,
                PiAgentRuntimeCapability(
                    name="npm_build",
                    status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
                    detail=_setup_failure_detail("npm run build", build),
                    path=npm,
                ),
            )
    return preflight_pi_agent_runtime(target_dir, env=effective_env)


def prepared_pi_agent_runtime_command(
    runtime_dir: str | Path,
    *,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int = 300,
) -> tuple[tuple[str, ...], PiAgentRuntimePreflightReport]:
    """Prepare the default runtime and return the executable command."""

    report = prepare_pi_agent_runtime(runtime_dir, env=env, timeout_seconds=timeout_seconds)
    if not report.available:
        raise ContractValidationError(
            "MissionForge PiAgent runtime preflight failed: " + "; ".join(report.failures)
        )
    return report.command, report


def preflight_pi_agent_runtime(
    runtime_dir: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    require_sandbox_linux: bool = False,
) -> PiAgentRuntimePreflightReport:
    """Report whether the host can run MissionForge's bundled PiAgent runtime."""

    effective_env = env or os.environ
    root = Path(runtime_dir).expanduser().resolve() if runtime_dir is not None else find_pi_agent_runtime_dir(env=env)
    capabilities = [
        _path_capability("node", node_executable(env=effective_env), env=effective_env),
        _runtime_file_capability(root),
        _node_modules_capability(root),
    ]
    sandbox_capability = _sandbox_linux_capability(env=effective_env)
    if require_sandbox_linux:
        capabilities.append(sandbox_capability)
    return PiAgentRuntimePreflightReport(
        runtime_dir=root,
        command=(node_executable(env=effective_env), str(root / "dist" / "main.js")),
        capabilities=tuple(capabilities),
        sandbox_linux_enabled=sandbox_capability.status == PiAgentRuntimeCapabilityStatus.AVAILABLE,
    )


def node_executable(*, env: Mapping[str, str] | None = None) -> str:
    effective_env = env or os.environ
    return effective_env.get(PI_AGENT_RUNTIME_NODE_ENV) or "node"


def npm_executable(*, env: Mapping[str, str] | None = None) -> str | None:
    effective_env = env or os.environ
    configured = effective_env.get(PI_AGENT_RUNTIME_NPM_ENV)
    if configured:
        return configured
    return shutil.which("npm", path=effective_env.get("PATH"))


def runtime_home(*, env: Mapping[str, str] | None = None) -> Path:
    effective_env = env or os.environ
    configured = effective_env.get(PI_AGENT_RUNTIME_HOME_ENV) or effective_env.get(PI_AGENT_RUNTIME_CACHE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".cache" / "missionforge"


def _materialized_runtime_dir(source_dir: Path, *, env: Mapping[str, str]) -> Path:
    if _is_development_runtime_dir(source_dir):
        return source_dir
    package_lock_hash = _file_fingerprint(source_dir / "package-lock.json")
    return runtime_home(env=env) / "pi-agent-runtime" / PI_AGENT_RUNTIME_VERSION / package_lock_hash


def _is_development_runtime_dir(path: Path) -> bool:
    try:
        resolved = path.resolve()
        repo_runtime = Path(__file__).resolve().parents[2] / "workers" / "pi-agent-runtime"
        return resolved == repo_runtime.resolve()
    except OSError:
        return False


def _copy_runtime_assets(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("package.json", "package-lock.json", "tsconfig.json", "NOTICE"):
        source = source_dir / filename
        if source.is_file():
            shutil.copy2(source, target_dir / filename)
    for dirname in ("src", "dist"):
        source = source_dir / dirname
        target = target_dir / dirname
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)


def _is_runtime_asset_dir(path: Path) -> bool:
    return (path / "package.json").is_file() and (path / "package-lock.json").is_file()


def _validate_runtime_asset_dir(path: Path, *, source: str) -> None:
    if not _is_runtime_asset_dir(path):
        raise ContractValidationError(f"{source} does not point to a packaged PI Agent runtime: {path}")


def _has_node_modules(path: Path) -> bool:
    return (path / "node_modules").is_dir()


def _path_capability(
    name: str,
    executable: str | None,
    *,
    env: Mapping[str, str],
) -> PiAgentRuntimeCapability:
    if executable is None:
        return PiAgentRuntimeCapability(
            name=name,
            status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
            detail=f"{name} executable was not configured or found on PATH",
        )
    if Path(executable).is_absolute():
        exists = Path(executable).is_file()
        return PiAgentRuntimeCapability(
            name=name,
            status=PiAgentRuntimeCapabilityStatus.AVAILABLE if exists else PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
            detail="configured executable exists" if exists else "configured executable does not exist",
            path=executable,
        )
    resolved = shutil.which(executable, path=env.get("PATH"))
    return PiAgentRuntimeCapability(
        name=name,
        status=PiAgentRuntimeCapabilityStatus.AVAILABLE if resolved else PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
        detail="executable found on PATH" if resolved else "executable was not found on PATH",
        path=resolved or executable,
    )


def _runtime_file_capability(path: Path) -> PiAgentRuntimeCapability:
    main = path / "dist" / "main.js"
    if main.is_file():
        return PiAgentRuntimeCapability(
            name="pi_agent_runtime_dist",
            status=PiAgentRuntimeCapabilityStatus.AVAILABLE,
            detail="bundled runtime entrypoint is present",
            path=str(main),
        )
    return PiAgentRuntimeCapability(
        name="pi_agent_runtime_dist",
        status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
        detail="bundled runtime entrypoint is missing and must be built",
        path=str(main),
    )


def _node_modules_capability(path: Path) -> PiAgentRuntimeCapability:
    node_modules = path / "node_modules"
    if node_modules.is_dir():
        return PiAgentRuntimeCapability(
            name="pi_agent_runtime_dependencies",
            status=PiAgentRuntimeCapabilityStatus.AVAILABLE,
            detail="runtime npm dependencies are installed",
            path=str(node_modules),
        )
    return PiAgentRuntimeCapability(
        name="pi_agent_runtime_dependencies",
        status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
        detail="runtime npm dependencies are not installed",
        path=str(node_modules),
    )


def _sandbox_linux_capability(*, env: Mapping[str, str]) -> PiAgentRuntimeCapability:
    bwrap = env.get(PI_AGENT_RUNTIME_BWRAP_ENV) or shutil.which("bwrap", path=env.get("PATH"))
    if platform.system().lower() != "linux":
        return PiAgentRuntimeCapability(
            name="sandbox_linux",
            status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
            detail="bubblewrap/seccomp sandbox is only supported on Linux",
            path=bwrap,
        )
    if not bwrap:
        return PiAgentRuntimeCapability(
            name="sandbox_linux",
            status=PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
            detail="bubblewrap executable was not found",
            path=None,
        )
    return PiAgentRuntimeCapability(
        name="sandbox_linux",
        status=PiAgentRuntimeCapabilityStatus.AVAILABLE,
        detail="bubblewrap sandbox executable is available",
        path=bwrap,
    )


def _with_failure(
    report: PiAgentRuntimePreflightReport,
    capability: PiAgentRuntimeCapability,
) -> PiAgentRuntimePreflightReport:
    return PiAgentRuntimePreflightReport(
        runtime_dir=report.runtime_dir,
        command=report.command,
        capabilities=(*report.capabilities, capability),
        sandbox_linux_enabled=report.sandbox_linux_enabled,
        platform_system=report.platform_system,
        runtime_version=report.runtime_version,
    )


@dataclass(frozen=True)
class _SetupCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


def _run_setup_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: Mapping[str, str],
) -> _SetupCommandResult:
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
        return _SetupCommandResult(
            returncode=-1,
            stdout=_process_output_text(exc.stdout),
            stderr=_process_output_text(exc.stderr),
            timed_out=True,
        )
    except OSError as exc:
        return _SetupCommandResult(returncode=-1, stderr=str(exc))
    return _SetupCommandResult(
        returncode=completed.returncode,
        stdout=_process_output_text(completed.stdout),
        stderr=_process_output_text(completed.stderr),
    )


def _setup_failure_detail(command: str, result: _SetupCommandResult) -> str:
    suffix = "timed out" if result.timed_out else f"exited with return code {result.returncode}"
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    detail = stderr or stdout
    if detail:
        return f"{command} {suffix}: {detail[-500:]}"
    return f"{command} {suffix}"


def _process_output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _file_fingerprint(path: Path) -> str:
    import hashlib

    require_non_empty_str(str(path), "pi_agent_runtime.package_lock")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:16]
