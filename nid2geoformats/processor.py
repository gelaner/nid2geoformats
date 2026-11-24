# nid2geoformats/processor.py
"""Odczyt pojedynczego archiwum ZIP NID do GeoDataFrame'ów (bez rozpakowywania na dysk)."""
from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path, PurePosixPath

import geopandas as gpd
from pyproj import CRS

from .config import TARGET_CRS

log = logging.getLogger(__name__)

# Normalizacja typu geometrii na podstawie nazwy pliku: *_area_*, *_Areal, *_line_*, *_Linear, *_point_*, ...
_GEOM_TOKENS = {
    "area": "area", "areal": "area", "polygon": "area",
    "line": "line", "linear": "line",
    "point": "point",
}
_TOKEN_SPLIT = re.compile(r"[_\-.]")
_GEOM_FROM_TYPE = {"Polygon": "area", "MultiPolygon": "area", "LineString": "line",
                   "MultiLineString": "line", "Point": "point", "MultiPoint": "point"}

_TARGET = CRS.from_user_input(TARGET_CRS)


def geometry_key(shp_name: str, gdf: gpd.GeoDataFrame | None = None) -> str:
    for token in _TOKEN_SPLIT.split(PurePosixPath(shp_name).stem.lower()):
        if token in _GEOM_TOKENS:
            return _GEOM_TOKENS[token]
    if gdf is not None and len(gdf):
        return _GEOM_FROM_TYPE.get(gdf.geom_type.dropna().iloc[0], "other")
    return "other"


def normalize_crs(gdf: gpd.GeoDataFrame, source: str = "") -> gpd.GeoDataFrame:
    """Ustala układ EPSG:2180.

    Pliki .prj NID opisują PUWG 1992 bez kodu EPSG (GDAL zwraca wtedy brak CRS lub CRS "Transverse_Mercator").
    Układ równoważny 2180 jest tylko oznaczany kodem; inny układ - przeliczany.
    """
    if gdf.crs is None:
        return gdf.set_crs(_TARGET, allow_override=True)
    if gdf.crs.equals(_TARGET, ignore_axis_order=True) or _is_puwg1992(gdf.crs):
        return gdf.set_crs(_TARGET, allow_override=True)
    log.warning("%s: układ %s różny od %s - przeliczam", source, gdf.crs.name, TARGET_CRS)
    return gdf.to_crs(_TARGET)


def _is_puwg1992(crs: CRS) -> bool:
    try:
        params = {p.name.lower(): p.value for p in crs.coordinate_operation.params}
    except AttributeError:
        return False
    def near(key: str, value: float) -> bool:
        return any(key in k and abs(v - value) < 1e-6 for k, v in params.items())
    return (near("central meridian", 19.0) or near("longitude of natural origin", 19.0)) and \
        near("scale factor", 0.9993) and near("false easting", 500000.0) and near("false northing", -5300000.0)


def _read_layer(zip_path: Path, inner: str, encoding: str | None) -> gpd.GeoDataFrame:
    vsi = f"/vsizip/{zip_path.resolve().as_posix()}/{inner}"
    return gpd.read_file(vsi, encoding=encoding) if encoding else gpd.read_file(vsi)


def read_zip(zip_path: Path | str) -> list[tuple[str, gpd.GeoDataFrame]]:
    """Zwraca listę (typ_geometrii, GeoDataFrame) dla wszystkich warstw SHP w archiwum.

    Kodowanie: zgodnie z plikiem .cpg; bez .cpg - próba UTF-8, a w razie błędu CP1250.
    Do danych dodawana jest kolumna nid_jednostka (nazwa pliku ZIP, np. kod TERYT).
    """
    zip_path = Path(zip_path)
    results: list[tuple[str, gpd.GeoDataFrame]] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError) as e:
        log.error("Nie można otworzyć %s: %s", zip_path, e)
        return results

    lower = {n.lower() for n in names}
    for inner in names:
        if not inner.lower().endswith(".shp"):
            continue
        has_cpg = inner[:-4].lower() + ".cpg" in lower
        try:
            if has_cpg:
                gdf = _read_layer(zip_path, inner, None)
            else:
                try:
                    gdf = _read_layer(zip_path, inner, "utf-8")
                except UnicodeDecodeError:
                    gdf = _read_layer(zip_path, inner, "cp1250")
        except Exception as e:  # noqa: BLE001
            log.error("Błąd odczytu %s!%s: %s", zip_path, inner, e)
            continue
        if gdf.empty:
            continue
        gdf = normalize_crs(gdf, f"{zip_path.name}!{inner}")
        gdf.insert(0, "nid_jednostka", zip_path.stem)
        results.append((geometry_key(inner, gdf), gdf))
    return results
