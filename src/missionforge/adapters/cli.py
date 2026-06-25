"""Read-only operator CLI for MissionForge refs.

This adapter module is deliberately outside the package root. It observes
existing refs and renders safe status summaries; it does not execute,
schedule, accept, repair, or mutate runs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import time
from typing import Any, TextIO

from ..contracts import assert_refs_only_payload, ensure_json_value, validate_ref
from ..kernel import KernelRunInspection, inspect_kernel_run


@dataclass(frozen=True)
class MissionRunView:
    """Refs-only operator view over one Kernel run."""

    flow_id: str
    run_id: str
    status: str
    flow_result_ref: str
    contract_ref: str
    contract_hash: str
    snapshot_status: str = ""
    current_step_id: str = ""
    current_role: str = ""
    latest_event_kind: str = ""
    latest_event_status: str = ""
    last_safe_point_ref: str = ""
    pending_user_event_count: int = 0
    step_record_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    decision_refs: list[str] = field(default_factory=list)
    observation_refs: list[str] = field(default_factory=list)
    metric_refs: list[str] = field(default_factory=list)
    failure_refs: list[str] = field(default_factory=list)
    run_event_count: int = 0
    ledger_event_count: int = 0
    stop_reason: str = ""
    missing_step_record_refs: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_inspection(cls, inspection: KernelRunInspection) -> "MissionRunView":
        return cls(
            flow_id=inspection.flow_id,
            run_id=inspection.run_id,
            status=inspection.status,
            flow_result_ref=inspection.flow_result_ref,
            contract_ref=inspection.contract_ref,
            contract_hash=inspection.contract_hash,
            snapshot_status=inspection.snapshot_status,
            current_step_id=inspection.current_step_id,
            current_role=inspection.current_role,
            latest_event_kind=inspection.latest_event_kind,
            latest_event_status=inspection.latest_event_status,
            last_safe_point_ref=inspection.last_safe_point_ref,
            pending_user_event_count=inspection.pending_user_event_count,
            step_record_refs=list(inspection.step_record_refs),
            artifact_refs=list(inspection.artifact_refs),
            decision_refs=list(inspection.decision_refs),
            observation_refs=list(inspection.observation_refs),
            metric_refs=list(inspection.metric_refs),
            failure_refs=list(inspection.failure_refs),
            run_event_count=inspection.run_event_count,
            ledger_event_count=inspection.ledger_event_count,
            stop_reason=inspection.stop_reason,
            missing_step_record_refs=list(inspection.missing_step_record_refs),
            steps=[
                {
                    "step_id": step.step_id,
                    "status": step.status,
                    "step_record_ref": step.step_record_ref,
                    "output_refs": list(step.output_refs),
                    "context_projection_ref": step.context_projection_ref,
                    "permission_manifest_ref": step.permission_manifest_ref,
                    "execution_report_ref": step.execution_report_ref,
                    "metric_refs": list(step.metric_refs),
                    "failure_refs": list(step.failure_refs),
                }
                for step in inspection.step_records
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "flow_id": self.flow_id,
            "run_id": self.run_id,
            "status": self.status,
            "flow_result_ref": self.flow_result_ref,
            "contract_ref": self.contract_ref,
            "contract_hash": self.contract_hash,
            "snapshot_status": self.snapshot_status,
            "current_step_id": self.current_step_id,
            "current_role": self.current_role,
            "latest_event_kind": self.latest_event_kind,
            "latest_event_status": self.latest_event_status,
            "last_safe_point_ref": self.last_safe_point_ref,
            "pending_user_event_count": self.pending_user_event_count,
            "step_record_refs": list(self.step_record_refs),
            "artifact_refs": list(self.artifact_refs),
            "decision_refs": list(self.decision_refs),
            "observation_refs": list(self.observation_refs),
            "metric_refs": list(self.metric_refs),
            "failure_refs": list(self.failure_refs),
            "run_event_count": self.run_event_count,
            "ledger_event_count": self.ledger_event_count,
            "stop_reason": self.stop_reason,
            "missing_step_record_refs": list(self.missing_step_record_refs),
            "steps": [dict(step) for step in self.steps],
        }
        return dict(assert_refs_only_payload(ensure_json_value(payload, "mission_run_view"), "mission_run_view"))


def build_mission_run_view(workspace: str | Path, *, flow_result_ref: str) -> MissionRunView:
    """Build a refs-only status view for one recorded Kernel run."""

    safe_ref = validate_ref(flow_result_ref, "mission_run_view.flow_result_ref")
    return MissionRunView.from_inspection(inspect_kernel_run(workspace, safe_ref))


def render_mission_run_view(view: MissionRunView) -> str:
    """Render a compact human-readable status view without artifact bodies."""

    current = view.current_step_id or "<none>"
    current_role = view.current_role or "<none>"
    latest = view.latest_event_kind or "<none>"
    latest_status = view.latest_event_status or "<none>"
    safe_point = view.last_safe_point_ref or "<none>"
    lines = [
        "MissionForge run",
        f"  flow: {view.flow_id}",
        f"  run: {view.run_id}",
        f"  status: {view.status}",
        f"  snapshot: {view.snapshot_status or '<none>'}",
        f"  current: {current} ({current_role})",
        f"  latest_event: {latest} status={latest_status}",
        f"  stop_reason: {view.stop_reason or '<none>'}",
        f"  pending_user_events: {view.pending_user_event_count}",
        f"  last_safe_point_ref: {safe_point}",
        f"  steps: {len(view.step_record_refs)} recorded",
        f"  events: {view.run_event_count} run, {view.ledger_event_count} ledger",
        "  refs:",
        f"    flow_result: {view.flow_result_ref}",
        f"    contract: {view.contract_ref}",
    ]
    if view.observation_refs:
        lines.append("    observations:")
        lines.extend(f"      - {ref}" for ref in view.observation_refs)
    if view.artifact_refs:
        lines.append("    artifacts:")
        lines.extend(f"      - {ref}" for ref in view.artifact_refs)
    if view.decision_refs:
        lines.append("    decisions:")
        lines.extend(f"      - {ref}" for ref in view.decision_refs)
    if view.missing_step_record_refs:
        lines.append("    missing_step_records:")
        lines.extend(f"      - {ref}" for ref in view.missing_step_record_refs)
    return "\n".join(lines) + "\n"


def main(
    argv: list[str] | None = None,
    *,
    output_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    output = output_stream or sys.stdout
    errors = error_stream or sys.stderr
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command in {"tui", "status"}:
        return _run_status_command(args, output_stream=output, error_stream=errors)
    parser.print_help(file=errors)
    return 2


def _run_status_command(args: argparse.Namespace, *, output_stream: TextIO, error_stream: TextIO) -> int:
    flow_result_ref = args.flow_result_ref or args.run_ref
    if not flow_result_ref:
        error_stream.write("missing required --flow-result-ref or --run-ref\n")
        return 2
    try:
        while True:
            view = build_mission_run_view(args.workspace, flow_result_ref=flow_result_ref)
            if args.json:
                payload = json.dumps(view.to_dict(), sort_keys=True)
                output_stream.write(payload + "\n")
            else:
                output_stream.write(render_mission_run_view(view))
            output_stream.flush()
            if not args.watch:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary normalizes failures.
        error_stream.write(f"missionforge adapter error: {type(exc).__name__}: {exc}\n")
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m missionforge.adapters.cli")
    subparsers = parser.add_subparsers(dest="command")
    for command in ("tui", "status"):
        sub = subparsers.add_parser(command, help="observe a Kernel run through refs-only records")
        sub.add_argument("--workspace", default=".", help="workspace root")
        sub.add_argument("--flow-result-ref", default="", help="Kernel flow_result.json ref")
        sub.add_argument("--run-ref", default="", help="alias for --flow-result-ref")
        sub.add_argument("--json", action="store_true", help="emit one JSON object")
        sub.add_argument("--watch", action="store_true", help="poll and render repeatedly")
        sub.add_argument("--interval", type=float, default=2.0, help="watch polling interval seconds")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
