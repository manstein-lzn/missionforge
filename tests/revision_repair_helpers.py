from __future__ import annotations

import json
from pathlib import Path

from missionforge import ContractAdjustmentRequest, MissionIR, RuntimeEngine, apply_mission_revision
from missionforge.work_unit import ExecutionReport, WorkerResult
from missionforge.workers import WorkerAdapterResult


class ResumableRevisionWorker:
    def run(self, work_unit, *, workspace=".", evidence_store=None):
        root = Path(workspace)
        artifact_ref = work_unit.expected_outputs[0]
        artifact_path = root / artifact_ref
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(f"artifact for {work_unit.work_unit_id}\n", encoding="utf-8")

        attempt_dir = root / f"attempts/{work_unit.work_unit_id}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        input_ref = f"attempts/{work_unit.work_unit_id}/pi_agent_input.json"
        output_ref = f"attempts/{work_unit.work_unit_id}/pi_agent_output.json"
        report_ref = f"attempts/{work_unit.work_unit_id}/execution_report.json"
        savepoints_ref = f"attempts/{work_unit.work_unit_id}/pi_agent_savepoints.jsonl"
        (root / input_ref).write_text(json.dumps({"work_unit_id": work_unit.work_unit_id}), encoding="utf-8")
        (root / output_ref).write_text(json.dumps({"produced_artifacts": [artifact_ref]}), encoding="utf-8")
        (root / savepoints_ref).write_text(
            json.dumps(
                {
                    "schema_version": "missionforge.pi_agent_runtime_savepoint.v1",
                    "turn_index": 1,
                    "resume_hint": {"boundary": "after_completed_turn"},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=[artifact_ref],
            changed_refs=[artifact_ref, output_ref, savepoints_ref],
            evidence_refs=[],
            metrics={
                "input_ref": input_ref,
                "output_ref": output_ref,
                "savepoints_ref": savepoints_ref,
            },
        )
        (root / report_ref).write_text(json.dumps(report.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(status="completed", execution_report_ref=report_ref),
        )

    def with_resume(self, **kwargs):
        return self


def split_adjustment() -> ContractAdjustmentRequest:
    return ContractAdjustmentRequest.from_dict(
        {
            "request_id": "adjust-001",
            "mission_run_id": "run-sample-mission",
            "iteration": 1,
            "contract_ref": "runs/run-sample-mission/contracts/base/frozen_contract.json",
            "requested_change": "split",
            "reason": "Split work.",
            "evidence_refs": ["runs/run-sample-mission/attempts.jsonl"],
            "authority_required": "harness",
        }
    )


def run_and_apply_split_revision(root: Path, mission: MissionIR):
    RuntimeEngine(workspace=root, worker=ResumableRevisionWorker()).run(mission)
    return apply_mission_revision(
        workspace=root,
        mission=mission,
        adjustment=split_adjustment(),
    )
