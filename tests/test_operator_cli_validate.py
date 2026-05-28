from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.cli import MissionCLI


class OperatorCLIValidateTests(unittest.TestCase):
    def test_validate_command_writes_log_ref_without_printing_raw_output(self) -> None:
        def runner(root: Path) -> tuple[int, str]:
            return 0, "validation passed\n"

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "scripts").mkdir()
            (root / "scripts/validate.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            result = MissionCLI(validate_runner=runner).run_command(["validate", "--workspace", str(root)])

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.command, "validate")
            self.assertEqual(result.data["script_ref"], "scripts/validate.sh")
            self.assertEqual(result.data["validation_log_ref"], "host_results/validation/validate.log")
            self.assertTrue((root / result.data["validation_log_ref"]).exists())
            self.assertNotIn("validation passed", str(result.to_dict()))

    def test_validate_command_maps_failure_to_validation_failed(self) -> None:
        def runner(root: Path) -> tuple[int, str]:
            return 1, "validation failed\n"

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "scripts").mkdir()
            (root / "scripts/validate.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            result = MissionCLI(validate_runner=runner).run_command(["validate", "--workspace", str(root)])

            self.assertEqual(result.exit_code, 8)
            self.assertEqual(result.error.code if result.error else "", "validation_failed")
            self.assertEqual(result.data["return_code"], 1)


if __name__ == "__main__":
    unittest.main()
