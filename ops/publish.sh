#!/usr/bin/env bash
# Commit the new snapshot (web data, published metrics, dbt docs, README findings and a
# fresh screenshot) back to main. Only runs for the main branch.
set -euo pipefail

if uv run --with playwright python -m playwright install --with-deps chromium > /dev/null 2>&1; then
  uv run --with playwright python scripts/screenshot.py web docs/screenshot.png \
    || echo "::warning::Screenshot could not be taken"
else
  echo "::warning::Playwright could not be installed; keeping the old screenshot"
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
for path in web/data web/dbt data/published README.md CASE_STUDY.md docs/screenshot.png uv.lock; do
  if [ -e "$path" ]; then
    git add "$path"
  fi
done
if git diff --cached --quiet; then
  echo "Nothing to publish"
  exit 0
fi
snapshot=$(python3 -c "import json; print(json.load(open('web/data/meta.json'))['snapshot_id'])")
git commit -m "Publish snapshot ${snapshot}"
git pull --rebase origin main
git push origin HEAD:main
