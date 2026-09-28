#!/usr/bin/env bash
# Lint and test (called by .github/workflows/ci.yml).
# Logs of public repositories are only visible when signed in, so the tail of every
# failing log is also published as a GitHub annotation.
set -uo pipefail

status=0
uv sync 2>&1 | tee install.log || status=1
if [ "$status" -eq 0 ]; then
  uv run ruff check --output-format=github . 2>&1 | tee lint.log || status=1
  uv run pytest 2>&1 | tee test.log || status=1
fi
if [ "$status" -ne 0 ]; then
  python3 scripts/annotate_failure.py install.log lint.log test.log
fi
exit "$status"
