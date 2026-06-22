"""Extension declaration locks and runtime load reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import (
    ContractValidationError,
    assert_refs_only_payload,
    ensure_json_value,
    require_bool,
    require_enum,
    require_mapping,
    require_non_empty_str,
    require_str_list,
    stable_json_hash,
    validate_ref,
)
from .task_contract import (
    ExtensionAdapterMode,
    ExtensionCapability,
    ExtensionGrant,
    NetworkPolicy,
    PermissionManifest,
)


EXTENSION_LOCK_SCHEMA_VERSION = "missionforge_extension_lock.v1"
EXTENSION_LOAD_REPORT_SCHEMA_VERSION = "missionforge_extension_load_report.v1"
EXTENSION_COMPILE_REPORT_SCHEMA_VERSION = "missionforge_extension_compile_report.v1"


@dataclass(frozen=True)
class ExtensionLockEntry:
    """Compiled, deployment-time lock for one declared extension grant."""

    grant_id: str
    package: str
    name: str
    version: str
    capability: ExtensionCapability
    install_path: str
    adapter_mode: ExtensionAdapterMode
    requires_network: bool = False
    requires_bash: bool = False
    required_env: list[str] = field(default_factory=list)
    resolved: str | None = None
    integrity: str | None = None
    package_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExtensionLockEntry":
        data = require_mapping(payload, "extension_lock_entry")
        entry = cls(
            grant_id=require_non_empty_str(data.get("grant_id"), "extension_lock_entry.grant_id"),
            package=_validate_extension_package(data.get("package"), "extension_lock_entry.package"),
            name=require_non_empty_str(data.get("name"), "extension_lock_entry.name"),
            version=require_non_empty_str(data.get("version"), "extension_lock_entry.version"),
            capability=require_enum(
                data.get("capability"),
                ExtensionCapability,
                "extension_lock_entry.capability",
            ),
            install_path=validate_ref(data.get("install_path"), "extension_lock_entry.install_path"),
            adapter_mode=require_enum(
                data.get("adapter_mode", ExtensionAdapterMode.MISSIONFORGE_PROVIDER.value),
                ExtensionAdapterMode,
                "extension_lock_entry.adapter_mode",
            ),
            requires_network=require_bool(
                data.get("requires_network", False),
                "extension_lock_entry.requires_network",
            ),
            requires_bash=require_bool(
                data.get("requires_bash", False),
                "extension_lock_entry.requires_bash",
            ),
            required_env=require_str_list(data.get("required_env", []), "extension_lock_entry.required_env"),
            resolved=_optional_non_empty_str(data.get("resolved"), "extension_lock_entry.resolved"),
            integrity=_optional_non_empty_str(data.get("integrity"), "extension_lock_entry.integrity"),
            package_hash=_optional_hash(data.get("package_hash"), "extension_lock_entry.package_hash"),
            metadata=_safe_mapping(data.get("metadata", {}), "extension_lock_entry.metadata"),
        )
        entry.validate()
        return entry

    def validate(self) -> None:
        require_non_empty_str(self.grant_id, "extension_lock_entry.grant_id")
        _validate_extension_package(self.package, "extension_lock_entry.package")
        require_non_empty_str(self.name, "extension_lock_entry.name")
        require_non_empty_str(self.version, "extension_lock_entry.version")
        require_enum(self.capability, ExtensionCapability, "extension_lock_entry.capability")
        validate_ref(self.install_path, "extension_lock_entry.install_path")
        require_enum(self.adapter_mode, ExtensionAdapterMode, "extension_lock_entry.adapter_mode")
        require_bool(self.requires_network, "extension_lock_entry.requires_network")
        require_bool(self.requires_bash, "extension_lock_entry.requires_bash")
        _validate_unique_strings(self.required_env, "extension_lock_entry.required_env")
        for name in self.required_env:
            _validate_env_name(name, "extension_lock_entry.required_env[]")
        if self.resolved is not None:
            require_non_empty_str(self.resolved, "extension_lock_entry.resolved")
        if self.integrity is not None:
            require_non_empty_str(self.integrity, "extension_lock_entry.integrity")
        if self.package_hash is not None:
            _validate_hash(self.package_hash, "extension_lock_entry.package_hash")
        _safe_mapping(self.metadata, "extension_lock_entry.metadata")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "grant_id": self.grant_id,
            "package": self.package,
            "name": self.name,
            "version": self.version,
            "capability": self.capability.value,
            "install_path": self.install_path,
            "adapter_mode": self.adapter_mode.value,
            "requires_network": self.requires_network,
            "requires_bash": self.requires_bash,
            "required_env": list(self.required_env),
            "resolved": self.resolved,
            "integrity": self.integrity,
            "package_hash": self.package_hash,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ExtensionLock:
    """Deployment-time lockfile produced from PermissionManifest.extension_grants."""

    source_permission_manifest_ref: str
    extensions: list[ExtensionLockEntry] = field(default_factory=list)
    compiled_at: str = ""
    install_root_ref: str = ".missionforge/extensions"
    compiled_by: str = "missionforge.extensions"
    schema_version: str = EXTENSION_LOCK_SCHEMA_VERSION
    lock_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "lock_hash", stable_json_hash(self._content_dict()))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExtensionLock":
        data = require_mapping(payload, "extension_lock")
        lock_hash = data.get("lock_hash")
        lock = cls(
            source_permission_manifest_ref=validate_ref(
                data.get("source_permission_manifest_ref"),
                "extension_lock.source_permission_manifest_ref",
            ),
            extensions=_lock_entries_from_dicts(data.get("extensions", []), "extension_lock.extensions"),
            compiled_at=require_non_empty_str(data.get("compiled_at", ""), "extension_lock.compiled_at"),
            install_root_ref=validate_ref(
                data.get("install_root_ref", ".missionforge/extensions"),
                "extension_lock.install_root_ref",
            ),
            compiled_by=require_non_empty_str(
                data.get("compiled_by", "missionforge.extensions"),
                "extension_lock.compiled_by",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", EXTENSION_LOCK_SCHEMA_VERSION),
                "extension_lock.schema_version",
            ),
        )
        if lock_hash is not None and lock_hash != lock.lock_hash:
            raise ContractValidationError("extension_lock.lock_hash does not match lock content")
        return lock

    def validate(self) -> None:
        _require_schema(self.schema_version, EXTENSION_LOCK_SCHEMA_VERSION, "extension_lock.schema_version")
        validate_ref(self.source_permission_manifest_ref, "extension_lock.source_permission_manifest_ref")
        _require_timestamp(self.compiled_at, "extension_lock.compiled_at")
        validate_ref(self.install_root_ref, "extension_lock.install_root_ref")
        require_non_empty_str(self.compiled_by, "extension_lock.compiled_by")
        _validate_lock_entries(self.extensions, "extension_lock.extensions")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        if stable_json_hash(self._content_dict()) != self.lock_hash:
            raise ContractValidationError("extension_lock content changed after compile")
        payload = self._content_dict()
        payload["lock_hash"] = self.lock_hash
        return payload

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_permission_manifest_ref": self.source_permission_manifest_ref,
            "compiled_at": self.compiled_at,
            "install_root_ref": self.install_root_ref,
            "compiled_by": self.compiled_by,
            "extensions": [entry.to_dict() for entry in self.extensions],
        }


@dataclass(frozen=True)
class ExtensionLoadRecord:
    """Runtime evidence for one extension load or rejection decision."""

    grant_id: str
    package: str
    capability: ExtensionCapability
    status: str
    adapter_mode: ExtensionAdapterMode
    reason: str = ""
    version: str | None = None
    integrity: str | None = None
    requires_network: bool = False
    network_policy_at_load: NetworkPolicy = NetworkPolicy.DISABLED
    tool_names: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExtensionLoadRecord":
        data = require_mapping(payload, "extension_load_record")
        record = cls(
            grant_id=require_non_empty_str(data.get("grant_id"), "extension_load_record.grant_id"),
            package=_validate_extension_package(data.get("package"), "extension_load_record.package"),
            capability=require_enum(
                data.get("capability"),
                ExtensionCapability,
                "extension_load_record.capability",
            ),
            status=_require_load_status(data.get("status"), "extension_load_record.status"),
            adapter_mode=require_enum(
                data.get("adapter_mode", ExtensionAdapterMode.MISSIONFORGE_PROVIDER.value),
                ExtensionAdapterMode,
                "extension_load_record.adapter_mode",
            ),
            reason=_optional_str(data.get("reason", ""), "extension_load_record.reason"),
            version=_optional_non_empty_str(data.get("version"), "extension_load_record.version"),
            integrity=_optional_non_empty_str(data.get("integrity"), "extension_load_record.integrity"),
            requires_network=require_bool(
                data.get("requires_network", False),
                "extension_load_record.requires_network",
            ),
            network_policy_at_load=require_enum(
                data.get("network_policy_at_load", NetworkPolicy.DISABLED.value),
                NetworkPolicy,
                "extension_load_record.network_policy_at_load",
            ),
            tool_names=require_str_list(data.get("tool_names", []), "extension_load_record.tool_names"),
        )
        record.validate()
        return record

    def validate(self) -> None:
        require_non_empty_str(self.grant_id, "extension_load_record.grant_id")
        _validate_extension_package(self.package, "extension_load_record.package")
        require_enum(self.capability, ExtensionCapability, "extension_load_record.capability")
        _require_load_status(self.status, "extension_load_record.status")
        require_enum(self.adapter_mode, ExtensionAdapterMode, "extension_load_record.adapter_mode")
        _optional_str(self.reason, "extension_load_record.reason")
        if self.version is not None:
            require_non_empty_str(self.version, "extension_load_record.version")
        if self.integrity is not None:
            require_non_empty_str(self.integrity, "extension_load_record.integrity")
        require_bool(self.requires_network, "extension_load_record.requires_network")
        require_enum(self.network_policy_at_load, NetworkPolicy, "extension_load_record.network_policy_at_load")
        _validate_unique_strings(self.tool_names, "extension_load_record.tool_names")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "grant_id": self.grant_id,
            "package": self.package,
            "capability": self.capability.value,
            "status": self.status,
            "adapter_mode": self.adapter_mode.value,
            "reason": self.reason,
            "version": self.version,
            "integrity": self.integrity,
            "requires_network": self.requires_network,
            "network_policy_at_load": self.network_policy_at_load.value,
            "tool_names": list(self.tool_names),
        }


@dataclass(frozen=True)
class ExtensionLoadReport:
    """Refs-first runtime report for extension loading decisions."""

    call_id: str
    loaded_extensions: list[ExtensionLoadRecord] = field(default_factory=list)
    rejected_extensions: list[ExtensionLoadRecord] = field(default_factory=list)
    extension_lock_ref: str | None = None
    permission_manifest_ref: str | None = None
    schema_version: str = EXTENSION_LOAD_REPORT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExtensionLoadReport":
        data = require_mapping(payload, "extension_load_report")
        report = cls(
            call_id=require_non_empty_str(data.get("call_id"), "extension_load_report.call_id"),
            loaded_extensions=_load_records_from_dicts(
                data.get("loaded_extensions", []),
                "extension_load_report.loaded_extensions",
            ),
            rejected_extensions=_load_records_from_dicts(
                data.get("rejected_extensions", []),
                "extension_load_report.rejected_extensions",
            ),
            extension_lock_ref=_optional_ref(data.get("extension_lock_ref"), "extension_load_report.extension_lock_ref"),
            permission_manifest_ref=_optional_ref(
                data.get("permission_manifest_ref"),
                "extension_load_report.permission_manifest_ref",
            ),
            schema_version=require_non_empty_str(
                data.get("schema_version", EXTENSION_LOAD_REPORT_SCHEMA_VERSION),
                "extension_load_report.schema_version",
            ),
        )
        report.validate()
        return report

    def validate(self) -> None:
        _require_schema(self.schema_version, EXTENSION_LOAD_REPORT_SCHEMA_VERSION, "extension_load_report.schema_version")
        require_non_empty_str(self.call_id, "extension_load_report.call_id")
        _validate_load_records(self.loaded_extensions, "extension_load_report.loaded_extensions")
        _validate_load_records(self.rejected_extensions, "extension_load_report.rejected_extensions")
        loaded_ids = {record.grant_id for record in self.loaded_extensions}
        rejected_ids = {record.grant_id for record in self.rejected_extensions}
        duplicate_ids = loaded_ids & rejected_ids
        if duplicate_ids:
            raise ContractValidationError(f"extension_load_report has duplicate load decisions: {sorted(duplicate_ids)}")
        _optional_ref(self.extension_lock_ref, "extension_load_report.extension_lock_ref")
        _optional_ref(self.permission_manifest_ref, "extension_load_report.permission_manifest_ref")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "call_id": self.call_id,
            "extension_lock_ref": self.extension_lock_ref,
            "permission_manifest_ref": self.permission_manifest_ref,
            "loaded_extensions": [record.to_dict() for record in self.loaded_extensions],
            "rejected_extensions": [record.to_dict() for record in self.rejected_extensions],
        }


@dataclass(frozen=True)
class ExtensionCompileReport:
    """Compile-time report that cites the generated lock ref."""

    source_permission_manifest_ref: str
    extension_lock_ref: str
    installed_count: int
    skipped_count: int
    schema_version: str = EXTENSION_COMPILE_REPORT_SCHEMA_VERSION

    def validate(self) -> None:
        _require_schema(self.schema_version, EXTENSION_COMPILE_REPORT_SCHEMA_VERSION, "extension_compile_report.schema_version")
        validate_ref(self.source_permission_manifest_ref, "extension_compile_report.source_permission_manifest_ref")
        validate_ref(self.extension_lock_ref, "extension_compile_report.extension_lock_ref")
        if self.installed_count < 0 or self.skipped_count < 0:
            raise ContractValidationError("extension_compile_report counts must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "source_permission_manifest_ref": self.source_permission_manifest_ref,
            "extension_lock_ref": self.extension_lock_ref,
            "installed_count": self.installed_count,
            "skipped_count": self.skipped_count,
        }


InstallExtension = Callable[[ExtensionGrant, Path], Mapping[str, Any]]


def npm_install_extension(grant: ExtensionGrant, install_root: Path) -> Mapping[str, Any]:
    """Install one extension into the declared install root.

    This is intentionally thin. npm packages are installed with scripts
    disabled. local packages are copied from the current working tree. Callers
    own the supply-chain risk.
    """

    safe_install_root = Path(install_root)
    safe_install_root.mkdir(parents=True, exist_ok=True)
    if grant.package.startswith("local:"):
        return _copy_local_extension_package(grant, safe_install_root, Path.cwd())
    package_name = _package_name(grant.package)
    install_path = (
        safe_install_root / "node_modules" / package_name
        if grant.package.startswith("npm:")
        else safe_install_root / package_name
    )
    package_json = safe_install_root / "package.json"
    if not package_json.exists():
        package_json.write_text('{"name":"missionforge-extensions","private":true}\n', encoding="utf-8")
    if install_path.exists() and (install_path / "package.json").is_file():
        return {}
    if not grant.package.startswith("npm:"):
        raise ContractValidationError("npm_install_extension only supports npm packages")
    try:
        subprocess.run(
            [
                "npm",
                "install",
                "--ignore-scripts",
                "--no-save",
                "--package-lock=false",
                f"{package_name}@{grant.version_spec}",
            ],
            cwd=safe_install_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ContractValidationError(
            f"npm install failed for {grant.package} with exit code {exc.returncode}"
        ) from exc
    return {}


def compile_extension_lock(
    permission_manifest: PermissionManifest,
    *,
    source_permission_manifest_ref: str,
    install_root_ref: str = ".missionforge/extensions",
    workspace_root: Path | str = ".",
    mode: str = "verify-installed",
    installer: InstallExtension | None = None,
    compiled_at: str | None = None,
) -> ExtensionLock:
    """Compile extension declarations into a deployment lock.

    The default mode validates local install paths only. Passing mode="install"
    requires an explicit installer callback so the caller owns supply-chain risk.
    """

    permission_manifest.validate()
    safe_source_ref = validate_ref(source_permission_manifest_ref, "source_permission_manifest_ref")
    safe_install_root_ref = validate_ref(install_root_ref, "install_root_ref")
    if mode not in {"verify-installed", "install"}:
        raise ContractValidationError("extension compile mode must be verify-installed or install")
    if mode == "install" and installer is None:
        raise ContractValidationError("extension compile install mode requires an explicit installer")
    workspace_path = Path(workspace_root)
    install_root = _resolve_workspace_ref(workspace_path, safe_install_root_ref)
    if mode == "install" and installer is npm_install_extension:
        _install_declared_extensions(permission_manifest.extension_grants, install_root, workspace_path)
        installer = None
    entries: list[ExtensionLockEntry] = []
    for grant in permission_manifest.extension_grants:
        if grant.requires_network and permission_manifest.network_policy is NetworkPolicy.DISABLED:
            raise ContractValidationError(f"extension {grant.grant_id} requires network but network_policy is disabled")
        missing_env = [name for name in grant.required_env if name not in permission_manifest.env_allowlist]
        if missing_env:
            raise ContractValidationError(f"extension {grant.grant_id} requires env not in env_allowlist: {missing_env}")
        install_info = dict(installer(grant, install_root) if mode == "install" and installer is not None else {})
        entry = _lock_entry_from_grant(
            grant,
            install_root_ref=safe_install_root_ref,
            workspace_root=workspace_path,
            install_info=install_info,
        )
        if mode == "install" and entry.package_hash is None:
            raise ContractValidationError(f"extension {grant.grant_id} is not installed at {entry.install_path}")
        if mode == "verify-installed" and entry.package_hash is None:
            raise ContractValidationError(f"extension {grant.grant_id} is not installed at {entry.install_path}")
        entries.append(entry)
    return ExtensionLock(
        source_permission_manifest_ref=safe_source_ref,
        install_root_ref=safe_install_root_ref,
        compiled_at=compiled_at or datetime.now(timezone.utc).isoformat(),
        extensions=entries,
    )


def verify_extension_lock(permission_manifest: PermissionManifest, extension_lock: ExtensionLock) -> ExtensionLoadReport:
    """Verify that a lock satisfies the manifest without loading third-party code."""

    permission_manifest.validate()
    extension_lock.validate()
    locked_by_id = {entry.grant_id: entry for entry in extension_lock.extensions}
    loaded: list[ExtensionLoadRecord] = []
    rejected: list[ExtensionLoadRecord] = []
    for grant in permission_manifest.extension_grants:
        entry = locked_by_id.get(grant.grant_id)
        if entry is None:
            rejected.append(_rejected_record(grant, "missing_lock_entry", permission_manifest.network_policy))
            continue
        reason = _grant_lock_mismatch(grant, entry, permission_manifest)
        if reason:
            rejected.append(_rejected_record(grant, reason, permission_manifest.network_policy, entry=entry))
            continue
        loaded.append(
            ExtensionLoadRecord(
                grant_id=grant.grant_id,
                package=grant.package,
                capability=grant.capability,
                status="loadable",
                adapter_mode=grant.adapter_mode,
                reason="lock entry matches declaration",
                version=entry.version,
                integrity=entry.integrity,
                requires_network=grant.requires_network,
                network_policy_at_load=permission_manifest.network_policy,
                tool_names=[],
            )
        )
    return ExtensionLoadReport(call_id="compile-verify", loaded_extensions=loaded, rejected_extensions=rejected)


def extension_load_report_from_lock(
    *,
    call_id: str,
    permission_manifest: PermissionManifest,
    extension_lock: ExtensionLock | None,
    extension_lock_ref: str | None = None,
    permission_manifest_ref: str | None = None,
) -> ExtensionLoadReport:
    """Build a runtime load report without importing extension code."""

    permission_manifest.validate()
    if extension_lock is None:
        rejected = [
            _rejected_record(grant, "missing_extension_lock", permission_manifest.network_policy)
            for grant in permission_manifest.extension_grants
        ]
        return ExtensionLoadReport(
            call_id=call_id,
            rejected_extensions=rejected,
            extension_lock_ref=extension_lock_ref,
            permission_manifest_ref=permission_manifest_ref,
        )
    report = verify_extension_lock(permission_manifest, extension_lock)
    loaded = [
        ExtensionLoadRecord(
            grant_id=record.grant_id,
            package=record.package,
            capability=record.capability,
            status="loaded",
            adapter_mode=record.adapter_mode,
            reason="extension lock matched; provider loading is delegated to runtime adapters",
            version=record.version,
            integrity=record.integrity,
            requires_network=record.requires_network,
            network_policy_at_load=permission_manifest.network_policy,
            tool_names=list(record.tool_names),
        )
        for record in report.loaded_extensions
    ]
    return ExtensionLoadReport(
        call_id=call_id,
        loaded_extensions=loaded,
        rejected_extensions=list(report.rejected_extensions),
        extension_lock_ref=extension_lock_ref,
        permission_manifest_ref=permission_manifest_ref,
    )


def read_extension_lock(path: Path | str) -> ExtensionLock:
    import json

    return ExtensionLock.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def write_extension_lock(path: Path | str, extension_lock: ExtensionLock) -> None:
    import json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(extension_lock.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _lock_entry_from_grant(
    grant: ExtensionGrant,
    *,
    install_root_ref: str,
    workspace_root: Path,
    install_info: Mapping[str, Any],
) -> ExtensionLockEntry:
    package_name = _package_name(grant.package)
    default_install_path_ref = (
        f"{install_root_ref}/node_modules/{package_name}"
        if grant.package.startswith("npm:")
        else f"{install_root_ref}/{package_name}"
    )
    install_path_ref = validate_ref(
        str(install_info.get("install_path_ref") or default_install_path_ref),
        "extension_lock_entry.install_path",
    )
    install_path = _resolve_workspace_ref(workspace_root, install_path_ref)
    package_metadata = _read_package_metadata(install_path) if install_path.exists() else {}
    package_hash = _path_hash(install_path) if install_path.exists() else None
    if install_info.get("package_hash") is not None:
        package_hash = _validate_hash(install_info.get("package_hash"), "extension_lock_entry.package_hash")
    version = str(
        install_info.get("version")
        or package_metadata.get("version")
        or _exact_version_from_spec(grant.version_spec)
    )
    install_metadata = _safe_mapping(install_info.get("metadata", {}), "extension_lock_entry.metadata")
    grant_metadata = _safe_mapping(grant.metadata, "extension_grant.metadata")
    return ExtensionLockEntry(
        grant_id=grant.grant_id,
        package=grant.package,
        name=str(install_info.get("name") or package_metadata.get("name") or package_name),
        version=version,
        capability=grant.capability,
        install_path=install_path_ref,
        adapter_mode=grant.adapter_mode,
        requires_network=grant.requires_network,
        requires_bash=grant.requires_bash,
        required_env=list(grant.required_env),
        resolved=_optional_non_empty_str(
            install_info.get("resolved") or package_metadata.get("resolved"),
            "extension_lock_entry.resolved",
        ),
        integrity=_optional_non_empty_str(
            install_info.get("integrity") or grant.integrity or package_metadata.get("integrity"),
            "extension_lock_entry.integrity",
        ),
        package_hash=package_hash,
        metadata={**install_metadata, **grant_metadata},
    )


def _install_declared_extensions(grants: list[ExtensionGrant], install_root: Path, workspace_root: Path) -> None:
    _install_declared_npm_extensions(grants, install_root)
    _install_declared_local_extensions(grants, install_root, Path.cwd())


def _install_declared_npm_extensions(grants: list[ExtensionGrant], install_root: Path) -> None:
    if not grants:
        return
    install_root.mkdir(parents=True, exist_ok=True)
    dependencies = {
        _package_name(grant.package): grant.version_spec
        for grant in grants
        if grant.package.startswith("npm:")
    }
    if not dependencies:
        return
    package_json = install_root / "package.json"
    package_json.write_text(
        json.dumps(
            {
                "name": "missionforge-extensions",
                "private": True,
                "dependencies": dependencies,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["npm", "install", "--ignore-scripts", "--package-lock=false"],
            cwd=install_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ContractValidationError(
            f"npm install failed for declared extensions with exit code {exc.returncode}"
        ) from exc


def _install_declared_local_extensions(grants: list[ExtensionGrant], install_root: Path, workspace_root: Path) -> None:
    for grant in grants:
        if grant.package.startswith("local:"):
            _copy_local_extension_package(grant, install_root, workspace_root)


def _copy_local_extension_package(
    grant: ExtensionGrant,
    install_root: Path,
    source_root: Path,
) -> Mapping[str, Any]:
    source_ref = validate_ref(grant.package[len("local:"):], "extension.local_package")
    source_path = _resolve_workspace_ref(source_root, source_ref)
    if not source_path.exists():
        raise ContractValidationError(f"local extension source does not exist: {source_ref}")
    package_name = _package_name(grant.package)
    install_path = install_root / package_name
    if install_path.exists():
        if install_path.is_dir():
            shutil.rmtree(install_path)
        else:
            install_path.unlink()
    install_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.is_dir():
        shutil.copytree(
            source_path,
            install_path,
            ignore=shutil.ignore_patterns("node_modules", ".git", "__pycache__", "*.pyc"),
        )
    else:
        shutil.copy2(source_path, install_path)
    return {}


def _grant_lock_mismatch(
    grant: ExtensionGrant,
    entry: ExtensionLockEntry,
    permission_manifest: PermissionManifest,
) -> str:
    if grant.package != entry.package:
        return "package_mismatch"
    if grant.capability != entry.capability:
        return "capability_mismatch"
    if grant.adapter_mode != entry.adapter_mode:
        return "adapter_mode_mismatch"
    if grant.requires_network != entry.requires_network:
        return "requires_network_mismatch"
    if grant.requires_bash != entry.requires_bash:
        return "requires_bash_mismatch"
    if sorted(grant.required_env) != sorted(entry.required_env):
        return "required_env_mismatch"
    if grant.requires_network and permission_manifest.network_policy is NetworkPolicy.DISABLED:
        return "network_policy_disabled"
    missing_env = [name for name in grant.required_env if name not in permission_manifest.env_allowlist]
    if missing_env:
        return "required_env_not_allowed"
    if grant.integrity is not None and entry.integrity != grant.integrity:
        return "integrity_mismatch"
    return ""


def _rejected_record(
    grant: ExtensionGrant,
    reason: str,
    network_policy: NetworkPolicy,
    *,
    entry: ExtensionLockEntry | None = None,
) -> ExtensionLoadRecord:
    return ExtensionLoadRecord(
        grant_id=grant.grant_id,
        package=grant.package,
        capability=grant.capability,
        status="rejected",
        adapter_mode=grant.adapter_mode,
        reason=reason,
        version=entry.version if entry else None,
        integrity=entry.integrity if entry else grant.integrity,
        requires_network=grant.requires_network,
        network_policy_at_load=network_policy,
        tool_names=[],
    )


def _lock_entries_from_dicts(value: Any, field_name: str) -> list[ExtensionLockEntry]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    entries = [ExtensionLockEntry.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]
    _validate_lock_entries(entries, field_name)
    return entries


def _validate_lock_entries(entries: list[ExtensionLockEntry], field_name: str) -> None:
    if not isinstance(entries, list):
        raise ContractValidationError(f"{field_name} must be a list")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, ExtensionLockEntry):
            raise ContractValidationError(f"{field_name}[] must be an ExtensionLockEntry")
        entry.validate()
        if entry.grant_id in seen:
            raise ContractValidationError(f"duplicate {field_name} grant_id: {entry.grant_id}")
        seen.add(entry.grant_id)


def _load_records_from_dicts(value: Any, field_name: str) -> list[ExtensionLoadRecord]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field_name} must be a list")
    records = [ExtensionLoadRecord.from_dict(require_mapping(item, f"{field_name}[]")) for item in value]
    _validate_load_records(records, field_name)
    return records


def _validate_load_records(records: list[ExtensionLoadRecord], field_name: str) -> None:
    if not isinstance(records, list):
        raise ContractValidationError(f"{field_name} must be a list")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, ExtensionLoadRecord):
            raise ContractValidationError(f"{field_name}[] must be an ExtensionLoadRecord")
        record.validate()
        if record.grant_id in seen:
            raise ContractValidationError(f"duplicate {field_name} grant_id: {record.grant_id}")
        seen.add(record.grant_id)


def _path_hash(path: Path) -> str:
    if path.is_file():
        return _file_hash(path)
    if path.is_dir():
        digest = hashlib.sha256()
        for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
            digest.update(str(item.relative_to(path)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(item.read_bytes())
            digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"
    raise ContractValidationError(f"extension install path is not a file or directory: {path}")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _read_package_metadata(install_path: Path) -> dict[str, Any]:
    package_json = install_path / "package.json" if install_path.is_dir() else install_path
    if package_json.is_dir():
        package_json = package_json / "package.json"
    if not package_json.is_file():
        return {}
    data = json.loads(package_json.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ContractValidationError("extension package.json must contain an object")
    return ensure_json_value(data, "extension.package_metadata")


def _resolve_workspace_ref(root: Path, ref: str) -> Path:
    safe_ref = validate_ref(ref, "extension_workspace_ref")
    root_path = root.resolve()
    path = (root_path / safe_ref).resolve()
    if path != root_path and root_path not in path.parents:
        raise ContractValidationError("extension ref escapes workspace")
    return path


def _package_name(package: str) -> str:
    safe_package = _validate_extension_package(package, "extension.package")
    if safe_package.startswith("npm:"):
        name = safe_package[len("npm:"):]
        return require_non_empty_str(name, "extension.package.name")
    if safe_package.startswith("local:"):
        return Path(safe_package[len("local:"):]).name
    raise ContractValidationError("unsupported extension package")


def _exact_version_from_spec(version_spec: str) -> str:
    version = require_non_empty_str(version_spec, "extension.version_spec")
    if any(char in version for char in "*^~<>= "):
        raise ContractValidationError("extension version_spec must be exact unless installer returns a resolved version")
    return version


def _validate_extension_package(value: Any, field_name: str) -> str:
    package = require_non_empty_str(value, field_name)
    if not package.startswith(("npm:", "local:")):
        raise ContractValidationError(f"{field_name} must start with one of ('npm:', 'local:')")
    if package.startswith("local:"):
        validate_ref(package[len("local:"):], field_name)
    return package


def _validate_env_name(value: Any, field_name: str) -> str:
    name = require_non_empty_str(value, field_name)
    if not (name[0].isalpha() or name[0] == "_"):
        raise ContractValidationError(f"{field_name} must be an environment variable name")
    if not all(char.isalnum() or char == "_" for char in name):
        raise ContractValidationError(f"{field_name} must be an environment variable name")
    return name


def _validate_unique_strings(values: list[str], field_name: str) -> None:
    items = require_str_list(values, field_name)
    if len(items) != len(set(items)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")


def _safe_mapping(value: Any, field_name: str) -> dict[str, Any]:
    return ensure_json_value(assert_refs_only_payload(require_mapping(value, field_name), field_name), field_name)


def _optional_ref(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return validate_ref(value, field_name)


def _optional_non_empty_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def _optional_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be a string")
    return value


def _optional_hash(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_hash(value, field_name)


def _validate_hash(value: Any, field_name: str) -> str:
    hash_value = require_non_empty_str(value, field_name)
    prefix = "sha256:"
    if not hash_value.startswith(prefix):
        raise ContractValidationError(f"{field_name} must start with {prefix!r}")
    digest = hash_value[len(prefix):]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ContractValidationError(f"{field_name} must be a sha256 hex digest")
    return hash_value


def _require_load_status(value: Any, field_name: str) -> str:
    status = require_non_empty_str(value, field_name)
    if status not in {"loadable", "loaded", "rejected"}:
        raise ContractValidationError(f"{field_name} must be loadable, loaded, or rejected")
    return status


def _require_schema(actual: str, expected: str, field_name: str) -> None:
    if actual != expected:
        raise ContractValidationError(f"{field_name} must be {expected}")


def _require_timestamp(value: str, field_name: str) -> str:
    timestamp = require_non_empty_str(value, field_name)
    normalized = timestamp.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be ISO-8601") from exc
    return timestamp
