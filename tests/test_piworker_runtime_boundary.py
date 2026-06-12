from __future__ import annotations

import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.adapters.pi_agent_runtime import (
    PI_AGENT_OUTPUT_SCHEMA_VERSION,
    PiAgentCommandResult,
    PiAgentRuntimeAdapter,
    PiAgentRuntimeConfig,
)
from missionforge import stable_json_hash
from missionforge.agentic_ledger import (
    DecisionLedgerEventKind,
    TaskContractDecisionLedgerEntry,
    read_decision_ledger,
    replay_decision_ledger,
)
from missionforge.agentic_repair_controller import RepairExecutionDirective
from missionforge.agentic_revision_controller import RevisionPendingRecord
from missionforge.piworker_call import PiWorkerCallResultStatus
from missionforge.piworker_runtime import (
    PiWorkerRuntimeFactory,
    create_default_piworker_adapter,
    run_repair_directive_with_default_piworker,
    run_revision_draft_with_default_piworker,
)


class PiWorkerRuntimeBoundaryTests(unittest.TestCase):
    def test_factory_creates_pi_agent_runtime_adapter(self) -> None:
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",))

        adapter = PiWorkerRuntimeFactory(config=config).create_default_worker()

        self.assertIsInstance(adapter, PiAgentRuntimeAdapter)
        self.assertTrue(callable(getattr(adapter, "run_call", None)))
        self.assertEqual(adapter.config.command, ("pi-agent-runtime",))
        self.assertIsInstance(create_default_piworker_adapter(config), PiAgentRuntimeAdapter)

    def test_runner_does_not_import_pi_agent_adapter_directly(self) -> None:
        tree = ast.parse(Path("src/missionforge/runner.py").read_text(encoding="utf-8"))
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("missionforge.adapters.pi_agent_runtime"):
                        violations.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in {"missionforge.adapters.pi_agent_runtime", "adapters.pi_agent_runtime"}:
                    violations.append(module)

        self.assertEqual(violations, [])

    def test_repair_directive_runs_through_repair_piworker_call(self) -> None:
        runner = _RepairRuntimeRunner()
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",))
        directive = _repair_directive()

        with TemporaryDirectory() as tmpdir:
            _write_initial_ledger(Path(tmpdir))
            result = PiWorkerRuntimeFactory(config=config, runner=runner).run_repair_directive(
                directive,
                workspace=tmpdir,
                contract_ref="contract/task_contract.json",
                permission_manifest_ref="policy/permission_manifest.json",
                writable_refs=["artifacts", "reports"],
                decision_ledger_ref="ledgers/decision_ledger.jsonl",
            )
            call_result_payload = json.loads(
                Path(tmpdir, f"attempts/{result.call_id}/piworker_call_result.json").read_text(encoding="utf-8")
            )
            ledger_entries = read_decision_ledger(tmpdir, decision_ledger_ref="ledgers/decision_ledger.jsonl")
            replay = replay_decision_ledger(tmpdir, decision_ledger_ref="ledgers/decision_ledger.jsonl")

        self.assertEqual(result.status, PiWorkerCallResultStatus.COMPLETED)
        self.assertEqual(result.output_refs, ["artifacts/final.md"])
        self.assertEqual(call_result_payload, result.to_dict())
        self.assertEqual(ledger_entries[-1].event_kind, DecisionLedgerEventKind.REPAIR_EXECUTION_RECORDED)
        self.assertEqual(ledger_entries[-1].ref_map["piworker_call_result_ref"], f"attempts/{result.call_id}/piworker_call_result.json")
        self.assertEqual(replay.status.value, "repair")
        self.assertEqual(runner.captured_role, "repair_piworker")

    def test_repair_directive_helper_uses_default_piworker_factory(self) -> None:
        runner = _RepairRuntimeRunner()
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",))

        with TemporaryDirectory() as tmpdir:
            result = run_repair_directive_with_default_piworker(
                _repair_directive(),
                workspace=tmpdir,
                contract_ref="contract/task_contract.json",
                permission_manifest_ref="policy/permission_manifest.json",
                writable_refs=["artifacts", "reports"],
                piworker_config=config,
                runner=runner,
            )

            input_payload = json.loads(
                Path(tmpdir, f"attempts/{result.call_id}/pi_agent_input.json").read_text(encoding="utf-8")
            )
            call_result_payload = json.loads(
                Path(tmpdir, f"attempts/{result.call_id}/piworker_call_result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.output_refs, ["artifacts/final.md"])
        self.assertEqual(call_result_payload, result.to_dict())
        self.assertEqual(input_payload["piworker_call"]["role"], "repair_piworker")
        self.assertEqual(runner.captured_role, "repair_piworker")

    def test_revision_pending_runs_through_revision_drafter_piworker_call(self) -> None:
        runner = _RepairRuntimeRunner()
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",))
        expected_ref = "revisions/revision-request-001/revised_task_contract.json"

        with TemporaryDirectory() as tmpdir:
            _write_initial_ledger(Path(tmpdir))
            result = run_revision_draft_with_default_piworker(
                _revision_pending_record(),
                workspace=tmpdir,
                permission_manifest_ref="policy/permission_manifest.json",
                writable_refs=["revisions/revision-request-001"],
                expected_output_ref=expected_ref,
                piworker_config=config,
                runner=runner,
                decision_ledger_ref="ledgers/decision_ledger.jsonl",
            )
            input_payload = json.loads(
                Path(tmpdir, f"attempts/{result.call_id}/pi_agent_input.json").read_text(encoding="utf-8")
            )
            call_result_payload = json.loads(
                Path(tmpdir, f"attempts/{result.call_id}/piworker_call_result.json").read_text(encoding="utf-8")
            )
            ledger_entries = read_decision_ledger(tmpdir, decision_ledger_ref="ledgers/decision_ledger.jsonl")
            replay = replay_decision_ledger(tmpdir, decision_ledger_ref="ledgers/decision_ledger.jsonl")

        self.assertEqual(result.status, PiWorkerCallResultStatus.COMPLETED)
        self.assertEqual(result.output_refs, [expected_ref])
        self.assertEqual(call_result_payload, result.to_dict())
        self.assertEqual(ledger_entries[-1].event_kind, DecisionLedgerEventKind.REVISION_DRAFT_RECORDED)
        self.assertEqual(ledger_entries[-1].ref_map["piworker_call_result_ref"], f"attempts/{result.call_id}/piworker_call_result.json")
        self.assertEqual(replay.status.value, "revision_required")
        self.assertEqual(input_payload["piworker_call"]["role"], "revision_drafter_piworker")
        self.assertEqual(runner.captured_role, "revision_drafter_piworker")


if __name__ == "__main__":
    unittest.main()


class _RepairRuntimeRunner:
    def __init__(self) -> None:
        self.captured_role = ""

    def run(self, command, *, input_path: Path, cwd: Path, timeout_seconds: int, env) -> PiAgentCommandResult:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        self.captured_role = str(payload["piworker_call"]["role"])
        artifact_ref = str(payload["piworker_call"]["expected_output_refs"][0])
        output_ref = str(payload["output_ref"])
        session_ref = str(payload["session_ref"])
        events_ref = str(payload["events_ref"])
        metrics_ref = str(payload["metrics_ref"])
        savepoints_ref = str(payload["savepoints_ref"])
        _write_text(cwd / artifact_ref, "repaired\n")
        _write_text(cwd / session_ref, "{}\n")
        _write_text(cwd / events_ref, "{}\n")
        _write_text(cwd / metrics_ref, "{}\n")
        _write_text(cwd / savepoints_ref, '{"schema_version": "missionforge.pi_agent_runtime_savepoint.v1"}\n')
        _write_text(
            cwd / output_ref,
            json.dumps(
                {
                    "schema_version": PI_AGENT_OUTPUT_SCHEMA_VERSION,
                    "work_unit_id": payload["work_unit_id"],
                    "status": "completed",
                    "produced_artifacts": [artifact_ref],
                    "changed_refs": [artifact_ref],
                    "commands_run": [],
                    "tests_run": [],
                    "failures": [],
                    "worker_claims": ["assistant_final_text_present:length=8"],
                    "verifier_evidence": [artifact_ref],
                    "new_unknowns": [],
                    "recommended_next_steps": [],
                    "verification_status": "not_run",
                    "input_ref": payload["input_ref"],
                    "output_ref": output_ref,
                    "session_ref": session_ref,
                    "events_ref": events_ref,
                    "metrics_ref": metrics_ref,
                    "savepoints_ref": savepoints_ref,
                    "duration_ms": 1,
                    "metrics": {},
                },
                sort_keys=True,
            )
            + "\n",
        )
        return PiAgentCommandResult(returncode=0)


def _repair_directive() -> RepairExecutionDirective:
    repair_ticket_ref = "repairs/repair-ticket-001/repair_ticket.json"
    repair_ticket_hash = "sha256:" + ("b" * 64)
    payload = {
        "schema_version": "repair_execution_directive.v1",
        "directive_id": "repair-execution-"
        + stable_json_hash(
            {
                "schema_version": "repair_execution_directive.v1",
                "repair_ticket_ref": repair_ticket_ref,
                "repair_ticket_hash": repair_ticket_hash,
            }
        ).split(":", 1)[1],
        "run_id": "run-001",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + ("a" * 64),
        "repair_ticket_ref": repair_ticket_ref,
        "repair_ticket_hash": repair_ticket_hash,
        "source_result_ref": "results/result-001.json",
        "source_repair_brief_ref": "projections/repair_brief.json",
        "worker_brief_ref": "projections/worker_brief.json",
        "execution_packet_ref": "packets/repairs/repair-ticket-001/execution_packet.json",
        "execution_report_ref": "reports/repairs/repair-ticket-001/execution_report.json",
        "target_artifact_refs": ["artifacts/final.md"],
        "context_refs": [
            "repairs/repair-ticket-001/repair_ticket.json",
            "results/result-001.json",
            "projections/repair_brief.json",
        ],
        "status": "ready",
    }
    payload["directive_hash"] = "sha256:" + ("0" * 64)
    payload["directive_hash"] = stable_json_hash(
        {key: value for key, value in payload.items() if key != "directive_hash"}
    )
    return RepairExecutionDirective.from_dict(payload)


def _revision_pending_record() -> RevisionPendingRecord:
    source_result_ref = "results/result-001.json"
    source_revision_request_ref = "revisions/request.json"
    payload = {
        "schema_version": "revision_pending_record.v1",
        "pending_id": "revision-pending-"
        + stable_json_hash(
            {
                "schema_version": "revision_pending_record.v1",
                "run_id": "run-001",
                "contract_hash": "sha256:" + ("a" * 64),
                "source_result_ref": source_result_ref,
                "source_revision_request_ref": source_revision_request_ref,
            }
        ).split(":", 1)[1],
        "run_id": "run-001",
        "contract_id": "contract-001",
        "contract_hash": "sha256:" + ("a" * 64),
        "contract_ref": "contract/task_contract.json",
        "request_id": "revision-request-001",
        "source_result_ref": source_result_ref,
        "source_judge_report_ref": "reports/judge_report.json",
        "source_revision_request_ref": source_revision_request_ref,
        "execution_packet_ref": "packets/execution_packet.json",
        "execution_report_ref": "reports/execution_report.json",
        "judge_packet_ref": "packets/judge_packet.json",
        "judge_report_ref": "reports/judge_report.json",
        "authority_required": "product_integration",
        "evidence_refs": ["reports/execution_report.json"],
        "status": "pending",
    }
    payload["pending_hash"] = "sha256:" + ("0" * 64)
    payload["pending_hash"] = stable_json_hash(
        {key: value for key, value in payload.items() if key != "pending_hash"}
    )
    return RevisionPendingRecord.from_dict(payload)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_initial_ledger(root: Path) -> None:
    ledger = root / "ledgers/decision_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    entry = TaskContractDecisionLedgerEntry(
        entry_id="ledger-entry-000001",
        run_id="run-001",
        event_kind=DecisionLedgerEventKind.CONTRACT_FROZEN,
        contract_id="contract-001",
        contract_hash="sha256:" + ("a" * 64),
        ref_map={"contract_ref": "contract/task_contract.json"},
    )
    ledger.write_text(json.dumps(entry.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
