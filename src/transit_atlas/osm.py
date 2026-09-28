"""OpenStreetMap: regional extract for routing and extraction of destinations (POIs)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import osmium
import pandas as pd
import shapely
import shapely.errors

from .pois import classify

log = logging.getLogger(__name__)
POI_KEYS = ("amenity", "shop", "healthcare")
POI_COLUMNS = ["poi_id", "category", "is_strict", "name", "lon", "lat", "source"]


def _run(command: list[str]) -> None:
    log.info("$ %s", " ".join(command))
    subprocess.run(command, check=True)


def build_extract(
    sources: list[Path], bbox: tuple[float, float, float, float], target: Path
) -> Path:
    """Cut every source PBF to ``bbox`` (lon/lat) with osmium-tool and merge the parts."""
    if shutil.which("osmium") is None:
        raise RuntimeError("osmium-tool is required (apt-get install osmium-tool)")
    box = ",".join(f"{value:.5f}" for value in bbox)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        parts = []
        for index, source in enumerate(sources):
            part = Path(tmp) / f"part{index}.osm.pbf"
            _run(
                [
                    "osmium", "extract", "--bbox", box, "--strategy", "complete_ways",
                    "--overwrite", "--output", str(part), str(source),
                ]
            )
            parts.append(part)
        if len(parts) == 1:
            shutil.move(parts[0], target)
        else:
            _run(["osmium", "merge", "--overwrite", "--output", str(target), *map(str, parts)])
    return target


def _location(obj, factory: osmium.geom.WKBFactory) -> tuple[float, float] | None:
    if obj.is_node():
        location = obj.location
        return (location.lon, location.lat) if location.valid() else None
    try:
        geometry = shapely.from_wkb(bytes.fromhex(factory.create_multipolygon(obj)))
    except (RuntimeError, ValueError, shapely.errors.GEOSException):
        return None
    if geometry is None or geometry.is_empty:
        return None
    point = geometry.representative_point()
    return point.x, point.y


def _reference(obj) -> str:
    if obj.is_node():
        return f"n{obj.id}"
    return f"{'w' if obj.from_way() else 'r'}{obj.orig_id()}"


def extract_pois(pbf: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Destinations from OSM nodes and areas; an area is represented by an interior point."""
    factory = osmium.geom.WKBFactory()
    processor = (
        osmium.FileProcessor(str(pbf))
        .with_areas(osmium.filter.KeyFilter(*POI_KEYS))
        .with_filter(osmium.filter.KeyFilter(*POI_KEYS))
    )
    rows = []
    stats: Counter[str] = Counter()
    for obj in processor:
        if obj.is_way() or obj.is_relation():
            continue  # closed ways and multipolygons come back as areas
        tags = {tag.k: tag.v for tag in obj.tags}
        is_school = tags.get("amenity") == "school"
        stats["school_objects"] += is_school
        matches = classify(tags)
        if not matches:
            stats["school_unclassified"] += is_school
            continue
        point = _location(obj, factory)
        if point is None:
            stats["invalid_geometry"] += 1
            continue
        reference = _reference(obj)
        for category, strict in matches.items():
            rows.append(
                {
                    "poi_id": f"osm:{reference}",
                    "category": category,
                    "is_strict": strict,
                    "name": tags.get("name", ""),
                    "lon": point[0],
                    "lat": point[1],
                    "source": "osm",
                }
            )
            stats[category if strict else f"{category}_lenient_only"] += 1
    log.info("OSM destinations: %s", dict(stats))
    return pd.DataFrame(rows, columns=POI_COLUMNS), dict(stats)
