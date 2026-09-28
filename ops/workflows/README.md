# Workflow definitions to install

The GitHub connector used to build this repository may not create files in
`.github/workflows/` (that needs the `workflow` token scope). These three files therefore
live here and have to be moved once, e.g. in the GitHub web interface:

| File here | Move to |
| --- | --- |
| `ops/workflows/ci.yml` | `.github/workflows/ci.yml` |
| `ops/workflows/pipeline.yml` | `.github/workflows/pipeline.yml` |
| `ops/workflows/pages.yml` | `.github/workflows/pages.yml` |

The workflows only prepare the runner and call the scripts in `ops/`, so later changes
to the pipeline do not require editing them.
