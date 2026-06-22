#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-all}"

run_deepresearch() {
  echo "==> Testing DeepResearch integration"
  PYTHONPATH=src:integrations/deepresearch/src \
    python3 -m unittest discover -s integrations/deepresearch/tests
}

case "$TARGET" in
  all)
    run_deepresearch
    ;;
  deepresearch)
    run_deepresearch
    ;;
  *)
    echo "unsupported integration target: $TARGET" >&2
    exit 2
    ;;
esac

echo "==> MissionForge integration validation passed"
