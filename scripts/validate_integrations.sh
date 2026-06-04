#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-all}"

run_skillfoundry() {
  echo "==> Testing SkillFoundry integration"
  PYTHONPATH=src:integrations/skillfoundry/src \
    python3 -m unittest discover -s integrations/skillfoundry/tests
}

case "$TARGET" in
  all)
    run_skillfoundry
    ;;
  skillfoundry)
    run_skillfoundry
    ;;
  *)
    echo "unsupported integration target: $TARGET" >&2
    exit 2
    ;;
esac

echo "==> MissionForge integration validation passed"
