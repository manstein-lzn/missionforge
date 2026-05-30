from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge import ContractValidationError
from missionforge.frontdesk.pi_node_runner import FrontDeskPiNodeRunner
from missionforge.work_unit import ExecutionReport, WorkUnitContract, WorkerResult
from missionforge.workers import WorkerAdapterResult


class _ScriptedPiWorker:
    adapter_family = "piworker"

    def __init__(self, *, produced_refs: list[str] | None = None, unsafe_metrics: bool = False) -> None:
        self.produced_refs = produced_refs
        self.unsafe_metrics = unsafe_metrics
        self.seen_work_unit: WorkUnitContract | None = None

    def run(self, work_unit: WorkUnitContract, *, workspace: str | Path = ".", evidence_store=None) -> WorkerAdapterResult:
        self.seen_work_unit = work_unit
        produced_refs = list(self.produced_refs if self.produced_refs is not None else work_unit.expected_outputs)
        for ref in produced_refs:
            path = Path(workspace) / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        metrics = {"adapter_id": "scripted_piworker"}
        if self.unsafe_metrics:
            metrics["raw_prompt"] = "hidden provider payload"
        report = ExecutionReport(
            report_id=f"R-{work_unit.work_unit_id}",
            work_unit_id=work_unit.work_unit_id,
            status="completed",
            produced_artifacts=produced_refs,
            changed_refs=produced_refs,
            evidence_refs=["evidence/frontdesk_pi_node.json"],
            worker_claims=[],
            metrics=metrics,
        )
        return WorkerAdapterResult(
            execution_report=report,
            worker_result=WorkerResult(
                status="completed",
                execution_report_ref=f"attempts/{work_unit.work_unit_id}/execution_report.json",
            ),
            event_evidence_refs=["evidence/frontdesk_pi_node.json"],
            metrics={"adapter_result_status": "completed"},
        )


class FrontDeskPiNodeRunnerTests(unittest.TestCase):
    def test_builds_bounded_piworker_contract_for_frontdesk_node(self) -> None:
        contract = FrontDeskPiNodeRunner().build_contract(
            node_name="need_griller",
            session_id="fd-pi",
            visible_refs=["frontdesk/conversation.jsonl", "frontdesk/workspace_facts.json"],
            expected_outputs=["frontdesk/need_grilling_report.json"],
        )

        self.assertEqual(contract.work_unit.allowed_scope, ["frontdesk/need_grilling_report.json"])
        self.assertEqual(contract.work_unit.expected_outputs, ["frontdesk/need_grilling_report.json"])
        self.assertIn("frontdesk/workspace_facts.json", contract.work_unit.visible_refs)

    def test_rejects_non_frontdesk_outputs(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "frontdesk/"):
            FrontDeskPiNodeRunner().build_contract(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["outside/result.json"],
            )

    def test_rejects_missing_or_extra_produced_refs(self) -> None:
        runner = FrontDeskPiNodeRunner()
        contract = runner.build_contract(
            node_name="solution_architect",
            session_id="fd-pi",
            visible_refs=["frontdesk/semantic_lock.json"],
            expected_outputs=["frontdesk/solution_plan.json"],
        )

        with self.assertRaisesRegex(ContractValidationError, "missing expected"):
            runner.validate_produced_refs(contract, [])
        with self.assertRaisesRegex(ContractValidationError, "outside allowed"):
            runner.validate_produced_refs(
                contract,
                ["frontdesk/solution_plan.json", "frontdesk/unplanned.json"],
            )
        runner.validate_produced_refs(contract, ["frontdesk/solution_plan.json"])

    def test_run_node_requires_explicit_piworker_adapter(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "explicit PiWorker adapter"):
            FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
            )

        with self.assertRaisesRegex(ContractValidationError, "PiWorker-compatible"):
            FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=object(),
            )

    def test_run_node_invokes_adapter_and_records_execution_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            worker = _ScriptedPiWorker()
            result = FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="FD Pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=worker,
                workspace=tempdir,
            )

            self.assertIsNotNone(worker.seen_work_unit)
            self.assertEqual(worker.seen_work_unit.allowed_scope, ["frontdesk/need_grilling_report.json"])
            self.assertEqual(result.execution_record.produced_refs, ["frontdesk/need_grilling_report.json"])
            execution_ref = "frontdesk/pi_nodes/fd-pi/need_griller/execution.json"
            self.assertEqual(result.execution_record.node_execution_ref, execution_ref)
            self.assertTrue((Path(tempdir) / execution_ref).exists())
            self.assertIn("frontdesk/need_grilling_report.json", result.execution_record.output_hashes)
            self.assertIn("frontdesk/pi_nodes/fd-pi/need_griller/node_spec.json", result.execution_record.input_hashes)

    def test_require_ai_authored_rejects_missing_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir) / "frontdesk/need_grilling_report.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "missing PiWorker execution provenance"):
                FrontDeskPiNodeRunner().require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_rejects_tampered_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            runner = FrontDeskPiNodeRunner()
            runner.run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )
            (Path(tempdir) / "frontdesk/need_grilling_report.json").write_text(
                "{\"changed\": true}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ContractValidationError, "output hash"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_rejects_stale_visible_input(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            visible = Path(tempdir) / "frontdesk/conversation.jsonl"
            visible.parent.mkdir(parents=True, exist_ok=True)
            visible.write_text("{\"turn_id\":\"turn-001\"}\n", encoding="utf-8")
            runner = FrontDeskPiNodeRunner()
            runner.run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
            )
            visible.write_text("{\"turn_id\":\"turn-001\"}\n{\"turn_id\":\"turn-002\"}\n", encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "visible input hash is stale"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/need_grilling_report.json",
                    node_name="need_griller",
                    session_id="fd-pi",
                )

    def test_require_ai_authored_checks_product_profile_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            runner = FrontDeskPiNodeRunner()
            profile_hash = "sha256:" + ("a" * 64)
            runner.run_node(
                node_name="intent_bundle_author",
                session_id="fd-pi",
                visible_refs=["frontdesk/product_inquiry_profile.json"],
                expected_outputs=["frontdesk/intent_bundle_candidate.json"],
                worker=_ScriptedPiWorker(),
                workspace=tempdir,
                product_profile_hash=profile_hash,
            )
            runner.require_ai_authored(
                workspace=tempdir,
                ref="frontdesk/intent_bundle_candidate.json",
                node_name="intent_bundle_author",
                session_id="fd-pi",
                product_profile_hash=profile_hash,
            )

            with self.assertRaisesRegex(ContractValidationError, "product profile hash is stale"):
                runner.require_ai_authored(
                    workspace=tempdir,
                    ref="frontdesk/intent_bundle_candidate.json",
                    node_name="intent_bundle_author",
                    session_id="fd-pi",
                    product_profile_hash="sha256:" + ("b" * 64),
                )

    def test_optional_outputs_may_be_produced_without_being_required(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            worker = _ScriptedPiWorker(
                produced_refs=[
                    "frontdesk/need_grilling_report.json",
                    "frontdesk/core_need_brief.json",
                ]
            )
            result = FrontDeskPiNodeRunner().run_node(
                node_name="need_griller",
                session_id="fd-pi",
                visible_refs=["frontdesk/conversation.jsonl"],
                expected_outputs=["frontdesk/need_grilling_report.json"],
                optional_outputs=["frontdesk/core_need_brief.json"],
                worker=worker,
                workspace=tempdir,
            )

            self.assertEqual(
                result.execution_record.produced_refs,
                ["frontdesk/need_grilling_report.json", "frontdesk/core_need_brief.json"],
            )

    def test_run_node_rejects_unsafe_worker_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "raw_prompt"):
                FrontDeskPiNodeRunner().run_node(
                    node_name="mission_ir_mapper",
                    session_id="fd-pi",
                    visible_refs=["frontdesk/solution_plan.json"],
                    expected_outputs=["frontdesk/draft_mission.json"],
                    worker=_ScriptedPiWorker(unsafe_metrics=True),
                    workspace=tempdir,
                )

    def test_run_node_rejects_unexpected_worker_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, "missing expected"):
                FrontDeskPiNodeRunner().run_node(
                    node_name="mission_ir_mapper",
                    session_id="fd-pi",
                    visible_refs=["frontdesk/solution_plan.json"],
                    expected_outputs=["frontdesk/draft_mission.json"],
                    worker=_ScriptedPiWorker(produced_refs=[]),
                    workspace=tempdir,
                )


if __name__ == "__main__":
    unittest.main()
