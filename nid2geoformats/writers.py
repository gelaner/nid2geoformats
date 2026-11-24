# nid2geoformats/writers.py
"""Zapis zagregowanych danych do formatów wyjściowych: GeoParquet, GeoPackage, PostGIS."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import geopandas as gpd

log = logging.getLogger(__name__)

FORMATS = ("parquet", "gpkg", "postgis")


class Writer(Protocol):
    def write(self, gdf: gpd.GeoDataFrame, group: Path, dataset: str, geometry: str) -> None:
        """group - ścieżka względna grupy (np. 'wojewodztwa'), dataset - np. 'ZEN', geometry - area/line/point."""

    def close(self) -> None: ...


class ParquetWriter:
    def __init__(self, outdir: Path | str):
        self.outdir = Path(outdir)

    def write(self, gdf, group, dataset, geometry):
        path = self.outdir / group / f"{dataset}_{geometry}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_parquet(path, engine="pyarrow", index=False)
        log.info("Zapisano: %s (%d obiektów)", path, len(gdf))

    def close(self):
        pass


class GpkgWriter:
    """Jeden plik GPKG na zbiór (np. ZEN.gpkg) z warstwami ZEN_area, ZEN_line, ZEN_point.

    Istniejący plik jest zastępowany przy pierwszym zapisie w danym przebiegu (brak dopisywania duplikatów).
    """

    def __init__(self, outdir: Path | str):
        self.outdir = Path(outdir)
        self._started: set[Path] = set()

    def write(self, gdf, group, dataset, geometry):
        path = self.outdir / group / f"{dataset}.gpkg"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path not in self._started:
            if path.exists():
                os.remove(path)
            self._started.add(path)
        layer = f"{dataset}_{geometry}"
        gdf.to_file(path, layer=layer, driver="GPKG")
        log.info("Zapisano warstwę '%s' do: %s (%d obiektów)", layer, path, len(gdf))

    def close(self):
        pass


@dataclass
class PostgisParams:
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    database: str | None = None
    schema: str | None = None

    @classmethod
    def from_env(cls, **overrides) -> "PostgisParams":
        """Parametry z argumentów, a w drugiej kolejności ze zmiennych PGHOST, PGPORT, PGUSER,
        PGPASSWORD, PGDATABASE, PGSCHEMA (także z pliku .env)."""
        env = {
            "host": os.environ.get("PGHOST"),
            "port": os.environ.get("PGPORT"),
            "user": os.environ.get("PGUSER"),
            "password": os.environ.get("PGPASSWORD"),
            "database": os.environ.get("PGDATABASE"),
            "schema": os.environ.get("PGSCHEMA"),
        }
        env.update({k: v for k, v in overrides.items() if v})
        if env["port"]:
            env["port"] = int(env["port"])
        return cls(**env)


class PostgisWriter:
    """Import do tabel nid_<zbiór>_<geometria> w podanym schemacie (nazwy tabel i kolumn małymi literami).

    Funkcjonalność zaproponowana przez Tomasza Rychlickiego (PR #2).
    """

    def __init__(self, params: PostgisParams, if_exists: str = "replace", table_prefix: str = "nid_"):
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.engine import URL
        except ImportError as e:
            raise ImportError(
                "Eksport do PostGIS wymaga dodatkowych pakietów: pip install \"nid2geoformats[postgis]\""
            ) from e
        driver = "postgresql+psycopg"
        try:
            import psycopg  # noqa: F401
        except ImportError:
            driver = "postgresql+psycopg2"
        # URL.create poprawnie koduje znaki specjalne w haśle (np. @, /, #)
        url = URL.create(
            driver,
            username=params.user,
            password=params.password,
            host=params.host,
            port=params.port,
            database=params.database,
        )
        self.engine = create_engine(url)
        self._text = text
        self.schema = params.schema or "public"
        self.if_exists = if_exists
        self.prefix = table_prefix
        with self.engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"'))

    def write(self, gdf, group, dataset, geometry):
        table = f"{self.prefix}{dataset}_{geometry}".lower()
        if str(group) not in ("", "."):
            table = f"{self.prefix}{Path(group).as_posix().replace('/', '_')}_{dataset}_{geometry}".lower()
        out = gdf.rename(columns={c: c.lower() for c in gdf.columns if c != gdf.geometry.name})
        out = out.rename_geometry("geom")
        out.to_postgis(table, self.engine, schema=self.schema, if_exists=self.if_exists, index=False)
        # klucz główny (wymagany m.in. do edycji w QGIS); przy append kolumna już istnieje
        with self.engine.begin() as conn:
            conn.execute(self._text(
                f'ALTER TABLE "{self.schema}"."{table}" '
                "ADD COLUMN IF NOT EXISTS gid bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
            ))
        log.info("Zapisano do PostGIS: %s.%s (%d obiektów)", self.schema, table, len(out))

    def close(self):
        self.engine.dispose()


def make_writer(fmt: str, outdir: Path | str | None = None, pg: PostgisParams | None = None, **kw) -> Writer:
    if fmt == "parquet":
        return ParquetWriter(outdir)
    if fmt == "gpkg":
        return GpkgWriter(outdir)
    if fmt == "postgis":
        return PostgisWriter(pg or PostgisParams.from_env(), **kw)
    raise ValueError(f"Nieobsługiwany format: {fmt} (dostępne: {', '.join(FORMATS)})")
