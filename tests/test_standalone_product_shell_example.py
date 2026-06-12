from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from examples.standalone_product_shell import run


class StandaloneProductShellExampleTests(unittest.TestCase):
    def test_standalone_product_shell_reaches_accepted_from_public_primitives(self) -> None:
        with TemporaryDirectory() as tmpdir:
            summary = run(tmpdir)
            run_root = Path(tmpdir) / "runs/mini-doc"

            self.assertEqual(summary["status"], "accepted")
            self.assertEqual(summary["replay_status"], "accepted")
            self.assertEqual(summary["accepted_artifact_refs"], ["package/README.md"])
            self.assertTrue((run_root / "packages/final_package.json").is_file())
            self.assertTrue((run_root / "ledgers/decision_ledger.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
