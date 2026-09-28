#!/usr/bin/env bash
# Smoke runs on other branches than main: push the generated web data to the branch
# "smoke-preview", so the website can be checked with real data before merging, e.g.
# https://raw.githack.com/tojacob03/Letzte-Bahn/smoke-preview/web/index.html
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout -B smoke-preview
git add -f web/data web/dbt
git commit --allow-empty -m "Smoke run preview of ${GITHUB_SHA:-a local run}"
git push --force origin smoke-preview
