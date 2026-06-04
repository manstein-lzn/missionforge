from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge import (
    ContractValidationError,
    DecisionLedgerEventKind,
    FinalPackage,
    RunReplayStatus,
    TaskContractDecisionLedgerEntry,
    replay_decision_ledger,
    stable_json_hash,
)


CONTRACT_HASH = "sha256:" + ("1" * 64)
OTHER_CONTRACT_HASH = "sha256:" + ("2" * 64)


class AgenticLedgerTests(unittest.TestCase):
    def test_final_package_rejects_raw_payload_fields(self) -> None:
        payload = _final_package_payload()
        payload["raw_transcript"] = "not ledger truth"

        with self.assertRaises(ContractValidationError):
            FinalPackage.from_dict(payload)

    def test_replay_accepts_final_package_tail(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_json(root / "packages/final_package.json", _final_package_payload())
            _write_ledger(
                root,
                [
                    _entry(
                        "ledger-entry-000001",
                        DecisionLedgerEventKind.JUDGE_REPORT_RECORDED,
                        status="accepted",
                        refs={"judge_report_ref": "reports/judge_report.json"},
                    ),
                    _entry(
                        "ledger-entry-000002",
                        DecisionLedgerEventKind.FINAL_PACKAGE_EMITTED,
                        status="accepted",
                        refs={"final_package_ref": "packages/final_package.json"},
                    ),
                ],
            )

            summary = replay_decision_ledger(root, decision_ledger_ref="ledgers/decision_ledger.jsonl")

            self.assertEqual(summary.status, RunReplayStatus.ACCEPTED)
            self.assertEqual(summary.final_package_ref, "packages/final_package.json")
            self.assertEqual(summary.accepted_artifact_refs, ["artifacts/final.md"])

    def test_replay_reports_repair_revision_rejected_and_blocked_tails(self) -> None:
        cases = [
            (
                DecisionLedgerEventKind.REPAIR_REQUESTED,
                "repair",
                {"repair_brief_ref": "projections/repair_brief.json"},
                RunReplayStatus.REPAIR,
            ),
            (
                DecisionLedgerEventKind.REVISION_REQUESTED,
                "revision_required",
                {"revision_request_ref": "revisions/request.json"},
                RunReplayStatus.REVISION_REQUIRED,
            ),
            (
                DecisionLedgerEventKind.JUDGE_REPORT_RECORDED,
                "rejected",
                {"judge_report_ref": "reports/judge_report.json"},
                RunReplayStatus.REJECTED,
            ),
            (
                DecisionLedgerEventKind.EXECUTION_REPORT_RECORDED,
                "blocked",
                {"execution_report_ref": "reports/execution_report.json"},
                RunReplayStatus.BLOCKED,
            ),
        ]
        for event_kind, status, refs, expected in cases:
            with self.subTest(event_kind=event_kind.value):
                with TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    _write_ledger(root, [_entry("ledger-entry-000001", event_kind, status=status, refs=refs)])

                    summary = replay_decision_ledger(root, decision_ledger_ref="ledgers/decision_ledger.jsonl")

                    self.assertEqual(summary.status, expected)

    def test_replay_fails_closed_on_mixed_contract_hashes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = _entry("ledger-entry-000001", DecisionLedgerEventKind.CONTRACT_FROZEN)
            second = _entry(
                "ledger-entry-000002",
                DecisionLedgerEventKind.JUDGE_REPORT_RECORDED,
                contract_hash=OTHER_CONTRACT_HASH,
            )
            _write_ledger(root, [first, second])

            with self.assertRaises(ContractValidationError):
                replay_decision_ledger(root, decision_ledger_ref="ledgers/decision_ledger.jsonl")

    def test_ledger_entry_rejects_artifact_body_field(self) -> None:
        payload = _entry("ledger-entry-000001", DecisionLedgerEventKind.CONTRACT_FROZEN).to_dict()
        payload["artifact_body"] = "body must stay in artifacts, not ledger"

        with self.assertRaises(ContractValidationError):
            TaskContractDecisionLedgerEntry.from_dict(payload)


def _entry(
    entry_id: str,
    event_kind: DecisionLedgerEventKind,
    *,
    status: str = "completed",
    refs: dict[str, str] | None = None,
    contract_hash: str = CONTRACT_HASH,
) -> TaskContractDecisionLedgerEntry:
    return TaskContractDecisionLedgerEntry(
        entry_id=entry_id,
        created_at="2026-06-03T00:00:00Z",
        run_id="run-001",
        event_kind=event_kind,
        contract_id="contract-001",
        contract_hash=contract_hash,
        status=status,
        ref_map=refs or {"contract_ref": "contract/task_contract.json"},
    )


def _final_package_payload() -> dict[str, object]:
    return {
        "schema_version": "final_package.v1",
        "package_id": "final-package-run-001",
        "run_id": "run-001",
        "contract_id": "contract-001",
        "contract_hash": CONTRACT_HASH,
        "contract_ref": "contract/task_contract.json",
        "judge_report_ref": "reports/judge_report.json",
        "decision_ledger_ref": "ledgers/decision_ledger.jsonl",
        "accepted_artifact_refs": ["artifacts/final.md"],
        "hard_check_refs": ["reports/hard_checks.json"],
        "metric_refs": ["metrics/run.json"],
        "product_payload_refs": [],
    }


def _write_ledger(root: Path, entries: list[TaskContractDecisionLedgerEntry]) -> None:
    ledger = root / "ledgers/decision_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "".join(json.dumps(entry.to_dict(), sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
