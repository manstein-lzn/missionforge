"""Optional CLI/Python host shell for MissionForge."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..adapters.contracts import AdapterResult
from ..contracts import (
    ContractValidationError,
    ensure_json_value,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    validate_ref,
)
from ..ir import MissionIR
from ..runner import MissionResult, MissionRuntime


@dataclass(frozen=True)
class MissionCLIResult:
    """Refs-only host-shell result summary."""

    mission_id: str
    status: str
    mission_result_ref: str
    evidence_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    failed_constraint_ids: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MissionCLIResult":
        data = require_mapping(payload, "mission_cli_result")
        result = cls(
            mission_id=require_non_empty_str(data.get("mission_id"), "mission_cli_result.mission_id"),
            status=require_non_empty_str(data.get("status"), "mission_cli_result.status"),
            mission_result_ref=validate_ref(data.get("mission_result_ref"), "mission_cli_result.mission_result_ref"),
            evidence_refs=require_str_list(data.get("evidence_refs", []), "mission_cli_result.evidence_refs"),
            artifact_refs=require_str_list(data.get("artifact_refs", []), "mission_cli_result.artifact_refs"),
            failed_constraint_ids=require_str_list(
                data.get("failed_constraint_ids", []),
                "mission_cli_result.failed_constraint_ids",
            ),
            metrics=ensure_json_value(
                require_mapping(data.get("metrics", {}), "mission_cli_result.metrics"),
                "mission_cli_result.metrics",
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        require_non_empty_str(self.mission_id, "mission_cli_result.mission_id")
        require_non_empty_str(self.status, "mission_cli_result.status")
        validate_ref(self.mission_result_ref, "mission_cli_result.mission_result_ref")
        for ref in self.evidence_refs:
            validate_ref(ref, "mission_cli_result.evidence_refs[]")
        for ref in self.artifact_refs:
            validate_ref(ref, "mission_cli_result.artifact_refs[]")
        require_str_list(self.failed_constraint_ids, "mission_cli_result.failed_constraint_ids")
        ensure_json_value(require_mapping(self.metrics, "mission_cli_result.metrics"), "mission_cli_result.metrics")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "mission_id": self.mission_id,
            "status": self.status,
            "mission_result_ref": self.mission_result_ref,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "failed_constraint_ids": list(self.failed_constraint_ids),
            "metrics": ensure_json_value(self.metrics, "mission_cli_result.metrics"),
        }


class MissionCLI:
    """Small host shell around the primary Python MissionRuntime API."""

    adapter_id = "missionforge_cli_shell"

    def run_mission_ref(
        self,
        mission_ref: str,
        *,
        workspace: str | Path = ".",
        result_ref: str | None = None,
        max_attempts: int = 1,
    ) -> MissionCLIResult:
        root = Path(workspace).resolve()
        mission_path = _resolve_workspace_ref(root, mission_ref)
        mission = MissionIR.from_dict(json.loads(mission_path.read_text(encoding="utf-8")))
        mission_result = MissionRuntime(workspace=root, max_attempts=max_attempts).run(mission)
        mission_result.validate()

        output_ref = result_ref or f"host_results/{mission_result.mission_id}.mission_result.json"
        _write_json_ref(root, output_ref, mission_result.to_dict())
        cli_result = MissionCLIResult(
            mission_id=mission_result.mission_id,
            status=mission_result.status,
            mission_result_ref=output_ref,
            evidence_refs=list(mission_result.evidence_refs),
            artifact_refs=list(mission_result.artifact_refs),
            failed_constraint_ids=list(mission_result.failed_constraint_ids),
            metrics=dict(mission_result.metrics),
        )
        adapter_result = AdapterResult(
            invocation_id=f"cli-run-{mission_result.mission_id}",
            adapter_id=self.adapter_id,
            status="completed",
            output_refs=[output_ref],
            evidence_refs=list(mission_result.evidence_refs),
            metrics={"artifact_count": len(mission_result.artifact_refs)},
        )
        adapter_result.validate()
        cli_result.validate()
        return cli_result

    def run(self, argv: Sequence[str]) -> MissionCLIResult:
        parser = _parser()
        args = parser.parse_args(list(argv))
        return self.run_mission_ref(
            args.mission_ref,
            workspace=args.workspace,
            result_ref=args.result_ref,
            max_attempts=args.max_attempts,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the optional CLI shell and print the refs-only result summary."""

    result = MissionCLI().run(argv or [])
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a MissionForge MissionIR ref through the optional CLI shell.")
    parser.add_argument("--workspace", default=".", help="Workspace root.")
    parser.add_argument("--mission-ref", required=True, help="Workspace-relative MissionIR JSON ref.")
    parser.add_argument("--result-ref", default=None, help="Workspace-relative MissionResult output ref.")
    parser.add_argument("--max-attempts", type=int, default=1, help="Runtime max attempts.")
    return parser


def _write_json_ref(root: Path, ref: str, payload: Mapping[str, Any]) -> None:
    data = ensure_json_value(require_mapping(payload, ref), ref)
    path = _resolve_workspace_ref(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "workspace_ref")
    path = (root / safe_ref).resolve()
    if root not in path.parents and path != root:
        raise ContractValidationError("MissionCLI ref escapes workspace")
    return path
