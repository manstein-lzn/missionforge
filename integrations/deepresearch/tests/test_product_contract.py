from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge_deepresearch import (
    AcademicResearchRequest,
    DeepResearchRunResult,
    DeepResearchRunStatus,
    ResearchIntensity,
    research_intensity_profile,
)


def sample_request() -> AcademicResearchRequest:
    return AcademicResearchRequest(
        request_id="npu-compiler-survey",
        topic="NPU compiler autotuning kernel autogen LLM harness",
        audience="R&D compiler team",
        language="zh",
        previous_run_refs=["runs/previous/packages/deepresearch_run_result.json"],
        constraints=["Prefer evidence-grounded claims."],
        non_goals=["Do not write a market research report."],
    )


class ProductContractTests(unittest.TestCase):
    def test_academic_request_round_trips(self) -> None:
        request = sample_request()

        self.assertEqual(AcademicResearchRequest.from_dict(request.to_dict()), request)
        self.assertEqual(request.research_intensity, ResearchIntensity.STANDARD)
        self.assertEqual(request.previous_run_refs, ["runs/previous/packages/deepresearch_run_result.json"])

    def test_academic_request_accepts_research_intensity(self) -> None:
        request = AcademicResearchRequest(
            request_id="intensive-demo",
            topic="compiler autotuning",
            research_intensity="intensive",
        )

        payload = request.to_dict()

        self.assertEqual(request.research_intensity, ResearchIntensity.INTENSIVE)
        self.assertEqual(payload["research_intensity"], "intensive")
        self.assertEqual(AcademicResearchRequest.from_dict(payload), request)
        self.assertGreater(
            research_intensity_profile(ResearchIntensity.INTENSIVE).max_sources,
            research_intensity_profile(ResearchIntensity.QUICK).max_sources,
        )

    def test_request_rejects_unknown_research_intensity(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "research_intensity"):
            AcademicResearchRequest(
                request_id="bad-intensity",
                topic="compiler autotuning",
                research_intensity="exhaustive",
            )

    def test_request_rejects_nested_request_id(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "one ref segment"):
            AcademicResearchRequest(request_id="bad/id", topic="compiler autotuning").validate()

    def test_run_result_is_refs_first_and_draft_ready_not_accepted(self) -> None:
        result = DeepResearchRunResult(
            request_id="demo",
            status=DeepResearchRunStatus.DRAFT_READY,
            run_workspace_ref="runs/demo",
            run_result_ref="runs/demo/packages/deepresearch_run_result.json",
            task_contract_ref="runs/demo/contract/task_contract.json",
            manual_ref="runs/demo/manuals/deep_research_academic.md",
            source_packet_ref="runs/demo/sources/source_packet.json",
            output_contract_ref="runs/demo/product_contract/output_contract.json",
            researcher_call_ref="runs/demo/attempts/researcher/piworker_call.json",
            researcher_call_result_ref="runs/demo/attempts/researcher/piworker_call_result.json",
            structural_check_ref="runs/demo/reports/structural_checks.json",
            draft_artifact_refs=["runs/demo/reports/final_report.md"],
            evidence_refs=["runs/demo/reports/structural_checks.json"],
            metric_refs=["runs/demo/attempts/researcher/metrics.json"],
            contract_hash="sha256:" + "0" * 64,
        )

        payload = result.to_dict()

        self.assertEqual(DeepResearchRunResult.from_dict(payload), result)
        self.assertEqual(payload["status"], "draft_ready")
        self.assertNotEqual(payload["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
