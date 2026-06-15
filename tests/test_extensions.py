from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from missionforge import ContractValidationError, PermissionManifest
from missionforge.extensions import (
    ExtensionLoadReport,
    ExtensionLock,
    compile_extension_lock,
    extension_load_report_from_lock,
    verify_extension_lock,
)


def sample_manifest(**overrides: object) -> PermissionManifest:
    payload: dict[str, object] = {
        "manifest_id": "perm-extensions",
        "readable_refs": ["inputs"],
        "writable_refs": ["artifacts"],
        "network_policy": "enabled",
        "env_allowlist": ["PATH", "SEARCH_API_KEY"],
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
    payload.update(overrides)
    return PermissionManifest.from_dict(payload)


class ExtensionTests(unittest.TestCase):
    def test_compile_extension_lock_requires_preinstalled_package_by_default(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ContractValidationError, "not installed"):
                compile_extension_lock(
                    sample_manifest(),
                    source_permission_manifest_ref="policy/permission_manifest.json",
                    workspace_root=tmpdir,
                )

    def test_compile_extension_lock_round_trip_from_installed_package(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            install_path = root / ".missionforge/extensions/node_modules/pi-web-access"
            install_path.mkdir(parents=True)
            (install_path / "package.json").write_text('{"name":"pi-web-access"}\n', encoding="utf-8")

            lock = compile_extension_lock(
                sample_manifest(),
                source_permission_manifest_ref="policy/permission_manifest.json",
                workspace_root=root,
                compiled_at="2026-06-15T00:00:00Z",
            )

            self.assertEqual(ExtensionLock.from_dict(lock.to_dict()), lock)
            self.assertEqual(lock.extensions[0].install_path, ".missionforge/extensions/node_modules/pi-web-access")
            self.assertTrue(lock.extensions[0].package_hash.startswith("sha256:"))

            report = verify_extension_lock(sample_manifest(), lock)
            self.assertEqual(len(report.loaded_extensions), 1)
            self.assertEqual(report.loaded_extensions[0].status, "loadable")
            self.assertEqual(report.rejected_extensions, [])

    def test_compile_extension_lock_install_mode_keeps_multiple_packages(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = sample_manifest(
                extension_grants=[
                    {
                        "grant_id": "web-search",
                        "package": "npm:pi-web-access",
                        "version_spec": "0.10.7",
                        "capability": "web",
                        "requires_network": True,
                        "required_env": ["SEARCH_API_KEY"],
                    },
                    {
                        "grant_id": "code-search",
                        "package": "npm:@juicesharp/rpiv-web-tools",
                        "version_spec": "0.1.0",
                        "capability": "code_search",
                        "requires_network": True,
                        "required_env": ["SEARCH_API_KEY"],
                    },
                ],
            )
            lock = compile_extension_lock(
                manifest,
                source_permission_manifest_ref="policy/permission_manifest.json",
                workspace_root=root,
                mode="install",
                installer=_fake_npm_install,
                compiled_at="2026-06-15T00:00:00Z",
            )

            self.assertTrue((root / ".missionforge/extensions/node_modules/pi-web-access/package.json").is_file())
            self.assertTrue((root / ".missionforge/extensions/node_modules/@juicesharp/rpiv-web-tools/package.json").is_file())
            self.assertEqual(len(lock.extensions), 2)

    def test_compile_rejects_network_extension_when_network_disabled(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ContractValidationError, "network_policy is disabled"):
                compile_extension_lock(
                    sample_manifest(network_policy="disabled"),
                    source_permission_manifest_ref="policy/permission_manifest.json",
                    workspace_root=tmpdir,
                )

    def test_compile_rejects_required_env_not_in_allowlist(self) -> None:
        with TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ContractValidationError, "requires env"):
                compile_extension_lock(
                    sample_manifest(env_allowlist=["PATH"]),
                    source_permission_manifest_ref="policy/permission_manifest.json",
                    workspace_root=tmpdir,
                )

    def test_verify_reports_rejected_lock_mismatch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            install_path = root / ".missionforge/extensions/node_modules/pi-web-access"
            install_path.mkdir(parents=True)
            (install_path / "package.json").write_text("{}\n", encoding="utf-8")
            lock = compile_extension_lock(
                sample_manifest(),
                source_permission_manifest_ref="policy/permission_manifest.json",
                workspace_root=root,
                compiled_at="2026-06-15T00:00:00Z",
            )
            changed_payload = lock.to_dict()
            changed_payload["extensions"][0]["capability"] = "mcp"
            changed_payload.pop("lock_hash")
            changed_lock = ExtensionLock.from_dict(changed_payload)

            report = verify_extension_lock(sample_manifest(), changed_lock)

            self.assertEqual(report.loaded_extensions, [])
            self.assertEqual(report.rejected_extensions[0].reason, "capability_mismatch")

    def test_runtime_load_report_requires_lock_for_declared_extensions(self) -> None:
        report = extension_load_report_from_lock(
            call_id="call-001",
            permission_manifest=sample_manifest(),
            extension_lock=None,
            permission_manifest_ref="policy/permission_manifest.json",
            extension_lock_ref="compiled/extension_lock.json",
        )

        self.assertEqual(ExtensionLoadReport.from_dict(report.to_dict()), report)
        self.assertEqual(report.loaded_extensions, [])
        self.assertEqual(report.rejected_extensions[0].reason, "missing_extension_lock")


def _fake_npm_install(grant, install_root):
    package_name = grant.package.split(":", 1)[1]
    install_path = install_root / "node_modules" / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "package.json").write_text(
        f'{{"name":"{package_name}","version":"{grant.version_spec}"}}\n',
        encoding="utf-8",
    )
    return {}


if __name__ == "__main__":
    unittest.main()
