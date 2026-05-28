#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Checking Node runtime"
node --version
npm --version
node -e '
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 19)) {
  console.error(`MissionForge requires Node >=22.19.0; found ${process.versions.node}`);
  process.exit(1);
}
'

if [[ "${MISSIONFORGE_SKIP_NPM_CI:-0}" == "1" ]]; then
  echo "==> Skipping npm ci because MISSIONFORGE_SKIP_NPM_CI=1"
else
  echo "==> Installing PI Agent runtime dependencies"
  npm ci --prefix workers/pi-agent-runtime
fi

echo "==> Testing PI Agent runtime"
npm test --prefix workers/pi-agent-runtime

echo "==> Running Python test suite"
PYTHONPATH=src python3 -m unittest discover -s tests

echo "==> Checking whitespace"
git diff --check

echo "==> MissionForge validation passed"
