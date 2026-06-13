from __future__ import annotations

import json
from pathlib import Path

from missionforge.freeze import freeze_mission
from missionforge.ir import MissionIR
from missionforge.state import ArtifactHygieneReport, MissionRun, PiWorkerAttempt, RuntimeSafePoint
from tests.test_ir import sample_mission_payload


RUN_ID = "run-sample-mission"
MISSION_ID = "sample-mission"
CONTRACT_REF = f"runs/{RUN_ID}/contracts/base/frozen_contract.json"
CONTRACT_HASH = "sha256:fixture"


def seed_operator_run(
    root: Path,
    *,
    status: str = "completed_verified",
    current_contract_ref: str = CONTRACT_REF,
    revision_refs: list[str] | None = None,
    latest_safe_point: dict[str, str] | None = None,
    failed_constraint_ids: list[str] | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    contract_hash = _write_contract(root, current_contract_ref)
    _write_text(root / "package/SKILL.md", "# Fixture artifact\n")
    _write_json(root / "evidence/verifier.json", {"status": "completed_verified"})
    _write_json(root / "attempts/WU-000001/pi_agent_input.json", {"fixture": True})
    _write_json(root / "attempts/WU-000001/pi_agent_output.json", {"status": "completed"})
    _write_text(root / "attempts/WU-000001/pi_agent_session.jsonl", "{}\n")
    _write_text(root / "attempts/WU-000001/pi_agent_events.jsonl", "{}\n")
    _write_text(root / "attempts/WU-000001/pi_agent_savepoints.jsonl", "{}\n")
    _write_json(
        root / "attempts/WU-000001/pi_agent_execution_report.json",
        {
            "report_id": "R-WU-000001",
            "call_id": "WU-000001",
            "status": "completed",
            "produced_artifacts": ["package/SKILL.md"],
            "changed_refs": ["package/SKILL.md"],
            "evidence_refs": ["evidence/verifier.json"],
            "worker_claims": ["worker_claim_present:length=16"],
            "metrics": {},
        },
    )
    attempt = PiWorkerAttempt(
        attempt_id="attempt-000001",
        call_id="WU-000001",
        attempt_kind="initial",
        worker="pi_agent_runtime",
        input_ref="attempts/WU-000001/pi_agent_input.json",
        output_ref="attempts/WU-000001/pi_agent_output.json",
        report_ref="attempts/WU-000001/pi_agent_execution_report.json",
        savepoints_ref="attempts/WU-000001/pi_agent_savepoints.jsonl",
        status="completed",
        verification_status=status,
        decision="verified" if status == "completed_verified" else "failed",
        created_at="2026-06-12T00:00:00Z",
        evidence_refs=["evidence/verifier.json"],
        artifact_refs=["package/SKILL.md"],
    )
    _write_text(root / f"runs/{RUN_ID}/attempts.jsonl", json.dumps(attempt.to_dict(), sort_keys=True) + "\n")
    hygiene = ArtifactHygieneReport(
        mission_run_id=RUN_ID,
        passed=True,
        checks=[{"name": "required_ref_exists", "passed": True, "detail": "package/SKILL.md"}],
        failures=[],
    )
    _write_json(root / f"runs/{RUN_ID}/artifact_hygiene.json", hygiene.to_dict())
    _write_text(root / f"runs/{RUN_ID}/metrics/events.jsonl", "")
    _write_json(
        root / f"runs/{RUN_ID}/metrics/projection.json",
        {
            "schema_version": "missionforge.metric_projection.v1",
            "mission_run_id": RUN_ID,
            "metric_event_refs": [],
            "namespaces": {"missionforge.runtime": {"attempt_count": 1}},
            "diagnostic_flags": [],
        },
    )
    safe_point = latest_safe_point
    if safe_point is None:
        safe_point = {
            "kind": "after_completed_turn",
            "savepoint_ref": "attempts/WU-000001/pi_agent_savepoints.jsonl",
            "session_ref": "attempts/WU-000001/pi_agent_session.jsonl",
            "events_ref": "attempts/WU-000001/pi_agent_events.jsonl",
        }
    run = MissionRun(
        mission_run_id=RUN_ID,
        mission_id=MISSION_ID,
        status=status,
        current_attempt="attempt-000001",
        latest_call_id="WU-000001",
        latest_safe_point=RuntimeSafePoint.from_dict(safe_point) if safe_point else None,
        current_contract_ref=current_contract_ref,
        current_contract_hash=contract_hash,
        revision_refs=revision_refs or [],
        latest_decision="verified" if status == "completed_verified" else "failed",
        next_action="no_action" if status == "completed_verified" else "resume_repair",
        artifact_refs=["package/SKILL.md"],
        evidence_refs=["evidence/verifier.json"],
        failed_constraint_ids=failed_constraint_ids or [],
        attempts_ref=f"runs/{RUN_ID}/attempts.jsonl",
        artifact_hygiene_ref=f"runs/{RUN_ID}/artifact_hygiene.json",
        metrics={
            "contract_hash": contract_hash,
            "current_contract_ref": current_contract_ref,
            "metric_events_ref": f"runs/{RUN_ID}/metrics/events.jsonl",
            "metric_projection_ref": f"runs/{RUN_ID}/metrics/projection.json",
            "revision_refs": revision_refs or [],
        },
        updated_at="2026-06-12T00:00:00Z",
    )
    _write_json(root / f"runs/{RUN_ID}/mission_run.json", run.to_dict())


def seed_revision(root: Path) -> tuple[str, str]:
    revision_ref = f"runs/{RUN_ID}/revisions/revision-000001/revision.json"
    new_contract_ref = f"runs/{RUN_ID}/revisions/revision-000001/frozen_contract.json"
    _write_json(root / revision_ref, {"revision_id": "revision-000001", "new_contract_ref": new_contract_ref})
    new_hash = _write_contract(root, new_contract_ref)
    seed_operator_run(root, current_contract_ref=new_contract_ref, revision_refs=[revision_ref])
    return new_contract_ref, new_hash


def workspace_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = path.read_text(encoding="utf-8", errors="replace")
    return snapshot


def _write_contract(root: Path, ref: str) -> str:
    mission = MissionIR.from_dict(sample_mission_payload())
    frozen = freeze_mission(mission)
    _write_json(root / ref, frozen.to_dict())
    _write_json(root / "mission/frozen_contract.json", frozen.to_dict())
    return frozen.contract_hash


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
