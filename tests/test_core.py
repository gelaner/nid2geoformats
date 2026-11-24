import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from nid2geoformats.converter import convert_data, drop_duplicates
from nid2geoformats.processor import geometry_key, normalize_crs, read_zip
from nid2geoformats.wms import find_zip_links
from nid2geoformats.writers import PostgisParams

PUWG_PRJ = (
    'PROJCS["Transverse_Mercator",GEOGCS["GCS_ETRS_1989",DATUM["D_ETRS_1989",SPHEROID["GRS_1980",6378137.0,'
    '298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",-5300000.0],PARAMETER["Central_Meridian",19.0],'
    'PARAMETER["Scale_Factor",0.9993],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]'
)


def make_nid_zip(path: Path, stem: str, gdf: gpd.GeoDataFrame, prj: str | None = PUWG_PRJ) -> Path:
    """Tworzy archiwum ZIP w stylu NID (shp/shx/dbf/cpg + .prj bez kodu EPSG)."""
    tmp = path.parent / f"_{stem}"
    tmp.mkdir(parents=True, exist_ok=True)
    gdf.to_file(tmp / f"{stem}.shp", encoding="utf-8")
    if prj is not None:
        (tmp / f"{stem}.prj").write_text(prj)
    else:
        (tmp / f"{stem}.prj").unlink(missing_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for f in tmp.iterdir():
            z.write(f, f.name)
    return path


def sample(n=2, offset=0.0, ids=None):
    ids = ids or [f"PL.1.9.ZIPOZ.NID_N_02_BK.{i}" for i in range(n)]
    return gpd.GeoDataFrame(
        {"INSPIRE_ID": ids, "NAZWA": ["kościół", "dwór żółty"][: len(ids)]},
        geometry=[Point(500000 + i + offset, 400000) for i in range(len(ids))],
        crs=None,
    )


def test_find_zip_links_absolute_relative_and_dedup():
    text = (
        '<a href="https://mapy.zabytek.gov.pl/dane/ZEN/E84C86A0FE844BD39EB5C5FA4830BBBF.zip"/>'
        '<a href="/dane/zra/E84C86A0FE844BD39EB5C5FA4830BBBF.zip"/>'
        '<a href="https://mapy.zabytek.gov.pl/dane/ZEN/E84C86A0FE844BD39EB5C5FA4830BBBF.zip"/>'
    )
    assert find_zip_links(text) == [
        ("ZEN", "https://mapy.zabytek.gov.pl/dane/ZEN/E84C86A0FE844BD39EB5C5FA4830BBBF.zip"),
        ("ZRA", "https://mapy.zabytek.gov.pl/dane/zra/E84C86A0FE844BD39EB5C5FA4830BBBF.zip"),
    ]


@pytest.mark.parametrize("name,expected", [
    ("abc_ZEN_area_E84C86A0FE844BD39EB5C5FA4830BBBF.shp", "area"),
    ("abc_ZEN_line_E84C86A0FE844BD39EB5C5FA4830BBBF.shp", "line"),
    ("PomnikiHistorii_Areal.shp", "area"),
    ("UNESCO_Linear.shp", "line"),
    ("UNESCO_Point.shp", "point"),
])
def test_geometry_key(name, expected):
    assert geometry_key(name) == expected


def test_geometry_key_fallback_to_geometry_type():
    assert geometry_key("dane.shp", sample()) == "point"


def test_normalize_crs_marks_puwg1992_without_reprojection():
    gdf = sample().set_crs(PUWG_PRJ)
    out = normalize_crs(gdf)
    assert out.crs.to_epsg() == 2180
    assert out.geometry.iloc[0].x == 500000


def test_normalize_crs_reprojects_other_crs():
    gdf = gpd.GeoDataFrame(geometry=[Point(19.0, 52.0)], crs="EPSG:4326")
    out = normalize_crs(gdf)
    assert out.crs.to_epsg() == 2180
    assert 400000 < out.geometry.iloc[0].x < 600000


def test_read_zip_keeps_polish_characters_and_sets_crs(tmp_path):
    z = make_nid_zip(tmp_path / "0201011.zip", "x_ZEN_point_E84C86A0FE844BD39EB5C5FA4830BBBF", sample())
    [(key, gdf)] = read_zip(z)
    assert key == "point"
    assert gdf.crs.to_epsg() == 2180
    assert list(gdf["NAZWA"]) == ["kościół", "dwór żółty"]
    assert set(gdf["nid_jednostka"]) == {"0201011"}


def test_drop_duplicates_only_identical_id_and_geometry():
    a = sample()
    b = sample()  # identyczne
    c = sample(offset=5)  # ten sam ID, inna geometria - zostaje
    merged = gpd.GeoDataFrame(pd.concat([a, b, c], ignore_index=True))
    assert len(drop_duplicates(merged, "t")) == 4


def test_convert_parquet_and_gpkg_rerun_without_duplicates(tmp_path):
    raw = tmp_path / "raw" / "wojewodztwa" / "ZEN"
    raw.mkdir(parents=True)
    stem = "x_ZEN_point_E84C86A0FE844BD39EB5C5FA4830BBBF"
    make_nid_zip(raw / "02.zip", stem, sample())
    make_nid_zip(raw / "04.zip", stem, sample())  # duplikaty między paczkami
    convert_data(tmp_path / "raw", tmp_path / "pq", "parquet")
    out = gpd.read_parquet(tmp_path / "pq" / "wojewodztwa" / "ZEN_point.parquet")
    assert len(out) == 2
    for _ in range(2):
        convert_data(tmp_path / "raw", tmp_path / "gp", "gpkg")
    gp = gpd.read_file(tmp_path / "gp" / "wojewodztwa" / "ZEN.gpkg", layer="ZEN_point")
    assert len(gp) == 2


def test_postgis_params_env_and_overrides(monkeypatch):
    monkeypatch.setenv("PGHOST", "db")
    monkeypatch.setenv("PGPORT", "5433")
    monkeypatch.setenv("PGPASSWORD", "p@ss/w#rd")
    p = PostgisParams.from_env(host="override")
    assert (p.host, p.port, p.password) == ("override", 5433, "p@ss/w#rd")


def test_postgis_url_escapes_password():
    sa = pytest.importorskip("sqlalchemy")
    url = sa.engine.URL.create("postgresql+psycopg", username="u", password="p@ss/w#rd", host="h", database="d")
    rendered = url.render_as_string(hide_password=False)
    assert sa.engine.make_url(rendered).password == "p@ss/w#rd"


def test_find_zip_links_voivodeship_path_and_update_date():
    from nid2geoformats.wms import find_update_date
    text = ('<Attribute Name="Rejestr">&lt;a href="/dane/ZRN/WOJ/ZRN_16.zip"&gt;</Attribute>'
            '<Attribute Name="Data-aktualizacji">2026-09-30</Attribute>')
    assert find_zip_links(text) == [("ZRN", "https://mapy.zabytek.gov.pl/dane/ZRN/WOJ/ZRN_16.zip")]
    assert find_update_date(text) == "2026-09-30"


@pytest.mark.parametrize("code,expected", [
    ("020101_1", "0201011"),
    ("160202_4", "1602024"),
    ("146502_8", "1465011"),  # dzielnica Warszawy -> całe miasto
    ("106102_9", "1061011"),  # delegatura Łodzi -> całe miasto
])
def test_teryt7(code, expected):
    from nid2geoformats.initializer import teryt7
    assert teryt7(code) == expected


def test_build_link():
    from nid2geoformats.initializer import build_link
    assert build_link("wojewodztwa", "16", "ZEA") == "https://mapy.zabytek.gov.pl/dane/ZEA/WOJ/ZEA_16.zip"
    assert build_link("gminy", "020101_1", "ZEN") == "https://mapy.zabytek.gov.pl/dane/ZEN/0201011.zip"


def test_merge_frames_promotes_to_multi_and_validity(caplog):
    from shapely.geometry import MultiPolygon
    from nid2geoformats.converter import check_validity, merge_frames
    sq = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    bow = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])  # samoprzecięcie
    a = gpd.GeoDataFrame({"INSPIRE_ID": ["a"]}, geometry=[sq], crs="EPSG:2180")
    b = gpd.GeoDataFrame({"INSPIRE_ID": ["b"]}, geometry=[MultiPolygon([sq]), ], crs="EPSG:2180")
    c = gpd.GeoDataFrame({"INSPIRE_ID": ["c"]}, geometry=[bow], crs="EPSG:2180")
    m = merge_frames([a, b, c])
    assert set(m.geom_type) == {"MultiPolygon"}
    out = check_validity(m, "t")
    assert "1 niepoprawnych" in caplog.text and not out.is_valid.all()
    assert check_validity(m, "t", make_valid=True).is_valid.all()
