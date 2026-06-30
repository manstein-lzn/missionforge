from __future__ import annotations

from pathlib import Path
import unittest


CORE_MODULES = [
    "src/missionforge/__init__.py",
    "src/missionforge/observation.py",
    "src/missionforge/progress_stream.py",
    "src/missionforge/interaction.py",
    "src/missionforge/piworker_progress.py",
    "src/missionforge/pi_agent_runtime_bundle.py",
    "src/missionforge/kernel/io.py",
    "src/missionforge/kernel/inspect.py",
    "src/missionforge/kernel/runner.py",
    "src/missionforge/kernel/runtime_store.py",
    "src/missionforge/kernel/context_runtime.py",
    "src/missionforge/kernel/context_reduction_runtime.py",
    "src/missionforge/kernel/batch.py",
    "src/missionforge/kernel/extensions.py",
    "src/missionforge/extensions.py",
]

ALLOWED_PATH_PATTERNS = (
    "src/missionforge/adapters/",
    "src/missionforge/evidence_store.py",
    "src/missionforge/artifacts.py",
    "src/missionforge/workspace_runtime.py",
    "src/missionforge/decision_ledger.py",
)

DISALLOWED_SNIPPETS = (
    "Path('.')",
    "Path(\".\")",
    "TemporaryDirectory(",
    "tempfile.",
)


class StaticSideEffectBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_introduce_new_implicit_filesystem_patterns(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        for rel_path in CORE_MODULES:
            path = repo_root / rel_path
            text = path.read_text(encoding="utf-8")
            if any(marker in rel_path for marker in ALLOWED_PATH_PATTERNS):
                continue
            for snippet in DISALLOWED_SNIPPETS:
                self.assertNotIn(snippet, text, msg=f"{rel_path} contains forbidden snippet {snippet}")


if __name__ == "__main__":
    unittest.main()
