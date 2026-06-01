"""Runtime state snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .contracts import ContractValidationError, ensure_json_value, require_bool, require_mapping, require_non_empty_str, require_str_list, validate_ref


MISSION_RUN_SCHEMA_VERSION = "missionforge.mission_run.v1"
RUNTIME_ATTEMPT_SCHEMA_VERSION = "missionforge.runtime_attempt.v1"
ARTIFACT_HYGIENE_SCHEMA_VERSION = "missionforge.artifact_hygiene.v1"
SUPPORTED_RESUME_BOUNDARY = "after_completed_turn"


@dataclass(frozen=True)
class MissionRunState:
    """Refs-only runtime state snapshot."""

    mission_id: str
    status: str
    contract_hash: str
    work_unit_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    latest_decision: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRunState":
        data = require_mapping(payload, "mission_run_state")
        state = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_run_state.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_run_state.status"),
            contract_hash=require_non_empty_str(data.get("contract_hash"), "mission_run_state.contract_hash"),
            work_unit_refs=require_str_list(data.get("work_unit_refs", []), "mission_run_state.work_unit_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_run_state.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_run_state.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_run_state.failed_constraint_ids",
            ),
            latest_decision=data.get("latest_decision", ""),
        )
        state.validate()
        return state

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_run_state.mission_id")
        require_non_empty_str(self.status, "mission_run_state.status")
        require_non_empty_str(self.contract_hash, "mission_run_state.contract_hash")
        require_str_list(self.work_unit_refs, "mission_run_state.work_unit_refs")
        require_str_list(self.evidence_refs, "mission_run_state.evidence_refs")
        require_str_list(self.artifact_refs, "mission_run_state.artifact_refs")
        require_str_list(self.failed_constraint_ids, "mission_run_state.failed_constraint_ids")
        if self.latest_decision:
            require_non_empty_str(self.latest_decision, "mission_run_state.latest_decision")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "status": self.status,
            "contract_hash": self.contract_hash,
            "work_unit_refs": list(self.work_unit_refs),
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "latest_decision": self.latest_decision,
        }


@dataclass(frozen=True)
class RuntimeSafePoint:
    """Durable runtime resume boundary."""

    kind: str
    savepoint_ref: str
    session_ref: str = ""
    events_ref: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeSafePoint":
        data = require_mapping(payload, "runtime_safe_point")
        safe_point = cls(
            kind=require_non_empty_str(data.get("kind"), "runtime_safe_point.kind"),
            savepoint_ref=validate_ref(data.get("savepoint_ref"), "runtime_safe_point.savepoint_ref"),
            session_ref=data.get("session_ref", ""),
            events_ref=data.get("events_ref", ""),
        )
        safe_point.validate()
        return safe_point

    def validate(self) -> None:
        require_non_empty_str(self.kind, "runtime_safe_point.kind")
        validate_ref(self.savepoint_ref, "runtime_safe_point.savepoint_ref")
        if self.session_ref:
            validate_ref(self.session_ref, "runtime_safe_point.session_ref")
        if self.events_ref:
            validate_ref(self.events_ref, "runtime_safe_point.events_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = {
            "kind": self.kind,
            "savepoint_ref": self.savepoint_ref,
        }
        if self.session_ref:
            payload["session_ref"] = self.session_ref
        if self.events_ref:
            payload["events_ref"] = self.events_ref
        return payload


@dataclass(frozen=True)
class RuntimeAttempt:
    """Refs-only record for one worker dispatch."""

    attempt_id: str
    work_unit_id: str
    attempt_kind: str
    worker: str
    input_ref: str
    output_ref: str
    report_ref: str
    savepoints_ref: str
    status: str
    verification_status: str
    decision: str
    created_at: str
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failure_category: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RUNTIME_ATTEMPT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeAttempt":
        data = require_mapping(payload, "runtime_attempt")
        if data.get("schema_version") != RUNTIME_ATTEMPT_SCHEMA_VERSION:
            raise ContractValidationError("runtime_attempt.schema_version is unsupported")
        attempt = cls(
            attempt_id=require_non_empty_str(data.get("attempt_id"), "runtime_attempt.attempt_id"),
            work_unit_id=require_non_empty_str(data.get("work_unit_id"), "runtime_attempt.work_unit_id"),
            attempt_kind=require_non_empty_str(data.get("attempt_kind"), "runtime_attempt.attempt_kind"),
            worker=require_non_empty_str(data.get("worker"), "runtime_attempt.worker"),
            input_ref=validate_ref(data.get("input_ref"), "runtime_attempt.input_ref"),
            output_ref=validate_ref(data.get("output_ref"), "runtime_attempt.output_ref"),
            report_ref=validate_ref(data.get("report_ref"), "runtime_attempt.report_ref"),
            savepoints_ref=validate_ref(data.get("savepoints_ref"), "runtime_attempt.savepoints_ref"),
            status=require_non_empty_str(data.get("status"), "runtime_attempt.status"),
            verification_status=require_non_empty_str(
                data.get("verification_status"),
                "runtime_attempt.verification_status",
            ),
            decision=require_non_empty_str(data.get("decision"), "runtime_attempt.decision"),
            created_at=require_non_empty_str(data.get("created_at"), "runtime_attempt.created_at"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "runtime_attempt.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "runtime_attempt.artifact_refs"),
            failure_category=data.get("failure_category", ""),
            metrics=require_mapping(data.get("metrics", {}), "runtime_attempt.metrics"),
        )
        attempt.validate()
        return attempt

    def validate(self) -> None:
        require_non_empty_str(self.attempt_id, "runtime_attempt.attempt_id")
        require_non_empty_str(self.work_unit_id, "runtime_attempt.work_unit_id")
        require_non_empty_str(self.attempt_kind, "runtime_attempt.attempt_kind")
        require_non_empty_str(self.worker, "runtime_attempt.worker")
        validate_ref(self.input_ref, "runtime_attempt.input_ref")
        validate_ref(self.output_ref, "runtime_attempt.output_ref")
        validate_ref(self.report_ref, "runtime_attempt.report_ref")
        validate_ref(self.savepoints_ref, "runtime_attempt.savepoints_ref")
        require_non_empty_str(self.status, "runtime_attempt.status")
        require_non_empty_str(self.verification_status, "runtime_attempt.verification_status")
        require_non_empty_str(self.decision, "runtime_attempt.decision")
        require_non_empty_str(self.created_at, "runtime_attempt.created_at")
        require_str_list(self.evidence_refs, "runtime_attempt.evidence_refs")
        require_str_list(self.artifact_refs, "runtime_attempt.artifact_refs")
        if self.failure_category:
            require_non_empty_str(self.failure_category, "runtime_attempt.failure_category")
        ensure_json_value(self.metrics, "runtime_attempt.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "work_unit_id": self.work_unit_id,
            "attempt_kind": self.attempt_kind,
            "worker": self.worker,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "report_ref": self.report_ref,
            "savepoints_ref": self.savepoints_ref,
            "status": self.status,
            "verification_status": self.verification_status,
            "decision": self.decision,
            "created_at": self.created_at,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "failure_category": self.failure_category,
            "metrics": ensure_json_value(self.metrics, "runtime_attempt.metrics"),
        }


@dataclass(frozen=True)
class MissionRun:
    """Durable refs-only runtime run state."""

    mission_run_id: str
    mission_id: str
    status: str
    current_attempt: str
    latest_work_unit_id: str
    latest_decision: str
    next_action: str
    updated_at: str
    attempts_ref: str
    artifact_hygiene_ref: str
    latest_safe_point: RuntimeSafePoint | None = None
    current_contract_ref: str = ""
    current_contract_hash: str = ""
    revision_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = MISSION_RUN_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionRun":
        data = require_mapping(payload, "mission_run")
        if data.get("schema_version") != MISSION_RUN_SCHEMA_VERSION:
            raise ContractValidationError("mission_run.schema_version is unsupported")
        safe_point_payload = data.get("latest_safe_point")
        mission_run = cls(
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "mission_run.mission_run_id"),
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_run.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_run.status"),
            current_attempt=require_non_empty_str(data.get("current_attempt"), "mission_run.current_attempt"),
            latest_work_unit_id=require_non_empty_str(data.get("latest_work_unit_id"), "mission_run.latest_work_unit_id"),
            latest_decision=require_non_empty_str(data.get("latest_decision"), "mission_run.latest_decision"),
            next_action=require_non_empty_str(data.get("next_action"), "mission_run.next_action"),
            updated_at=require_non_empty_str(data.get("updated_at"), "mission_run.updated_at"),
            attempts_ref=validate_ref(data.get("attempts_ref"), "mission_run.attempts_ref"),
            artifact_hygiene_ref=validate_ref(data.get("artifact_hygiene_ref"), "mission_run.artifact_hygiene_ref"),
            latest_safe_point=RuntimeSafePoint.from_dict(safe_point_payload) if isinstance(safe_point_payload, Mapping) else None,
            current_contract_ref=data.get("current_contract_ref", ""),
            current_contract_hash=data.get("current_contract_hash", ""),
            revision_refs=require_str_list(data.get("revision_refs", []), "mission_run.revision_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_run.artifact_refs"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_run.evidence_refs"),
            failed_constraint_ids=require_str_list(data.get("failed_constraint_ids", []), "mission_run.failed_constraint_ids"),
            metrics=require_mapping(data.get("metrics", {}), "mission_run.metrics"),
        )
        mission_run.validate()
        return mission_run

    def validate(self) -> None:
        require_non_empty_str(self.mission_run_id, "mission_run.mission_run_id")
        require_non_empty_str(self.mission_id, "mission_run.mission_id")
        require_non_empty_str(self.status, "mission_run.status")
        require_non_empty_str(self.current_attempt, "mission_run.current_attempt")
        require_non_empty_str(self.latest_work_unit_id, "mission_run.latest_work_unit_id")
        require_non_empty_str(self.latest_decision, "mission_run.latest_decision")
        require_non_empty_str(self.next_action, "mission_run.next_action")
        require_non_empty_str(self.updated_at, "mission_run.updated_at")
        validate_ref(self.attempts_ref, "mission_run.attempts_ref")
        validate_ref(self.artifact_hygiene_ref, "mission_run.artifact_hygiene_ref")
        if self.latest_safe_point is not None:
            self.latest_safe_point.validate()
        if self.current_contract_ref:
            validate_ref(self.current_contract_ref, "mission_run.current_contract_ref")
        if self.current_contract_hash:
            require_non_empty_str(self.current_contract_hash, "mission_run.current_contract_hash")
        for ref in self.revision_refs:
            validate_ref(ref, "mission_run.revision_refs[]")
        require_str_list(self.artifact_refs, "mission_run.artifact_refs")
        require_str_list(self.evidence_refs, "mission_run.evidence_refs")
        require_str_list(self.failed_constraint_ids, "mission_run.failed_constraint_ids")
        ensure_json_value(self.metrics, "mission_run.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "mission_run_id": self.mission_run_id,
            "mission_id": self.mission_id,
            "status": self.status,
            "current_attempt": self.current_attempt,
            "latest_work_unit_id": self.latest_work_unit_id,
            "latest_safe_point": self.latest_safe_point.to_dict() if self.latest_safe_point else None,
            "current_contract_ref": self.current_contract_ref,
            "current_contract_hash": self.current_contract_hash,
            "revision_refs": list(self.revision_refs),
            "latest_decision": self.latest_decision,
            "next_action": self.next_action,
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "attempts_ref": self.attempts_ref,
            "artifact_hygiene_ref": self.artifact_hygiene_ref,
            "metrics": ensure_json_value(self.metrics, "mission_run.metrics"),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ArtifactHygieneReport:
    """Deterministic artifact hygiene scan result."""

    mission_run_id: str
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    schema_version: str = ARTIFACT_HYGIENE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactHygieneReport":
        data = require_mapping(payload, "artifact_hygiene")
        if data.get("schema_version") != ARTIFACT_HYGIENE_SCHEMA_VERSION:
            raise ContractValidationError("artifact_hygiene.schema_version is unsupported")
        report = cls(
            mission_run_id=require_non_empty_str(data.get("mission_run_id"), "artifact_hygiene.mission_run_id"),
            passed=require_bool(data.get("passed"), "artifact_hygiene.passed"),
            checks=list(data.get("checks", [])),
            failures=require_str_list(data.get("failures", []), "artifact_hygiene.failures"),
        )
        report.validate()
        return report

    def validate(self) -> None:
        require_non_empty_str(self.mission_run_id, "artifact_hygiene.mission_run_id")
        if not isinstance(self.passed, bool):
            raise ContractValidationError("artifact_hygiene.passed must be a boolean")
        ensure_json_value(self.checks, "artifact_hygiene.checks")
        require_str_list(self.failures, "artifact_hygiene.failures")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "mission_run_id": self.mission_run_id,
            "passed": self.passed,
            "checks": ensure_json_value(self.checks, "artifact_hygiene.checks"),
            "failures": list(self.failures),
        }


def mission_run_id_for(mission_id: str) -> str:
    return f"run-{require_non_empty_str(mission_id, 'mission_id')}"


def mission_run_refs(mission_id: str) -> dict[str, str]:
    return mission_run_refs_for_run_id(mission_run_id_for(mission_id))


def mission_run_refs_for_run_id(mission_run_id: str) -> dict[str, str]:
    safe_run_id = validate_ref(mission_run_id, "mission_run_id")
    root = f"runs/{safe_run_id}"
    return {
        "run_dir": root,
        "mission_run": f"{root}/mission_run.json",
        "attempts": f"{root}/attempts.jsonl",
        "artifact_hygiene": f"{root}/artifact_hygiene.json",
    }


def load_mission_run(workspace: str | Path, mission_run_id: str | None = None) -> MissionRun:
    root = Path(workspace)
    path = _mission_run_path(root, mission_run_id)
    return MissionRun.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_runtime_attempts(workspace: str | Path, mission_run_id: str) -> list[RuntimeAttempt]:
    path = Path(workspace) / f"runs/{mission_run_id}/attempts.jsonl"
    if not path.is_file():
        return []
    attempts: list[RuntimeAttempt] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            attempts.append(RuntimeAttempt.from_dict(json.loads(line)))
    return attempts


def inspect_runtime(workspace: str | Path, mission_run_id: str | None = None) -> dict[str, Any]:
    run = load_mission_run(workspace, mission_run_id)
    attempts = load_runtime_attempts(workspace, run.mission_run_id)
    return {
        "schema_version": "missionforge.runtime_inspection.v1",
        "mission_run": run.to_dict(),
        "attempt_count": len(attempts),
        "latest_attempt": attempts[-1].to_dict() if attempts else None,
        "next_action": run.next_action,
    }


def write_artifact_hygiene_report(
    workspace: str | Path,
    *,
    mission_run_id: str,
    expected_artifacts: list[str],
    report_refs: list[str],
    required_refs: list[str],
    secret_values: list[str] | None = None,
) -> ArtifactHygieneReport:
    report = scan_artifact_hygiene(
        workspace,
        mission_run_id=mission_run_id,
        expected_artifacts=expected_artifacts,
        report_refs=report_refs,
        required_refs=required_refs,
        secret_values=secret_values or [],
    )
    refs = mission_run_refs_for_run_id(mission_run_id)
    path = Path(workspace) / refs["artifact_hygiene"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def scan_artifact_hygiene(
    workspace: str | Path,
    *,
    mission_run_id: str,
    expected_artifacts: list[str],
    report_refs: list[str],
    required_refs: list[str],
    secret_values: list[str] | None = None,
) -> ArtifactHygieneReport:
    root = Path(workspace)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            failures.append(f"{name}: {detail}")

    for ref in [*expected_artifacts, *report_refs, *required_refs]:
        try:
            validate_ref(ref, "artifact_hygiene.ref")
            add_check("workspace_relative_ref", True, ref)
        except ContractValidationError as exc:
            add_check("workspace_relative_ref", False, f"{ref}: {exc}")

    for ref in required_refs:
        path = _resolve_workspace_ref(root, ref)
        add_check("required_ref_exists", path.is_file(), ref)

    workspace_text = _workspace_text(root)
    for secret in secret_values or []:
        if isinstance(secret, str) and len(secret) >= 4:
            add_check("secret_absent", secret not in workspace_text, "<redacted>")
    for pattern in [r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._\-]+", r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*[^,\\s\\\"']+"]:
        add_check("secret_pattern_absent", re.search(pattern, workspace_text) is None, pattern)

    for report_ref in report_refs:
        report_path = _resolve_workspace_ref(root, report_ref)
        report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.is_file() else ""
        for artifact_ref in expected_artifacts:
            artifact_path = _resolve_workspace_ref(root, artifact_ref)
            artifact_text = artifact_path.read_text(encoding="utf-8", errors="replace") if artifact_path.is_file() else ""
            if artifact_text.strip():
                add_check(
                    "report_refs_only",
                    artifact_text not in report_text,
                    f"{report_ref} does not embed {artifact_ref}",
                )

    return ArtifactHygieneReport(
        mission_run_id=mission_run_id,
        passed=not failures,
        checks=checks,
        failures=failures,
    )


def _mission_run_path(root: Path, mission_run_id: str | None) -> Path:
    if mission_run_id:
        return root / f"runs/{validate_ref(mission_run_id, 'mission_run_id')}/mission_run.json"
    candidates = sorted((root / "runs").glob("*/mission_run.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise ContractValidationError("mission run state is missing")
    return candidates[0]


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    workspace = root.resolve()
    if workspace not in path.parents and path != workspace:
        raise ContractValidationError("workspace ref escapes root")
    return path


def _workspace_text(root: Path) -> str:
    texts: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(texts)
