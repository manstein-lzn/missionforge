"""Minimal host-Python use of MissionForge Kernel primitives.

This example is intentionally product-neutral. It shows how ordinary Python
code can assemble a tiny bounded worker/judge flow, preview one step boundary,
debug-run one explicit step, execute the flow, and inspect the run through
refs-only records.

Run from the repository root with:

    PYTHONPATH=src python3 examples/kernel_host_toolkit_example.py --workspace /tmp/mf-kernel-host-example
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from missionforge import PiWorkerCall, PiWorkerCallRole, stable_json_hash
from missionforge.kernel import (
    Artifact,
    ArtifactRole,
    Flow,
    Step,
    StepCompileContext,
    inspect_kernel_run,
    preview_flow_step,
    read_flow_route,
    run_flow,
    run_flow_step_once,
)


CONTRACT_REF = "contract/task_contract.json"
REQUEST_REF = "inputs/request.md"
BRIEF_REF = "reports/implementation_brief.md"
WRITER_DECISION_REF = "state/writer_decision.json"
DECISION_REF = "reviews/judge_decision.json"


class FixturePiWorkerAdapter:
    """Small deterministic adapter used only by this host-side example."""

    adapter_family = "kernel-host-toolkit-fixture"

    def run_call(
        self,
        call: PiWorkerCall,
        *,
        workspace: str | Path = ".",
        evidence_store: Any | None = None,
        call_spec: Any | None = None,
        exit_criteria: list[str] | None = None,
        stop_conditions: list[str] | None = None,
        extension_lock_ref: str | None = None,
        runtime_progress_sink: Any | None = None,
    ) -> "ExampleWorkerAdapterResult":
        root = Path(workspace)
        produced_refs: list[str] = []
        for output_ref in call.expected_output_refs:
            if output_ref == BRIEF_REF:
                _write_text(
                    root,
                    output_ref,
                    "\n".join(
                        [
                            "# Implementation Brief",
                            "",
                            "The host application supplies the product logic.",
                            "MissionForge supplies refs, permissions, context diagnostics, and ledgers.",
                            "",
                        ]
                    ),
                )
            elif output_ref == WRITER_DECISION_REF:
                _write_json(root, output_ref, {"decision": "ready_for_judge", "artifact_refs": [BRIEF_REF]})
            elif output_ref == DECISION_REF:
                _write_json(root, output_ref, {"decision": "accepted", "accepted_artifact_refs": [BRIEF_REF]})
            else:
                _write_json(root, output_ref, {"status": "completed"})
            produced_refs.append(output_ref)

        report_ref = f"attempts/{call.call_id}/execution_report.json"
        report = ExampleExecutionReport(
            report_id=f"R-{call.call_id}",
            call_id=call.call_id,
            status="completed",
            produced_artifacts=produced_refs,
            changed_refs=[*produced_refs, report_ref],
            evidence_refs=[],
        )
        _write_json(root, report_ref, report.to_dict())
        return ExampleWorkerAdapterResult(
            execution_report=report,
            worker_result=ExampleWorkerResult(status="completed", execution_report_ref=report_ref),
        )


@dataclass(frozen=True)
class ExampleExecutionReport:
    report_id: str
    call_id: str
    status: str
    produced_artifacts: list[str]
    changed_refs: list[str]
    evidence_refs: list[str]
    worker_claims: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.report_id or not self.call_id or not self.status:
            raise ValueError("invalid example execution report")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "report_id": self.report_id,
            "call_id": self.call_id,
            "status": self.status,
            "produced_artifacts": list(self.produced_artifacts),
            "changed_refs": list(self.changed_refs),
            "evidence_refs": list(self.evidence_refs),
            "worker_claims": list(self.worker_claims),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class ExampleWorkerResult:
    status: str
    execution_report_ref: str

    def validate(self) -> None:
        if not self.status or not self.execution_report_ref:
            raise ValueError("invalid example worker result")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"status": self.status, "execution_report_ref": self.execution_report_ref}


@dataclass(frozen=True)
class ExampleWorkerAdapterResult:
    execution_report: ExampleExecutionReport
    worker_result: ExampleWorkerResult
    event_evidence_refs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.execution_report.validate()
        self.worker_result.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "execution_report": self.execution_report.to_dict(),
            "worker_result": self.worker_result.to_dict(),
            "event_evidence_refs": list(self.event_evidence_refs),
            "metrics": dict(self.metrics),
        }


def build_flow() -> Flow:
    """Return a tiny worker -> independent judge flow."""

    writer = Step(
        id="writer",
        brief="Use the frozen contract and request ref to write a short implementation brief.",
        inputs=[CONTRACT_REF, REQUEST_REF],
        outputs=[BRIEF_REF, WRITER_DECISION_REF],
        read=["contract", "inputs"],
        write=["reports", "state"],
        role=PiWorkerCallRole.EXECUTOR,
        route_on=WRITER_DECISION_REF,
        route_fields=["decision"],
    )
    judge = Step(
        id="judge",
        brief="Review the brief against the frozen contract and write a structured decision.",
        inputs=[CONTRACT_REF, BRIEF_REF],
        outputs=[DECISION_REF],
        read=["contract", "reports"],
        write=["reviews"],
        role=PiWorkerCallRole.JUDGE,
        route_on=DECISION_REF,
        route_fields=["decision"],
    )
    return Flow(
        id="kernel-host-toolkit-demo",
        steps=[writer, judge],
        routes={"writer.ready_for_judge": "judge", "judge.accepted": Flow.stop("accepted")},
        artifacts=[
            Artifact(CONTRACT_REF, role=ArtifactRole.INPUT, owner="product"),
            Artifact(REQUEST_REF, role=ArtifactRole.INPUT, owner="product"),
            Artifact(BRIEF_REF, role=ArtifactRole.OUTPUT, owner="piworker"),
            Artifact(WRITER_DECISION_REF, role=ArtifactRole.DECISION, owner="piworker"),
            Artifact(DECISION_REF, role=ArtifactRole.DECISION, owner="piworker"),
        ],
    )


def prepare_workspace(workspace: str | Path) -> StepCompileContext:
    """Write a minimal contract and request, then return compile context."""

    root = Path(workspace)
    contract = {
        "schema_version": "example.task_contract.v1",
        "contract_id": "kernel-host-toolkit-demo-contract",
        "objective": "Demonstrate product-neutral MissionForge Kernel orchestration.",
        "required_outputs": [BRIEF_REF],
        "acceptance": "An independent judge step must route to accepted.",
    }
    _write_json(root, CONTRACT_REF, contract)
    _write_text(root, REQUEST_REF, "Show the smallest useful host-owned MissionForge Kernel flow.\n")
    return StepCompileContext(
        flow_id="kernel-host-toolkit-demo",
        contract_id=contract["contract_id"],
        contract_hash=stable_json_hash(contract),
        contract_ref=CONTRACT_REF,
    )


def run_demo(workspace: str | Path) -> dict[str, Any]:
    """Run the example and return refs-only debug/inspection summaries."""

    root = Path(workspace)
    context = prepare_workspace(root)
    flow = build_flow()
    adapter = FixturePiWorkerAdapter()

    preview = preview_flow_step(flow, "writer", context=context)
    debug_result = run_flow_step_once(
        flow,
        "writer",
        context=context,
        workspace=root,
        ref_prefix="debug/writer",
        adapter=adapter,
        resume=False,
    )
    flow_result = run_flow(flow, context=context, workspace=root, adapter=adapter, resume=False)
    inspection = inspect_kernel_run(root, flow_result.flow_result_ref)
    route = read_flow_route(flow, "judge", workspace=root)

    return {
        "workspace": str(root),
        "preview": preview.to_dict(),
        "single_step_debug": debug_result.to_dict(),
        "flow_result_ref": flow_result.flow_result_ref,
        "route": route.to_dict(),
        "inspection": inspection.to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="workspace directory for generated refs")
    args = parser.parse_args(argv)

    if args.workspace:
        summary = run_demo(args.workspace)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    with TemporaryDirectory(prefix="missionforge-kernel-example-") as tmp:
        summary = run_demo(tmp)
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _write_json(root: Path, ref: str, payload: dict[str, Any]) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(root: Path, ref: str, content: str) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
