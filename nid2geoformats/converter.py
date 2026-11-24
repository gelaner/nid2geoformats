# nid2geoformats/converter.py
"""Agregacja pobranych archiwów ZIP i zapis do wybranego formatu."""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiLineString, MultiPoint, MultiPolygon
from tqdm import tqdm

from .config import TARGET_CRS
from .processor import read_zip
from .writers import PostgisParams, Writer, make_writer

log = logging.getLogger(__name__)


def find_datasets(indir: Path) -> list[Path]:
    """Katalogi zawierające bezpośrednio pliki ZIP (np. data/raw/wojewodztwa/ZEN)."""
    found = {p.parent for p in indir.rglob("*.zip") if p.is_file()}
    return sorted(found)


_MULTI = {"Polygon": MultiPolygon, "LineString": MultiLineString, "Point": MultiPoint}


def to_multi(geoms: gpd.GeoSeries) -> gpd.GeoSeries:
    """Ujednolica typy w warstwie (Polygon -> MultiPolygon itd.), aby kolumna miała jeden typ geometrii."""
    def conv(g):
        cls = _MULTI.get(g.geom_type) if g is not None else None
        return cls([g]) if cls else g
    return geoms.apply(conv)


def check_validity(gdf: gpd.GeoDataFrame, label: str, make_valid: bool = False) -> gpd.GeoDataFrame:
    invalid = ~gdf.geometry.is_valid & gdf.geometry.notna()
    if invalid.any():
        ids = gdf.loc[invalid, "INSPIRE_ID"].head(5).tolist() if "INSPIRE_ID" in gdf.columns else []
        if make_valid:
            gdf = gdf.copy()
            gdf.loc[invalid, gdf.geometry.name] = gdf.geometry[invalid].make_valid()
            log.info("%s: naprawiono %d niepoprawnych geometrii", label, int(invalid.sum()))
        else:
            log.warning("%s: %d niepoprawnych geometrii (np. %s); użyj --make-valid, aby je naprawić",
                        label, int(invalid.sum()), ", ".join(map(str, ids)))
    return gdf


def merge_frames(frames: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=TARGET_CRS)
    combined[combined.geometry.name] = to_multi(combined.geometry)
    # kolumny tekstowe o mieszanych typach -> tekst (wymóg zapisu do parquet)
    for col in combined.columns:
        if col != combined.geometry.name and combined[col].dtype == object:
            combined[col] = combined[col].map(lambda x: None if x is None or x != x else str(x))
    return combined


def drop_duplicates(gdf: gpd.GeoDataFrame, label: str) -> gpd.GeoDataFrame:
    """Usuwa obiekty powtórzone w kilku paczkach (ten sam INSPIRE_ID i identyczna geometria)."""
    if "INSPIRE_ID" not in gdf.columns:
        return gdf
    key = pd.DataFrame({"id": gdf["INSPIRE_ID"], "wkb": gdf.geometry.to_wkb()})
    dup = key.duplicated()
    if dup.any():
        log.info("%s: usunięto %d zduplikowanych obiektów", label, int(dup.sum()))
        gdf = gdf.loc[~dup.values].reset_index(drop=True)
    return gdf


def collect_dataset(zip_files: list[Path], workers: int, desc: str) -> dict[str, list[gpd.GeoDataFrame]]:
    aggregated: dict[str, list[gpd.GeoDataFrame]] = defaultdict(list)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(read_zip, z) for z in zip_files]
        for future in tqdm(as_completed(futures), total=len(futures), desc=desc):
            for geometry, gdf in future.result():
                aggregated[geometry].append(gdf)
    return aggregated


def convert_data(
    indir: Path | str,
    outdir: Path | str | None,
    format: str = "parquet",
    workers: int = 4,
    dedupe: bool = True,
    pg: PostgisParams | None = None,
    writer: Writer | None = None,
    make_valid: bool = False,
) -> None:
    """Przetwarza wszystkie katalogi z ZIP-ami w `indir` i zapisuje je do `outdir` (lub PostGIS).

    Struktura wyjścia odzwierciedla wejście, np. data/raw/wojewodztwa/ZEN/*.zip ->
    data/processed/wojewodztwa/ZEN_area.parquet.
    """
    indir = Path(indir)
    writer = writer or make_writer(format, outdir, pg)
    try:
        datasets = find_datasets(indir)
        if not datasets:
            log.warning("Nie znaleziono plików ZIP w %s", indir)
        for ds_dir in datasets:
            dataset = ds_dir.name
            group = ds_dir.parent.relative_to(indir)
            zips = sorted(ds_dir.glob("*.zip"))
            aggregated = collect_dataset(zips, workers, f"{group.as_posix()}/{dataset}".lstrip("./"))
            for geometry, frames in sorted(aggregated.items()):
                gdf = merge_frames(frames)
                if dedupe:
                    gdf = drop_duplicates(gdf, f"{dataset}_{geometry}")
                gdf = check_validity(gdf, f"{dataset}_{geometry}", make_valid)
                writer.write(gdf, group, dataset, geometry)
    finally:
        writer.close()
