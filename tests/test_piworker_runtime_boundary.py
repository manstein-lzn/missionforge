from __future__ import annotations

import ast
from pathlib import Path
import unittest

from missionforge.adapters.pi_agent_runtime import PiAgentRuntimeAdapter, PiAgentRuntimeConfig
from missionforge.piworker_runtime import PiWorkerRuntimeFactory, create_default_piworker_adapter


class PiWorkerRuntimeBoundaryTests(unittest.TestCase):
    def test_factory_creates_pi_agent_runtime_adapter(self) -> None:
        config = PiAgentRuntimeConfig(command=("pi-agent-runtime",))

        worker = PiWorkerRuntimeFactory(config=config).create_default_worker()

        self.assertIsInstance(worker, PiAgentRuntimeAdapter)
        self.assertEqual(worker.config.command, ("pi-agent-runtime",))
        self.assertIsInstance(create_default_piworker_adapter(config), PiAgentRuntimeAdapter)

    def test_runner_does_not_import_pi_agent_adapter_directly(self) -> None:
        tree = ast.parse(Path("src/missionforge/runner.py").read_text(encoding="utf-8"))
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("missionforge.adapters.pi_agent_runtime"):
                        violations.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in {"missionforge.adapters.pi_agent_runtime", "adapters.pi_agent_runtime"}:
                    violations.append(module)

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
