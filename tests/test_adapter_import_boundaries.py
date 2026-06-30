from __future__ import annotations

import ast
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
ALLOWED_CORE_ADAPTER_IMPORTS = {
    (CORE_ROOT / "piworker_runtime.py", "missionforge.adapters.pi_agent_runtime"),
    (CORE_ROOT / "piworker_runtime.py", "adapters.pi_agent_runtime"),
}
FORBIDDEN_PRODUCT_ADAPTER_MODULES = {
    "codexarium.py",
    "frontdesk.py",
    "example_product.py",
}
FORBIDDEN_PRODUCT_IMPORT_ROOTS = {
    "missionforge_example_product",
}


class AdapterImportBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_import_adapter_package(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            if ADAPTER_ROOT in path.parents:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "missionforge.adapters" or alias.name.startswith("missionforge.adapters."):
                            if (path, alias.name) not in ALLOWED_CORE_ADAPTER_IMPORTS:
                                violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "missionforge.adapters" or module.startswith("missionforge.adapters."):
                        if (path, module) not in ALLOWED_CORE_ADAPTER_IMPORTS:
                            violations.append(f"{path}: from {module} import ...")
                    if node.level == 1 and (module == "adapters" or module.startswith("adapters.")):
                        if (path, module) not in ALLOWED_CORE_ADAPTER_IMPORTS:
                            violations.append(f"{path}: from .{module} import ...")

        self.assertEqual(violations, [])

    def test_package_root_does_not_reexport_adapters(self) -> None:
        init_text = (CORE_ROOT / "__init__.py").read_text(encoding="utf-8")
        tree = ast.parse(init_text)
        exported_symbols: set[str] = set()
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                continue
            exported_symbols = set(ast.literal_eval(node.value))
            break

        self.assertNotIn("adapters", init_text)
        self.assertNotIn("AdapterBoundary", exported_symbols)
        self.assertNotIn("AdapterResult", exported_symbols)

    def test_no_unplanned_host_adapter_implementation_modules_exist_yet(self) -> None:
        forbidden = {
            ADAPTER_ROOT / "langgraph.py",
            ADAPTER_ROOT / "http.py",
        }

        self.assertEqual([str(path) for path in forbidden if path.exists()], [])

    def test_no_product_specific_adapter_modules_in_core_package(self) -> None:
        forbidden = {ADAPTER_ROOT / module for module in FORBIDDEN_PRODUCT_ADAPTER_MODULES}

        self.assertEqual([str(path) for path in forbidden if path.exists()], [])

    def test_core_package_does_not_import_product_integrations(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_PRODUCT_IMPORT_ROOTS:
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module in FORBIDDEN_PRODUCT_IMPORT_ROOTS:
                        violations.append(f"{path}: from {module} import ...")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
