# nid2geoformats/units.py
"""Aktualizacja listy jednostek (gmin / jednostek ewidencyjnych) z Państwowego Rejestru Granic (GUGiK)."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import geopandas as gpd

from .http import make_session

log = logging.getLogger(__name__)

PRG_WFS = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/PRG/WFS/AdministrativeBoundaries"
PRG_UNITS_LAYER = "ms:A05_Granice_jednostek_ewidencyjnych"
UNITS_COLUMNS = ["JPT_KOD_JE", "JPT_NAZWA", "XCoord", "YCoord"]


def download_prg_units(target: Path | str) -> Path:
    """Pobiera granice jednostek ewidencyjnych (GML, ok. 180 MB) z usługi WFS PRG."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    params = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": PRG_UNITS_LAYER}
    with make_session().get(PRG_WFS, params=params, stream=True, timeout=(10, 600)) as r:
        r.raise_for_status()
        part = target.with_name(target.name + ".part")
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    part.replace(target)
    return target


def build_units(prg_path: Path | str) -> list[list[str]]:
    """Punkt reprezentatywny (zawsze wewnątrz poligonu) dla każdej jednostki, EPSG:2180."""
    g = gpd.read_file(prg_path).to_crs("EPSG:2180")
    pts = g.geometry.representative_point()
    rows = [
        [code, name, f"{p.x:.0f}", f"{p.y:.0f}"]
        for code, name, p in zip(g["JPT_KOD_JE"], g["JPT_NAZWA_"], pts)
    ]
    return sorted(rows)


def update_units(output: Path | str, cache_dir: Path | str = "data/prg", refresh: bool = False) -> list[list[str]]:
    gml = Path(cache_dir) / "A05_jednostki_ewidencyjne.gml"
    if refresh or not gml.exists():
        log.info("Pobieranie granic jednostek z PRG (WFS GUGiK)...")
        download_prg_units(gml)
    rows = build_units(gml)
    output = Path(output)
    previous = set()
    if output.exists():
        with open(output, encoding="utf-8", newline="") as f:
            previous = {r["JPT_KOD_JE"] for r in csv.DictReader(f, delimiter="\t")}
    with open(output, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(UNITS_COLUMNS)
        w.writerows(rows)
    current = {r[0] for r in rows}
    log.info("Zapisano %d jednostek do %s", len(rows), output)
    if previous:
        if added := sorted(current - previous):
            log.info("Nowe jednostki: %s", ", ".join(added))
        if removed := sorted(previous - current):
            log.info("Usunięte jednostki: %s", ", ".join(removed))
    return rows

