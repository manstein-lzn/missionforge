"""Decision ledger, final package, and replay contracts for TaskContract flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_enum,
    require_mapping,
    require_non_empty_str,
    stable_json_hash,
    validate_ref,
)


DECISION_LEDGER_ENTRY_SCHEMA_VERSION = "decision_ledger_entry.v1"
FINAL_PACKAGE_SCHEMA_VERSION = "final_package.v1"
RUN_REPLAY_SUMMARY_SCHEMA_VERSION = "run_replay_summary.v1"
_JUDGE_ACCEPTED = "accepted"
_JUDGE_REPAIR = "repair"
_JUDGE_REVISION_REQUIRED = "revision_required"
_JUDGE_REJECTED = "rejected"


class DecisionLedgerEventKind(StrEnum):
    """Append-only TaskContract flow ledger event kinds."""

    CONTRACT_FROZEN = "contract_frozen"
    PROJECTION_WRITTEN = "projection_written"
    EXECUTION_PACKET_ISSUED = "execution_packet_issued"
    EXECUTION_REPORT_RECORDED = "execution_report_recorded"
    HARD_CHECKS_RECORDED = "hard_checks_recorded"
    JUDGE_PACKET_ISSUED = "judge_packet_issued"
    JUDGE_REPORT_RECORDED = "judge_report_recorded"
    REPAIR_REQUESTED = "repair_requested"
    REPAIR_EXECUTION_RECORDED = "repair_execution_recorded"
    REVISION_REQUESTED = "revision_requested"
    REVISION_DRAFT_RECORDED = "revision_draft_recorded"
    REVISION_APPLIED = "revision_applied"
    REVISION_JUDGE_REPORT_RECORDED = "revision_judge_report_recorded"
    FINAL_PACKAGE_EMITTED = "final_package_emitted"


class RunReplayStatus(StrEnum):
    """Replay-derived run status."""

    ACCEPTED = "accepted"
    REPAIR = "repair"
    REVISION_REQUIRED = "revision_required"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TaskContractDecisionLedgerEntry:
    """Refs-first append-only ledger entry for one TaskContract runtime event."""

    entry_id: str
    run_id: str
    event_kind: DecisionLedgerEventKind
    contract_id: str
    contract_hash: str
    ref_map: Mapping[str, str]
    created_at: str = ""
    status: str | None = None
    content_hashes: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = DECISION_LEDGER_ENTRY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TaskContractDecisionLedgerEntry":
        data = _strict_mapping(
            payload,
            "decision_ledger_entry",
            {
                "schema_version",
                "entry_id",
                "created_at",
                "run_id",
                "event_kind",
                "contract_id",
                "contract_hash",
                "status",
                "ref_map",
                "content_hashes",
            },
        )
        entry = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", DECISION_LEDGER_ENTRY_SCHEMA_VERSION),
                "decision_ledger_entry.schema_version",
            ),
            entry_id=require_non_empty_str(data.get("entry_id"), "decision_ledger_entry.entry_id"),
            created_at=str(data.get("created_at", "")),
            run_id=require_non_empty_str(data.get("run_id"), "decision_ledger_entry.run_id"),
            event_kind=require_enum(
                data.get("event_kind"),
                DecisionLedgerEventKind,
                "decision_ledger_entry.event_kind",
            ),
            contract_id=require_non_empty_str(data.get("contract_id"), "decision_ledger_entry.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "decision_ledger_entry.contract_hash"),
            status=_optional_str(data.get("status"), "decision_ledger_entry.status"),
            ref_map=_ref_mapping(data.get("ref_map", {}), "decision_ledger_entry.ref_map"),
            content_hashes=_hash_mapping(
                data.get("content_hashes", {}),
                "decision_ledger_entry.content_hashes",
            ),
        )
        entry.validate()
        return entry

    def validate(self) -> None:
        _require_schema(
            self.schema_version,
            DECISION_LEDGER_ENTRY_SCHEMA_VERSION,
            "decision_ledger_entry.schema_version",
        )
        require_non_empty_str(self.entry_id, "decision_ledger_entry.entry_id")
        require_non_empty_str(self.run_id, "decision_ledger_entry.run_id")
        require_enum(self.event_kind, DecisionLedgerEventKind, "decision_ledger_entry.event_kind")
        require_non_empty_str(self.contract_id, "decision_ledger_entry.contract_id")
        _validate_hash(self.contract_hash, "decision_ledger_entry.contract_hash")
        _ref_mapping(self.ref_map, "decision_ledger_entry.ref_map")
        _hash_mapping(self.content_hashes, "decision_ledger_entry.content_hashes")
        _optional_str(self.status, "decision_ledger_entry.status")
        assert_refs_only_payload(self.to_dict_without_validation(), "decision_ledger_entry")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "created_at": self.created_at,
            "run_id": self.run_id,
            "event_kind": self.event_kind.value,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "status": self.status,
            "ref_map": dict(self.ref_map),
            "content_hashes": dict(self.content_hashes),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class FinalPackage:
    """Refs-only handoff package for an accepted TaskContract run."""

    package_id: str
    run_id: str
    contract_id: str
    contract_hash: str
    contract_ref: str
    judge_report_ref: str
    decision_ledger_ref: str
    accepted_artifact_refs: list[str]
    hard_check_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    product_payload_refs: list[str] = field(default_factory=list)
    schema_version: str = FINAL_PACKAGE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FinalPackage":
        data = _strict_mapping(
            payload,
            "final_package",
            {
                "schema_version",
                "package_id",
                "run_id",
                "contract_id",
                "contract_hash",
                "contract_ref",
                "judge_report_ref",
                "decision_ledger_ref",
                "accepted_artifact_refs",
                "hard_check_refs",
                "metric_refs",
                "product_payload_refs",
            },
        )
        package = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", FINAL_PACKAGE_SCHEMA_VERSION),
                "final_package.schema_version",
            ),
            package_id=require_non_empty_str(data.get("package_id"), "final_package.package_id"),
            run_id=require_non_empty_str(data.get("run_id"), "final_package.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "final_package.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "final_package.contract_hash"),
            contract_ref=validate_ref(data.get("contract_ref"), "final_package.contract_ref"),
            judge_report_ref=validate_ref(data.get("judge_report_ref"), "final_package.judge_report_ref"),
            decision_ledger_ref=validate_ref(
                data.get("decision_ledger_ref"),
                "final_package.decision_ledger_ref",
            ),
            accepted_artifact_refs=_ref_list(
                data.get("accepted_artifact_refs", []),
                "final_package.accepted_artifact_refs",
            ),
            hard_check_refs=_ref_list(data.get("hard_check_refs", []), "final_package.hard_check_refs"),
            metric_refs=_ref_list(data.get("metric_refs", []), "final_package.metric_refs"),
            product_payload_refs=_ref_list(
                data.get("product_payload_refs", []),
                "final_package.product_payload_refs",
            ),
        )
        package.validate()
        return package

    def validate(self) -> None:
        _require_schema(self.schema_version, FINAL_PACKAGE_SCHEMA_VERSION, "final_package.schema_version")
        require_non_empty_str(self.package_id, "final_package.package_id")
        require_non_empty_str(self.run_id, "final_package.run_id")
        require_non_empty_str(self.contract_id, "final_package.contract_id")
        _validate_hash(self.contract_hash, "final_package.contract_hash")
        validate_ref(self.contract_ref, "final_package.contract_ref")
        validate_ref(self.judge_report_ref, "final_package.judge_report_ref")
        validate_ref(self.decision_ledger_ref, "final_package.decision_ledger_ref")
        if not _ref_list(self.accepted_artifact_refs, "final_package.accepted_artifact_refs"):
            raise ContractValidationError("final_package.accepted_artifact_refs must not be empty")
        _ref_list(self.hard_check_refs, "final_package.hard_check_refs")
        _ref_list(self.metric_refs, "final_package.metric_refs")
        _ref_list(self.product_payload_refs, "final_package.product_payload_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "final_package")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "contract_ref": self.contract_ref,
            "judge_report_ref": self.judge_report_ref,
            "decision_ledger_ref": self.decision_ledger_ref,
            "accepted_artifact_refs": list(self.accepted_artifact_refs),
            "hard_check_refs": list(self.hard_check_refs),
            "metric_refs": list(self.metric_refs),
            "product_payload_refs": list(self.product_payload_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


@dataclass(frozen=True)
class RunReplaySummary:
    """Replay-derived status summary from a refs-first decision ledger."""

    run_id: str
    contract_id: str
    contract_hash: str
    status: RunReplayStatus
    decision_ledger_ref: str
    ledger_tail_ref: str
    final_package_ref: str | None = None
    judge_report_ref: str | None = None
    repair_brief_ref: str | None = None
    revision_request_ref: str | None = None
    accepted_artifact_refs: list[str] = field(default_factory=list)
    schema_version: str = RUN_REPLAY_SUMMARY_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunReplaySummary":
        data = _strict_mapping(
            payload,
            "run_replay_summary",
            {
                "schema_version",
                "run_id",
                "contract_id",
                "contract_hash",
                "status",
                "decision_ledger_ref",
                "ledger_tail_ref",
                "final_package_ref",
                "judge_report_ref",
                "repair_brief_ref",
                "revision_request_ref",
                "accepted_artifact_refs",
            },
        )
        summary = cls(
            schema_version=require_non_empty_str(
                data.get("schema_version", RUN_REPLAY_SUMMARY_SCHEMA_VERSION),
                "run_replay_summary.schema_version",
            ),
            run_id=require_non_empty_str(data.get("run_id"), "run_replay_summary.run_id"),
            contract_id=require_non_empty_str(data.get("contract_id"), "run_replay_summary.contract_id"),
            contract_hash=_validate_hash(data.get("contract_hash"), "run_replay_summary.contract_hash"),
            status=require_enum(data.get("status"), RunReplayStatus, "run_replay_summary.status"),
            decision_ledger_ref=validate_ref(
                data.get("decision_ledger_ref"),
                "run_replay_summary.decision_ledger_ref",
            ),
            ledger_tail_ref=validate_ref(data.get("ledger_tail_ref"), "run_replay_summary.ledger_tail_ref"),
            final_package_ref=_optional_ref(data.get("final_package_ref"), "run_replay_summary.final_package_ref"),
            judge_report_ref=_optional_ref(data.get("judge_report_ref"), "run_replay_summary.judge_report_ref"),
            repair_brief_ref=_optional_ref(data.get("repair_brief_ref"), "run_replay_summary.repair_brief_ref"),
            revision_request_ref=_optional_ref(
                data.get("revision_request_ref"),
                "run_replay_summary.revision_request_ref",
            ),
            accepted_artifact_refs=_ref_list(
                data.get("accepted_artifact_refs", []),
                "run_replay_summary.accepted_artifact_refs",
            ),
        )
        summary.validate()
        return summary

    def validate(self) -> None:
        _require_schema(self.schema_version, RUN_REPLAY_SUMMARY_SCHEMA_VERSION, "run_replay_summary.schema_version")
        require_non_empty_str(self.run_id, "run_replay_summary.run_id")
        require_non_empty_str(self.contract_id, "run_replay_summary.contract_id")
        _validate_hash(self.contract_hash, "run_replay_summary.contract_hash")
        require_enum(self.status, RunReplayStatus, "run_replay_summary.status")
        validate_ref(self.decision_ledger_ref, "run_replay_summary.decision_ledger_ref")
        validate_ref(self.ledger_tail_ref, "run_replay_summary.ledger_tail_ref")
        _optional_ref(self.final_package_ref, "run_replay_summary.final_package_ref")
        _optional_ref(self.judge_report_ref, "run_replay_summary.judge_report_ref")
        _optional_ref(self.repair_brief_ref, "run_replay_summary.repair_brief_ref")
        _optional_ref(self.revision_request_ref, "run_replay_summary.revision_request_ref")
        _ref_list(self.accepted_artifact_refs, "run_replay_summary.accepted_artifact_refs")
        assert_refs_only_payload(self.to_dict_without_validation(), "run_replay_summary")

    def to_dict_without_validation(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "status": self.status.value,
            "decision_ledger_ref": self.decision_ledger_ref,
            "ledger_tail_ref": self.ledger_tail_ref,
            "final_package_ref": self.final_package_ref,
            "judge_report_ref": self.judge_report_ref,
            "repair_brief_ref": self.repair_brief_ref,
            "revision_request_ref": self.revision_request_ref,
            "accepted_artifact_refs": list(self.accepted_artifact_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return self.to_dict_without_validation()


def build_final_package(
    *,
    run_id: str,
    contract_id: str,
    contract_hash: str,
    contract_ref: str,
    judge_report_ref: str,
    decision_ledger_ref: str,
    accepted_artifact_refs: list[str],
    hard_check_refs: list[str] | None = None,
    metric_refs: list[str] | None = None,
    product_payload_refs: list[str] | None = None,
) -> FinalPackage:
    package = FinalPackage(
        package_id=f"final-package-{run_id}",
        run_id=run_id,
        contract_id=contract_id,
        contract_hash=contract_hash,
        contract_ref=contract_ref,
        judge_report_ref=judge_report_ref,
        decision_ledger_ref=decision_ledger_ref,
        accepted_artifact_refs=list(accepted_artifact_refs),
        hard_check_refs=list(hard_check_refs or []),
        metric_refs=list(metric_refs or []),
        product_payload_refs=list(product_payload_refs or []),
    )
    package.validate()
    return package


def replay_decision_ledger(root: str | Path, *, decision_ledger_ref: str) -> RunReplaySummary:
    """Replay a TaskContract flow decision ledger into a refs-only status."""

    ledger_ref = validate_ref(decision_ledger_ref, "decision_ledger_ref")
    ledger_path = _resolve_ref(root, ledger_ref)
    entries = _read_ledger_entries(ledger_path)
    if not entries:
        raise ContractValidationError("decision ledger is empty")
    _validate_ledger_sequence(entries)
    latest = entries[-1]
    final_package_ref: str | None = None
    accepted_artifact_refs: list[str] = []
    if latest.event_kind is DecisionLedgerEventKind.FINAL_PACKAGE_EMITTED:
        final_package_ref = _required_ref(latest.ref_map, "final_package_ref")
        package = FinalPackage.from_dict(_read_json_ref(root, final_package_ref))
        accepted_artifact_refs = list(package.accepted_artifact_refs)
        status = RunReplayStatus.ACCEPTED
    else:
        status = _status_from_tail(latest)
    summary = RunReplaySummary(
        run_id=latest.run_id,
        contract_id=latest.contract_id,
        contract_hash=latest.contract_hash,
        status=status,
        decision_ledger_ref=ledger_ref,
        ledger_tail_ref=ledger_ref,
        final_package_ref=final_package_ref,
        judge_report_ref=_optional_ref_from_map(latest.ref_map, "judge_report_ref"),
        repair_brief_ref=_optional_ref_from_map(latest.ref_map, "repair_brief_ref"),
        revision_request_ref=_optional_ref_from_map(latest.ref_map, "revision_request_ref"),
        accepted_artifact_refs=accepted_artifact_refs,
    )
    summary.validate()
    return summary


def append_decision_ledger_entry(root: str | Path, ledger_ref: str, entry: TaskContractDecisionLedgerEntry) -> str:
    """Append one validated entry to a workspace-relative decision ledger."""

    entry.validate()
    safe_ref = validate_ref(ledger_ref, "decision_ledger_ref")
    path = _resolve_ref(root, safe_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
    return safe_ref


def next_ledger_entry_id(entries: list[TaskContractDecisionLedgerEntry]) -> str:
    return f"ledger-entry-{len(entries) + 1:06d}"


def read_decision_ledger(root: str | Path, *, decision_ledger_ref: str) -> list[TaskContractDecisionLedgerEntry]:
    return _read_ledger_entries(_resolve_ref(root, validate_ref(decision_ledger_ref, "decision_ledger_ref")))


def _read_ledger_entries(path: Path) -> list[TaskContractDecisionLedgerEntry]:
    if not path.is_file():
        raise ContractValidationError(f"decision ledger ref is missing: {path}")
    entries: list[TaskContractDecisionLedgerEntry] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractValidationError(f"decision ledger line {index} is invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractValidationError(f"decision ledger line {index} must be an object")
        entries.append(TaskContractDecisionLedgerEntry.from_dict(payload))
    return entries


def _validate_ledger_sequence(entries: list[TaskContractDecisionLedgerEntry]) -> None:
    first = entries[0]
    current_contract_hash = first.contract_hash
    for entry in entries:
        if entry.run_id != first.run_id:
            raise ContractValidationError("decision ledger contains multiple run_id values")
        if entry.contract_id != first.contract_id:
            raise ContractValidationError("decision ledger contains multiple contract_id values")
        if entry.contract_hash != current_contract_hash:
            if entry.event_kind is not DecisionLedgerEventKind.REVISION_APPLIED:
                raise ContractValidationError("decision ledger contract_hash changed without revision_applied")
            _required_ref(entry.ref_map, "revision_applied_ref")
            _required_ref(entry.ref_map, "task_contract_revision_ref")
            current_contract_hash = entry.contract_hash
        elif entry.event_kind is DecisionLedgerEventKind.REVISION_APPLIED:
            raise ContractValidationError("revision_applied ledger entry must change contract_hash")


def _status_from_tail(entry: TaskContractDecisionLedgerEntry) -> RunReplayStatus:
    if entry.event_kind is DecisionLedgerEventKind.JUDGE_REPORT_RECORDED:
        if entry.status == _JUDGE_ACCEPTED or entry.status == RunReplayStatus.ACCEPTED.value:
            return RunReplayStatus.ACCEPTED
        if entry.status == _JUDGE_REPAIR or entry.status == RunReplayStatus.REPAIR.value:
            return RunReplayStatus.REPAIR
        if entry.status == _JUDGE_REVISION_REQUIRED or entry.status == RunReplayStatus.REVISION_REQUIRED.value:
            return RunReplayStatus.REVISION_REQUIRED
        if entry.status == _JUDGE_REJECTED or entry.status == RunReplayStatus.REJECTED.value:
            return RunReplayStatus.REJECTED
    if entry.event_kind is DecisionLedgerEventKind.REVISION_JUDGE_REPORT_RECORDED:
        if entry.status == _JUDGE_ACCEPTED or entry.status == RunReplayStatus.ACCEPTED.value:
            return RunReplayStatus.ACCEPTED
        if entry.status == _JUDGE_REPAIR or entry.status == RunReplayStatus.REPAIR.value:
            return RunReplayStatus.REPAIR
        if entry.status == _JUDGE_REVISION_REQUIRED or entry.status == RunReplayStatus.REVISION_REQUIRED.value:
            return RunReplayStatus.REVISION_REQUIRED
        if entry.status == _JUDGE_REJECTED or entry.status == RunReplayStatus.REJECTED.value:
            return RunReplayStatus.REJECTED
    if entry.event_kind is DecisionLedgerEventKind.REPAIR_REQUESTED:
        return RunReplayStatus.REPAIR
    if entry.event_kind is DecisionLedgerEventKind.REPAIR_EXECUTION_RECORDED:
        return RunReplayStatus.REPAIR if entry.status == "completed" else RunReplayStatus.BLOCKED
    if entry.event_kind is DecisionLedgerEventKind.REVISION_REQUESTED:
        return RunReplayStatus.REVISION_REQUIRED
    if entry.event_kind is DecisionLedgerEventKind.REVISION_DRAFT_RECORDED:
        return RunReplayStatus.REVISION_REQUIRED if entry.status == "completed" else RunReplayStatus.BLOCKED
    if entry.event_kind is DecisionLedgerEventKind.REVISION_APPLIED:
        return RunReplayStatus.REVISION_REQUIRED
    return RunReplayStatus.BLOCKED


def _strict_mapping(value: Mapping[str, Any], field_name: str, allowed: set[str]) -> dict[str, Any]:
    data = require_mapping(value, field_name)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"{field_name} contains unknown fields: {unknown}")
    return data


def _ref_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = require_mapping(value, field_name)
    refs: dict[str, str] = {}
    for key, item in data.items():
        require_non_empty_str(key, f"{field_name}.key")
        refs[str(key)] = validate_ref(item, f"{field_name}.{key}")
    return refs


def _hash_mapping(value: Any, field_name: str) -> dict[str, str]:
    data = require_mapping(value, field_name)
    hashes: dict[str, str] = {}
    for key, item in data.items():
        validate_ref(str(key), f"{field_name}.key")
        hashes[str(key)] = _validate_hash(item, f"{field_name}.{key}")
    return hashes


def _ref_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    refs = [validate_ref(item, f"{field_name}[]") for item in value]
    if len(refs) != len(set(refs)):
        raise ContractValidationError(f"{field_name} must not contain duplicate refs")
    return refs


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _optional_ref_from_map(ref_map: Mapping[str, str], key: str) -> str | None:
    value = ref_map.get(key)
    if value is None:
        return None
    return validate_ref(value, f"ref_map.{key}")


def _required_ref(ref_map: Mapping[str, str], key: str) -> str:
    value = ref_map.get(key)
    if value is None:
        raise ContractValidationError(f"ref_map.{key} is required")
    return validate_ref(value, f"ref_map.{key}")


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"unsupported {field_name}: {actual}")


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix):]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _read_json_ref(root: str | Path, ref: str) -> dict[str, Any]:
    path = _resolve_ref(root, validate_ref(ref, "json_ref"))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractValidationError(f"json ref is missing: {ref}") from exc
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"json ref is invalid: {ref}") from exc
    return require_mapping(payload, ref)


def _resolve_ref(root: str | Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "ref")
    root_path = Path(root).resolve()
    path = (root_path / safe_ref).resolve()
    if path != root_path and root_path not in path.parents:
        raise ContractValidationError("ref escapes root")
    return path


__all__ = [
    "TaskContractDecisionLedgerEntry",
    "DecisionLedgerEventKind",
    "FinalPackage",
    "RunReplayStatus",
    "RunReplaySummary",
    "append_decision_ledger_entry",
    "build_final_package",
    "read_decision_ledger",
    "replay_decision_ledger",
]
