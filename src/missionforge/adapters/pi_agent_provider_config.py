"""Provider environment resolution for the dedicated PI Agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tomllib
from typing import Mapping

from ..contracts import ContractValidationError, require_non_empty_str


PI_AGENT_ENV_KEYS = {
    "MISSIONFORGE_PI_AGENT_PROVIDER",
    "MISSIONFORGE_PI_AGENT_MODEL",
    "MISSIONFORGE_PI_AGENT_BASE_URL",
    "MISSIONFORGE_PI_AGENT_API_KEY",
    "MISSIONFORGE_PI_AGENT_REASONING",
    "MISSIONFORGE_PI_AGENT_MAX_TURNS",
    "MISSIONFORGE_PI_AGENT_TOOL_TIMEOUT_SECONDS",
}
SECRET_ENV_KEYS = {
    "MISSIONFORGE_PI_AGENT_API_KEY",
    "OPENAI_API_KEY",
    "AUTHORIZATION",
}


@dataclass(frozen=True)
class PiAgentProviderEnvironment:
    """Resolved child-process environment with a redacted diagnostic view."""

    env: dict[str, str] = field(repr=False)
    redacted_env: dict[str, str]
    source: str

    def require_no_empty_values(self) -> None:
        for key, value in self.env.items():
            require_non_empty_str(key, "pi_agent_provider_env.key")
            require_non_empty_str(value, f"pi_agent_provider_env.{key}")


def resolve_pi_agent_provider_environment(
    *,
    provider_mode: str,
    provider_config_source: str = "env",
    model: str | None = None,
    metadata: Mapping[str, object] | None = None,
    environ: Mapping[str, str] | None = None,
    codex_home: str | Path | None = None,
) -> PiAgentProviderEnvironment:
    """Resolve the dedicated PI Agent runtime environment."""

    current_env = dict(os.environ if environ is None else environ)
    normalized_mode = _normalize_choice(provider_mode, {"faux", "live"}, "provider_mode")
    normalized_source = _normalize_choice(
        provider_config_source,
        {"env", "codex_current", "explicit"},
        "provider_config_source",
    )
    metadata_map = dict(metadata or {})

    env = _copy_pi_agent_env(current_env)
    env["MISSIONFORGE_PI_AGENT_PROVIDER"] = normalized_mode
    if model and "MISSIONFORGE_PI_AGENT_MODEL" not in env:
        env["MISSIONFORGE_PI_AGENT_MODEL"] = model

    if normalized_mode == "faux":
        result = PiAgentProviderEnvironment(env=env, redacted_env=redact_provider_env(env), source=normalized_source)
        result.require_no_empty_values()
        return result

    if "base_url" in metadata_map and "MISSIONFORGE_PI_AGENT_BASE_URL" not in env:
        env["MISSIONFORGE_PI_AGENT_BASE_URL"] = require_non_empty_str(
            metadata_map["base_url"],
            "pi_agent_config.metadata.base_url",
        )

    if normalized_source == "codex_current":
        codex = load_codex_current_provider(codex_home=codex_home, environ=current_env)
        if codex.get("wire_api") != "responses":
            raise ContractValidationError("Codex current provider must use responses wire_api for PI Agent runtime")
        env.setdefault("MISSIONFORGE_PI_AGENT_MODEL", require_non_empty_str(codex.get("model"), "codex.model"))
        env.setdefault("MISSIONFORGE_PI_AGENT_BASE_URL", require_non_empty_str(codex.get("base_url"), "codex.base_url"))
        env.setdefault("MISSIONFORGE_PI_AGENT_API_KEY", require_non_empty_str(codex.get("api_key"), "codex.api_key"))
    elif normalized_source == "explicit":
        if "MISSIONFORGE_PI_AGENT_BASE_URL" not in env and "base_url" not in metadata_map:
            raise ContractValidationError("explicit live PI Agent config requires base URL")
        if "OPENAI_API_KEY" in current_env and "MISSIONFORGE_PI_AGENT_API_KEY" not in env:
            env["MISSIONFORGE_PI_AGENT_API_KEY"] = current_env["OPENAI_API_KEY"]
    elif normalized_source == "env":
        if "OPENAI_API_KEY" in current_env and "MISSIONFORGE_PI_AGENT_API_KEY" not in env:
            env["MISSIONFORGE_PI_AGENT_API_KEY"] = current_env["OPENAI_API_KEY"]
    else:
        raise ContractValidationError("unsupported provider_config_source")

    missing = [
        key
        for key in (
            "MISSIONFORGE_PI_AGENT_MODEL",
            "MISSIONFORGE_PI_AGENT_BASE_URL",
            "MISSIONFORGE_PI_AGENT_API_KEY",
        )
        if not env.get(key)
    ]
    if missing:
        raise ContractValidationError(f"live PI Agent provider config is missing: {missing}")

    result = PiAgentProviderEnvironment(env=env, redacted_env=redact_provider_env(env), source=normalized_source)
    result.require_no_empty_values()
    return result


def load_codex_current_provider(
    *,
    codex_home: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load current Codex provider config and auth key."""

    current_env = dict(os.environ if environ is None else environ)
    home = _codex_home(codex_home=codex_home, environ=current_env)
    config_path = home / "config.toml"
    auth_path = home / "auth.json"
    if not config_path.is_file():
        raise ContractValidationError(f"Codex config not found: {config_path}")
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    provider_name = require_non_empty_str(config.get("model_provider"), "codex.model_provider")
    providers = config.get("model_providers")
    if not isinstance(providers, Mapping):
        raise ContractValidationError("Codex config requires model_providers")
    provider = providers.get(provider_name)
    if not isinstance(provider, Mapping):
        raise ContractValidationError(f"Codex provider is not configured: {provider_name}")

    api_key = current_env.get("MISSIONFORGE_PI_AGENT_API_KEY")
    if not api_key:
        if not auth_path.is_file():
            raise ContractValidationError(f"Codex auth not found: {auth_path}")
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
        if not isinstance(auth, Mapping):
            raise ContractValidationError("Codex auth must be a JSON object")
        api_key = auth.get("OPENAI_API_KEY")

    return {
        "model_provider": provider_name,
        "model": require_non_empty_str(config.get("model"), "codex.model"),
        "base_url": require_non_empty_str(provider.get("base_url"), "codex.provider.base_url"),
        "wire_api": require_non_empty_str(provider.get("wire_api"), "codex.provider.wire_api"),
        "api_key": require_non_empty_str(api_key, "codex.auth.OPENAI_API_KEY"),
    }


def redact_provider_env(env: Mapping[str, str]) -> dict[str, str]:
    return {key: "<redacted>" if _is_secret_env_key(key) else str(value) for key, value in env.items()}


def _copy_pi_agent_env(environ: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in PI_AGENT_ENV_KEYS:
        value = environ.get(key)
        if value is not None and value.strip():
            result[key] = value
    return result


def _codex_home(*, codex_home: str | Path | None, environ: Mapping[str, str]) -> Path:
    if codex_home is not None:
        return Path(codex_home)
    configured = environ.get("CODEX_HOME")
    if configured:
        return Path(configured)
    return Path.home() / ".codex"


def _normalize_choice(value: str, allowed: set[str], field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractValidationError(f"{field_name} must be one of {sorted(allowed)}")
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise ContractValidationError(f"{field_name} must be one of {sorted(allowed)}")
    return normalized


def _is_secret_env_key(key: str) -> bool:
    normalized = key.strip().upper()
    if normalized in SECRET_ENV_KEYS:
        return True
    lowered = normalized.lower()
    return any(fragment in lowered for fragment in ("api_key", "authorization", "password", "secret", "token"))
