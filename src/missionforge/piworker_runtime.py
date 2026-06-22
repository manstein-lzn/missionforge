"""PiWorker runtime construction boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .piworker_call import PiWorkerCall, PiWorkerCallResult
from .evidence_store import EvidenceLedger
from .piworker_progress import PiWorkerProgressSink
from .runtime_results import WorkerAdapterResult


class PiWorkerCallAdapter(Protocol):
    """Minimal adapter protocol for the PiWorkerCall runtime boundary."""

    adapter_family: str

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
        call_spec: Any | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        extension_lock_ref: str | None = None,
        runtime_progress_sink: PiWorkerProgressSink | None = None,
    ) -> WorkerAdapterResult:
        """Execute one bounded PiWorker call."""
        ...


@dataclass(frozen=True)
class PiWorkerRuntimeFactory:
    """Create the single supported LLM worker runtime."""

    config: Any | None = None
    runner: Any | None = None

    def create_default_worker(self) -> PiWorkerCallAdapter:
        from .adapters.pi_agent_runtime import PiAgentRuntimeAdapter

        if self.runner is None:
            return PiAgentRuntimeAdapter(self.config)
        return PiAgentRuntimeAdapter(self.config, runner=self.runner)


def create_default_piworker_adapter(config: Any | None = None, *, runner: Any | None = None) -> PiWorkerCallAdapter:
    """Return the default PiWorkerCall adapter."""

    return PiWorkerRuntimeFactory(config=config, runner=runner).create_default_worker()


def run_piworker_call(
    call: PiWorkerCall,
    *,
    workspace: str | Path = ".",
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    evidence_store: EvidenceLedger | None = None,
    call_spec: Any | None = None,
    exit_criteria: list[str] | None = None,
    stop_conditions: list[str] | None = None,
    extension_lock_ref: str | None = None,
    result_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    runtime_progress_sink: PiWorkerProgressSink | None = None,
) -> PiWorkerCallResult:
    """Run one bounded PiWorker call and return its refs-first result.

    This is the smallest programmer-facing execution primitive. It does not
    decide semantic acceptance and does not prescribe a product workflow; it
    only normalizes the adapter result for one unreliable intelligence RPC.
    """

    call.validate()
    worker = adapter or create_default_piworker_adapter(piworker_config, runner=runner)
    run_kwargs: dict[str, Any] = {
        "workspace": workspace,
        "evidence_store": evidence_store,
        "call_spec": call_spec,
        "exit_criteria": exit_criteria,
        "stop_conditions": stop_conditions,
        "extension_lock_ref": extension_lock_ref,
    }
    if runtime_progress_sink is not None:
        run_kwargs["runtime_progress_sink"] = runtime_progress_sink
    worker_result = worker.run_call(call, **run_kwargs)
    result = PiWorkerCallResult.from_worker_adapter_result(
        call,
        worker_result,
        result_id=result_id,
        metadata=metadata,
    )
    result.validate_against_call(call)
    return result
