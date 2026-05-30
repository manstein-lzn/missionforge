"""PiWorker boundary helpers for FrontDesk spec-grill nodes.

This module does not introduce a second worker abstraction and does not call a
live provider by default. It builds and validates bounded WorkUnitContract
objects for future PiWorker-backed FrontDesk LLM nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
    validate_ref,
)
from ..evidence_store import EvidenceLedger
from ..work_unit import WorkUnitContract
from ..workers import WorkerAdapter, WorkerAdapterResult
from .workspace import FrontDeskWorkspace


FRONTDESK_NODE_NAMES = frozenset(
    {
        "need_griller",
        "intent_bundle_author",
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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrontDeskPiNodeContract":
        data = require_mapping(payload, "frontdesk_pi_node_contract")
        contract = cls(
            node_name=require_non_empty_str(data.get("node_name"), "frontdesk_pi_node_contract.node_name"),
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_pi_node_contract.session_id"),
            work_unit=WorkUnitContract.from_dict(require_mapping(data.get("work_unit"), "frontdesk_pi_node_contract.work_unit")),
        )
        contract.validate()
        return contract

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
    """Content-bound provenance for one opt-in FrontDesk PiWorker node execution."""

    node_name: str
    session_id: str
    contract: FrontDeskPiNodeContract
    produced_refs: list[str]
    output_hashes: dict[str, str]
    input_hashes: dict[str, str]
    node_spec_ref: str
    node_spec_hash: str
    work_unit_hash: str
    evidence_refs: list[str]
    execution_report_ref: str
    node_execution_ref: str
    status: str
    product_profile_hash: str = ""

    def validate(self) -> None:
        if self.node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk_pi_node_execution.node_name is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_pi_node_execution.session_id")
        self.contract.validate()
        for ref in self.produced_refs:
            _require_frontdesk_output_ref(ref)
        _validate_hash_map(self.output_hashes, "frontdesk_pi_node_execution.output_hashes")
        _validate_hash_map(self.input_hashes, "frontdesk_pi_node_execution.input_hashes", allow_missing=True)
        missing_hashes = sorted(set(self.produced_refs) - set(self.output_hashes))
        if missing_hashes:
            raise ContractValidationError(
                f"frontdesk_pi_node_execution missing output hash(es): {', '.join(missing_hashes)}"
            )
        validate_ref(self.node_spec_ref, "frontdesk_pi_node_execution.node_spec_ref")
        _validate_hash(self.node_spec_hash, "frontdesk_pi_node_execution.node_spec_hash")
        _validate_hash(self.work_unit_hash, "frontdesk_pi_node_execution.work_unit_hash")
        for ref in self.evidence_refs:
            validate_ref(ref, "frontdesk_pi_node_execution.evidence_refs[]")
        validate_ref(self.execution_report_ref, "frontdesk_pi_node_execution.execution_report_ref")
        validate_ref(self.node_execution_ref, "frontdesk_pi_node_execution.node_execution_ref")
        require_non_empty_str(self.status, "frontdesk_pi_node_execution.status")
        if self.product_profile_hash:
            _validate_hash(self.product_profile_hash, "frontdesk_pi_node_execution.product_profile_hash")
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_pi_node_execution")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrontDeskPiNodeExecutionRecord":
        data = require_mapping(payload, "frontdesk_pi_node_execution")
        contract = FrontDeskPiNodeContract.from_dict(require_mapping(data.get("contract"), "frontdesk_pi_node_execution.contract"))
        record = cls(
            node_name=require_non_empty_str(data.get("node_name"), "frontdesk_pi_node_execution.node_name"),
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_pi_node_execution.session_id"),
            contract=contract,
            produced_refs=_require_string_list(data.get("produced_refs", []), "frontdesk_pi_node_execution.produced_refs"),
            output_hashes=_require_string_mapping(
                data.get("output_hashes", {}),
                "frontdesk_pi_node_execution.output_hashes",
            ),
            input_hashes=_require_string_mapping(
                data.get("input_hashes", {}),
                "frontdesk_pi_node_execution.input_hashes",
            ),
            node_spec_ref=validate_ref(data.get("node_spec_ref"), "frontdesk_pi_node_execution.node_spec_ref"),
            node_spec_hash=require_non_empty_str(
                data.get("node_spec_hash"),
                "frontdesk_pi_node_execution.node_spec_hash",
            ),
            work_unit_hash=require_non_empty_str(
                data.get("work_unit_hash"),
                "frontdesk_pi_node_execution.work_unit_hash",
            ),
            evidence_refs=_require_string_list(data.get("evidence_refs", []), "frontdesk_pi_node_execution.evidence_refs"),
            execution_report_ref=validate_ref(
                data.get("execution_report_ref"),
                "frontdesk_pi_node_execution.execution_report_ref",
            ),
            node_execution_ref=validate_ref(
                data.get("node_execution_ref"),
                "frontdesk_pi_node_execution.node_execution_ref",
            ),
            status=require_non_empty_str(data.get("status"), "frontdesk_pi_node_execution.status"),
            product_profile_hash=str(data.get("product_profile_hash", "")),
        )
        record.validate()
        return record

    def to_dict_without_validation(self) -> dict[str, object]:
        return {
            "node_name": self.node_name,
            "session_id": self.session_id,
            "contract": self.contract.to_dict(),
            "produced_refs": list(self.produced_refs),
            "output_hashes": dict(self.output_hashes),
            "input_hashes": dict(self.input_hashes),
            "node_spec_ref": self.node_spec_ref,
            "node_spec_hash": self.node_spec_hash,
            "work_unit_hash": self.work_unit_hash,
            "evidence_refs": list(self.evidence_refs),
            "execution_report_ref": self.execution_report_ref,
            "node_execution_ref": self.node_execution_ref,
            "status": self.status,
            "product_profile_hash": self.product_profile_hash,
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
        optional_outputs: list[str] | None = None,
    ) -> FrontDeskPiNodeContract:
        if node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk pi node is unsupported")
        for ref in expected_outputs:
            _require_frontdesk_output_ref(ref)
        allowed_outputs = _dedupe_refs([*expected_outputs, *(optional_outputs or [])])
        for ref in allowed_outputs:
            _require_frontdesk_output_ref(ref)
        for ref in visible_refs:
            validate_ref(ref, "frontdesk_pi_node.visible_refs[]")
        work_unit = WorkUnitContract(
            work_unit_id=f"frontdesk-{session_id}-{node_name}",
            mission_id=f"frontdesk-{session_id}",
            iteration=1,
            next_objective=f"Produce structured {node_name} output JSON only.",
            allowed_scope=allowed_outputs,
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
        optional_outputs: list[str] | None = None,
        worker: WorkerAdapter | None = None,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
        product_profile_hash: str = "",
    ) -> FrontDeskPiNodeRunResult:
        """Run one node through an explicitly supplied PiWorker-compatible adapter."""

        if worker is None:
            raise ContractValidationError("frontdesk pi node execution requires an explicit PiWorker adapter")
        if getattr(worker, "adapter_family", "") != "piworker":
            raise ContractValidationError("frontdesk pi node execution requires an explicit PiWorker-compatible adapter")
        active_workspace = FrontDeskWorkspace(workspace)
        node_spec_ref = _node_spec_ref(session_id=session_id, node_name=node_name)
        allowed_outputs = _dedupe_refs([*expected_outputs, *(optional_outputs or [])])
        node_spec = {
            "schema_version": "missionforge.frontdesk.pi_node_spec.v1",
            "node_name": node_name,
            "session_id": session_id,
            "visible_refs": list(visible_refs),
            "expected_outputs": list(expected_outputs),
            "optional_outputs": list(optional_outputs or []),
            "allowed_scope": allowed_outputs,
            "rules": [
                "Produce structured FrontDesk artifacts only.",
                "Do not approve, freeze, verify, run, or mutate frozen contracts.",
                "Do not use raw conversation as runtime task truth.",
            ],
        }
        active_workspace.write_json(node_spec_ref, node_spec)
        contract_visible_refs = _dedupe_refs([node_spec_ref, *visible_refs])
        contract = self.build_contract(
            node_name=node_name,
            session_id=session_id,
            visible_refs=contract_visible_refs,
            expected_outputs=expected_outputs,
            optional_outputs=optional_outputs,
        )
        input_hashes = _hash_visible_refs(active_workspace, contract.work_unit.visible_refs)
        worker_result = worker.run(contract.work_unit, workspace=workspace, evidence_store=evidence_store)
        worker_result.validate()
        assert_refs_only_payload(worker_result.to_dict(), "frontdesk_pi_node_worker_result")
        produced_refs = list(worker_result.execution_report.produced_artifacts)
        self.validate_produced_refs(contract, produced_refs)
        output_hashes = {ref: _hash_ref(active_workspace, ref) for ref in produced_refs}

        execution_ref = _node_execution_ref(session_id=session_id, node_name=node_name)
        execution_record = FrontDeskPiNodeExecutionRecord(
            node_name=node_name,
            session_id=session_id,
            contract=contract,
            produced_refs=produced_refs,
            output_hashes=output_hashes,
            input_hashes=input_hashes,
            node_spec_ref=node_spec_ref,
            node_spec_hash=_hash_ref(active_workspace, node_spec_ref),
            work_unit_hash=stable_json_hash(contract.work_unit.to_dict()),
            evidence_refs=list(worker_result.execution_report.evidence_refs),
            execution_report_ref=worker_result.worker_result.execution_report_ref,
            node_execution_ref=execution_ref,
            status=worker_result.worker_result.status,
            product_profile_hash=product_profile_hash,
        )
        active_workspace.write_json(execution_ref, execution_record.to_dict())
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

    def require_ai_authored(
        self,
        *,
        workspace: str | Path,
        ref: str,
        node_name: str,
        session_id: str,
        product_profile_hash: str = "",
    ) -> FrontDeskPiNodeExecutionRecord:
        """Require that the current ref bytes match a validated PiWorker execution."""

        output_ref = _require_frontdesk_output_ref(ref)
        if node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk pi node is unsupported")
        active_workspace = FrontDeskWorkspace(workspace)
        execution_ref = _node_execution_ref(session_id=session_id, node_name=node_name)
        if not active_workspace.exists(execution_ref):
            raise ContractValidationError("frontdesk artifact is missing PiWorker execution provenance")
        record = FrontDeskPiNodeExecutionRecord.from_dict(active_workspace.read_json(execution_ref))
        if record.node_name != node_name or record.session_id != session_id:
            raise ContractValidationError("frontdesk artifact PiWorker execution provenance does not match node/session")
        if output_ref not in record.produced_refs:
            raise ContractValidationError("frontdesk artifact was not produced by the recorded PiWorker node")
        expected_hash = record.output_hashes.get(output_ref, "")
        if not expected_hash or _hash_ref(active_workspace, output_ref) != expected_hash:
            raise ContractValidationError("frontdesk artifact bytes do not match recorded PiWorker output hash")
        if stable_json_hash(record.contract.work_unit.to_dict()) != record.work_unit_hash:
            raise ContractValidationError("frontdesk PiWorker work unit hash does not match execution record")
        if _hash_ref(active_workspace, record.node_spec_ref) != record.node_spec_hash:
            raise ContractValidationError("frontdesk PiWorker node spec hash is stale")
        for input_ref, input_hash in record.input_hashes.items():
            current_hash = _hash_ref(active_workspace, input_ref) if active_workspace.exists(input_ref) else "missing"
            if current_hash != input_hash:
                raise ContractValidationError("frontdesk PiWorker visible input hash is stale")
        if product_profile_hash and record.product_profile_hash != product_profile_hash:
            raise ContractValidationError("frontdesk PiWorker product profile hash is stale")
        if record.status not in {"completed", "success", "succeeded"}:
            raise ContractValidationError("frontdesk PiWorker execution did not complete successfully")
        return record


def _require_frontdesk_output_ref(ref: str) -> str:
    safe = validate_ref(ref, "frontdesk_pi_node.output_ref")
    if not safe.startswith("frontdesk/"):
        raise ContractValidationError("frontdesk pi node outputs must stay under frontdesk/")
    return safe


def _node_spec_ref(*, session_id: str, node_name: str) -> str:
    return f"frontdesk/pi_nodes/{_safe_ref_fragment(session_id)}/{_safe_ref_fragment(node_name)}/node_spec.json"


def _node_execution_ref(*, session_id: str, node_name: str) -> str:
    return f"frontdesk/pi_nodes/{_safe_ref_fragment(session_id)}/{_safe_ref_fragment(node_name)}/execution.json"


def frontdesk_pi_node_spec_ref(*, session_id: str, node_name: str) -> str:
    if node_name not in FRONTDESK_NODE_NAMES:
        raise ContractValidationError("frontdesk pi node is unsupported")
    return _node_spec_ref(session_id=session_id, node_name=node_name)


def frontdesk_pi_node_execution_ref(*, session_id: str, node_name: str) -> str:
    if node_name not in FRONTDESK_NODE_NAMES:
        raise ContractValidationError("frontdesk pi node is unsupported")
    return _node_execution_ref(session_id=session_id, node_name=node_name)


def _safe_ref_fragment(value: str) -> str:
    text = require_non_empty_str(value, "frontdesk_pi_node.ref_fragment").lower()
    safe = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    if not safe:
        raise ContractValidationError("frontdesk pi node ref fragment is empty after sanitization")
    return safe


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe = validate_ref(ref, "frontdesk_pi_node.ref")
        if safe not in seen:
            result.append(safe)
            seen.add(safe)
    return result


def _hash_visible_refs(workspace: FrontDeskWorkspace, refs: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for ref in refs:
        safe = validate_ref(ref, "frontdesk_pi_node.visible_ref")
        hashes[safe] = _hash_ref(workspace, safe) if workspace.exists(safe) else "missing"
    return hashes


def _hash_ref(workspace: FrontDeskWorkspace, ref: str) -> str:
    path = workspace.resolve_ref(ref)
    if not path.exists() or not path.is_file():
        raise ContractValidationError(f"frontdesk artifact ref is missing: {ref}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _validate_hash(value: str, field_name: str) -> None:
    _validate_hash_value(value, field_name, allow_missing=False)


def _validate_hash_value(value: str, field_name: str, *, allow_missing: bool) -> None:
    text = require_non_empty_str(value, field_name)
    if text == "missing" and allow_missing:
        return
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", text):
        raise ContractValidationError(f"{field_name} must be sha256:*")


def _validate_hash_map(value: dict[str, str], field_name: str, *, allow_missing: bool = False) -> None:
    for ref, digest in value.items():
        validate_ref(ref, f"{field_name}.ref")
        _validate_hash_value(digest, f"{field_name}.{ref}", allow_missing=allow_missing)


def _require_string_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = require_mapping(value, field_name)
    result: dict[str, str] = {}
    for key, item in data.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, str) or not item.strip():
            raise ContractValidationError(f"{field_name} must be a mapping of non-empty strings")
        result[key.strip()] = item.strip()
    return result


def _require_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ContractValidationError(f"{field_name} must be a list of non-empty strings")
    return [item.strip() for item in value]


__all__ = [
    "FRONTDESK_NODE_NAMES",
    "FrontDeskPiNodeContract",
    "FrontDeskPiNodeExecutionRecord",
    "FrontDeskPiNodeRunResult",
    "FrontDeskPiNodeRunner",
    "frontdesk_pi_node_execution_ref",
    "frontdesk_pi_node_spec_ref",
]
