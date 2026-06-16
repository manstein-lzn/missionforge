from __future__ import annotations

import ast
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
DEEPRESEARCH_MODULE = "missionforge_deepresearch"
EXPERIMENTAL_EXPORTS = {
    "run_deepresearch_academic_reviewed",
    "run_deepresearch_academic_reviewed_judged",
    "run_deepresearch_quality_evaluation",
    "run_deepresearch_tool_healthcheck",
}


class DeepResearchImportBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_import_deepresearch_integration(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == DEEPRESEARCH_MODULE or alias.name.startswith(f"{DEEPRESEARCH_MODULE}."):
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == DEEPRESEARCH_MODULE or module.startswith(f"{DEEPRESEARCH_MODULE}."):
                        violations.append(f"{path}: from {module} import ...")

        self.assertEqual(violations, [])

    def test_missionforge_package_does_not_contain_deepresearch_adapter(self) -> None:
        self.assertFalse((ADAPTER_ROOT / "deepresearch.py").exists())

    def test_deepresearch_primary_exports_exclude_experimental_workflows(self) -> None:
        import missionforge_deepresearch

        exported = set(missionforge_deepresearch.__all__)

        self.assertFalse(EXPERIMENTAL_EXPORTS & exported)


if __name__ == "__main__":
    unittest.main()
