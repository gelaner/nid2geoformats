# nid2geoformats/converter.py
from .processor import process_zip
import geopandas as gpd
import pandas as pd
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


def convert_data(indir: Path, outdir: Path, format: str) -> None:
    """
    Funkcja przetwarzająca ZIPy z NID do wybranego formatu GIS
    """
    outdir.mkdir(parents=True, exist_ok=True)

    for register_type_path in sorted(indir.iterdir()):
        register_type = register_type_path.name.lower()
        
        print(f"Przetwarzanie katalogu: {register_type_path}")
        aggregated = defaultdict(list)

        zip_files = [f for f in register_type_path.iterdir() if f.name.lower().endswith(".zip")]

        # równoległe przetwarzanie zawartości plików ZIP
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(process_zip, zip_path, register_type_path): zip_path for zip_path in zip_files}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"ZIP-y {register_type_path}"):
                for geometry_type, gdf in future.result():
                    aggregated[geometry_type].append(gdf)
        # obsługa plików parquet
        if format == "parquet":
            for geometry_type, gdf_list in aggregated.items():
                if gdf_list:
                    # Upewnij się, że wszystkie GeoDataFrame'y mają ten sam CRS
                    target_crs = "EPSG:2180"
                    normalized_gdfs = []
                    for gdf in gdf_list:
                        if gdf.crs != target_crs:
                            gdf = gdf.to_crs(target_crs)
                        normalized_gdfs.append(gdf)
                    combined = gpd.GeoDataFrame(pd.concat(normalized_gdfs, ignore_index=True), crs=target_crs)  # operacje na danych geoprzestrzennych
                    for col in combined.select_dtypes(include="object").columns:
                        combined[col] = combined[col].apply(lambda x: str(x) if x is not None else None)
                    output_path = outdir / f"{register_type}_{geometry_type}.parquet"
                    combined.to_parquet(output_path, engine="pyarrow")
                    print(f"Zapisano: {output_path}")

        # obsługa plików gepackage
        elif format == "gpkg":
            output_gpkg_path = outdir / f"{register_type}.gpkg"
            for geometry_type, gdf_list in aggregated.items():
                if gdf_list:
                    # Upewnij się, że wszystkie GeoDataFrame'y mają ten sam CRS
                    target_crs = "EPSG:2180"
                    normalized_gdfs = []
                    for gdf in gdf_list:
                        if gdf.crs != target_crs:
                            gdf = gdf.to_crs(target_crs)
                        normalized_gdfs.append(gdf)
                    combined = gpd.GeoDataFrame(pd.concat(normalized_gdfs, ignore_index=True), crs=target_crs)  # operacje na danych geoprzestrzennych
                    for col in combined.select_dtypes(include="object").columns:
                        combined[col] = combined[col].apply(lambda x: str(x) if x is not None else None)
                    layer_name = f"{register_type}_{geometry_type}"
                    mode = 'w' if not output_gpkg_path.exists() else 'a'
                    combined.to_file(output_gpkg_path, layer=layer_name, driver="GPKG", mode=mode)  # operacje na danych geoprzestrzennych
                    print(f"Zapisano warstwę '{layer_name}' do: {output_gpkg_path}")

        else:
            raise ValueError(f"Nieobsługiwany format: {format}")
