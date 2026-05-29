"""PiWorker boundary helpers for FrontDesk spec-grill nodes.

This module does not introduce a second worker abstraction and does not call a
live provider by default. It builds and validates bounded WorkUnitContract
objects for future PiWorker-backed FrontDesk LLM nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from ..contracts import ContractValidationError, assert_refs_only_payload, require_non_empty_str, validate_ref
from ..evidence_store import EvidenceLedger
from ..work_unit import WorkUnitContract
from ..workers import WorkerAdapter, WorkerAdapterResult
from .workspace import FrontDeskWorkspace


FRONTDESK_NODE_NAMES = frozenset(
    {
        "need_griller",
        "solution_architect",
        "mission_ir_mapper",
        "mission_ir_auditor",
    }
)


@dataclass(frozen=True)
class FrontDeskPiNodeContract:
    """Bounded contract for one PiWorker-backed FrontDesk node."""

    node_name: str
    session_id: str
    work_unit: WorkUnitContract

    def validate(self) -> None:
        if self.node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk_pi_node_contract.node_name is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_pi_node_contract.session_id")
        self.work_unit.validate()
        for ref in self.work_unit.visible_refs:
            validate_ref(ref, "frontdesk_pi_node_contract.visible_refs[]")
        for ref in self.work_unit.expected_outputs:
            _require_frontdesk_output_ref(ref)
        for ref in self.work_unit.allowed_scope:
            _require_frontdesk_output_ref(ref)
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_pi_node_contract")

    def to_dict_without_validation(self) -> dict[str, object]:
        return {
            "node_name": self.node_name,
            "session_id": self.session_id,
            "work_unit": self.work_unit.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class FrontDeskPiNodeExecutionRecord:
    """Refs-only provenance for one opt-in FrontDesk PiWorker node execution."""

    node_name: str
    session_id: str
    contract: FrontDeskPiNodeContract
    produced_refs: list[str]
    evidence_refs: list[str]
    execution_report_ref: str
    node_execution_ref: str
    status: str

    def validate(self) -> None:
        if self.node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk_pi_node_execution.node_name is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_pi_node_execution.session_id")
        self.contract.validate()
        for ref in self.produced_refs:
            _require_frontdesk_output_ref(ref)
        for ref in self.evidence_refs:
            validate_ref(ref, "frontdesk_pi_node_execution.evidence_refs[]")
        validate_ref(self.execution_report_ref, "frontdesk_pi_node_execution.execution_report_ref")
        validate_ref(self.node_execution_ref, "frontdesk_pi_node_execution.node_execution_ref")
        require_non_empty_str(self.status, "frontdesk_pi_node_execution.status")
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_pi_node_execution")

    def to_dict_without_validation(self) -> dict[str, object]:
        return {
            "node_name": self.node_name,
            "session_id": self.session_id,
            "contract": self.contract.to_dict(),
            "produced_refs": list(self.produced_refs),
            "evidence_refs": list(self.evidence_refs),
            "execution_report_ref": self.execution_report_ref,
            "node_execution_ref": self.node_execution_ref,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class FrontDeskPiNodeRunResult:
    """Validated result of one opt-in FrontDesk PiWorker node run."""

    contract: FrontDeskPiNodeContract
    worker_result: WorkerAdapterResult
    execution_record: FrontDeskPiNodeExecutionRecord

    def validate(self) -> None:
        self.contract.validate()
        self.worker_result.validate()
        self.execution_record.validate()
        assert_refs_only_payload(self.worker_result.to_dict(), "frontdesk_pi_node_worker_result")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "contract": self.contract.to_dict(),
            "worker_result": self.worker_result.to_dict(),
            "execution_record": self.execution_record.to_dict(),
        }


class FrontDeskPiNodeRunner:
    """Build and validate PiWorker node contracts for FrontDesk."""

    def build_contract(
        self,
        *,
        node_name: str,
        session_id: str,
        visible_refs: list[str],
        expected_outputs: list[str],
    ) -> FrontDeskPiNodeContract:
        if node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk pi node is unsupported")
        for ref in expected_outputs:
            _require_frontdesk_output_ref(ref)
        for ref in visible_refs:
            validate_ref(ref, "frontdesk_pi_node.visible_refs[]")
        work_unit = WorkUnitContract(
            work_unit_id=f"frontdesk-{session_id}-{node_name}",
            mission_id=f"frontdesk-{session_id}",
            iteration=1,
            next_objective=f"Produce structured {node_name} output JSON only.",
            allowed_scope=list(expected_outputs),
            visible_refs=list(visible_refs),
            expected_outputs=list(expected_outputs),
            exit_criteria=["Expected output refs exist and validate against FrontDesk schemas."],
            stop_conditions=["Do not approve, freeze, verify, run, or mutate frozen contracts."],
        )
        contract = FrontDeskPiNodeContract(node_name=node_name, session_id=session_id, work_unit=work_unit)
        contract.validate()
        return contract

    def run_node(
        self,
        *,
        node_name: str,
        session_id: str,
        visible_refs: list[str],
        expected_outputs: list[str],
        worker: WorkerAdapter | None = None,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
    ) -> FrontDeskPiNodeRunResult:
        """Run one node through an explicitly supplied PiWorker-compatible adapter."""

        if worker is None:
            raise ContractValidationError("frontdesk pi node execution requires an explicit PiWorker adapter")
        contract = self.build_contract(
            node_name=node_name,
            session_id=session_id,
            visible_refs=visible_refs,
            expected_outputs=expected_outputs,
        )
        worker_result = worker.run(contract.work_unit, workspace=workspace, evidence_store=evidence_store)
        worker_result.validate()
        assert_refs_only_payload(worker_result.to_dict(), "frontdesk_pi_node_worker_result")
        produced_refs = list(worker_result.execution_report.produced_artifacts)
        self.validate_produced_refs(contract, produced_refs)

        execution_ref = _node_execution_ref(session_id=session_id, node_name=node_name)
        execution_record = FrontDeskPiNodeExecutionRecord(
            node_name=node_name,
            session_id=session_id,
            contract=contract,
            produced_refs=produced_refs,
            evidence_refs=list(worker_result.execution_report.evidence_refs),
            execution_report_ref=worker_result.worker_result.execution_report_ref,
            node_execution_ref=execution_ref,
            status=worker_result.worker_result.status,
        )
        FrontDeskWorkspace(workspace).write_json(execution_ref, execution_record.to_dict())
        result = FrontDeskPiNodeRunResult(
            contract=contract,
            worker_result=worker_result,
            execution_record=execution_record,
        )
        result.validate()
        return result

    def validate_produced_refs(self, contract: FrontDeskPiNodeContract, produced_refs: list[str]) -> None:
        contract.validate()
        for ref in produced_refs:
            _require_frontdesk_output_ref(ref)
        missing = sorted(set(contract.work_unit.expected_outputs) - set(produced_refs))
        if missing:
            raise ContractValidationError(f"frontdesk pi node missing expected output(s): {', '.join(missing)}")
        extra = sorted(set(produced_refs) - set(contract.work_unit.allowed_scope))
        if extra:
            raise ContractValidationError(f"frontdesk pi node wrote outside allowed scope: {', '.join(extra)}")


def _require_frontdesk_output_ref(ref: str) -> str:
    safe = validate_ref(ref, "frontdesk_pi_node.output_ref")
    if not safe.startswith("frontdesk/"):
        raise ContractValidationError("frontdesk pi node outputs must stay under frontdesk/")
    return safe


def _node_execution_ref(*, session_id: str, node_name: str) -> str:
    return f"frontdesk/pi_nodes/{_safe_ref_fragment(session_id)}/{_safe_ref_fragment(node_name)}/execution.json"


def _safe_ref_fragment(value: str) -> str:
    text = require_non_empty_str(value, "frontdesk_pi_node.ref_fragment").lower()
    safe = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    if not safe:
        raise ContractValidationError("frontdesk pi node ref fragment is empty after sanitization")
    return safe


__all__ = [
    "FRONTDESK_NODE_NAMES",
    "FrontDeskPiNodeContract",
    "FrontDeskPiNodeExecutionRecord",
    "FrontDeskPiNodeRunResult",
    "FrontDeskPiNodeRunner",
]
