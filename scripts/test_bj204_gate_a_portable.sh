#!/usr/bin/env bash
# Fixture-only, clean-checkout validation for #204 Gate A v5.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${PYTHON_BIN:?Set PYTHON_BIN to the pinned repository Python interpreter}"
if [[ -e data ]]; then
  echo "refusing archive-backed run: execute from a clean checkout without data/" >&2
  exit 2
fi

PYTHONPATH=src "$PYTHON_BIN" -m pytest -q \
  tests/test_unified_model_gate_a.py
PYTHONPATH=src "$PYTHON_BIN" -m ruff check \
  src/unified_model/contract.py src/unified_model/gate_a.py \
  scripts/freeze_bj204_model_gate_a.py tests/test_unified_model_gate_a.py
