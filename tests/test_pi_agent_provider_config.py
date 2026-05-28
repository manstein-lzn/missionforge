from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from missionforge.adapters.pi_agent_provider_config import (
    load_codex_current_provider,
    redact_provider_env,
    resolve_pi_agent_provider_environment,
)
from missionforge.contracts import ContractValidationError


class PiAgentProviderConfigTests(unittest.TestCase):
    def test_codex_current_provider_maps_to_live_pi_agent_env_with_redaction(self) -> None:
        secret = "sk-test-secret-123"
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir)
            _write_codex_config(codex_home, wire_api="responses")
            (codex_home / "auth.json").write_text('{"OPENAI_API_KEY": "sk-test-secret-123"}\n', encoding="utf-8")

            result = resolve_pi_agent_provider_environment(
                provider_mode="live",
                provider_config_source="codex_current",
                environ={},
                codex_home=codex_home,
            )

        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_PROVIDER"], "live")
        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_MODEL"], "gpt-5.5")
        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_BASE_URL"], "https://right.codes/codex/v1")
        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_API_KEY"], secret)
        self.assertEqual(result.redacted_env["MISSIONFORGE_PI_AGENT_API_KEY"], "<redacted>")
        self.assertNotIn(secret, repr(result))

    def test_codex_current_rejects_non_responses_wire_api(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir)
            _write_codex_config(codex_home, wire_api="chat")
            (codex_home / "auth.json").write_text('{"OPENAI_API_KEY": "secret"}\n', encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "responses"):
                resolve_pi_agent_provider_environment(
                    provider_mode="live",
                    provider_config_source="codex_current",
                    environ={},
                    codex_home=codex_home,
                )

    def test_env_live_requires_model_base_url_and_key(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "missing"):
            resolve_pi_agent_provider_environment(
                provider_mode="live",
                provider_config_source="env",
                environ={"MISSIONFORGE_PI_AGENT_MODEL": "gpt-5.5"},
            )

    def test_faux_provider_does_not_require_secret(self) -> None:
        result = resolve_pi_agent_provider_environment(provider_mode="faux", provider_config_source="env", environ={})

        self.assertEqual(result.env, {"MISSIONFORGE_PI_AGENT_PROVIDER": "faux"})

    def test_redact_provider_env_masks_secret_shaped_keys(self) -> None:
        redacted = redact_provider_env(
            {
                "MISSIONFORGE_PI_AGENT_API_KEY": "secret",
                "MISSIONFORGE_PI_AGENT_MODEL": "gpt-5.5",
                "CUSTOM_TOKEN": "token",
            }
        )

        self.assertEqual(redacted["MISSIONFORGE_PI_AGENT_API_KEY"], "<redacted>")
        self.assertEqual(redacted["CUSTOM_TOKEN"], "<redacted>")
        self.assertEqual(redacted["MISSIONFORGE_PI_AGENT_MODEL"], "gpt-5.5")

    def test_load_codex_current_provider_uses_pi_agent_env_key_before_auth_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir)
            _write_codex_config(codex_home, wire_api="responses")

            provider = load_codex_current_provider(
                codex_home=codex_home,
                environ={"MISSIONFORGE_PI_AGENT_API_KEY": "env-secret"},
            )

        self.assertEqual(provider["api_key"], "env-secret")

    def test_codex_current_rejects_missing_auth_key(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            codex_home = Path(tempdir)
            _write_codex_config(codex_home, wire_api="responses")
            (codex_home / "auth.json").write_text('{"auth_mode": "api-key"}\n', encoding="utf-8")

            with self.assertRaisesRegex(ContractValidationError, "OPENAI_API_KEY"):
                load_codex_current_provider(codex_home=codex_home, environ={})

    def test_explicit_live_accepts_base_url_from_metadata_and_key_from_openai_env(self) -> None:
        result = resolve_pi_agent_provider_environment(
            provider_mode="live",
            provider_config_source="explicit",
            model="gpt-5.5",
            metadata={"base_url": "https://right.codes/codex/v1"},
            environ={"OPENAI_API_KEY": "env-secret"},
        )

        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_MODEL"], "gpt-5.5")
        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_BASE_URL"], "https://right.codes/codex/v1")
        self.assertEqual(result.env["MISSIONFORGE_PI_AGENT_API_KEY"], "env-secret")
        self.assertEqual(result.redacted_env["MISSIONFORGE_PI_AGENT_API_KEY"], "<redacted>")


def _write_codex_config(codex_home: Path, *, wire_api: str) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "globalai"',
                'model = "gpt-5.5"',
                "",
                "[model_providers.globalai]",
                'base_url = "https://right.codes/codex/v1"',
                f'wire_api = "{wire_api}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
