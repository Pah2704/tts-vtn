#!/usr/bin/env bash
set -euo pipefail

echo "== Preflight checks =="

PIPER_BIN_PATH=${PIPER_BIN:-/usr/local/bin/piper}
MODELS_DIR=${MODELS_DIR:-./models}

# Piper binary
if [ -x "$PIPER_BIN_PATH" ]; then
  echo "Piper binary: OK ($PIPER_BIN_PATH)"
else
  echo "Piper binary: MISSING at $PIPER_BIN_PATH"
  exit 1
fi

# At least one ONNX model
if ls "$MODELS_DIR"/*.onnx >/dev/null 2>&1; then
  echo "Piper model(s): OK"
else
  echo "Piper model(s): MISSING in $MODELS_DIR/"
  exit 1
fi

# JSON config for chosen model (optional but recommended)
if ls "$MODELS_DIR"/*.json >/dev/null 2>&1; then
  echo "Model JSON config: OK"
else
  echo "Model JSON config: NOT FOUND (optional but recommended)"
fi

echo "Outputs dir: ensuring exists"
mkdir -p backend/outputs
echo "All good."
