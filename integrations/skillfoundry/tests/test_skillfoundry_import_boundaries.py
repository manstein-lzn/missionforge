from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
INTEGRATION_ROOT = Path("integrations/skillfoundry/src/missionforge_skillfoundry")
SKILLFOUNDRY_CORE_MODULE = "missionforge.adapters.skillfoundry"
SKILLFOUNDRY_INTEGRATION_MODULE = "missionforge_skillfoundry"
SKILLFOUNDRY_SYMBOLS = {
    "FrontDeskArtifactRef",
    "SkillFoundryCompileResult",
    "SkillFoundryMissionCompiler",
    "SkillFoundrySourceBundle",
    "SkillPackageTarget",
    "compile_skillfoundry_bundle",
}
FORBIDDEN_LIVE_IMPORT_ROOTS = {
    "anthropic",
    "http",
    "httpx",
    "langgraph",
    "openai",
    "requests",
    "skillfoundry",
    "socket",
    "urllib",
}
ALLOWED_SUBPROCESS_IMPORTERS = {
    ADAPTER_ROOT / "cli.py",
    ADAPTER_ROOT / "pi_agent_runtime.py",
}


class SkillFoundryImportBoundaryTests(unittest.TestCase):
    def test_missionforge_package_does_not_contain_skillfoundry_adapter_module(self) -> None:
        self.assertFalse((ADAPTER_ROOT / "skillfoundry.py").exists())
        self.assertIsNone(importlib.util.find_spec(SKILLFOUNDRY_CORE_MODULE))

    def test_core_modules_do_not_import_skillfoundry_integration(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if (
                            alias.name == SKILLFOUNDRY_CORE_MODULE
                            or alias.name.startswith(f"{SKILLFOUNDRY_CORE_MODULE}.")
                            or alias.name == SKILLFOUNDRY_INTEGRATION_MODULE
                            or alias.name.startswith(f"{SKILLFOUNDRY_INTEGRATION_MODULE}.")
                        ):
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    alias_names = {alias.name for alias in node.names}
                    if (
                        module == SKILLFOUNDRY_CORE_MODULE
                        or module.startswith(f"{SKILLFOUNDRY_CORE_MODULE}.")
                        or module == SKILLFOUNDRY_INTEGRATION_MODULE
                        or module.startswith(f"{SKILLFOUNDRY_INTEGRATION_MODULE}.")
                    ):
                        violations.append(f"{path}: from {module} import ...")
                    if module == "missionforge.adapters" and ("skillfoundry" in alias_names or alias_names & SKILLFOUNDRY_SYMBOLS):
                        violations.append(f"{path}: from {module} import {sorted(alias_names)}")
                    if node.level == 1 and module == "adapters" and ("skillfoundry" in alias_names or alias_names & SKILLFOUNDRY_SYMBOLS):
                        violations.append(f"{path}: from .{module} import {sorted(alias_names)}")
                    if node.level == 1 and module == "adapters.skillfoundry":
                        violations.append(f"{path}: from .{module} import ...")

        self.assertEqual(violations, [])

    def test_package_roots_do_not_reexport_skillfoundry_integration(self) -> None:
        root_init = (CORE_ROOT / "__init__.py").read_text(encoding="utf-8")
        adapter_init = (ADAPTER_ROOT / "__init__.py").read_text(encoding="utf-8")

        for symbol in SKILLFOUNDRY_SYMBOLS | {"skillfoundry"}:
            self.assertNotIn(symbol, root_init)
            self.assertNotIn(symbol, adapter_init)

    def test_no_live_skillfoundry_provider_or_host_dependencies(self) -> None:
        violations: list[str] = []
        for path in INTEGRATION_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0]
                        if root in FORBIDDEN_LIVE_IMPORT_ROOTS:
                            violations.append(f"{path}: import {alias.name}")
                        if root == "subprocess" and path not in ALLOWED_SUBPROCESS_IMPORTERS:
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    root = module.split(".", 1)[0]
                    if node.level == 0 and root in FORBIDDEN_LIVE_IMPORT_ROOTS:
                        violations.append(f"{path}: from {module} import ...")
                    if node.level == 0 and root == "subprocess" and path not in ALLOWED_SUBPROCESS_IMPORTERS:
                        violations.append(f"{path}: from {module} import ...")

        forbidden_modules = [
            ADAPTER_ROOT / "langgraph.py",
            ADAPTER_ROOT / "http.py",
            ADAPTER_ROOT / "skillfoundry.py",
            ADAPTER_ROOT / "frontdesk.py",
        ]
        violations.extend(str(path) for path in forbidden_modules if path.exists())

        self.assertEqual(violations, [])

    def test_core_runtime_has_no_skillfoundry_product_branch(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            if ADAPTER_ROOT in path.parents:
                continue
            text = path.read_text(encoding="utf-8").lower()
            if "skillfoundry" in text or "codexarium" in text:
                violations.append(str(path))

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
