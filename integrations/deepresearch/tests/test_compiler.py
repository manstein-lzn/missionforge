from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge_deepresearch import (
    DeepResearchTaskContractCompileResult,
    compile_deepresearch_academic_task_contract,
    load_deepresearch_task_contract,
)

from test_product_contract import sample_request


class CompilerTests(unittest.TestCase):
    def test_request_compiles_to_task_contract_workspace_permissions_and_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            result = compile_deepresearch_academic_task_contract(sample_request(), workspace=root)
            task_contract, workspace_policy, permission_manifest = load_deepresearch_task_contract(root, result)

            self.assertEqual(DeepResearchTaskContractCompileResult.from_dict(result.to_dict()), result)
            self.assertEqual(task_contract.product_id, "deepresearch.academic")
            self.assertEqual(task_contract.contract_hash, result.contract_hash)
            self.assertEqual(workspace_policy.workspace_root_ref, result.run_workspace_ref)
            self.assertEqual(workspace_policy.artifact_root_refs, ["reports", "packages", "compiled"])
            self.assertIn("reports", permission_manifest.writable_refs)
            self.assertIn("attempts", permission_manifest.writable_refs)
            self.assertEqual(
                [ref for clause in task_contract.required_outputs for ref in clause.refs],
                [
                    "reports/final_report.md",
                    "reports/evidence_index.md",
                    "reports/research_delta.md",
                    "reports/reading_plan.md",
                    "reports/source_gaps.md",
                ],
            )
            self.assertIn("manuals/deep_research_academic.md", task_contract.source_refs)
            self.assertIn("sources/search_intent.json", task_contract.source_refs)
            self.assertIn("sources/source_collection_report.json", task_contract.source_refs)
            self.assertIn("product_contract/output_contract.json", task_contract.product_contract_refs)
            self.assertTrue((root / result.task_contract_ref).exists())
            self.assertTrue((root / result.worker_brief_ref).exists())
            self.assertTrue((root / result.judge_rubric_ref).exists())
            self.assertTrue((root / result.manual_ref).exists())
            self.assertTrue((root / "runs/npu-compiler-survey/sources/search_intent.json").exists())
            self.assertTrue((root / result.source_packet_ref).exists())
            self.assertTrue((root / result.source_collection_report_ref).exists())

    def test_live_extension_mode_compiles_extension_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            install_root = root / ".missionforge/extensions/node_modules"
            for package_name in ("pi-web-access", "@juicesharp/rpiv-web-tools"):
                install_path = install_root / package_name
                install_path.mkdir(parents=True, exist_ok=True)
                (install_path / "package.json").write_text(f'{{"name":"{package_name}"}}\n', encoding="utf-8")
            result = compile_deepresearch_academic_task_contract(
                sample_request(),
                workspace=root,
                live_extension_mode=True,
                extension_installer=_fake_extension_installer,
            )

            self.assertIsNotNone(result.extension_lock_ref)
            self.assertTrue((root / result.extension_lock_ref).exists())
            source_packet = json.loads((root / result.source_packet_ref).read_text(encoding="utf-8"))
            self.assertEqual(source_packet["mode"], "live")
            self.assertEqual(source_packet["collection_policy"]["source_acquisition"], "pi_extensions")
            report = json.loads((root / result.source_collection_report_ref).read_text(encoding="utf-8"))
            self.assertEqual(report["extension_lock_ref"], result.extension_lock_ref)
            self.assertIn("web", report["tool_surface"])
            self.assertIn("code_search", report["tool_surface"])

    def test_compile_result_does_not_embed_topic_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_deepresearch_academic_task_contract(sample_request(), workspace=tempdir)

            payload_text = json.dumps(result.to_dict(), sort_keys=True)

            self.assertIn("task_contract_ref", payload_text)
            self.assertNotIn("NPU compiler autotuning", payload_text)


def _fake_extension_installer(grant, install_root):
    package_name = grant.package.split(":", 1)[1]
    install_path = install_root / "node_modules" / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "package.json").write_text(
        f'{{"name":"{package_name}","version":"{grant.version_spec}"}}\n',
        encoding="utf-8",
    )
    return {}


if __name__ == "__main__":
    unittest.main()
