"""Deterministic fake worker for harness tests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .contracts import ContractValidationError, EvidenceTrustLevel, validate_ref
from .evidence_store import EvidenceLedger, InMemoryEvidenceStore
from .work_unit import ExecutionReport, WorkUnitContract, WorkerResult


@dataclass(frozen=True)
class FakeWorkerRunResult:
    """Fake worker output bundle."""

    execution_report: ExecutionReport
    worker_result: WorkerResult


class FakeWorker:
    """Write one deterministic artifact and execution report."""

    def run(
        self,
        work_unit: WorkUnitContract,
        *,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
    ) -> FakeWorkerRunResult:
        work_unit.validate()
        if not work_unit.expected_outputs:
            raise ContractValidationError("fake worker requires at least one expected output")
        store = evidence_store or InMemoryEvidenceStore()
        output_ref = validate_ref(work_unit.expected_outputs[0], "work_unit.expected_outputs[]")
        root = Path(workspace).resolve()
        output_path = (root / output_ref).resolve()
        if root not in output_path.parents and output_path != root:
            raise ContractValidationError("fake worker output escapes workspace")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"fake worker artifact for {work_unit.work_unit_id}\n"
        output_path.write_text(content, encoding="utf-8")
        artifact_hash = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        evidence_ref = store.append(
            payload={
                "work_unit_id": work_unit.work_unit_id,
                "artifact_ref": output_ref,
                "sha256": artifact_hash,
            },
            trust_level=EvidenceTrustLevel.ARTIFACT_REF,
            kind="fake_worker_artifact",
        )
        report_ref = f"attempts/{work_unit.work_unit_id}/execution_report.json"
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=[output_ref],
            changed_refs=[output_ref],
            evidence_refs=[evidence_ref.evidence_id],
            worker_claims=["fake worker produced deterministic artifact"],
            metrics={"produced_artifact_count": 1},
        )
        report_path = (root / report_ref).resolve()
        if root not in report_path.parents and report_path != root:
            raise ContractValidationError("fake worker report escapes workspace")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return FakeWorkerRunResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
        )
