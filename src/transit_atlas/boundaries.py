"""Municipality boundaries from BKG VG250, read directly from the zip archive."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pyogrio
import shapely

GPKG_MEMBER = "vg250_ebenen_0101/DE_VG250.gpkg"
CRS_UTM32 = "EPSG:25832"
LAND = 4  # Geofaktor 4: land area ("Land mit Struktur")


def gpkg_path(zip_path: Path) -> str:
    return f"/vsizip/{Path(zip_path).resolve()}/{GPKG_MEMBER}"


def load_municipalities(zip_path: Path, ags_prefix: str) -> gpd.GeoDataFrame:
    """Municipalities whose AGS starts with ``ags_prefix`` (EPSG:25832)."""
    if not ags_prefix.isdigit():
        raise ValueError(f"Invalid AGS prefix: {ags_prefix!r}")
    path = gpkg_path(zip_path)
    gem = pyogrio.read_dataframe(
        path, layer="vg250_gem", where=f"AGS LIKE '{ags_prefix}%' AND GF = {LAND}"
    )
    if gem.empty:
        raise ValueError(f"No municipalities found for AGS prefix {ags_prefix}")
    kreise = pyogrio.read_dataframe(
        path,
        layer="vg250_krs",
        where=f"AGS LIKE '{ags_prefix[:5]}%' AND GF = {LAND}",
        read_geometry=False,
    )
    gem = gem.dissolve(by="AGS", as_index=False, aggfunc="first")
    kreise = kreise.drop_duplicates("AGS").rename(columns={"AGS": "kreis_ags", "GEN": "kreis_name"})
    municipalities = gpd.GeoDataFrame(
        {
            "ags": gem["AGS"],
            "name": gem["GEN"],
            "bez": gem["BEZ"],
            "kreis_ags": gem["AGS"].str[:5],
        },
        geometry=gem.geometry,
        crs=gem.crs,
    ).to_crs(CRS_UTM32)
    municipalities = municipalities.merge(
        kreise[["kreis_ags", "kreis_name"]], on="kreis_ags", how="left"
    )
    municipalities["area_km2"] = municipalities.geometry.area / 1e6
    return municipalities.sort_values("ags").reset_index(drop=True)


def load_country(zip_path: Path) -> shapely.Geometry:
    """Land area of Germany (EPSG:25832); destinations abroad are not covered by the data."""
    states = pyogrio.read_dataframe(gpkg_path(zip_path), layer="vg250_sta", where=f"GF = {LAND}")
    return shapely.union_all(states.to_crs(CRS_UTM32).geometry.to_numpy())
