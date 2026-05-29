"""Durable runtime state writing."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .contracts import ContractValidationError, stable_json_hash, validate_ref
from .json_store import JsonWorkspaceStore
from .metric_store import MetricStore
from .metrics import MetricEvent, MetricTrustLevel, safe_metric_values
from .state import (
    SUPPORTED_RESUME_BOUNDARY,
    MissionRun,
    MissionRunState,
    RuntimeAttempt,
    RuntimeSafePoint,
    load_mission_run,
    scan_artifact_hygiene,
)


class RuntimeStateWriter:
    """Write MissionRun, attempts, hygiene, and metric refs."""

    def write(
        self,
        *,
        root: Path,
        mission_run_id: str,
        mission_id: str,
        current_contract_ref: str,
        current_contract_hash: str,
        revision_refs: list[str] | None = None,
        refs: dict[str, str],
        work_unit_id: str,
        attempt_records: list[RuntimeAttempt],
        status: str,
        latest_decision: str,
        next_action: str,
        state: MissionRunState,
        result: Any,
        expected_artifacts: list[str],
        report_refs: list[str],
        required_refs: list[str],
        metrics: dict[str, Any],
        previous_attempts: list[RuntimeAttempt] | None = None,
    ) -> None:
        metrics = dict(metrics)
        previous_run = _load_previous_run(root, mission_run_id)
        active_contract_ref = validate_ref(
            current_contract_ref or (previous_run.current_contract_ref if previous_run else ""),
            "runtime_state_writer.current_contract_ref",
        )
        active_contract_hash = current_contract_hash or (previous_run.current_contract_hash if previous_run else "")
        if not active_contract_hash:
            raise ContractValidationError("runtime state writer requires current_contract_hash")
        active_revision_refs = (
            _dedupe_refs(list(revision_refs))
            if revision_refs is not None
            else _dedupe_refs(list(previous_run.revision_refs) if previous_run else [])
        )
        metrics["current_contract_ref"] = active_contract_ref
        metrics["contract_hash"] = active_contract_hash
        metrics["revision_refs"] = list(active_revision_refs)
        result.metrics["current_contract_ref"] = active_contract_ref
        result.metrics["contract_hash"] = active_contract_hash
        result.metrics["revision_refs"] = list(active_revision_refs)
        all_attempts = [*(previous_attempts or []), *attempt_records]
        all_report_refs = _dedupe_refs([*[attempt.report_ref for attempt in all_attempts], *report_refs])
        metric_refs = _write_metric_ledger(
            root=root,
            mission_run_id=mission_run_id,
            refs=refs,
            attempts=all_attempts,
            metrics=metrics,
        )
        for key, value in metric_refs.items():
            metrics[key] = value
            result.metrics[key] = value
        all_required_refs = _dedupe_refs([
            *[attempt.input_ref for attempt in all_attempts],
            *[attempt.output_ref for attempt in all_attempts],
            *[attempt.report_ref for attempt in all_attempts],
            *[attempt.savepoints_ref for attempt in all_attempts],
            *metric_refs.values(),
            *required_refs,
        ])
        hygiene = scan_artifact_hygiene(
            root,
            mission_run_id=mission_run_id,
            expected_artifacts=expected_artifacts,
            report_refs=all_report_refs,
            required_refs=all_required_refs,
        )
        _write_json(root, refs["artifact_hygiene"], hygiene.to_dict())
        if attempt_records:
            _append_jsonl(root, refs["attempts"], [attempt.to_dict() for attempt in all_attempts])
        else:
            _append_jsonl(root, refs["attempts"], [])
        latest_attempt = all_attempts[-1] if all_attempts else None
        safe_point = _latest_safe_point(root, latest_attempt)
        mission_run = MissionRun(
            mission_run_id=mission_run_id,
            mission_id=mission_id,
            status=status,
            current_attempt=latest_attempt.attempt_id if latest_attempt else "attempt-000000",
            latest_work_unit_id=work_unit_id,
            latest_safe_point=safe_point,
            current_contract_ref=active_contract_ref,
            current_contract_hash=active_contract_hash,
            revision_refs=active_revision_refs,
            latest_decision=latest_decision,
            next_action=next_action,
            artifact_refs=list(result.artifact_refs),
            evidence_refs=list(result.evidence_refs),
            failed_constraint_ids=list(result.failed_constraint_ids),
            attempts_ref=refs["attempts"],
            artifact_hygiene_ref=refs["artifact_hygiene"],
            metrics={
                **metrics,
                "artifact_hygiene_passed": hygiene.passed,
                "state_hash": stable_json_hash(state.to_dict()),
            },
            updated_at=_now(),
        )
        _write_json(root, refs["mission_run"], mission_run.to_dict())


def _write_json(root: Path, ref: str, payload: dict[str, Any]) -> str:
    return JsonWorkspaceStore(root).write_json(ref, payload)


def _load_previous_run(root: Path, mission_run_id: str) -> MissionRun | None:
    try:
        return load_mission_run(root, mission_run_id)
    except (FileNotFoundError, ContractValidationError):
        return None


def _append_jsonl(root: Path, ref: str, payloads: list[dict[str, Any]]) -> None:
    JsonWorkspaceStore(root).write_jsonl(ref, payloads)


def _write_metric_ledger(
    *,
    root: Path,
    mission_run_id: str,
    refs: dict[str, str],
    attempts: list[RuntimeAttempt],
    metrics: dict[str, Any],
) -> dict[str, str]:
    store = MetricStore(root)
    events = _metric_events(
        mission_run_id=mission_run_id,
        run_ref=refs["mission_run"],
        attempt_ref=refs["attempts"],
        attempts=attempts,
        metrics=metrics,
    )
    events_ref = store.write_events(mission_run_id, events)
    projection = store.rebuild_projection(mission_run_id)
    projection_ref = store.write_projection(projection)
    return {
        "metric_events_ref": events_ref,
        "metric_projection_ref": projection_ref,
    }


def _metric_events(
    *,
    mission_run_id: str,
    run_ref: str,
    attempt_ref: str,
    attempts: list[RuntimeAttempt],
    metrics: dict[str, Any],
) -> list[MetricEvent]:
    events: list[MetricEvent] = []

    def append(
        namespace: str,
        values: dict[str, Any],
        *,
        metric_kind: str = "summary",
        trust_level: str = MetricTrustLevel.RUNTIME_DIAGNOSTIC.value,
        source_ref: str = "",
        tags: list[str] | None = None,
    ) -> None:
        safe_values = safe_metric_values(values)
        if not safe_values:
            return
        events.append(
            MetricEvent(
                metric_id=f"ME-{len(events) + 1:06d}",
                mission_run_id=mission_run_id,
                namespace=namespace,
                metric_kind=metric_kind,
                values=safe_values,
                trust_level=trust_level,
                source_ref=source_ref,
                run_ref=run_ref,
                tags=tags or [],
            )
        )

    append(
        "missionforge.runtime",
        {
            "attempt_count": metrics.get("attempt_count"),
            "repair_attempted": metrics.get("repair_attempted"),
            "repair_exhausted": metrics.get("repair_exhausted"),
            "retry_attempted": metrics.get("retry_attempted"),
            "retry_exhausted": metrics.get("retry_exhausted"),
            "redesign_required": metrics.get("redesign_required"),
            "resume_count": metrics.get("resume_count"),
            "latest_decision": metrics.get("latest_decision"),
            "next_action": metrics.get("next_action"),
        },
        source_ref=attempt_ref,
        tags=["runtime"],
    )
    append(
        "missionforge.verifier",
        {
            "verification_status": metrics.get("verification_status"),
            "validator_result_count": metrics.get("validator_result_count"),
            "failed_constraint_count": len(metrics.get("failed_constraint_ids", []))
            if isinstance(metrics.get("failed_constraint_ids"), list)
            else None,
        },
        source_ref=attempt_ref,
        tags=["verifier"],
    )
    append(
        "missionforge.steering",
        {
            "proposal_count": metrics.get("proposal_count"),
            "accepted_proposal_count": metrics.get("accepted_proposal_count"),
            "rejected_proposal_count": metrics.get("rejected_proposal_count"),
            "observation_signal_count": metrics.get("observation_signal_count"),
            "review_packet_count": metrics.get("review_packet_count"),
            "reviewer_decision_count": metrics.get("reviewer_decision_count"),
            "provider_failure_count": metrics.get("provider_failure_count"),
            "unsafe_proposal_rejection_count": metrics.get("unsafe_proposal_rejection_count"),
        },
        source_ref=attempt_ref,
        tags=["steering"],
    )
    for attempt in attempts:
        worker_metrics = {
            key: value
            for key, value in attempt.metrics.items()
            if not key.endswith("_ref") and key not in {"adapter_id"}
        }
        source_ref = attempt.metrics.get("metrics_ref")
        append(
            "missionforge.worker.pi_agent",
            worker_metrics,
            trust_level=MetricTrustLevel.ADAPTER_DIAGNOSTIC.value,
            source_ref=source_ref if isinstance(source_ref, str) and source_ref else attempt.report_ref,
            tags=["worker", "pi_agent"],
        )
    return events


def _latest_safe_point(root: Path, attempt: RuntimeAttempt | None) -> RuntimeSafePoint | None:
    if attempt is None:
        return None
    savepoints_path = _resolve_workspace_ref(root, attempt.savepoints_ref)
    if not savepoints_path.is_file():
        return None
    turn_ref = attempt.savepoints_ref
    for line in savepoints_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        resume_hint = payload.get("resume_hint") if isinstance(payload, dict) else None
        if isinstance(resume_hint, dict) and resume_hint.get("boundary") == SUPPORTED_RESUME_BOUNDARY:
            turn_index = payload.get("turn_index")
            if isinstance(turn_index, int):
                turn_ref = f"{attempt.savepoints_ref}#turn={turn_index}"
    return RuntimeSafePoint(
        kind=SUPPORTED_RESUME_BOUNDARY,
        savepoint_ref=turn_ref,
        session_ref=f"attempts/{attempt.work_unit_id}/pi_agent_session.jsonl",
        events_ref=f"attempts/{attempt.work_unit_id}/pi_agent_events.jsonl",
    )


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "runtime.ref")
    path = (root / safe_ref).resolve()
    workspace = root.resolve()
    if workspace not in path.parents and path != workspace:
        raise ContractValidationError("runtime ref escapes workspace")
    return path


def _dedupe_refs(refs: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, str) or not ref:
            continue
        safe_ref = validate_ref(ref, "runtime_state_writer.revision_refs[]")
        if safe_ref in seen:
            continue
        result.append(safe_ref)
        seen.add(safe_ref)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
