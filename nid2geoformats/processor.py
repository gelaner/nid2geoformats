# nid2geoformats/converter.py
import os
import zipfile
import geopandas as gpd
from pathlib import Path
import re

shp_pattern = re.compile(r"(\w+)_(\w+)_(point|line|area)_[A-F0-9]{32}\.shp$", re.IGNORECASE)

def process_zip(zip_path: Path, register_type: str) -> list[tuple[str, gpd.GeoDataFrame]]:
    """
    Funkcja przetwrzająca pojedyncze archiwa ZIP pobierane z NID do listy krotek (geometry_type, GeoDataFrame)
    """
    results = []
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:  # otwarcie archiwum ZIP
            for file in archive.namelist():
                if file.lower().endswith(".shp"):
                    match = shp_pattern.search(os.path.basename(file))
                    if match:
                        _, _, geometry_type = match.groups()

                        temp_dir = Path("/tmp/") / f"{os.path.basename(zip_path)}_{geometry_type}"
                        temp_dir.mkdir(parents=True, exist_ok=True)

                        for ext in ['.shp', '.shx', '.dbf', '.prj']:
                            name = file[:-4] + ext
                            if name in archive.namelist():
                                archive.extract(name, temp_dir)

                        shp_path = temp_dir / file

                        #testowanie zawartości plików pod kątem kodowania i narzucenie ukłądu współrzędnych
                        try:
                            gdf = gpd.read_file(shp_path, encoding="utf-8")
                            # Sprawdź czy CRS jest już ustawiony, jeśli nie - ustaw na EPSG:2180
                            if gdf.crs is None:
                                gdf.set_crs("EPSG:2180", inplace=True)
                            else:
                                # Przekształć do EPSG:2180 jeśli ma inny CRS
                                gdf = gdf.to_crs("EPSG:2180")
                        except UnicodeDecodeError:
                            #naprawianie kodowania jeśli jest inne niż utf-8
                            try:
                                gdf = gpd.read_file(shp_path, encoding="cp1250")
                                # Sprawdź i ustaw CRS również dla plików z problemami kodowania
                                if gdf.crs is None:
                                    gdf.set_crs("EPSG:2180", inplace=True)
                                else:
                                    # Przekształć do EPSG:2180 jeśli ma inny CRS
                                    gdf = gdf.to_crs("EPSG:2180")
                                for col in gdf.select_dtypes(include="object").columns:
                                    gdf[col] = gdf[col].apply(
                                        lambda x: x.encode("cp1250", errors="replace").decode("utf-8", errors="replace")
                                        if isinstance(x, str) else x
                                    )
                            except Exception as e:
                                print(f"Nie udało się naprawić pliku {shp_path}: {e}")
                                continue

                        results.append((geometry_type, gdf))
    except Exception as e:
        print(f"Błąd przetwarzania {zip_path}: {e}")
    return results
