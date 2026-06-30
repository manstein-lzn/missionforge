"""Compile Kernel Step declarations into existing MissionForge core objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..contracts import validate_ref
from ..permissions import ref_is_under
from ..piworker_call import PiWorkerCall
from ..task_contract import ExtensionGrant, NetworkPolicy, PermissionManifest
from .contracts import Artifact, ArtifactRole, KernelValidationError, Step, Toolset


CORE_TOOLS = {"read", "write", "edit", "bash"}


@dataclass(frozen=True)
class StepCompileContext:
    """Frozen authority refs used to compile one Step."""

    flow_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str = "contract/task_contract.json"
    workspace_policy_ref: str = "policy/workspace_policy.json"
    denied_refs: list[str] | None = None
    permission_manifest_ref: str | None = None
    ref_prefix: str | None = None
    call_id: str | None = None
    context_feed_refs: list[str] | None = None
    context_thrash_diagnostics_refs: list[str] | None = None

    def validate(self) -> None:
        _safe_id(self.flow_id, "kernel_step_compile_context.flow_id")
        _non_empty(self.contract_id, "kernel_step_compile_context.contract_id")
        _hash(self.contract_hash, "kernel_step_compile_context.contract_hash")
        validate_ref(self.contract_ref, "kernel_step_compile_context.contract_ref")
        validate_ref(self.workspace_policy_ref, "kernel_step_compile_context.workspace_policy_ref")
        if self.permission_manifest_ref is not None:
            validate_ref(self.permission_manifest_ref, "kernel_step_compile_context.permission_manifest_ref")
        if self.ref_prefix is not None:
            validate_ref(self.ref_prefix, "kernel_step_compile_context.ref_prefix")
        if self.call_id is not None:
            _safe_id(self.call_id, "kernel_step_compile_context.call_id")
        for ref in self.denied_refs or []:
            validate_ref(ref, "kernel_step_compile_context.denied_refs[]")
        for ref in self.context_feed_refs or []:
            validate_ref(ref, "kernel_step_compile_context.context_feed_refs[]")
        for ref in self.context_thrash_diagnostics_refs or []:
            validate_ref(ref, "kernel_step_compile_context.context_thrash_diagnostics_refs[]")


@dataclass(frozen=True)
class CompiledStep:
    """Compiled core objects for one Step."""

    step: Step
    piworker_call: PiWorkerCall
    permission_manifest: PermissionManifest
    permission_manifest_ref: str

    def validate(self) -> None:
        self.step.validate()
        validate_ref(self.permission_manifest_ref, "compiled_step.permission_manifest_ref")
        self.permission_manifest.validate()
        self.piworker_call.validate()


def compile_step(
    step: Step,
    *,
    context: StepCompileContext,
    toolsets: Mapping[str, Toolset] | None = None,
    artifacts: Mapping[str, Artifact] | None = None,
) -> CompiledStep:
    """Compile a product-neutral Step to PiWorkerCall and PermissionManifest."""

    step.validate()
    context.validate()
    toolset_map = dict(toolsets or {})
    artifact_map = dict(artifacts or {})
    for toolset in toolset_map.values():
        toolset.validate()
    for artifact in artifact_map.values():
        artifact.validate()

    _validate_ref_authority(step.inputs, step.read, "kernel_step.inputs")
    if step.context_working_set_ref is not None:
        _validate_ref_authority([step.context_working_set_ref], step.read, "kernel_step.context_working_set_ref")
    _validate_ref_authority(step.outputs, step.write, "kernel_step.outputs")
    _validate_contract_write_boundary(step, context)
    _validate_runtime_owned_outputs(step, artifact_map)

    extension_grants: list[ExtensionGrant] = []
    for tool in step.tools:
        if tool in CORE_TOOLS:
            continue
        toolset = toolset_map.get(tool)
        if toolset is None:
            raise KernelValidationError(f"kernel_step.tools contains unknown tool or toolset: {tool}")
        extension_grants.append(_extension_grant_for_toolset(context.flow_id, step.id, toolset))

    if "bash" in step.tools and not step.command_allowlist:
        raise KernelValidationError("kernel_step using bash requires command_allowlist")

    network_policy = NetworkPolicy.ENABLED if step.network or any(grant.requires_network for grant in extension_grants) else NetworkPolicy.DISABLED
    ref_prefix = context.ref_prefix or f"kernel/{context.flow_id}/steps/{step.id}"
    permission_manifest_ref = context.permission_manifest_ref or f"{ref_prefix}/permission_manifest.json"
    allowed_tools = _allowed_tools_for_step(step, toolset_map)
    permission_manifest = PermissionManifest(
        manifest_id=f"{context.flow_id}-{step.id}-permissions",
        workspace_policy_ref=context.workspace_policy_ref,
        readable_refs=_dedupe_refs([context.contract_ref, *step.read]),
        writable_refs=_dedupe_refs(step.write),
        denied_refs=_dedupe_refs(context.denied_refs or []),
        allowed_tools=allowed_tools,
        allowed_commands=list(step.command_allowlist),
        network_policy=network_policy,
        env_allowlist=_dedupe_strings([*step.env_allowlist, *[env for grant in extension_grants for env in grant.required_env]]),
        extension_grants=extension_grants,
    )
    permission_manifest.validate()

    step_spec_ref = f"{ref_prefix}/step_spec.json"
    call_id = context.call_id or f"{context.flow_id}-{step.id}"
    visible_refs = _dedupe_refs([context.contract_ref, *step.inputs])
    _validate_visible_refs_authority(visible_refs, permission_manifest.readable_refs)
    call = PiWorkerCall(
        call_id=call_id,
        role=step.role,
        contract_id=context.contract_id,
        contract_hash=context.contract_hash,
        contract_ref=context.contract_ref,
        objective=step.brief,
        visible_refs=visible_refs,
        writable_refs=list(step.write),
        expected_output_refs=list(step.outputs),
        permission_manifest_ref=permission_manifest_ref,
        source_packet_ref=None,
        source_packet_hash=None,
        evidence_refs=_dedupe_refs([
            *step.inputs,
            *([step.context_working_set_ref] if step.context_working_set_ref else []),
        ]),
        runtime_budget=dict(step.runtime_budget),
        metadata={
            "kernel_flow_id": context.flow_id,
            "kernel_step_id": step.id,
            "kernel_step_spec_ref": step_spec_ref,
            "kernel_step_spec_hash": step.spec_hash,
            "route_on_ref": step.route_on or "",
            "route_fields": list(step.route_fields),
        },
    )
    call.validate()
    compiled = CompiledStep(
        step=step,
        piworker_call=call,
        permission_manifest=permission_manifest,
        permission_manifest_ref=permission_manifest_ref,
    )
    compiled.validate()
    return compiled


def _extension_grant_for_toolset(flow_id: str, step_id: str, toolset: Toolset) -> ExtensionGrant:
    return ExtensionGrant(
        grant_id=f"{flow_id}-{step_id}-{toolset.id}",
        package=toolset.package,
        version_spec=toolset.version_spec,
        capability=toolset.capability,
        config_ref=toolset.config_ref,
        requires_network=toolset.network,
        requires_bash=toolset.bash,
        required_env=list(toolset.required_env),
        adapter_mode=toolset.adapter_mode,
        integrity=toolset.integrity,
        metadata={
            "kernel_toolset_id": toolset.id,
            "tool_names": list(toolset.tools),
            **dict(toolset.metadata),
        },
    )


def _allowed_tools_for_step(step: Step, toolsets: Mapping[str, Toolset]) -> list[str]:
    allowed: list[str] = []
    for tool in step.tools:
        if tool in CORE_TOOLS:
            allowed.append(tool)
            continue
        toolset = toolsets.get(tool)
        if toolset is not None:
            allowed.extend(toolset.tools)
    return _dedupe_strings(allowed)


def _validate_ref_authority(refs: list[str], roots: list[str], field_name: str) -> None:
    for ref in refs:
        safe_ref = validate_ref(ref, f"{field_name}[]")
        if not any(ref_is_under(safe_ref, root) for root in roots):
            raise KernelValidationError(f"{field_name} contains ref outside declared roots: {safe_ref}")


def _validate_runtime_owned_outputs(step: Step, artifacts: Mapping[str, Artifact]) -> None:
    for output in step.outputs:
        artifact = artifacts.get(output)
        if artifact is None:
            continue
        if artifact.owner != "piworker" or artifact.role not in {
            ArtifactRole.OUTPUT,
            ArtifactRole.DECISION,
            ArtifactRole.STATE,
        }:
            raise KernelValidationError(f"kernel_step.outputs includes non-piworker-output artifact: {output}")


def _validate_contract_write_boundary(step: Step, context: StepCompileContext) -> None:
    for root in step.write:
        if ref_is_under(context.contract_ref, root):
            raise KernelValidationError("kernel_step.write must not cover the frozen contract ref")
    for output in step.outputs:
        if output == context.contract_ref:
            raise KernelValidationError("kernel_step.outputs must not include the frozen contract ref")


def _validate_visible_refs_authority(visible_refs: list[str], readable_refs: list[str]) -> None:
    for ref in visible_refs:
        if not any(ref_is_under(ref, root) for root in readable_refs):
            raise KernelValidationError(f"kernel_step visible ref is outside permission readable refs: {ref}")


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _non_empty(value, "value")
        if text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _safe_id(value: str, field_name: str) -> str:
    text = _non_empty(value, field_name)
    if "/" in text or "\\" in text or text in {".", ".."}:
        raise KernelValidationError(f"{field_name} must be a single safe id segment")
    validate_ref(text, field_name)
    return text


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KernelValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _hash(value: str, field_name: str) -> str:
    text = _non_empty(value, field_name)
    if not text.startswith("sha256:") or len(text) <= len("sha256:"):
        raise KernelValidationError(f"{field_name} must be a sha256 hash")
    return text
