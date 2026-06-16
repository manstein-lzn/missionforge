from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from missionforge_deepresearch import (
    DeepResearchTaskContractCompileResult,
    ResearchIntensity,
    compile_deepresearch_academic_task_contract,
    load_deepresearch_task_contract,
    research_intensity_profile,
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
            self.assertIn("sources/source_packet.json", permission_manifest.writable_refs)
            self.assertIn("attempts", permission_manifest.writable_refs)
            self.assertEqual(
                [ref for clause in task_contract.required_outputs for ref in clause.refs],
                [
                    "sources/source_packet.json",
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
            output_contract = json.loads((root / result.output_contract_ref).read_text(encoding="utf-8"))
            self.assertEqual(output_contract["source_packet_ref"], "sources/source_packet.json")
            self.assertEqual(output_contract["artifact_write_order"][0], "sources/source_packet.json")
            self.assertEqual(output_contract["research_intensity"], "standard")
            self.assertIn("sources/source_packet.json", output_contract["expected_worker_output_refs"])
            self.assertIn("quality_contract", output_contract)
            self.assertIn("Comparison Matrix", output_contract["quality_contract"]["required_report_sections"])
            self.assertEqual(
                output_contract["quality_contract"]["source_packet_minimums"]["min_source_records"],
                research_intensity_profile(ResearchIntensity.STANDARD).min_source_records,
            )
            self.assertTrue((root / result.task_contract_ref).exists())
            self.assertTrue((root / result.worker_brief_ref).exists())
            self.assertTrue((root / result.judge_rubric_ref).exists())
            self.assertTrue((root / result.manual_ref).exists())
            self.assertTrue((root / "runs/npu-compiler-survey/sources/search_intent.json").exists())
            self.assertTrue((root / result.source_packet_ref).exists())
            self.assertTrue((root / result.source_collection_report_ref).exists())

    def test_compile_records_research_intensity_in_contract_and_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            request = sample_request().__class__(
                **{
                    **sample_request().to_dict(),
                    "research_intensity": ResearchIntensity.INTENSIVE.value,
                }
            )

            result = compile_deepresearch_academic_task_contract(request, workspace=root)
            task_contract, _workspace_policy, _permission_manifest = load_deepresearch_task_contract(root, result)
            output_contract = json.loads((root / result.output_contract_ref).read_text(encoding="utf-8"))
            compile_report = json.loads((root / result.compile_report_ref).read_text(encoding="utf-8"))
            manual = (root / result.manual_ref).read_text(encoding="utf-8")

            self.assertEqual(output_contract["research_intensity"], "intensive")
            self.assertEqual(
                output_contract["research_intensity_profile"]["max_sources"],
                research_intensity_profile(ResearchIntensity.INTENSIVE).max_sources,
            )
            self.assertEqual(
                output_contract["quality_contract"]["source_packet_minimums"]["min_source_records"],
                research_intensity_profile(ResearchIntensity.INTENSIVE).min_source_records,
            )
            self.assertEqual(compile_report["research_intensity"], "intensive")
            self.assertEqual(task_contract.metadata["research_intensity"], "intensive")
            self.assertIn("Research intensity: `intensive`", manual)
            self.assertIn("High-quality contract bar", manual)
            self.assertIn("## 对比矩阵", manual)
            self.assertIn("`section_id`: `comparison_matrix`", manual)
            self.assertIn("Do not label the", manual)
            self.assertIn("Write order matters", manual)
            self.assertIn("First gather evidence", task_contract.objective)
            self.assertTrue(any(clause.clause_id == "dr-accept-methodology" for clause in task_contract.semantic_acceptance))
            self.assertTrue(any(clause.clause_id == "dr-accept-counterevidence" for clause in task_contract.semantic_acceptance))

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
            lock_payload = json.loads((root / result.extension_lock_ref).read_text(encoding="utf-8"))
            self.assertIn(
                "local:extensions/pi-academic-sources",
                [entry["package"] for entry in lock_payload["extensions"]],
            )

    def test_compile_result_does_not_embed_topic_text(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            result = compile_deepresearch_academic_task_contract(sample_request(), workspace=tempdir)

            payload_text = json.dumps(result.to_dict(), sort_keys=True)

            self.assertIn("task_contract_ref", payload_text)
            self.assertNotIn("NPU compiler autotuning", payload_text)


def _fake_extension_installer(grant, install_root):
    if grant.package.startswith("local:"):
        package_name = Path(grant.package.split(":", 1)[1]).name
        install_path = install_root / package_name
        install_path.mkdir(parents=True, exist_ok=True)
        (install_path / "package.json").write_text(
            f'{{"name":"@missionforge/{package_name}","version":"{grant.version_spec}"}}\n',
            encoding="utf-8",
        )
        (install_path / "index.js").write_text("export default function () {}\n", encoding="utf-8")
        return {}
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
