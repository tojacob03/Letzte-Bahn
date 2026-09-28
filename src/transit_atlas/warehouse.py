"""Transform stage: build the dbt project (DuckDB) on top of the staging files."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from .config import Config, Paths

log = logging.getLogger(__name__)
DATABASE = "atlas.duckdb"


@contextlib.contextmanager
def working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def dbt(paths: Paths, *args: str) -> None:
    """Invoke dbt; staging sources resolve relative to ``paths.root`` (the working dir)."""
    from dbt.cli.main import dbtRunner

    project = paths.root / "dbt"
    paths.warehouse.mkdir(parents=True, exist_ok=True)
    os.environ["ATLAS_DUCKDB_PATH"] = str(paths.warehouse / DATABASE)
    with working_directory(paths.root):
        result = dbtRunner().invoke(
            [*args, "--project-dir", str(project), "--profiles-dir", str(project)]
        )
    if not result.success:
        raise RuntimeError(f"dbt {' '.join(args)} failed: {result.exception}")


def run(config: Config, paths: Paths) -> None:
    del config  # the dbt project reads everything it needs from the staging files
    database = paths.warehouse / DATABASE
    database.unlink(missing_ok=True)  # every run rebuilds the warehouse from staging
    dbt(paths, "build")
    dbt(paths, "docs", "generate", "--static")
    docs = paths.root / "web" / "dbt"
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths.root / "dbt" / "target" / "static_index.html", docs / "index.html")
    log.info("dbt docs written to %s", docs)
