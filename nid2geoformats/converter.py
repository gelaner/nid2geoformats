# nid2geoformats/converter.py
import os
import zipfile
import geopandas as gpd
import pandas as pd
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import re

shp_pattern = re.compile(r"(\w+)_(\w+)_(point|line|area)_[A-F0-9]{32}\.shp$", re.IGNORECASE)

def process_zip(zip_path, register_type):
    """
    Funkcja przetwrzająca pojedyncze archiwa ZIP pobierane z NID
    """
    results = []
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:  # otwarcie archiwum ZIP
            for file in archive.namelist():
                if file.lower().endswith(".shp"):
                    match = shp_pattern.search(os.path.basename(file))
                    if match:
                        _, _, geometry_type = match.groups()

                        temp_dir = f"/tmp/{os.path.basename(zip_path)}_{geometry_type}"
                        os.makedirs(temp_dir, exist_ok=True)

                        for ext in ['.shp', '.shx', '.dbf', '.prj']:
                            name = file[:-4] + ext
                            if name in archive.namelist():
                                archive.extract(name, temp_dir)

                        shp_path = os.path.join(temp_dir, file)

                        #testowanie zawartości plików pod kątem kodowania i narzucenie ukłądu współrzędnych
                        try:
                            gdf = gpd.read_file(shp_path, encoding="utf-8")
                            gdf.set_crs("EPSG:2180", inplace=True, allow_override=True)
                        except UnicodeDecodeError:
                            #naprawianie kodowania jeśli jest inne niż utf-8
                            try:
                                gdf = gpd.read_file(shp_path, encoding="cp1250")
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

def convert_data(indir, outdir, format):
    """
    Funkcja przetwarzająca ZIPy z NID do wybranego formatu GIS
    """
    os.makedirs(outdir, exist_ok=True)

    for register_type in sorted(os.listdir(indir)):
        subdir = os.path.join(indir, register_type)
        if not os.path.isdir(subdir):
            continue

        print(f"Przetwarzanie katalogu: {register_type}")
        aggregated = defaultdict(list)

        zip_files = [os.path.join(subdir, f) for f in os.listdir(subdir) if f.lower().endswith(".zip")]

        # równoległe przetwarzanie zawartości plików ZIP
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(process_zip, zip_path, register_type): zip_path for zip_path in zip_files}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"ZIP-y {register_type}"):
                for geometry_type, gdf in future.result():
                    aggregated[geometry_type].append(gdf)
        # obsługa plików parquet
        if format == "parquet":
            for geometry_type, gdf_list in aggregated.items():
                if gdf_list:
                    combined = gpd.GeoDataFrame(pd.concat(gdf_list, ignore_index=True), crs=gdf_list[0].crs)  # operacje na danych geoprzestrzennych
                    for col in combined.select_dtypes(include="object").columns:
                        combined[col] = combined[col].apply(lambda x: str(x) if x is not None else None)
                    output_path = os.path.join(outdir, f"{register_type}_{geometry_type}.parquet")
                    combined.to_parquet(output_path, engine="pyarrow")
                    print(f"Zapisano: {output_path}")

        # obsługa plików gepackage
        elif format == "gpkg":
            output_gpkg_path = os.path.join(outdir, f"{register_type}.gpkg")
            for geometry_type, gdf_list in aggregated.items():
                if gdf_list:
                    combined = gpd.GeoDataFrame(pd.concat(gdf_list, ignore_index=True), crs=gdf_list[0].crs)  # operacje na danych geoprzestrzennych
                    for col in combined.select_dtypes(include="object").columns:
                        combined[col] = combined[col].apply(lambda x: str(x) if x is not None else None)
                    layer_name = f"{register_type}_{geometry_type}"
                    mode = 'w' if not os.path.exists(output_gpkg_path) else 'a'
                    combined.to_file(output_gpkg_path, layer=layer_name, driver="GPKG", mode=mode)  # operacje na danych geoprzestrzennych
                    print(f"Zapisano warstwę '{layer_name}' do: {output_gpkg_path}")

        else:
            raise ValueError(f"Nieobsługiwany format: {format}")