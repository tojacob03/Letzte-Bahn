#!/usr/bin/env bash
# Run the data pipeline step by step (called by .github/workflows/pipeline.yml).
# Usage: ops/pipeline.sh <config file> <publish: true|false>
set -euo pipefail

config="$1"
publish="${2:-false}"
failed=0

for step in download prepare route transform export; do
  echo "::group::${step}"
  if ! uv run atlas run --config "$config" --steps "$step" 2>&1 | tee -a pipeline.log; then
    failed=1
  fi
  echo "::endgroup::"
  if [ "$failed" -ne 0 ]; then
    echo "::error::Pipeline step '${step}' failed"
    break
  fi
done

python3 scripts/annotate_summary.py data/staging/run_metadata.json web/data/findings.json || true

if [ "$failed" -ne 0 ]; then
  python3 scripts/annotate_failure.py pipeline.log
  exit 1
fi

if [ "$publish" = "true" ]; then
  bash ops/publish.sh
fi
