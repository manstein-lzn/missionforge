from __future__ import annotations

import ast
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
PI_AGENT_MODULES = {
    "missionforge.adapters.pi_agent_runtime",
    "missionforge.adapters.pi_agent_provider_config",
}
PI_AGENT_SYMBOLS = {
    "PiAgentCommandResult",
    "PiAgentCommandRunner",
    "PiAgentProviderEnvironment",
    "PiAgentRunResult",
    "PiAgentRuntimeAdapter",
    "PiAgentRuntimeConfig",
    "SubprocessPiAgentCommandRunner",
}
ALLOWED_CORE_IMPORTS = {
    (CORE_ROOT / "piworker_runtime.py", "missionforge.adapters.pi_agent_runtime"),
    (CORE_ROOT / "piworker_runtime.py", "adapters.pi_agent_runtime"),
}
ALLOWED_SUBPROCESS_IMPORTERS = {
    ADAPTER_ROOT / "pi_agent_runtime.py",
    CORE_ROOT / "pi_agent_runtime_bundle.py",
}
FORBIDDEN_LIVE_IMPORT_ROOTS = {
    "anthropic",
    "http",
    "httpx",
    "langgraph",
    "openai",
    "requests",
    "socket",
    "urllib",
}


class PiAgentRuntimeImportBoundaryTests(unittest.TestCase):
    def test_only_runner_imports_dedicated_pi_agent_runtime_adapter(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            if ADAPTER_ROOT in path.parents:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == module or alias.name.startswith(f"{module}.") for module in PI_AGENT_MODULES):
                            if (path, alias.name) not in ALLOWED_CORE_IMPORTS:
                                violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    alias_names = {alias.name for alias in node.names}
                    if any(module == pi_agent_module or module.startswith(f"{pi_agent_module}.") for pi_agent_module in PI_AGENT_MODULES):
                        if (path, module) not in ALLOWED_CORE_IMPORTS:
                            violations.append(f"{path}: from {module} import ...")
                    if module == "missionforge.adapters" and ("pi_agent_runtime" in alias_names or alias_names & PI_AGENT_SYMBOLS):
                        violations.append(f"{path}: from {module} import {sorted(alias_names)}")
                    if node.level == 1 and module == "adapters" and ("pi_agent_runtime" in alias_names or alias_names & PI_AGENT_SYMBOLS):
                        violations.append(f"{path}: from .{module} import {sorted(alias_names)}")

        self.assertEqual(violations, [])

    def test_package_roots_do_not_reexport_pi_agent_runtime_adapter(self) -> None:
        root_init = (CORE_ROOT / "__init__.py").read_text(encoding="utf-8")
        adapter_init = (ADAPTER_ROOT / "__init__.py").read_text(encoding="utf-8")

        for symbol in PI_AGENT_SYMBOLS:
            self.assertNotIn(symbol, root_init)
            self.assertNotIn(symbol, adapter_init)
        self.assertNotIn("adapters.pi_agent_runtime", root_init)
        self.assertNotIn("from .adapters import pi_agent_runtime", root_init)

    def test_no_direct_python_provider_or_network_dependencies(self) -> None:
        violations: list[str] = []
        for path in [*ADAPTER_ROOT.rglob("*.py"), CORE_ROOT / "pi_agent_runtime_bundle.py"]:
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

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
