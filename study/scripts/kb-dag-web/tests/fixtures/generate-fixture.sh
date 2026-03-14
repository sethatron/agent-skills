#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KB_DAG_PY="$SCRIPT_DIR/../../../kb-dag.py"
FIXTURE_KB="$SCRIPT_DIR/test-kb.yaml"
OUT_DIR="/tmp/kb-dag-test"
python3 "$KB_DAG_PY" --kb "$FIXTURE_KB" --output "$OUT_DIR/index.html" --no-serve --no-open
echo "Fixture generated at $OUT_DIR/index.html"
