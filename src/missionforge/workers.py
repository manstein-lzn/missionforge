"""Generic worker adapter protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from .contracts import ensure_json_value, require_mapping, require_str_list
from .evidence_store import EvidenceLedger
from .work_unit import ExecutionReport, WorkUnitContract, WorkerResult


@dataclass(frozen=True)
class WorkerAdapterResult:
    """Worker adapter result used by harness-compatible adapters."""

    execution_report: ExecutionReport
    worker_result: WorkerResult
    event_evidence_refs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.execution_report.validate()
        self.worker_result.validate()
        require_str_list(self.event_evidence_refs, "worker_adapter_result.event_evidence_refs")
        ensure_json_value(
            require_mapping(self.metrics, "worker_adapter_result.metrics"),
            "worker_adapter_result.metrics",
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "execution_report": self.execution_report.to_dict(),
            "worker_result": self.worker_result.to_dict(),
            "event_evidence_refs": list(self.event_evidence_refs),
            "metrics": ensure_json_value(self.metrics, "worker_adapter_result.metrics"),
        }


class WorkerAdapter(Protocol):
    """Harness-compatible worker adapter protocol."""

    def run(
        self,
        work_unit: WorkUnitContract,
        *,
        workspace: str | Path = ".",
        evidence_store: EvidenceLedger | None = None,
    ) -> WorkerAdapterResult:
        """Execute a committed work-unit contract and return refs-only results."""
