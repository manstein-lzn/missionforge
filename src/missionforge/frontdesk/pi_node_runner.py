"""PiWorker boundary helpers for FrontDesk spec-grill nodes.

This module does not introduce a second worker abstraction and does not call a
live provider by default. It builds and validates bounded PiWorkerCall objects
for PiWorker-backed FrontDesk LLM nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from ..contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
    validate_ref,
)
from ..evidence_store import EvidenceLedger
from ..piworker_call import PiWorkerCall, PiWorkerCallResult, PiWorkerCallRole
from ..workers import WorkerAdapterResult
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


FRONTDESK_EXIT_CRITERIA = ["Expected output refs exist and validate against FrontDesk schemas."]
FRONTDESK_STOP_CONDITIONS = ["Do not approve, freeze, verify, run, or mutate frozen contracts."]


class FrontDeskPiWorkerAdapter(Protocol):
    """Minimal FrontDesk PiWorker adapter boundary."""

    adapter_family: str

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
    ) -> WorkerAdapterResult:
        """Execute one bounded FrontDesk PiWorker call."""
        ...


@dataclass(frozen=True)
class FrontDeskPiNodeContract:
    """Bounded contract for one PiWorker-backed FrontDesk node."""

    node_name: str
    session_id: str
    call: PiWorkerCall

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrontDeskPiNodeContract":
        data = require_mapping(payload, "frontdesk_pi_node_contract")
        contract = cls(
            node_name=require_non_empty_str(data.get("node_name"), "frontdesk_pi_node_contract.node_name"),
            session_id=require_non_empty_str(data.get("session_id"), "frontdesk_pi_node_contract.session_id"),
            call=PiWorkerCall.from_dict(require_mapping(data.get("call"), "frontdesk_pi_node_contract.call")),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if self.node_name not in FRONTDESK_NODE_NAMES:
            raise ContractValidationError("frontdesk_pi_node_contract.node_name is unsupported")
        require_non_empty_str(self.session_id, "frontdesk_pi_node_contract.session_id")
        self.call.validate()
        if self.call.role != PiWorkerCallRole.FRONTDESK_AUTHOR:
            raise ContractValidationError("frontdesk_pi_node_contract.call must be a FrontDesk author PiWorker call")
        for ref in self.call.visible_refs:
            validate_ref(ref, "frontdesk_pi_node_contract.visible_refs[]")
        for ref in self.call.expected_output_refs:
            _require_frontdesk_output_ref(ref)
        for ref in self.call.writable_refs:
            _require_frontdesk_output_ref(ref)
        assert_refs_only_payload(self.to_dict_without_validation(), "frontdesk_pi_node_contract")

    def to_dict_without_validation(self) -> dict[str, object]:
        return {
            "node_name": self.node_name,
            "session_id": self.session_id,
            "call": self.call.to_dict(),
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
    call_hash: str
    piworker_call_result_ref: str
    piworker_call_result_hash: str
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
        _validate_hash(self.call_hash, "frontdesk_pi_node_execution.call_hash")
        validate_ref(self.piworker_call_result_ref, "frontdesk_pi_node_execution.piworker_call_result_ref")
        _validate_hash(self.piworker_call_result_hash, "frontdesk_pi_node_execution.piworker_call_result_hash")
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
            call_hash=require_non_empty_str(
                data.get("call_hash"),
                "frontdesk_pi_node_execution.call_hash",
            ),
            piworker_call_result_ref=validate_ref(
                data.get("piworker_call_result_ref"),
                "frontdesk_pi_node_execution.piworker_call_result_ref",
            ),
            piworker_call_result_hash=require_non_empty_str(
                data.get("piworker_call_result_hash"),
                "frontdesk_pi_node_execution.piworker_call_result_hash",
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
            "call_hash": self.call_hash,
            "piworker_call_result_ref": self.piworker_call_result_ref,
            "piworker_call_result_hash": self.piworker_call_result_hash,
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
        node_spec_ref: str | None = None,
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
        safe_node_spec_ref = validate_ref(
            node_spec_ref or _node_spec_ref(session_id=session_id, node_name=node_name),
            "frontdesk_pi_node.node_spec_ref",
        )
        call = _frontdesk_piworker_call(
            node_name=node_name,
            session_id=session_id,
            node_spec_ref=safe_node_spec_ref,
            visible_refs=visible_refs,
            expected_outputs=expected_outputs,
            allowed_outputs=allowed_outputs,
        )
        contract = FrontDeskPiNodeContract(node_name=node_name, session_id=session_id, call=call)
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
        worker: FrontDeskPiWorkerAdapter | None = None,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
        product_profile_hash: str = "",
    ) -> FrontDeskPiNodeRunResult:
        """Run one node through an explicitly supplied PiWorker-compatible adapter."""

        if worker is None:
            raise ContractValidationError("frontdesk pi node execution requires an explicit PiWorker adapter")
        _validate_frontdesk_piworker_adapter(worker)
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
                "Use conversation refs as FrontDesk elicitation evidence for pain, constraints, inferences, and questions.",
                "Do not copy raw conversation text or cite raw conversation refs as runtime/product truth.",
            ],
            "guidance": _node_guidance(
                node_name=node_name,
                session_id=session_id,
                expected_outputs=expected_outputs,
                optional_outputs=optional_outputs or [],
            ),
        }
        active_workspace.write_json(node_spec_ref, node_spec)
        contract_visible_refs = _dedupe_refs([node_spec_ref, *visible_refs])
        contract = self.build_contract(
            node_name=node_name,
            session_id=session_id,
            visible_refs=contract_visible_refs,
            expected_outputs=expected_outputs,
            optional_outputs=optional_outputs,
            node_spec_ref=node_spec_ref,
        )
        input_hashes = _hash_visible_refs(active_workspace, contract.call.visible_refs)
        worker_result = worker.run_call(
            contract.call,
            workspace=workspace,
            evidence_store=evidence_store,
            exit_criteria=list(FRONTDESK_EXIT_CRITERIA),
            stop_conditions=list(FRONTDESK_STOP_CONDITIONS),
        )
        worker_result.validate()
        assert_refs_only_payload(worker_result.to_dict(), "frontdesk_pi_node_worker_result")
        produced_refs = list(worker_result.execution_report.produced_artifacts)
        self.validate_produced_refs(contract, produced_refs)
        output_hashes = {ref: _hash_ref(active_workspace, ref) for ref in produced_refs}
        call_result = PiWorkerCallResult.from_worker_adapter_result(contract.call, worker_result)
        call_result_ref = _node_call_result_ref(session_id=session_id, node_name=node_name)
        active_workspace.write_json(call_result_ref, call_result.to_dict())

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
            call_hash=stable_json_hash(contract.call.to_dict()),
            piworker_call_result_ref=call_result_ref,
            piworker_call_result_hash=_hash_ref(active_workspace, call_result_ref),
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
        missing = sorted(set(contract.call.expected_output_refs) - set(produced_refs))
        if missing:
            raise ContractValidationError(f"frontdesk pi node missing expected output(s): {', '.join(missing)}")
        extra = sorted(set(produced_refs) - set(contract.call.writable_refs))
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
        if stable_json_hash(record.contract.call.to_dict()) != record.call_hash:
            raise ContractValidationError("frontdesk PiWorker call hash does not match execution record")
        if _hash_ref(active_workspace, record.node_spec_ref) != record.node_spec_hash:
            raise ContractValidationError("frontdesk PiWorker node spec hash is stale")
        if _hash_ref(active_workspace, record.piworker_call_result_ref) != record.piworker_call_result_hash:
            raise ContractValidationError("frontdesk PiWorker call result hash is stale")
        call_result = PiWorkerCallResult.from_dict(active_workspace.read_json(record.piworker_call_result_ref))
        call_result.validate_against_call(record.contract.call)
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


def _validate_frontdesk_piworker_adapter(worker: object) -> None:
    if getattr(worker, "adapter_family", "") != "piworker":
        raise ContractValidationError("frontdesk pi node execution requires an explicit PiWorker-compatible adapter")
    if not callable(getattr(worker, "run_call", None)):
        raise ContractValidationError("frontdesk pi node execution requires a PiWorker run_call adapter")


def _frontdesk_node_contract_hash(
    *,
    node_name: str,
    session_id: str,
    node_spec_ref: str,
    visible_refs: list[str],
    expected_outputs: list[str],
    allowed_outputs: list[str],
) -> str:
    return stable_json_hash(
        {
            "schema_version": "missionforge.frontdesk.pi_node_call_authority.v1",
            "node_name": node_name,
            "session_id": session_id,
            "node_spec_ref": validate_ref(node_spec_ref, "frontdesk_pi_node.node_spec_ref"),
            "visible_refs": [validate_ref(ref, "frontdesk_pi_node.visible_refs[]") for ref in visible_refs],
            "expected_outputs": [_require_frontdesk_output_ref(ref) for ref in expected_outputs],
            "allowed_outputs": [_require_frontdesk_output_ref(ref) for ref in allowed_outputs],
        }
    )


def _node_spec_ref(*, session_id: str, node_name: str) -> str:
    return f"frontdesk/pi_nodes/{_safe_ref_fragment(session_id)}/{_safe_ref_fragment(node_name)}/node_spec.json"


def _node_execution_ref(*, session_id: str, node_name: str) -> str:
    return f"frontdesk/pi_nodes/{_safe_ref_fragment(session_id)}/{_safe_ref_fragment(node_name)}/execution.json"


def _node_call_result_ref(*, session_id: str, node_name: str) -> str:
    return f"frontdesk/pi_nodes/{_safe_ref_fragment(session_id)}/{_safe_ref_fragment(node_name)}/piworker_call_result.json"


def _frontdesk_piworker_call(
    *,
    node_name: str,
    session_id: str,
    node_spec_ref: str,
    visible_refs: list[str],
    expected_outputs: list[str],
    allowed_outputs: list[str],
) -> PiWorkerCall:
    return PiWorkerCall(
        call_id=f"frontdesk-{session_id}-{node_name}",
        role=PiWorkerCallRole.FRONTDESK_AUTHOR,
        contract_id=f"frontdesk-{session_id}",
        contract_hash=_frontdesk_node_contract_hash(
            node_name=node_name,
            session_id=session_id,
            node_spec_ref=node_spec_ref,
            visible_refs=visible_refs,
            expected_outputs=expected_outputs,
            allowed_outputs=allowed_outputs,
        ),
        contract_ref=node_spec_ref,
        objective=f"Produce structured {node_name} output JSON only.",
        visible_refs=_dedupe_refs([node_spec_ref, *visible_refs]),
        writable_refs=allowed_outputs,
        expected_output_refs=list(expected_outputs),
        source_packet_ref=node_spec_ref,
        metadata={"frontdesk_node_name": node_name},
    )


def _node_guidance(
    *,
    node_name: str,
    session_id: str,
    expected_outputs: list[str] | None = None,
    optional_outputs: list[str] | None = None,
) -> dict[str, Any]:
    expected_output_set = set(expected_outputs or [])
    optional_output_set = set(optional_outputs or [])
    core_need_required = "frontdesk/core_need_brief.json" in expected_output_set
    guidance: dict[str, Any] = {
        "session_id": session_id,
        "execution_policy": {
            "core_need_brief_required": core_need_required,
            "core_need_brief_optional": "frontdesk/core_need_brief.json" in optional_output_set,
        },
        "conversation_policy": {
            "may_use": [
                "Use frontdesk/conversation.jsonl and frontdesk/turns/* as elicitation evidence.",
                "Infer the user's pain, constraints, candidate answers, and next high-value question from conversation evidence.",
            ],
            "must_not": [
                "Do not copy raw conversation text into runtime-facing or product-facing artifacts.",
                "Do not list frontdesk/conversation.jsonl or frontdesk/turns/* as product/runtime source_refs.",
                "Do not treat hidden prompts, provider payloads, credentials, or transcripts as admissible product content.",
            ],
        },
        "format_rules": [
            "Write valid JSON for JSON outputs.",
            "Use only the expected or optional output refs declared in this node spec.",
            "Use exact schema_version values and exact enum values.",
        ],
    }
    if node_name == "need_griller":
        guidance["role"] = (
            "Act as a restrained requirements interviewer. If the conversation already contains enough information, "
            "produce a core need brief instead of asking a generic follow-up."
        )
        guidance["schema_hints"] = {
            "frontdesk/decision_tree.json": {
                "schema_version": "missionforge.frontdesk_decision_tree.v1",
                "required_fields": ["schema_version", "session_id", "decisions"],
                "decision_fields": [
                    "decision_id",
                    "topic",
                    "status",
                    "current_hypothesis",
                    "options",
                    "blocking",
                    "source_refs",
                    "chosen_option_id",
                ],
                "decision_option_fields": ["option_id", "summary"],
                "decision_status_values": ["open", "confirmed", "rejected", "deferred"],
            },
            "frontdesk/need_grilling_report.json": {
                "schema_version": "missionforge.frontdesk_need_grilling_report.v1",
                "required_fields": [
                    "schema_version",
                    "session_id",
                    "readiness",
                    "observations",
                    "inferences",
                    "confirmed_requirements",
                    "open_decision_ids",
                    "next_question",
                    "decision_tree_ref",
                    "core_need_brief_ref",
                ],
                "readiness_values": [
                    "needs_clarification",
                    "core_need_ready",
                    "human_review_required",
                    "failed_closed",
                ],
                "readiness_rules": [
                    "needs_clarification requires next_question.",
                    "core_need_ready requires core_need_brief_ref and frontdesk/core_need_brief.json.",
                    "failed_closed is only for unsafe or impossible sessions, not for merely excluded raw conversation refs.",
                    "When execution_policy.core_need_brief_required is true, treat the run as a no-user-loop handoff: choose core_need_ready whenever the evidence can support a safe assumption-backed brief.",
                    "In a no-user-loop handoff, do not block only because extra personalization would improve quality; record assumptions and non-blocking unknowns in frontdesk/core_need_brief.json instead.",
                ],
                "next_question_fields": [
                    "question_id",
                    "inference",
                    "recommended_answer",
                    "question",
                    "why_this_matters",
                    "blocks_freeze",
                    "expected_answer_type",
                    "related_decision_ids",
                    "choices",
                ],
                "next_question_expected_answer_type_values": [
                    "choice_or_free_text",
                    "ranked_choices_or_free_text",
                    "free_text",
                    "enum",
                    "boolean",
                    "number",
                    "file",
                    "example",
                ],
            },
            "frontdesk/core_need_brief.json": {
                "schema_version": "missionforge.frontdesk_core_need_brief.v1",
                "required_when": "Write this optional output when readiness is core_need_ready.",
                "required_fields": [
                    "schema_version",
                    "session_id",
                    "core_pain",
                    "target_users",
                    "usage_moment",
                    "deliverable_type",
                    "desired_outcome",
                    "success_signals",
                    "constraints",
                    "non_goals",
                    "source_refs",
                ],
                "optional_fields": ["assumptions", "open_questions"],
                "open_question_fields": ["question_id", "question", "impact"],
                "open_question_policy": (
                    "Only include non-blocking refinement questions here. Blocking questions must use "
                    "need_grilling_report.next_question with readiness needs_clarification."
                ),
            },
        }
    elif node_name == "solution_architect":
        guidance["role"] = "Act as a senior product architect over already structured FrontDesk need artifacts."
        guidance["schema_hints"] = {
            "frontdesk/solution_plan.json": {
                "schema_version": "missionforge.frontdesk_solution_plan.v1",
                "required_fields": [
                    "schema_version",
                    "session_id",
                    "status",
                    "summary",
                    "core_need_ref",
                    "mvp_scope",
                    "future_scope",
                    "rejected_directions",
                    "expected_artifacts",
                    "selected_capability_profile_ids",
                    "selected_verification_profile_ids",
                    "verification_strategy",
                    "risks",
                    "authority_requirements",
                    "source_refs",
                ],
                "status_values": ["draft", "awaiting_review", "approved", "revision_requested", "rejected"],
                "string_list_fields": [
                    "mvp_scope",
                    "future_scope",
                    "rejected_directions",
                    "expected_artifacts",
                    "selected_capability_profile_ids",
                    "selected_verification_profile_ids",
                    "verification_strategy",
                    "risks",
                    "authority_requirements",
                    "source_refs",
                ],
                "field_rules": [
                    "mvp_scope, future_scope, rejected_directions, verification_strategy, risks, and authority_requirements must be arrays of strings, not arrays of objects.",
                    "expected_artifacts and source_refs must be arrays of safe ref strings such as package/SKILL.md or frontdesk/core_need_brief.json.",
                ],
            },
            "frontdesk/plan_risk_register.json": {
                "schema_version": "missionforge.frontdesk_plan_risk_register.v1",
                "required_fields": ["schema_version", "session_id", "risks", "mitigations", "source_refs"],
                "string_list_fields": ["risks", "mitigations", "source_refs"],
                "field_rules": [
                    "risks and mitigations must be arrays of strings, not arrays of objects.",
                    "source_refs must be an array of safe ref strings.",
                ],
            },
            "frontdesk/profile_recommendations.json": {
                "schema_version": "missionforge.frontdesk_profile_recommendations.v1",
                "required_fields": ["schema_version", "session_id", "recommendations", "rejected_profile_ids"],
                "recommendation_fields": ["schema_version", "profile_id", "kind", "rationale", "requirements", "selected"],
                "kind_values": ["capability", "verification"],
                "field_rules": [
                    "recommendations must be an array of objects.",
                    "Each recommendation.requirements must be a JSON object, not an array; put bullet-like requirements under keys such as required_outputs or checks.",
                    "rejected_profile_ids must be an array of strings.",
                ],
            },
            "frontdesk/mission_plan.json": {
                "schema_version": "missionforge.frontdesk_mission_plan.v1",
                "required_fields": [
                    "schema_version",
                    "session_id",
                    "expected_artifacts",
                    "constraints",
                    "validators",
                    "manual_gates",
                    "risk_notes",
                ],
                "field_rules": [
                    "expected_artifacts must be an array of safe ref strings, not objects.",
                    "constraints, validators, and manual_gates must be arrays of JSON objects.",
                    "risk_notes must be an array of strings.",
                ],
            },
            "frontdesk/solution_plan.md": {
                "format": "Concise Markdown summary of the solution plan; do not include raw conversation text.",
            },
        }
    elif node_name == "intent_bundle_author":
        guidance["role"] = (
            "Convert structured FrontDesk artifacts plus ProductInquiryProfile into a product-aware "
            "FrontDeskIntentBundle candidate."
        )
        guidance["schema_hints"] = {
            "frontdesk/intent_bundle_candidate.json": {
                "schema_version": "missionforge.frontdesk.intent_bundle.v1",
                "required_fields": [
                    "schema_version",
                    "session_id",
                    "intent_bundle_ref",
                    "generic_refs",
                    "product_context",
                    "slot_values",
                    "product_hypotheses",
                    "risk_flags",
                    "missing_blocking_slots",
                    "readiness",
                    "clarification_questions",
                    "evidence_refs",
                ],
                "candidate_rules": [
                    "intent_bundle_ref must be frontdesk/intent_bundle_candidate.json in the candidate.",
                    "product_context.product_id and product_context.profile_hash must match frontdesk/product_inquiry_profile.json.",
                    "slot_values must contain exactly every ProductInquiryProfile slot_id.",
                    "source_refs must obey ProductInquiryProfile.source_policy.allowed_source_refs and excluded_source_refs.",
                    "Infer slot values from structured FrontDesk refs when evidence is sufficient; do not mark a slot missing solely because raw conversation refs are excluded.",
                ],
                "field_rules": [
                    "All confidence fields are strings such as high, medium, low, inferred, confirmed, or assumed; do not use numeric confidence values.",
                    "Missing optional ref fields must be empty strings, not null.",
                    "All source_refs, evidence_refs, missing_blocking_slots, and clarification_questions fields are arrays of strings.",
                ],
                "product_context_fields": ["product_id", "display_name", "profile_ref", "profile_hash", "version"],
                "generic_refs_fields": [
                    "session_ref",
                    "workspace_facts_ref",
                    "source_admission_report_ref",
                    "core_need_brief_ref",
                    "sanitized_sources_ref",
                    "semantic_lock_ref",
                    "mission_brief_ref",
                    "semantic_coverage_ref",
                    "solution_plan_ref",
                    "mission_plan_ref",
                    "mission_mapping_report_ref",
                    "draft_mission_ref",
                ],
                "slot_value_fields": ["slot_id", "status", "value", "confidence", "source_refs", "question"],
                "slot_status_values": ["confirmed", "inferred", "assumed", "missing", "rejected", "not_applicable"],
                "slot_value_type_rules": [
                    "free_text values are strings.",
                    "enum values must be one of the slot.choices in frontdesk/product_inquiry_profile.json.",
                    "string_list, ref_list, and artifact_path_list values are arrays of strings.",
                    "ref and artifact_path values are safe ref strings.",
                    "missing status requires a clarification question.",
                ],
                "product_hypothesis_fields": ["hypothesis_id", "statement", "confidence", "source_refs"],
                "risk_flag_fields": ["risk_id", "status", "rationale", "source_refs"],
                "risk_status_values": ["observed", "inferred", "not_observed", "needs_review"],
                "readiness_values": [
                    "needs_clarification",
                    "ready_for_product_compile",
                    "generic_compile_only",
                    "unsupported_product",
                    "human_review_required",
                    "failed_closed",
                ],
            },
        }
    elif node_name == "mission_ir_mapper":
        guidance["role"] = "Map approved structured FrontDesk artifacts into draft MissionIR refs only."
        guidance["schema_hints"] = {
            "mapping_policy": [
                "Do not invent product compiler behavior.",
                "Prefer product integration compile output when a ProductIntegration is present.",
                "Keep raw conversation and provider payloads out of MissionIR.",
            ]
        }
    elif node_name == "mission_ir_auditor":
        guidance["role"] = "Audit draft MissionIR against structured FrontDesk artifacts and product boundaries."
        guidance["schema_hints"] = {
            "audit_policy": [
                "Route to clarification or human review when product/domain authority is missing.",
                "Do not freeze or approve contracts from this node.",
            ]
        }
    return guidance


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
    "FrontDeskPiWorkerAdapter",
    "FrontDeskPiNodeRunner",
    "frontdesk_pi_node_execution_ref",
    "frontdesk_pi_node_spec_ref",
]
