"""Minimal product-neutral Kernel debug stepping helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..context import build_call_context_view
from ..context import build_context_replay_plan as _build_context_replay_plan
from ..contracts import assert_refs_only_payload, stable_json_hash, validate_ref
from ..evidence_store import EvidenceLedger
from ..piworker_progress import PiWorkerProgressSink
from ..piworker_runtime import PiWorkerCallAdapter
from .compiler import StepCompileContext, compile_step
from .contracts import Artifact, Flow, KernelValidationError, Step, StepStatus, Toolset
from .extensions import ExtensionInstaller
from .inspect import KernelStepInspection
from .routing import KernelRouteDecision, resolve_step_route
from .runner import StepRunResult, run_step


@dataclass(frozen=True)
class KernelStepPreview:
    """Refs-only preview for one compiled Kernel step boundary."""

    flow_id: str
    step_id: str
    call_id: str
    role: str
    contract_ref: str
    contract_hash: str
    permission_manifest_ref: str
    permission_manifest_hash: str = ""
    readable_refs: list[str] = field(default_factory=list)
    visible_refs: list[str] = field(default_factory=list)
    writable_refs: list[str] = field(default_factory=list)
    denied_refs: list[str] = field(default_factory=list)
    expected_output_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    network_policy: str = ""
    context_hash: str = ""
    context_projection_ref: str = ""
    route_on: str = ""
    route_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "flow_id": self.flow_id,
            "step_id": self.step_id,
            "call_id": self.call_id,
            "role": self.role,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "permission_manifest_ref": self.permission_manifest_ref,
            "permission_manifest_hash": self.permission_manifest_hash,
            "readable_refs": list(self.readable_refs),
            "visible_refs": list(self.visible_refs),
            "writable_refs": list(self.writable_refs),
            "denied_refs": list(self.denied_refs),
            "expected_output_refs": list(self.expected_output_refs),
            "evidence_refs": list(self.evidence_refs),
            "allowed_tools": list(self.allowed_tools),
            "network_policy": self.network_policy,
            "context_hash": self.context_hash,
            "context_projection_ref": self.context_projection_ref,
            "route_on": self.route_on,
            "route_fields": list(self.route_fields),
        }
        return dict(assert_refs_only_payload(payload, "kernel_step_preview"))


@dataclass(frozen=True)
class KernelStepDebugResult:
    """Refs-only debug result for one explicitly executed step."""

    step: KernelStepInspection
    route_decision: KernelRouteDecision | None = None

    @classmethod
    def from_step_run(
        cls,
        result: StepRunResult,
        *,
        flow: Flow | None = None,
        workspace: str | Path = ".",
    ) -> "KernelStepDebugResult":
        route_decision = None
        if flow is not None and result.step_record.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}:
            if result.compiled.step.route_on is not None:
                route_decision = resolve_step_route(flow, result.compiled.step, workspace)
        return cls(
            step=KernelStepInspection.from_record(result.step_record_ref, result.step_record),
            route_decision=route_decision,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "step": self.step.to_dict(),
            "route_decision": self.route_decision.to_dict() if self.route_decision is not None else None,
        }
        return dict(assert_refs_only_payload(payload, "kernel_step_debug_result"))


def preview_kernel_step(
    step: Step,
    *,
    context: StepCompileContext,
    toolsets: Mapping[str, Toolset] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    context_projection_ref: str | None = None,
) -> KernelStepPreview:
    """Compile one step and return a safe preview without writing files."""

    compiled = compile_step(step, context=context, toolsets=toolsets, artifacts=artifacts)
    diagnostics_ref = context_projection_ref or _context_projection_ref(context, step)
    view = build_call_context_view(
        view_id=f"{compiled.piworker_call.call_id}-context",
        role=compiled.piworker_call.role.value,
        contract_ref=compiled.piworker_call.contract_ref,
        contract_hash=compiled.piworker_call.contract_hash,
        permission_manifest_ref=compiled.permission_manifest_ref,
        visible_refs=list(compiled.piworker_call.visible_refs),
        expected_output_refs=list(compiled.piworker_call.expected_output_refs),
        evidence_refs=list(compiled.piworker_call.evidence_refs),
        diagnostics_ref=diagnostics_ref,
    )
    return KernelStepPreview(
        flow_id=context.flow_id,
        step_id=step.id,
        call_id=compiled.piworker_call.call_id,
        role=compiled.piworker_call.role.value,
        contract_ref=compiled.piworker_call.contract_ref,
        contract_hash=compiled.piworker_call.contract_hash,
        permission_manifest_ref=compiled.permission_manifest_ref,
        permission_manifest_hash=stable_json_hash(compiled.permission_manifest.to_dict()),
        readable_refs=list(compiled.permission_manifest.readable_refs),
        visible_refs=list(compiled.piworker_call.visible_refs),
        writable_refs=list(compiled.piworker_call.writable_refs),
        denied_refs=list(compiled.permission_manifest.denied_refs),
        expected_output_refs=list(compiled.piworker_call.expected_output_refs),
        evidence_refs=list(compiled.piworker_call.evidence_refs),
        allowed_tools=list(compiled.permission_manifest.allowed_tools),
        network_policy=compiled.permission_manifest.network_policy.value,
        context_hash=view.context_hash,
        context_projection_ref=diagnostics_ref,
        route_on=step.route_on or "",
        route_fields=list(step.route_fields),
    )


def preview_flow_step(
    flow: Flow,
    step_id: str,
    *,
    context: StepCompileContext,
    ref_prefix: str | None = None,
) -> KernelStepPreview:
    """Preview one explicit Flow step without executing it."""

    step = _flow_step(flow, step_id)
    step_context = _debug_context(context, step, ref_prefix=ref_prefix)
    return preview_kernel_step(
        step,
        context=step_context,
        toolsets={toolset.id: toolset for toolset in flow.toolsets},
        artifacts={artifact.ref: artifact for artifact in flow.artifacts},
    )


def run_kernel_step_once(
    step: Step,
    *,
    context: StepCompileContext,
    workspace: str | Path = ".",
    flow: Flow | None = None,
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    evidence_store: EvidenceLedger | None = None,
    toolsets: Mapping[str, Toolset] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
    extension_lock_ref: str | None = None,
    extension_lock_mode: str = "verify-installed",
    extension_installer: ExtensionInstaller | None = None,
    extension_install_root_ref: str = ".missionforge/extensions",
    extension_lock_compiled_at: str | None = None,
    resume: bool = True,
    runtime_progress_sink: PiWorkerProgressSink | None = None,
) -> KernelStepDebugResult:
    """Run exactly one step through the normal Kernel boundary."""

    result = run_step(
        step,
        context=context,
        workspace=workspace,
        adapter=adapter,
        piworker_config=piworker_config,
        runner=runner,
        evidence_store=evidence_store,
        toolsets=toolsets,
        artifacts=artifacts,
        extension_lock_ref=extension_lock_ref,
        extension_lock_mode=extension_lock_mode,
        extension_installer=extension_installer,
        extension_install_root_ref=extension_install_root_ref,
        extension_lock_compiled_at=extension_lock_compiled_at,
        resume=resume,
        runtime_progress_sink=runtime_progress_sink,
    )
    return KernelStepDebugResult.from_step_run(result, flow=flow, workspace=workspace)


def run_flow_step_once(
    flow: Flow,
    step_id: str,
    *,
    context: StepCompileContext,
    workspace: str | Path = ".",
    ref_prefix: str,
    adapter: PiWorkerCallAdapter | None = None,
    piworker_config: Any | None = None,
    runner: Any | None = None,
    evidence_store: EvidenceLedger | None = None,
    extension_lock_ref: str | None = None,
    extension_lock_mode: str = "verify-installed",
    extension_installer: ExtensionInstaller | None = None,
    extension_install_root_ref: str = ".missionforge/extensions",
    extension_lock_compiled_at: str | None = None,
    resume: bool = True,
    runtime_progress_sink: PiWorkerProgressSink | None = None,
) -> KernelStepDebugResult:
    """Run exactly one explicit Flow step under a caller-chosen debug prefix."""

    step = _flow_step(flow, step_id)
    step_context = _debug_context(context, step, ref_prefix=ref_prefix)
    return run_kernel_step_once(
        step,
        context=step_context,
        workspace=workspace,
        flow=flow,
        adapter=adapter,
        piworker_config=piworker_config,
        runner=runner,
        evidence_store=evidence_store,
        toolsets={toolset.id: toolset for toolset in flow.toolsets},
        artifacts={artifact.ref: artifact for artifact in flow.artifacts},
        extension_lock_ref=extension_lock_ref,
        extension_lock_mode=extension_lock_mode,
        extension_installer=extension_installer,
        extension_install_root_ref=extension_install_root_ref,
        extension_lock_compiled_at=extension_lock_compiled_at,
        resume=resume,
        runtime_progress_sink=runtime_progress_sink,
    )


def resolve_kernel_step_route(flow: Flow, step: Step, *, workspace: str | Path = ".") -> KernelRouteDecision:
    """Resolve one step route without executing additional work."""

    return resolve_step_route(flow, step, workspace)


def read_flow_route(flow: Flow, step_id: str, *, workspace: str | Path = ".") -> KernelRouteDecision:
    """Resolve the route for one explicit Flow step."""

    return resolve_step_route(flow, _flow_step(flow, step_id), workspace)


def build_context_replay_plan(
    *,
    plan_id: str,
    view_ref: str,
    checkpoint_ref: str,
    view,
    source_refs: list[str] | None = None,
    summary_refs: list[str] | None = None,
    allowed_source_refs: list[str] | None = None,
    denied_source_refs: list[str] | None = None,
):
    """Build a refs-only context replay plan through the core context module."""

    return _build_context_replay_plan(
        plan_id=plan_id,
        view_ref=view_ref,
        checkpoint_ref=checkpoint_ref,
        view=view,
        source_refs=source_refs,
        summary_refs=summary_refs,
        allowed_source_refs=allowed_source_refs,
        denied_source_refs=denied_source_refs,
    )


def _context_projection_ref(context: StepCompileContext, step: Step) -> str:
    prefix = context.ref_prefix or f"kernel/{context.flow_id}/steps/{step.id}"
    return validate_ref(f"{prefix}/context_projection.json", "kernel_step_debug.context_projection_ref")


def _debug_context(context: StepCompileContext, step: Step, *, ref_prefix: str | None) -> StepCompileContext:
    context.validate()
    prefix = validate_ref(ref_prefix, "kernel_step_debug.ref_prefix") if ref_prefix else context.ref_prefix
    call_id = context.call_id or f"{context.flow_id}-{_call_suffix(prefix, step)}"
    return StepCompileContext(
        flow_id=context.flow_id,
        contract_id=context.contract_id,
        contract_hash=context.contract_hash,
        contract_ref=context.contract_ref,
        workspace_policy_ref=context.workspace_policy_ref,
        denied_refs=context.denied_refs,
        permission_manifest_ref=None,
        ref_prefix=prefix,
        call_id=call_id,
    )


def _flow_step(flow: Flow, step_id: str) -> Step:
    flow.validate()
    safe_step_id = validate_ref(step_id, "kernel_step_debug.step_id")
    for step in flow.steps:
        if step.id == safe_step_id:
            return step
    raise KernelValidationError(f"unknown kernel flow step: {safe_step_id}")


def _call_suffix(ref_prefix: str | None, step: Step) -> str:
    if not ref_prefix:
        return step.id
    suffix = validate_ref(ref_prefix, "kernel_step_debug.ref_prefix").rsplit("/", 1)[-1]
    if "/" in suffix or "\\" in suffix or suffix in {"", ".", ".."}:
        return step.id
    return suffix
