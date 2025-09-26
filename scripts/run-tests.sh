#!/usr/bin/env bash
set -euo pipefail

echo "== Backend tests =="
python -m pytest -q backend/tests

echo "== Frontend tests =="
pushd frontend >/dev/null
npm run test
npm run typecheck
popd >/dev/null

echo "✅ All tests passed."
