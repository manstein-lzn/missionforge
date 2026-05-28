from __future__ import annotations

import ast
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
HOST_MODULES = {
    "missionforge.adapters.cli",
    "missionforge.adapters.observation",
    "missionforge.adapters.rpc",
}
HOST_SYMBOLS = {
    "ControlRequestWriter",
    "ControlRequestWriteResult",
    "MissionCLI",
    "MissionCLIResult",
    "MissionJSONLRPC",
    "MissionRunView",
    "read_control_request",
}
FORBIDDEN_HOST_IMPORT_ROOTS = {
    "anthropic",
    "fastapi",
    "flask",
    "http",
    "httpx",
    "langgraph",
    "openai",
    "requests",
    "socket",
    "urllib",
}
ALLOWED_SUBPROCESS_IMPORTERS = {
    ADAPTER_ROOT / "cli.py",
    ADAPTER_ROOT / "pi_agent_runtime.py",
}


class HostImportBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_import_host_adapters(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            if ADAPTER_ROOT in path.parents:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in HOST_MODULES or any(alias.name.startswith(f"{module}.") for module in HOST_MODULES):
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    alias_names = {alias.name for alias in node.names}
                    if module in HOST_MODULES or any(module.startswith(f"{host_module}.") for host_module in HOST_MODULES):
                        violations.append(f"{path}: from {module} import ...")
                    if module == "missionforge.adapters" and (alias_names & HOST_SYMBOLS or {"cli", "observation"} & alias_names):
                        violations.append(f"{path}: from {module} import {sorted(alias_names)}")
                    if node.level == 1 and module == "adapters" and (alias_names & HOST_SYMBOLS or {"cli", "observation"} & alias_names):
                        violations.append(f"{path}: from .{module} import {sorted(alias_names)}")

        self.assertEqual(violations, [])

    def test_package_roots_do_not_reexport_host_adapters(self) -> None:
        root_init = (CORE_ROOT / "__init__.py").read_text(encoding="utf-8")
        adapter_init = (ADAPTER_ROOT / "__init__.py").read_text(encoding="utf-8")

        for symbol in HOST_SYMBOLS | {"cli", "observation", "langgraph", "http"}:
            self.assertNotIn(symbol, root_init)
            self.assertNotIn(symbol, adapter_init)

    def test_no_required_langgraph_http_or_network_dependencies(self) -> None:
        violations: list[str] = []
        for path in ADAPTER_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0]
                        if root in FORBIDDEN_HOST_IMPORT_ROOTS:
                            violations.append(f"{path}: import {alias.name}")
                        if root == "subprocess" and path not in ALLOWED_SUBPROCESS_IMPORTERS:
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    root = module.split(".", 1)[0]
                    if node.level == 0 and root in FORBIDDEN_HOST_IMPORT_ROOTS:
                        violations.append(f"{path}: from {module} import ...")
                    if node.level == 0 and root == "subprocess" and path not in ALLOWED_SUBPROCESS_IMPORTERS:
                        violations.append(f"{path}: from {module} import ...")

        forbidden_modules = [
            ADAPTER_ROOT / "langgraph.py",
            ADAPTER_ROOT / "http.py",
        ]
        violations.extend(str(path) for path in forbidden_modules if path.exists())

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
