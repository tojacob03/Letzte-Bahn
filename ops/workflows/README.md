# Workflow definitions (reference copies)

These files are installed in `.github/workflows/`. They are kept here as the reference
for the three workflows, because the GitHub connector used to build this repository may
not write to `.github/workflows/` directly.

| File here | Installed as |
| --- | --- |
| `ops/workflows/ci.yml` | `.github/workflows/ci.yml` |
| `ops/workflows/pipeline.yml` | `.github/workflows/pipeline.yml` |
| `ops/workflows/pages.yml` | `.github/workflows/pages.yml` |

The workflows only prepare the runner and call the scripts in `ops/`, so later changes
to the pipeline do not require editing them.
