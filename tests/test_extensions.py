from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from missionforge import ContractValidationError, MemoryRefStore, PermissionManifest
from missionforge.extensions import (
    ExtensionLoadReport,
    ExtensionLock,
    compile_extension_lock,
    extension_load_report_from_lock,
    npm_install_extension,
    verify_extension_lock,
    read_extension_lock,
    write_extension_lock,
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

    def test_compile_extension_lock_preserves_grant_metadata(self) -> None:
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
                        "metadata": {"tool_names": ["web_search"], "profile": "test"},
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

            self.assertEqual(lock.extensions[0].metadata["tool_names"], ["web_search"])
            self.assertEqual(lock.extensions[0].metadata["profile"], "test")

    def test_compile_extension_lock_install_mode_copies_local_package(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = sample_manifest(
                extension_grants=[
                    {
                        "grant_id": "academic-sources",
                        "package": "local:extensions/pi-academic-sources",
                        "version_spec": "0.1.0",
                        "capability": "web",
                        "requires_network": True,
                    }
                ],
                env_allowlist=["PATH"],
            )

            lock = compile_extension_lock(
                manifest,
                source_permission_manifest_ref="policy/permission_manifest.json",
                workspace_root=root,
                mode="install",
                installer=npm_install_extension,
                compiled_at="2026-06-15T00:00:00Z",
            )

            installed = root / ".missionforge/extensions/pi-academic-sources"
            self.assertTrue((installed / "package.json").is_file())
            self.assertTrue((installed / "index.js").is_file())
            self.assertTrue((installed / "src" / "academic_sources.js").is_file())
            self.assertEqual(lock.extensions[0].install_path, ".missionforge/extensions/pi-academic-sources")
            self.assertEqual(lock.extensions[0].name, "@missionforge/pi-academic-sources")
            self.assertEqual(lock.extensions[0].version, "0.1.0")

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

    def test_verify_reports_rejected_extra_lock_entry(self) -> None:
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
            payload = lock.to_dict()
            extra = dict(payload["extensions"][0])
            extra["grant_id"] = "unauthorized-web-search"
            payload["extensions"].append(extra)
            payload.pop("lock_hash")
            changed_lock = ExtensionLock.from_dict(payload)

            report = verify_extension_lock(sample_manifest(), changed_lock)

        self.assertEqual(len(report.loaded_extensions), 1)
        self.assertEqual(len(report.rejected_extensions), 1)
        self.assertEqual(report.rejected_extensions[0].grant_id, "unauthorized-web-search")
        self.assertEqual(report.rejected_extensions[0].reason, "extra_lock_entry")

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

    def test_extension_lock_round_trips_through_memory_store_without_filesystem_writes(self) -> None:
        store = MemoryRefStore()
        lock = ExtensionLock(
            source_permission_manifest_ref="policy/permission_manifest.json",
            compiled_at="2026-06-15T00:00:00Z",
        )

        with TemporaryDirectory() as tmpdir:
            before = _snapshot(tmpdir)
            write_extension_lock(store, lock, ref="compiled/extension_lock.json")
            reloaded = read_extension_lock(store, ref="compiled/extension_lock.json")
            after = _snapshot(tmpdir)

        self.assertEqual(before, after)
        self.assertEqual(reloaded, lock)
        self.assertTrue(store.exists("compiled/extension_lock.json"))

    def test_extension_lock_helpers_validate_ref_before_custom_store_call(self) -> None:
        store = _RecordingStore()
        lock = ExtensionLock(
            source_permission_manifest_ref="policy/permission_manifest.json",
            compiled_at="2026-06-15T00:00:00Z",
        )

        with self.assertRaises(ContractValidationError):
            read_extension_lock(store, ref="../outside.json")
        with self.assertRaises(ContractValidationError):
            write_extension_lock(store, lock, ref="../outside.json")

        self.assertEqual(store.calls, [])


def _fake_npm_install(grant, install_root):
    if grant.package.startswith("local:"):
        package_name = Path(grant.package.split(":", 1)[1]).name
        install_path = install_root / package_name
        install_path.mkdir(parents=True, exist_ok=True)
        (install_path / "package.json").write_text(
            f'{{"name":"@missionforge/{package_name}","version":"{grant.version_spec}"}}\n',
            encoding="utf-8",
        )
        (install_path / "index.js").write_text("export default function () {}\n", encoding="utf-8")
        return {}
    package_name = grant.package.split(":", 1)[1]
    install_path = install_root / "node_modules" / package_name
    install_path.mkdir(parents=True, exist_ok=True)
    (install_path / "package.json").write_text(
        f'{{"name":"{package_name}","version":"{grant.version_spec}"}}\n',
        encoding="utf-8",
    )
    return {}


def _snapshot(root: str) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in Path(root).rglob("*"))


class _RecordingStore:
    store_id = "recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def read_json(self, ref: str):
        self.calls.append(("read_json", ref))
        return {}

    def write_bytes(self, ref: str, body: bytes, *, media_type: str = "application/octet-stream", metadata=None):
        self.calls.append(("write_bytes", ref))
        raise AssertionError("store should not be called")


if __name__ == "__main__":
    unittest.main()
