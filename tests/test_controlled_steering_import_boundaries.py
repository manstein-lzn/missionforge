from __future__ import annotations

import ast
from pathlib import Path
import unittest


CORE_ROOT = Path("src/missionforge")
ADAPTER_ROOT = CORE_ROOT / "adapters"
STEERING_LLM_MODULE = "missionforge.adapters.steering_llm"


class ControlledSteeringImportBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_import_optional_llm_steering_adapter(self) -> None:
        violations: list[str] = []
        for path in CORE_ROOT.rglob("*.py"):
            if ADAPTER_ROOT in path.parents:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == STEERING_LLM_MODULE or alias.name.startswith(f"{STEERING_LLM_MODULE}."):
                            violations.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == STEERING_LLM_MODULE or module.startswith(f"{STEERING_LLM_MODULE}."):
                        violations.append(f"{path}: from {module} import ...")

        self.assertEqual(violations, [])

    def test_package_root_does_not_reexport_optional_llm_steering_adapter(self) -> None:
        root_init = (CORE_ROOT / "__init__.py").read_text(encoding="utf-8")

        self.assertNotIn("ControlledSteeringLLMAdapter", root_init)
        self.assertNotIn("steering_llm", root_init)


if __name__ == "__main__":
    unittest.main()

