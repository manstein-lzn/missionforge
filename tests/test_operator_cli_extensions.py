from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from missionforge.adapters.cli import MissionCLI
from missionforge.json_store import JsonWorkspaceStore


class OperatorCLIExtensionsTests(unittest.TestCase):
    def test_extensions_compile_inspect_and_verify(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = JsonWorkspaceStore(root)
            store.write_json("policy/permission_manifest.json", sample_manifest_payload())
            install_path = root / ".missionforge/extensions/node_modules/pi-web-access"
            install_path.mkdir(parents=True)
            (install_path / "package.json").write_text("{}\n", encoding="utf-8")

            compiled = MissionCLI().run_command(
                [
                    "extensions",
                    "compile",
                    "--workspace",
                    str(root),
                    "--manifest",
                    "policy/permission_manifest.json",
                    "--out",
                    "compiled/extension_lock.json",
                ]
            )
            self.assertEqual(compiled.exit_code, 0)
            self.assertEqual(compiled.command, "extensions compile")
            self.assertEqual(compiled.data["extension_count"], 1)
            self.assertEqual(compiled.data["extension_lock_ref"], "compiled/extension_lock.json")

            inspected = MissionCLI().run_command(
                [
                    "extensions",
                    "inspect",
                    "--workspace",
                    str(root),
                    "--manifest",
                    "policy/permission_manifest.json",
                    "--lock",
                    "compiled/extension_lock.json",
                ]
            )
            self.assertEqual(inspected.exit_code, 0)
            self.assertEqual(inspected.data["declared_grant_ids"], ["web-search"])
            self.assertEqual(inspected.data["lock"]["extension_count"], 1)

            verified = MissionCLI().run_command(
                [
                    "extensions",
                    "verify",
                    "--workspace",
                    str(root),
                    "--manifest",
                    "policy/permission_manifest.json",
                    "--lock",
                    "compiled/extension_lock.json",
                    "--report-ref",
                    "reports/extension_load_report.json",
                ]
            )
            self.assertEqual(verified.exit_code, 0)
            self.assertEqual(verified.command, "extensions verify")
            self.assertEqual(verified.data["loadable_count"], 1)
            self.assertEqual(verified.data["rejected_count"], 0)
            self.assertTrue((root / "reports/extension_load_report.json").is_file())

    def test_extensions_compile_fails_when_declared_package_is_not_installed(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            JsonWorkspaceStore(root).write_json("policy/permission_manifest.json", sample_manifest_payload())

            result = MissionCLI().run_command(
                [
                    "extensions",
                    "compile",
                    "--workspace",
                    str(root),
                    "--manifest",
                    "policy/permission_manifest.json",
                    "--out",
                    "compiled/extension_lock.json",
                ]
            )

            self.assertEqual(result.exit_code, 2)
            self.assertIn("not installed", result.error.message if result.error else "")


def sample_manifest_payload() -> dict[str, object]:
    return {
        "manifest_id": "perm-extensions",
        "schema_version": "permission_manifest.v1",
        "readable_refs": ["inputs"],
        "writable_refs": ["artifacts"],
        "network_policy": "enabled",
        "env_allowlist": ["SEARCH_API_KEY"],
        "extension_grants": [
            {
                "grant_id": "web-search",
                "package": "npm:pi-web-access",
                "version_spec": "0.10.7",
                "capability": "web",
                "requires_network": True,
                "required_env": ["SEARCH_API_KEY"],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
