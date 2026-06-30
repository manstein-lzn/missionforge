"""Managed ContextReducer bridge.

This module builds and validates MissionForge-owned reducer calls. It does not
summarize content, judge task quality, or mutate active context. Kernel may use
these helpers at safe provider-turn boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

from .context_engine import (
    ContextCompactionRecord,
    ContextCompactionStatus,
    ContextReductionRequest,
    ContextReductionResult,
    ContextReductionStatus,
)
from .contracts import ContractValidationError, validate_ref
from .permissions import ReadGate, WriteGate
from .piworker_call import PiWorkerCall, PiWorkerCallRole
from .task_contract import NetworkPolicy, PermissionManifest


DEFAULT_CONTEXT_REDUCER_TOOLS = ("read", "write")


@dataclass(frozen=True)
class ManagedContextReducerCall:
    """Compiled call boundary for one managed reducer invocation."""

    call: PiWorkerCall
    permission_manifest: PermissionManifest
    permission_manifest_ref: str

    def validate(self) -> None:
        self.call.validate()
        self.permission_manifest.validate()
        validate_ref(self.permission_manifest_ref, "managed_context_reducer.permission_manifest_ref")
        if self.call.role is not PiWorkerCallRole.CONTEXT_REDUCER:
            raise ContractValidationError("managed context reducer call must use context_reducer_piworker role")
        if self.call.permission_manifest_ref != self.permission_manifest_ref:
            raise ContractValidationError("managed context reducer permission manifest ref mismatch")


@dataclass(frozen=True)
class ContextReductionStateTransition:
    """Refs-only state transition proposed by one validated reducer result."""

    reduction_id: str
    status: ContextReductionStatus
    request_ref: str
    result_ref: str
    input_epoch_ref: str
    input_context_view_ref: str
    output_epoch_ref: str | None = None
    output_context_view_ref: str | None = None
    checkpoint_ref: str | None = None
    working_set_ref: str | None = None
    summary_refs: list[str] | None = None
    compaction_record: ContextCompactionRecord | None = None

    def validate(self) -> None:
        if not isinstance(self.status, ContextReductionStatus):
            raise ContractValidationError("context_reduction_transition.status must be a ContextReductionStatus")
        if not self.reduction_id:
            raise ContractValidationError("context_reduction_transition.reduction_id must not be empty")
        validate_ref(self.request_ref, "context_reduction_transition.request_ref")
        validate_ref(self.result_ref, "context_reduction_transition.result_ref")
        validate_ref(self.input_epoch_ref, "context_reduction_transition.input_epoch_ref")
        validate_ref(self.input_context_view_ref, "context_reduction_transition.input_context_view_ref")
        if self.output_epoch_ref is not None:
            validate_ref(self.output_epoch_ref, "context_reduction_transition.output_epoch_ref")
        if self.output_context_view_ref is not None:
            validate_ref(self.output_context_view_ref, "context_reduction_transition.output_context_view_ref")
        if self.checkpoint_ref is not None:
            validate_ref(self.checkpoint_ref, "context_reduction_transition.checkpoint_ref")
        if self.working_set_ref is not None:
            validate_ref(self.working_set_ref, "context_reduction_transition.working_set_ref")
        _dedupe_refs(list(self.summary_refs or []))
        if self.compaction_record is not None:
            self.compaction_record.validate()


def build_managed_context_reducer_call(
    *,
    request: ContextReductionRequest,
    request_ref: str,
    permission_manifest_ref: str,
    call_id: str | None = None,
    maintenance_root_ref: str = "context/maintenance",
) -> ManagedContextReducerCall:
    """Build a tightly scoped PiWorker call for managed context reduction."""

    request.validate()
    safe_request_ref = validate_ref(request_ref, "managed_context_reducer.request_ref")
    safe_permission_manifest_ref = validate_ref(
        permission_manifest_ref,
        "managed_context_reducer.permission_manifest_ref",
    )
    safe_maintenance_root_ref = validate_ref(maintenance_root_ref, "managed_context_reducer.maintenance_root_ref")
    readable_refs = _dedupe_refs(
        [
            request.contract_ref,
            request.permission_manifest_ref,
            request.context_view_ref,
            request.source_snapshot_ref,
            safe_request_ref,
            *([request.worker_brief_ref] if request.worker_brief_ref else []),
            *([request.judge_rubric_ref] if request.judge_rubric_ref else []),
            *([request.pressure_ref] if request.pressure_ref else []),
            *([request.current_working_set_ref] if request.current_working_set_ref else []),
            *request.thrash_diagnostics_refs,
            *request.recent_projection_refs,
            *request.source_refs,
            *request.tool_observation_refs,
            *request.checkpoint_refs,
        ]
    )
    writable_refs = _dedupe_refs([safe_maintenance_root_ref, *request.expected_output_refs])
    manifest = PermissionManifest(
        manifest_id=f"{request.reduction_id}-context-reducer-permissions",
        readable_refs=readable_refs,
        writable_refs=writable_refs,
        denied_refs=[],
        allowed_tools=list(DEFAULT_CONTEXT_REDUCER_TOOLS),
        network_policy=NetworkPolicy.DISABLED,
    )
    manifest.validate()
    call = PiWorkerCall(
        call_id=call_id or f"{request.reduction_id}-context-reducer",
        role=PiWorkerCallRole.CONTEXT_REDUCER,
        contract_id=request.reduction_id,
        contract_hash=request.contract_hash,
        contract_ref=request.contract_ref,
        objective="Maintain bounded context state from admitted refs without changing task authority.",
        visible_refs=readable_refs,
        writable_refs=writable_refs,
        expected_output_refs=[request.expected_output_refs[0]],
        permission_manifest_ref=safe_permission_manifest_ref,
        evidence_refs=_dedupe_refs(
            [
                request.context_view_ref,
                request.source_snapshot_ref,
                *request.thrash_diagnostics_refs,
                *request.recent_projection_refs,
                *request.source_refs,
                *request.tool_observation_refs,
                *request.checkpoint_refs,
            ]
        ),
        runtime_budget={},
        metadata={
            "missionforge_internal_role": "context_reducer",
            "context_reduction_request_ref": safe_request_ref,
            "context_reduction_request_hash": request.reduction_request_hash,
            "context_reduction_reason": request.reason.value,
            "context_reduction_target_role": request.role,
        },
    )
    compiled = ManagedContextReducerCall(
        call=call,
        permission_manifest=manifest,
        permission_manifest_ref=safe_permission_manifest_ref,
    )
    compiled.validate()
    return compiled


def validate_context_reduction_result_boundary(
    *,
    result: ContextReductionResult,
    request: ContextReductionRequest,
    reducer_permission_manifest: PermissionManifest,
) -> ContextReductionResult:
    """Validate reducer result refs against its permission manifest."""

    result.validate()
    request.validate()
    if result.reduction_id != request.reduction_id:
        raise ContractValidationError("context_reduction_result reduction_id does not match request")
    read_gate = ReadGate(reducer_permission_manifest)
    write_gate = WriteGate(reducer_permission_manifest, runtime_owned_refs=())
    for ref in [
        *result.source_refs,
        *result.pinned_refs,
        *result.evicted_refs,
        *result.omitted_refs,
        *result.denied_source_refs,
    ]:
        if not read_gate.check(ref).allowed:
            raise ContractValidationError(f"context_reduction_result ref is not readable by reducer: {ref}")
    for ref in [
        *([result.checkpoint_ref] if result.checkpoint_ref else []),
        *([result.working_set_ref] if result.working_set_ref else []),
        *result.summary_refs,
        *([result.compaction_record_ref] if result.compaction_record_ref else []),
        *([result.validation_report_ref] if result.validation_report_ref else []),
    ]:
        if not write_gate.check(ref, writer_role=PiWorkerCallRole.CONTEXT_REDUCER.value).allowed:
            raise ContractValidationError(f"context_reduction_result ref is not writable by reducer: {ref}")
    if result.status is ContextReductionStatus.COMPLETED:
        expected_outputs = set(request.expected_output_refs)
        actual_outputs = {
            ref
            for ref in [
                result.checkpoint_ref,
                result.working_set_ref,
                result.compaction_record_ref,
                result.validation_report_ref,
                *result.summary_refs,
            ]
            if ref
        }
        if not expected_outputs.intersection(actual_outputs):
            raise ContractValidationError("completed context_reduction_result must cite an expected output ref")
    return result


def build_context_reduction_state_transition(
    *,
    request: ContextReductionRequest,
    result: ContextReductionResult,
    request_ref: str,
    result_ref: str,
    input_epoch_ref: str,
    input_context_view_ref: str,
    permission_manifest_ref: str,
    output_epoch_ref: str | None = None,
    output_context_view_ref: str | None = None,
) -> ContextReductionStateTransition:
    """Build a refs-only transition from a validated reducer result."""

    request.validate()
    result.validate()
    safe_request_ref = validate_ref(request_ref, "context_reduction_transition.request_ref")
    safe_result_ref = validate_ref(result_ref, "context_reduction_transition.result_ref")
    safe_input_epoch_ref = validate_ref(input_epoch_ref, "context_reduction_transition.input_epoch_ref")
    safe_input_context_view_ref = validate_ref(
        input_context_view_ref,
        "context_reduction_transition.input_context_view_ref",
    )
    safe_permission_manifest_ref = validate_ref(
        permission_manifest_ref,
        "context_reduction_transition.permission_manifest_ref",
    )
    status = _compaction_status_for_reduction_result(result.status)
    checkpoint_ref = result.checkpoint_ref or (request.checkpoint_refs[-1] if request.checkpoint_refs else "")
    if not checkpoint_ref:
        raise ContractValidationError("context reduction transition requires a checkpoint ref")
    output_epoch = validate_ref(output_epoch_ref, "context_reduction_transition.output_epoch_ref") if output_epoch_ref else None
    output_view = (
        validate_ref(output_context_view_ref, "context_reduction_transition.output_context_view_ref")
        if output_context_view_ref
        else None
    )
    if status is ContextCompactionStatus.ENDED and (not output_epoch or not output_view):
        raise ContractValidationError("completed context reduction transition requires output epoch and view refs")
    compaction = ContextCompactionRecord(
        record_id=f"{request.reduction_id}-compaction",
        status=status,
        reason_code=request.reason.value,
        input_epoch_ref=safe_input_epoch_ref,
        output_epoch_ref=output_epoch,
        input_context_view_ref=safe_input_context_view_ref,
        output_context_view_ref=output_view,
        checkpoint_ref=checkpoint_ref,
        summary_artifact_refs=list(result.summary_refs),
        source_refs=list(result.source_refs),
        denied_source_refs=list(result.denied_source_refs),
        producing_role=PiWorkerCallRole.CONTEXT_REDUCER.value,
        permission_manifest_ref=safe_permission_manifest_ref,
        metadata={
            "context_reduction_request_ref": safe_request_ref,
            "context_reduction_result_ref": safe_result_ref,
            "context_reduction_status": result.status.value,
            "working_set_ref": result.working_set_ref or "",
        },
    )
    transition = ContextReductionStateTransition(
        reduction_id=request.reduction_id,
        status=result.status,
        request_ref=safe_request_ref,
        result_ref=safe_result_ref,
        input_epoch_ref=safe_input_epoch_ref,
        input_context_view_ref=safe_input_context_view_ref,
        output_epoch_ref=output_epoch,
        output_context_view_ref=output_view,
        checkpoint_ref=checkpoint_ref,
        working_set_ref=result.working_set_ref,
        summary_refs=list(result.summary_refs),
        compaction_record=compaction,
    )
    transition.validate()
    return transition


def context_reduction_request_hash(request: ContextReductionRequest) -> str:
    """Return the stable request hash for callers that need a small helper."""

    request.validate()
    return request.reduction_request_hash


def _compaction_status_for_reduction_result(status: ContextReductionStatus) -> ContextCompactionStatus:
    if status is ContextReductionStatus.COMPLETED:
        return ContextCompactionStatus.ENDED
    if status in {
        ContextReductionStatus.FAILED,
        ContextReductionStatus.INVALID_OUTPUT,
        ContextReductionStatus.SKIPPED,
    }:
        return ContextCompactionStatus.FAILED
    return ContextCompactionStatus.STARTED


def _dedupe_refs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = validate_ref(value, "managed_context_reducer.ref")
        if ref not in seen:
            result.append(ref)
            seen.add(ref)
    return result
