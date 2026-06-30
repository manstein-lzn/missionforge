from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest

from missionforge import (
    PiAgentRuntimeCapabilityStatus,
    default_pi_agent_runtime_command,
    find_pi_agent_runtime_dir,
    preflight_pi_agent_runtime,
)
from missionforge.pi_agent_runtime_bundle import (
    PI_AGENT_RUNTIME_ENV,
    PI_AGENT_RUNTIME_HOME_ENV,
    prepared_pi_agent_runtime_command,
)


class PiAgentRuntimeBundleTests(unittest.TestCase):
    def test_default_runtime_assets_are_packaged(self) -> None:
        runtime_dir = find_pi_agent_runtime_dir()

        self.assertTrue((runtime_dir / "package.json").is_file())
        self.assertTrue((runtime_dir / "package-lock.json").is_file())
        self.assertTrue((runtime_dir / "src/main.ts").is_file())
        self.assertTrue((runtime_dir / "dist/main.js").is_file())
        self.assertEqual(default_pi_agent_runtime_command()[0], "node")

    def test_preflight_reports_dependency_and_sandbox_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_dir = Path(tempdir) / "runtime"
            _write_runtime_fixture(runtime_dir, with_node_modules=False)

            report = preflight_pi_agent_runtime(
                runtime_dir,
                env={"PATH": ""},
                require_sandbox_linux=True,
            )

        self.assertFalse(report.available)
        capabilities = {item.name: item for item in report.capabilities}
        self.assertEqual(capabilities["node"].status, PiAgentRuntimeCapabilityStatus.UNAVAILABLE)
        self.assertEqual(
            capabilities["pi_agent_runtime_dependencies"].status,
            PiAgentRuntimeCapabilityStatus.UNAVAILABLE,
        )
        self.assertEqual(capabilities["sandbox_linux"].status, PiAgentRuntimeCapabilityStatus.UNAVAILABLE)

    def test_prepared_runtime_materializes_packaged_assets_to_runtime_home(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source = root / "package-assets"
            runtime_home = root / "runtime-home"
            bin_dir = root / "bin"
            _write_runtime_fixture(source, with_node_modules=False)
            bin_dir.mkdir()
            npm_log = root / "npm.log"
            fake_npm = bin_dir / "npm"
            fake_npm.write_text(
                "#!/bin/sh\n"
                f"echo \"$@\" >> {npm_log}\n"
                "mkdir -p node_modules\n",
                encoding="utf-8",
            )
            fake_node = bin_dir / "node"
            fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_npm.chmod(0o755)
            fake_node.chmod(0o755)
            env = {
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                PI_AGENT_RUNTIME_ENV: str(source),
                PI_AGENT_RUNTIME_HOME_ENV: str(runtime_home),
            }

            command, report = prepared_pi_agent_runtime_command(
                source,
                env=env,
                timeout_seconds=10,
            )

            self.assertTrue(report.available)
            self.assertNotEqual(report.runtime_dir, source)
            self.assertTrue(str(report.runtime_dir).startswith(str(runtime_home)))
            self.assertTrue((report.runtime_dir / "node_modules").is_dir())
            self.assertEqual(command[0], "node")
            self.assertEqual(Path(command[1]).parent, report.runtime_dir / "dist")
            self.assertIn("ci --ignore-scripts", npm_log.read_text(encoding="utf-8"))

    def test_development_runtime_runs_in_place(self) -> None:
        runtime_dir = find_pi_agent_runtime_dir()
        if "workers/pi-agent-runtime" not in runtime_dir.as_posix():
            self.skipTest("source tree development runtime is not active")

        report = preflight_pi_agent_runtime(runtime_dir, env=os.environ)

        self.assertEqual(report.runtime_dir, runtime_dir)
        self.assertTrue((runtime_dir / "node_modules").is_dir())


def _write_runtime_fixture(path: Path, *, with_node_modules: bool) -> None:
    (path / "dist").mkdir(parents=True)
    (path / "src").mkdir(parents=True)
    (path / "package.json").write_text(
        '{"name":"@missionforge/pi-agent-runtime","scripts":{"build":"true"}}\n',
        encoding="utf-8",
    )
    (path / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    (path / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (path / "NOTICE").write_text("fixture\n", encoding="utf-8")
    (path / "src/main.ts").write_text("export {}\n", encoding="utf-8")
    (path / "dist/main.js").write_text("console.log('fixture')\n", encoding="utf-8")
    if with_node_modules:
        (path / "node_modules").mkdir()


if __name__ == "__main__":
    unittest.main()
