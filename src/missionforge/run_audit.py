"""Refs-only long-run audit helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from .freeze import FrozenMissionContract
from .json_store import JsonWorkspaceStore
from .metric_store import MetricStore
from .state import MissionRun, mission_run_refs_for_run_id


RUN_AUDIT_SCHEMA_VERSION = "missionforge.run_audit.v1"


@dataclass(frozen=True)
class MissionRunAudit:
    """Compact refs-only audit for a durable MissionRun."""

    mission_run_id: str
    mission_id: str
    status: str
    passed: bool
    run_ref: str
    current_contract_ref: str = ""
    current_contract_hash: str = ""
    revision_refs: list[str] = field(default_factory=list)
    metric_events_ref: str = ""
    metric_projection_ref: str = ""
    safe_point_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    ref_checks: list[dict[str, str]] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)
    stale_refs: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    schema_version: str = RUN_AUDIT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRunAudit":
        data = require_mapping(payload, "mission_run_audit")
        if data.get("schema_version") != RUN_AUDIT_SCHEMA_VERSION:
            raise ContractValidationError("mission_run_audit.schema_version is unsupported")
        audit = cls(
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "mission_run_audit.mission_run_id"),
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_run_audit.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_run_audit.status"),
            passed=data.get("passed"),
            run_ref=validate_ref(data.get("run_ref"), "mission_run_audit.run_ref"),
            current_contract_ref=data.get("current_contract_ref", ""),
            current_contract_hash=data.get("current_contract_hash", ""),
            revision_refs=require_str_list(data.get("revision_refs", []), "mission_run_audit.revision_refs"),
            metric_events_ref=data.get("metric_events_ref", ""),
            metric_projection_ref=data.get("metric_projection_ref", ""),
            safe_point_refs=require_str_list(data.get("safe_point_refs", []), "mission_run_audit.safe_point_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_run_audit.artifact_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_run_audit.evidence_refs"),
            ref_checks=[
                _ref_check_from_dict(require_mapping(item, "mission_run_audit.ref_checks[]"))
                for item in data.get("ref_checks", [])
            ],
            missing_refs=require_str_list(data.get("missing_refs", []), "mission_run_audit.missing_refs"),
            stale_refs=require_str_list(data.get("stale_refs", []), "mission_run_audit.stale_refs"),
            diagnostics=require_str_list(data.get("diagnostics", []), "mission_run_audit.diagnostics"),
            schema_version=require_non_empty_str(data.get("schema_version"), "mission_run_audit.schema_version"),
        )
        audit.validate()
        return audit

    def validate(self) -> None:
        require_non_empty_str(self.mission_run_id, "mission_run_audit.mission_run_id")
        require_non_empty_str(self.mission_id, "mission_run_audit.mission_id")
        require_non_empty_str(self.status, "mission_run_audit.status")
        if not isinstance(self.passed, bool):
            raise ContractValidationError("mission_run_audit.passed must be a boolean")
        validate_ref(self.run_ref, "mission_run_audit.run_ref")
        if self.current_contract_ref:
            validate_ref(self.current_contract_ref, "mission_run_audit.current_contract_ref")
        if self.current_contract_hash:
            require_non_empty_str(self.current_contract_hash, "mission_run_audit.current_contract_hash")
        for ref in self.revision_refs:
            validate_ref(ref, "mission_run_audit.revision_refs[]")
        if self.metric_events_ref:
            validate_ref(self.metric_events_ref, "mission_run_audit.metric_events_ref")
        if self.metric_projection_ref:
            validate_ref(self.metric_projection_ref, "mission_run_audit.metric_projection_ref")
        for ref in self.safe_point_refs:
            validate_ref(ref, "mission_run_audit.safe_point_refs[]")
        for ref in self.artifact_refs:
            validate_ref(ref, "mission_run_audit.artifact_refs[]")
        for ref in self.evidence_refs:
            validate_ref(ref, "mission_run_audit.evidence_refs[]")
        for item in self.ref_checks:
            _ref_check_from_dict(item)
        for ref in self.missing_refs:
            validate_ref(ref, "mission_run_audit.missing_refs[]")
        for ref in self.stale_refs:
            validate_ref(ref, "mission_run_audit.stale_refs[]")
        require_str_list(self.diagnostics, "mission_run_audit.diagnostics")
        if self.schema_version != RUN_AUDIT_SCHEMA_VERSION:
            raise ContractValidationError("mission_run_audit.schema_version is unsupported")
        assert_refs_only_payload(self.to_dict(validate=False), "mission_run_audit")

    def to_dict(self, *, validate: bool = True) -> dict[str, Any]:
        if validate:
            self.validate()
        return {
            "schema_version": self.schema_version,
            "mission_run_id": self.mission_run_id,
            "mission_id": self.mission_id,
            "status": self.status,
            "passed": self.passed,
            "run_ref": self.run_ref,
            "current_contract_ref": self.current_contract_ref,
            "current_contract_hash": self.current_contract_hash,
            "revision_refs": list(self.revision_refs),
            "metric_events_ref": self.metric_events_ref,
            "metric_projection_ref": self.metric_projection_ref,
            "safe_point_refs": list(self.safe_point_refs),
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "ref_checks": [dict(item) for item in self.ref_checks],
            "missing_refs": list(self.missing_refs),
            "stale_refs": list(self.stale_refs),
            "diagnostics": list(self.diagnostics),
        }


def build_run_audit(workspace: str | Path = ".", mission_run_id: str | None = None) -> MissionRunAudit:
    """Build a compact audit from durable refs without embedding raw artifacts."""

    root = Path(workspace)
    store = JsonWorkspaceStore(root)
    run = store.load_mission_run(mission_run_id)
    refs = mission_run_refs_for_run_id(run.mission_run_id)
    metric_store = MetricStore(root)
    ref_checks: list[dict[str, str]] = []
    missing_refs: list[str] = []
    stale_refs: list[str] = []
    diagnostics: list[str] = []

    def check_ref(name: str, ref: str, *, required: bool = True) -> None:
        if not ref:
            return
        safe_ref = validate_ref(ref, f"run_audit.{name}")
        storage_ref = _storage_ref(safe_ref)
        present = store.exists(storage_ref)
        item = {
            "name": name,
            "ref": safe_ref,
            "status": "present" if present else "missing",
        }
        if storage_ref != safe_ref:
            item["storage_ref"] = storage_ref
        ref_checks.append(item)
        if required and not present:
            missing_refs.append(safe_ref)

    run_ref = refs["mission_run"]
    check_ref("mission_run", run_ref)
    check_ref("attempts", run.attempts_ref)
    check_ref("artifact_hygiene", run.artifact_hygiene_ref)
    check_ref("current_contract", run.current_contract_ref)
    for ref in run.revision_refs:
        check_ref("revision", ref)
        _mark_stale_if_unreadable(store, ref, stale_refs, diagnostics, "revision_ref")

    metric_events_ref = _metric_ref(run, "metric_events_ref", metric_store.events_ref(run.mission_run_id))
    metric_projection_ref = _metric_ref(run, "metric_projection_ref", metric_store.projection_ref(run.mission_run_id))
    check_ref("metric_events", metric_events_ref)
    check_ref("metric_projection", metric_projection_ref)
    if metric_projection_ref:
        _mark_stale_if_unreadable(store, metric_projection_ref, stale_refs, diagnostics, "metric_projection_ref")

    safe_point_refs = _safe_point_refs(run)
    for ref in safe_point_refs:
        check_ref("safe_point", ref)
    for ref in run.artifact_refs:
        check_ref("artifact", ref)
    if run.current_contract_ref:
        try:
            _validate_current_contract(store=store, run=run)
        except ContractValidationError as exc:
            stale_refs.append(run.current_contract_ref)
            diagnostics.append(f"active_contract_invalid: {_compact_error(exc)}")

    missing_refs = _dedupe_refs(missing_refs)
    stale_refs = _dedupe_refs(stale_refs)
    if missing_refs:
        diagnostics.append("missing_refs_detected")
    if stale_refs:
        diagnostics.append("stale_refs_detected")

    audit = MissionRunAudit(
        mission_run_id=run.mission_run_id,
        mission_id=run.mission_id,
        status=run.status,
        passed=not missing_refs and not stale_refs,
        run_ref=run_ref,
        current_contract_ref=run.current_contract_ref,
        current_contract_hash=run.current_contract_hash,
        revision_refs=list(run.revision_refs),
        metric_events_ref=metric_events_ref,
        metric_projection_ref=metric_projection_ref,
        safe_point_refs=safe_point_refs,
        artifact_refs=list(run.artifact_refs),
        evidence_refs=list(run.evidence_refs),
        ref_checks=ref_checks,
        missing_refs=missing_refs,
        stale_refs=stale_refs,
        diagnostics=_dedupe_strings(diagnostics),
    )
    audit.validate()
    return audit


def _ref_check_from_dict(payload: Mapping[str, Any]) -> dict[str, str]:
    data = require_mapping(payload, "mission_run_audit.ref_check")
    name = require_non_empty_str(data.get("name"), "mission_run_audit.ref_check.name")
    ref = validate_ref(data.get("ref"), "mission_run_audit.ref_check.ref")
    status = require_non_empty_str(data.get("status"), "mission_run_audit.ref_check.status")
    if status not in {"present", "missing"}:
        raise ContractValidationError("mission_run_audit.ref_check.status must be present or missing")
    result = {"name": name, "ref": ref, "status": status}
    storage_ref = data.get("storage_ref", "")
    if storage_ref:
        result["storage_ref"] = validate_ref(storage_ref, "mission_run_audit.ref_check.storage_ref")
    return result


def _metric_ref(run: MissionRun, key: str, fallback: str) -> str:
    value = run.metrics.get(key)
    if isinstance(value, str) and value:
        return validate_ref(value, f"mission_run.metrics.{key}")
    return fallback


def _safe_point_refs(run: MissionRun) -> list[str]:
    if run.latest_safe_point is None:
        return []
    refs = [
        run.latest_safe_point.savepoint_ref,
        run.latest_safe_point.session_ref,
        run.latest_safe_point.events_ref,
    ]
    return _dedupe_refs([ref for ref in refs if ref])


def _validate_current_contract(*, store: JsonWorkspaceStore, run: MissionRun) -> None:
    contract_ref = validate_ref(run.current_contract_ref, "run_audit.current_contract_ref")
    if not store.exists(contract_ref):
        raise ContractValidationError(f"active contract ref is missing: {contract_ref}")
    frozen = FrozenMissionContract.from_dict(store.read_json(contract_ref))
    if frozen.mission_id != run.mission_id:
        raise ContractValidationError("active contract mission_id does not match MissionRun")
    if run.current_contract_hash and frozen.contract_hash != run.current_contract_hash:
        raise ContractValidationError("active contract hash does not match MissionRun.current_contract_hash")


def _storage_ref(ref: str) -> str:
    return validate_ref(ref.split("#", 1)[0], "run_audit.storage_ref")


def _mark_stale_if_unreadable(
    store: JsonWorkspaceStore,
    ref: str,
    stale_refs: list[str],
    diagnostics: list[str],
    label: str,
) -> None:
    try:
        if store.exists(_storage_ref(ref)):
            store.read_json(_storage_ref(ref))
    except (OSError, ValueError, ContractValidationError) as exc:
        stale_refs.append(ref)
        diagnostics.append(f"{label}_invalid: {_compact_error(exc)}")


def _compact_error(error: Exception) -> str:
    message = str(error).replace("\n", " ").strip()
    return message[:160]


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        safe_ref = validate_ref(ref, "run_audit.refs[]")
        if safe_ref in seen:
            continue
        result.append(safe_ref)
        seen.add(safe_ref)
    return result


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        safe_value = require_non_empty_str(value, "run_audit.diagnostics[]")
        if safe_value in seen:
            continue
        result.append(safe_value)
        seen.add(safe_value)
    return result
