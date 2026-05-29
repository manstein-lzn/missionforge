"""Runtime attempt assembly helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import VerificationStatus
from .state import RuntimeAttempt


class RuntimeAttemptRunner:
    """Build durable attempt records from harness dispatch results."""

    def record_attempt(
        self,
        *,
        root: Path,
        mission_run_id: str,
        index: int,
        attempt_kind: str,
        decision: str,
        dispatch: Any,
        verification_status: str,
    ) -> RuntimeAttempt:
        work_unit = dispatch.work_unit
        report = dispatch.execution_report
        worker_result = dispatch.worker_result
        work_unit_id = work_unit.work_unit_id if work_unit is not None else f"WU-{index:06d}"
        report_ref = (
            worker_result.execution_report_ref
            if worker_result is not None
            else f"attempts/{work_unit_id}/pi_agent_execution_report.json"
        )
        output_ref = _report_metric_or_default(report, "output_ref", f"attempts/{work_unit_id}/pi_agent_output.json")
        input_ref = _report_metric_or_default(report, "input_ref", f"attempts/{work_unit_id}/pi_agent_input.json")
        savepoints_ref = _report_metric_or_default(
            report,
            "savepoints_ref",
            f"attempts/{work_unit_id}/pi_agent_savepoints.jsonl",
        )
        return RuntimeAttempt(
            attempt_id=f"attempt-{index:06d}",
            work_unit_id=work_unit_id,
            attempt_kind=attempt_kind,
            worker="missionforge.pi_agent_runtime",
            input_ref=input_ref,
            output_ref=output_ref,
            report_ref=report_ref,
            savepoints_ref=savepoints_ref,
            status=report.status if report is not None else "failed",
            verification_status=verification_status,
            decision=decision,
            created_at=_now(),
            evidence_refs=list(report.evidence_refs) if report is not None else [],
            artifact_refs=list(report.produced_artifacts) if report is not None else [],
            failure_category=_failure_category(report, verification_status),
            metrics=dict(report.metrics) if report is not None else {},
        )


def _report_metric_or_default(report: Any, key: str, default: str) -> str:
    if report is not None and isinstance(report.metrics, dict):
        value = report.metrics.get(key)
        if isinstance(value, str) and value:
            return value
    return default


def _failure_category(report: Any, verification_status: str) -> str:
    if verification_status == VerificationStatus.COMPLETED_VERIFIED.value:
        return ""
    if report is not None:
        if report.status != "completed":
            return "worker_failure"
        if not report.produced_artifacts:
            return "missing_artifact"
    if verification_status == VerificationStatus.UNSUPPORTED_VERIFICATION_SPEC.value:
        return "redesign_required"
    if verification_status == VerificationStatus.FAILED.value:
        return "verifier_failure"
    return verification_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
