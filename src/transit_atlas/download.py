"""Download raw source files and record their provenance in ``data/raw/manifest.json``."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
from pathlib import Path

import requests

from .config import Config, Source

log = logging.getLogger(__name__)
MANIFEST = "manifest.json"
USER_AGENT = "transit-atlas/0.1 (+https://github.com/tojacob03/Letzte-Bahn)"
BLOCK = 1 << 20


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(source: Source, directory: Path, *, force: bool = False, retries: int = 3) -> dict:
    """Download ``source`` into ``directory`` unless the file is already there."""
    target = directory / source.filename
    if target.exists() and not force:
        log.info("Using existing %s", target.name)
        return _entry(source, target, _head(source.url), retrieved_at=None)
    for attempt in range(1, retries + 1):
        try:
            return _download(source, target)
        except requests.RequestException as error:
            if attempt == retries:
                raise
            log.warning("Download of %s failed (%s), retry %d", source.url, error, attempt)
            time.sleep(15 * attempt)
    raise AssertionError("unreachable")


def _head(url: str) -> dict:
    try:
        response = requests.head(
            url, allow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT}
        )
    except requests.RequestException:
        return {}
    return {"final_url": response.url, "last_modified": response.headers.get("Last-Modified")}


def _download(source: Source, target: Path) -> dict:
    log.info("Downloading %s", source.url)
    partial = target.with_name(target.name + ".part")
    headers = {"User-Agent": USER_AGENT}
    with requests.get(source.url, stream=True, timeout=(30, 600), headers=headers) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for block in response.iter_content(chunk_size=BLOCK):
                handle.write(block)
        info = {"final_url": response.url, "last_modified": response.headers.get("Last-Modified")}
    partial.replace(target)
    return _entry(source, target, info, retrieved_at=dt.datetime.now(dt.UTC))


def _entry(source: Source, target: Path, info: dict, retrieved_at: dt.datetime | None) -> dict:
    stat = target.stat()
    when = retrieved_at or dt.datetime.fromtimestamp(stat.st_mtime, dt.UTC)
    return {
        "url": source.url,
        "final_url": info.get("final_url"),
        "filename": source.filename,
        "bytes": stat.st_size,
        "sha256": sha256_file(target),
        "last_modified": info.get("last_modified"),
        "retrieved_at": when.isoformat(timespec="seconds"),
    }


def download_all(config: Config, directory: Path, *, force: bool = False) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "gtfs": fetch(config.gtfs, directory, force=force),
        "osm": [fetch(source, directory, force=force) for source in config.osm],
        "census": fetch(config.census, directory, force=force),
        "boundaries": fetch(config.boundaries, directory, force=force),
    }
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_manifest(directory: Path) -> dict:
    path = directory / MANIFEST
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run the download step first")
    return json.loads(path.read_text(encoding="utf-8"))
