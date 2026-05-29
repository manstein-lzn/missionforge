from __future__ import annotations

import unittest

from missionforge.contracts import ContractValidationError
from missionforge_skillfoundry import (
    BundleProfile,
    CODE_RUNTIME_REQUIRED_PACKAGE_REFS,
    ProductAcceptanceMatrix,
    RiskDomain,
    SkillBundleManifest,
    SkillFoundryRequest,
    SkillProductContract,
)


def sample_request() -> SkillFoundryRequest:
    return SkillFoundryRequest.from_dict(
        {
            "request_id": "request-001",
            "bundle_id": "demo-skill",
            "desired_capability": "Create a prompt-only Codex skill for reviewing release notes.",
            "target_user": "release engineer",
            "triggers": ["When release notes need review."],
            "non_triggers": ["When code changes are required."],
            "expected_outputs": ["A prompt-only Skill package."],
            "must": ["Write package files only under package/."],
            "must_not": ["Do not include raw conversations."],
            "privacy_boundaries": ["Use sanitized source refs only."],
            "distribution_boundaries": ["Local distribution only."],
            "source_refs": ["frontdesk/sanitized_task.json"],
            "desired_bundle_profile": "prompt_only",
        }
    )


def code_runtime_request() -> SkillFoundryRequest:
    return SkillFoundryRequest.from_dict(
        {
            "request_id": "request-code-001",
            "bundle_id": "code-skill",
            "desired_capability": "Create a code-runtime Codex skill with helper scripts, schemas, and local runtime assets.",
            "target_user": "codex_user",
            "triggers": ["When a user needs a packaged code runtime skill."],
            "non_triggers": ["When a prompt-only skill is enough."],
            "expected_outputs": [
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
                "package/scripts/skill_runtime.py",
                "package/schemas/runtime.schema.json",
            ],
            "must": [
                "Write package files only under package/.",
                "Expose a local helper script with --help.",
                "Validate structured JSON schemas.",
            ],
            "must_not": ["Do not include raw conversations, provider payloads, or secrets."],
            "privacy_boundaries": ["Use sanitized source refs only."],
            "distribution_boundaries": ["Local distribution only."],
            "source_refs": ["frontdesk/code_runtime_task.json"],
            "desired_bundle_profile": "code_runtime",
        }
    )


def codexarium_runtime_request() -> SkillFoundryRequest:
    return SkillFoundryRequest.from_dict(
        {
            "request_id": "request-codexarium-001",
            "bundle_id": "codexarium",
            "desired_capability": "Create Codexarium as a code-runtime Codex skill with helper scripts, schemas, and sidecar runtime assets.",
            "target_user": "codex_user",
            "expected_outputs": [
                "package/SKILL.md",
                "package/skillfoundry.bundle.json",
                "package/README.md",
                "package/scripts/codexarium.py",
                "package/bin/codexarium-core-linux-x64",
                "package/schemas/normalized_batch.schema.json",
                "package/schemas/codex_output.schema.json",
                "package/schemas/review_item.schema.json",
                "package/schemas/source_registry.schema.json",
            ],
            "must": [
                "Package Codexarium helper commands.",
                "Declare Rust sidecar runtime asset.",
                "Respect source evidence and wiki write boundaries.",
            ],
            "must_not": ["Do not include raw Codex JSONL, provider payloads, API keys, or secrets."],
            "privacy_boundaries": ["Use sanitized source refs only."],
            "distribution_boundaries": ["Local distribution only."],
            "source_refs": ["frontdesk/codexarium_semantic_lock.json"],
            "desired_bundle_profile": "code_runtime",
        }
    )


class ProductContractTests(unittest.TestCase):
    def test_skillfoundry_request_round_trip(self) -> None:
        request = sample_request()

        self.assertEqual(SkillFoundryRequest.from_dict(request.to_dict()), request)

    def test_request_rejects_raw_prompt_fields(self) -> None:
        payload = sample_request().to_dict()
        payload["raw_prompt"] = "private"

        with self.assertRaisesRegex(ContractValidationError, "sanitized source ref"):
            SkillFoundryRequest.from_dict(payload)

    def test_product_contract_round_trip_and_hash(self) -> None:
        contract = SkillProductContract.from_request(
            sample_request(),
            request_ref="product_contract/skillfoundry_request.json",
        )

        self.assertEqual(contract.bundle_profile, BundleProfile.PROMPT_ONLY)
        self.assertIn(RiskDomain.FILESYSTEM_WRITE, contract.risk_domains)
        self.assertEqual(
            contract.target_package_refs,
            ["package/SKILL.md", "package/skillfoundry.bundle.json", "package/README.md"],
        )
        self.assertEqual(SkillProductContract.from_dict(contract.to_dict()), contract)
        self.assertTrue(contract.contract_hash.startswith("sha256:"))

    def test_code_runtime_contract_round_trip_and_hash(self) -> None:
        request = code_runtime_request()
        contract = SkillProductContract.from_request(
            request,
            request_ref="product_contract/skillfoundry_request.json",
        )

        self.assertEqual(contract.bundle_profile, BundleProfile.CODE_RUNTIME)
        self.assertIn(RiskDomain.RUNTIME_EXECUTION, contract.risk_domains)
        self.assertIn(RiskDomain.STRUCTURED_DATA_VALIDATION, contract.risk_domains)
        self.assertEqual(contract.target_package_refs, CODE_RUNTIME_REQUIRED_PACKAGE_REFS)
        self.assertEqual(contract.allowed_write_scopes, ["package"])
        self.assertEqual(SkillProductContract.from_dict(contract.to_dict()), contract)
        self.assertTrue(contract.contract_hash.startswith("sha256:"))

    def test_code_runtime_contract_uses_request_declared_package_refs(self) -> None:
        request = codexarium_runtime_request()
        contract = SkillProductContract.from_request(
            request,
            request_ref="product_contract/skillfoundry_request.json",
        )

        self.assertEqual(contract.bundle_profile, BundleProfile.CODE_RUNTIME)
        self.assertIn("package/scripts/codexarium.py", contract.target_package_refs)
        self.assertIn("package/bin/codexarium-core-linux-x64", contract.target_package_refs)
        self.assertIn("package/schemas/source_registry.schema.json", contract.target_package_refs)
        self.assertNotIn("package/scripts/skill_runtime.py", contract.target_package_refs)

    def test_code_runtime_contract_extracts_package_refs_from_natural_language_clauses(self) -> None:
        request = SkillFoundryRequest.from_dict(
            {
                **code_runtime_request().to_dict(),
                "expected_outputs": ["A runtime package with package/scripts/custom_tool.py."],
                "must": ["Also include package/schemas/custom.schema.json for structured output."],
            }
        )

        contract = SkillProductContract.from_request(
            request,
            request_ref="product_contract/skillfoundry_request.json",
        )

        self.assertIn("package/scripts/custom_tool.py", contract.target_package_refs)
        self.assertIn("package/schemas/custom.schema.json", contract.target_package_refs)
        self.assertNotIn("package/scripts/skill_runtime.py", contract.target_package_refs)

    def test_unimplemented_profile_fails_closed_at_product_contract(self) -> None:
        payload = sample_request().to_dict()
        payload["desired_bundle_profile"] = "service_runtime"
        request = SkillFoundryRequest.from_dict(payload)

        with self.assertRaisesRegex(ContractValidationError, "not implemented"):
            SkillProductContract.from_request(request, request_ref="product_contract/skillfoundry_request.json")

    def test_product_contract_rejects_hash_mismatch(self) -> None:
        payload = SkillProductContract.from_request(
            sample_request(),
            request_ref="product_contract/skillfoundry_request.json",
        ).to_dict()
        payload["contract_hash"] = "sha256:bad"

        with self.assertRaisesRegex(ContractValidationError, "contract_hash"):
            SkillProductContract.from_dict(payload)

    def test_prompt_only_acceptance_matrix_has_required_checks(self) -> None:
        matrix = ProductAcceptanceMatrix.for_prompt_only(bundle_id="demo-skill")

        self.assertEqual(ProductAcceptanceMatrix.from_dict(matrix.to_dict()), matrix)
        self.assertEqual(len(matrix.items), 9)
        self.assertIn("SF-PROMPT-SKILL-EXISTS", [item.check_id for item in matrix.items])
        self.assertTrue(matrix.matrix_hash.startswith("sha256:"))

    def test_code_runtime_acceptance_matrix_has_required_checks(self) -> None:
        matrix = ProductAcceptanceMatrix.for_code_runtime(bundle_id="code-skill")

        self.assertEqual(ProductAcceptanceMatrix.from_dict(matrix.to_dict()), matrix)
        self.assertEqual(len(matrix.items), 12)
        self.assertIn("SF-CODE-RUNTIME-ASSETS-EXIST", [item.check_id for item in matrix.items])
        self.assertIn("SF-CODE-SCHEMAS-VALID", [item.check_id for item in matrix.items])
        self.assertTrue(matrix.matrix_hash.startswith("sha256:"))

    def test_prompt_only_manifest_round_trip(self) -> None:
        manifest = SkillBundleManifest.prompt_only("demo-skill", references=["package/references/workflow.md"])

        self.assertEqual(SkillBundleManifest.from_dict(manifest.to_dict()), manifest)

    def test_code_runtime_manifest_round_trip(self) -> None:
        manifest = SkillBundleManifest.code_runtime(
            "code-skill",
            runtime_assets=["package/scripts/skill_runtime.py"],
            data_assets=["package/schemas/runtime.schema.json"],
        )

        self.assertEqual(SkillBundleManifest.from_dict(manifest.to_dict()), manifest)
        self.assertEqual(manifest.bundle_profile, BundleProfile.CODE_RUNTIME)
        self.assertEqual(manifest.entrypoint, "SKILL.md")
        self.assertEqual(manifest.permissions["network"], False)

    def test_code_runtime_manifest_health_check_follows_custom_script(self) -> None:
        manifest = SkillBundleManifest.code_runtime(
            "codexarium",
            runtime_assets=["package/scripts/codexarium.py", "package/bin/codexarium-core-linux-x64"],
            data_assets=["package/schemas/source_registry.schema.json"],
        )

        self.assertEqual(
            manifest.verification["command_health_check"],
            ["python3", "package/scripts/codexarium.py", "--help"],
        )

    def test_manifest_rejects_refs_outside_package(self) -> None:
        with self.assertRaises(ContractValidationError):
            SkillBundleManifest.prompt_only("demo-skill", references=["../secret.md"])

    def test_code_runtime_manifest_requires_runtime_and_schema_assets(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "runtime_assets"):
            SkillBundleManifest.code_runtime(
                "code-skill",
                runtime_assets=[],
                data_assets=["package/schemas/runtime.schema.json"],
            )

        with self.assertRaisesRegex(ContractValidationError, "data_assets"):
            SkillBundleManifest.code_runtime(
                "code-skill",
                runtime_assets=["package/scripts/skill_runtime.py"],
                data_assets=[],
            )


if __name__ == "__main__":
    unittest.main()
