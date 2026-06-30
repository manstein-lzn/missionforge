"""Kernel runtime result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..piworker_call import PiWorkerCallResult
from ..ref_store import RefStore
from .compiler import CompiledStep
from ..contracts import ContractValidationError, validate_ref
from .contracts import Flow, FlowResult, StepRecord
from .projections import ProjectionRunResult


@dataclass(frozen=True)
class StepRunResult:
    """Refs-first result for one executed Kernel Step."""

    compiled: CompiledStep
    call_result: PiWorkerCallResult
    step_record: StepRecord
    step_spec_ref: str
    piworker_call_ref: str
    piworker_call_result_ref: str
    step_record_ref: str
    store: RefStore | None = field(default=None, repr=False, compare=False)

    def validate(self) -> None:
        self.compiled.validate()
        self.call_result.validate_against_call(self.compiled.piworker_call)
        self.step_record.validate()
        validate_ref(self.step_spec_ref, "kernel_step_run_result.step_spec_ref")
        validate_ref(self.piworker_call_ref, "kernel_step_run_result.piworker_call_ref")
        validate_ref(self.piworker_call_result_ref, "kernel_step_run_result.piworker_call_result_ref")
        validate_ref(self.step_record_ref, "kernel_step_run_result.step_record_ref")
        if self.step_record.piworker_call_ref != self.piworker_call_ref:
            raise ContractValidationError("kernel_step_run_result step_record piworker_call_ref mismatch")
        if self.step_record.piworker_call_result_ref != self.piworker_call_result_ref:
            raise ContractValidationError("kernel_step_run_result step_record piworker_call_result_ref mismatch")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "step_id": self.compiled.step.id,
            "status": self.step_record.status.value,
            "step_spec_ref": self.step_spec_ref,
            "piworker_call_ref": self.piworker_call_ref,
            "piworker_call_result_ref": self.piworker_call_result_ref,
            "step_record_ref": self.step_record_ref,
            "output_refs": list(self.step_record.output_refs),
        }


@dataclass(frozen=True)
class FlowRunResult:
    """Refs-first result for a Kernel Flow run."""

    flow: Flow
    flow_result: FlowResult
    flow_result_ref: str
    step_results: list[StepRunResult]
    projection_results: list[ProjectionRunResult] | None = None
    store: RefStore | None = field(default=None, repr=False, compare=False)

    def validate(self) -> None:
        self.flow.validate()
        self.flow_result.validate()
        validate_ref(self.flow_result_ref, "kernel_flow_run_result.flow_result_ref")
        for result in self.step_results:
            result.validate()
        for result in self.projection_results or []:
            result.validate()

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "flow_id": self.flow.id,
            "status": self.flow_result.status,
            "flow_result_ref": self.flow_result_ref,
            "step_record_refs": list(self.flow_result.step_record_refs),
            "final_artifact_refs": list(self.flow_result.final_artifact_refs),
            "decision_refs": list(self.flow_result.decision_refs),
            "ledger_refs": list(self.flow_result.ledger_refs),
            "projection_record_refs": [result.record_ref for result in self.projection_results or []],
        }
