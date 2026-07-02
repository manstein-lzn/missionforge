from __future__ import annotations

import ast
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
DEEPRESEARCH_ROOT = Path("integrations/deepresearch/src/missionforge_deepresearch")
DEEPRESEARCH_MODULE = "missionforge_deepresearch"


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

    def test_deepresearch_example_imports_missionforge_like_external_users(self) -> None:
        violations: list[str] = []
        for path in DEEPRESEARCH_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("missionforge."):
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "missionforge" or module.startswith("missionforge."):
                        violations.append(f"{path}: from {module} import ...")

        self.assertEqual(violations, [])

    def test_kernel_ref_constants_are_imported_from_data_module(self) -> None:
        violations: list[str] = []
        for path in DEEPRESEARCH_ROOT.rglob("*.py"):
            if path.name == "kernel_v2.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.level == 1 and node.module == "kernel_v2":
                    imported_refs = [alias.name for alias in node.names if alias.name.startswith("KERNEL_V2_")]
                    if imported_refs:
                        violations.append(f"{path}: import refs from kernel_v2 instead of kernel_refs: {imported_refs}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
