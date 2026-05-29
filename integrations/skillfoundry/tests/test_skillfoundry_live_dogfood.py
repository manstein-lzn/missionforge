from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from missionforge.contracts import ContractValidationError
from missionforge_skillfoundry import (
    ProductGradeFinding,
    SkillFoundryDogfoodReport,
    SkillFoundryProductReport,
    run_skillfoundry_live_dogfood,
)
from missionforge_skillfoundry.dogfood import DOGFOOD_OPT_IN_ENV
from missionforge_skillfoundry.product_contract import RegistryStatus
from missionforge_skillfoundry.product_grade_gate import PRODUCT_GRADE_REPORT_REF, ProductGradeReport
from missionforge_skillfoundry.workspace import read_json_ref, write_json_ref

from test_product_contract import sample_request


class SkillFoundryLiveDogfoodTests(unittest.TestCase):
    def test_live_dogfood_requires_explicit_opt_in_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(ContractValidationError, DOGFOOD_OPT_IN_ENV):
                run_skillfoundry_live_dogfood(
                    sample_request(),
                    workspace=Path(tempdir),
                    environ={},
                    build_runner=_unexpected_runner,
                )

    def test_live_dogfood_passes_live_codex_current_config_to_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            captured = {}

            def runner(request, **kwargs):
                captured["pi_agent_config"] = kwargs["pi_agent_config"]
                captured["allow_candidate_registration"] = kwargs["allow_candidate_registration"]
                return SkillFoundryProductReport(
                    bundle_id=request.bundle_id,
                    request_ref="product_contract/skillfoundry_request.json",
                    product_contract_ref="product_contract/skill_product_contract.json",
                    mission_ref="missions/demo-skill.mission.json",
                    mission_run_id="run-skillfoundry-demo-skill",
                    verifier_refs=["evidence/verifier.json"],
                    product_grade_report_ref=PRODUCT_GRADE_REPORT_REF,
                    registry_decision_ref="registry/skillfoundry_registry.json",
                    package_refs=["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
                    final_status=RegistryStatus.PRODUCT_GRADE_REGISTERED.value,
                )

            report = run_skillfoundry_live_dogfood(
                sample_request(),
                workspace=root,
                environ={DOGFOOD_OPT_IN_ENV: "1"},
                build_runner=runner,
            )
            payload = SkillFoundryDogfoodReport.from_dict(
                read_json_ref(root, "reports/skillfoundry_live_dogfood_report.json", "dogfood_report")
            )

            config = captured["pi_agent_config"]
            self.assertEqual(config.provider_mode, "live")
            self.assertEqual(config.provider_config_source, "codex_current")
            self.assertTrue(captured["allow_candidate_registration"])
            self.assertEqual(report.outcome_category, "completed")
            self.assertEqual(report.run_status, "completed")
            self.assertEqual(payload, report)

    def test_live_dogfood_classifies_product_grade_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            def runner(request, **kwargs):
                write_json_ref(root, PRODUCT_GRADE_REPORT_REF, _failed_product_grade_report().to_dict())
                return SkillFoundryProductReport(
                    bundle_id=request.bundle_id,
                    request_ref="product_contract/skillfoundry_request.json",
                    product_contract_ref="product_contract/skill_product_contract.json",
                    mission_ref="missions/demo-skill.mission.json",
                    mission_run_id="run-skillfoundry-demo-skill",
                    verifier_refs=["evidence/verifier.json"],
                    product_grade_report_ref=PRODUCT_GRADE_REPORT_REF,
                    registry_decision_ref="registry/skillfoundry_registry.json",
                    package_refs=["package/SKILL.md"],
                    final_status=RegistryStatus.CANDIDATE_REGISTERED.value,
                )

            report = run_skillfoundry_live_dogfood(
                sample_request(),
                workspace=root,
                environ={DOGFOOD_OPT_IN_ENV: "1"},
                build_runner=runner,
            )

            self.assertEqual(report.outcome_category, "product_grade")
            self.assertEqual(report.run_status, "classified_failure")
            self.assertIn("bundle_validator:SF-PROMPT-README-EXISTS", report.issue_codes)

    def test_live_dogfood_classifies_early_exception_as_product_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            def runner(request, **kwargs):
                raise ContractValidationError("fixture failure before product contract")

            report = run_skillfoundry_live_dogfood(
                sample_request(),
                workspace=root,
                environ={DOGFOOD_OPT_IN_ENV: "1"},
                build_runner=runner,
            )

            self.assertEqual(report.outcome_category, "product_contract")
            self.assertEqual(report.run_status, "classified_failure")
            self.assertIn("contract_validation_error", report.issue_codes)


class SkillFoundryLiveDogfoodOptInTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get(DOGFOOD_OPT_IN_ENV) == "1",
        f"set {DOGFOOD_OPT_IN_ENV}=1 to run the live SkillFoundry dogfood",
    )
    def test_opt_in_live_dogfood_produces_classified_report(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            report = run_skillfoundry_live_dogfood(
                sample_request(),
                workspace=Path(tempdir),
                environ=os.environ,
            )

        self.assertIn(
            report.outcome_category,
            {"product_contract", "worker_execution", "verifier", "product_grade", "registry", "completed"},
        )
        self.assertTrue(report.live_enabled)


def _failed_product_grade_report() -> ProductGradeReport:
    return ProductGradeReport(
        bundle_id="demo-skill",
        package_refs=["package/SKILL.md"],
        package_hash="sha256:" + "0" * 64,
        verifier_status="completed_verified",
        verifier_refs=["evidence/verifier.json"],
        bundle_validation_report_ref="qa/skill_bundle_validation_report.json",
        product_grade=False,
        recommended_registry_status=RegistryStatus.CANDIDATE_REGISTERED,
        findings=[
            ProductGradeFinding(
                finding_id="bundle_validator:SF-PROMPT-README-EXISTS",
                severity="blocking",
                message="README missing",
                source_refs=[],
            )
        ],
        repair_packet_ref="qa/product_repair_packet.json",
    )


def _unexpected_runner(*args, **kwargs):
    raise AssertionError("dogfood runner should not be called without opt-in")


if __name__ == "__main__":
    unittest.main()
