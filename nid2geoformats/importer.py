# nid2geoformats/converter.py
from .processor import process_zip
import geopandas as gpd
import pandas as pd
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from sqlalchemy import create_engine


def to_postgis(indir: Path, host: str, port: int, user: str, password: str, database: str, schema: str):
    """
    Funkcja importująca przetworzone pliki do bazy PostGIS
    """

    engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database}')
    
    for register_type_path in sorted(indir.iterdir()):
        register_type = register_type_path.name.lower()
        
        if not register_type_path.is_dir():
            continue

        print(f"Przetwarzanie katalogu: {register_type_path}")
        aggregated = defaultdict(list)

        zip_files = [f for f in register_type_path.iterdir() if f.name.lower().endswith(".zip")]
        
        # równoległe przetwarzanie zawartości plików ZIP
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(process_zip, zip_path, register_type_path): zip_path for zip_path in zip_files}
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"ZIP-y {register_type_path}"):
                for geometry_type, gdf in future.result():
                    gdf.columns = [col.lower() for col in gdf.columns] # zmiana nazw kolumn na małe litery
                    aggregated[geometry_type].append(gdf)
                    
        # obsługa importu do PostGIS
        for geometry_type, gdf_list in aggregated.items():
            if gdf_list:
                # Upewnij się, że wszystkie GeoDataFrame'y mają ten sam CRS
                target_crs = "EPSG:2180"
                normalized_gdfs = []
                for gdf in gdf_list:
                    if gdf.crs != target_crs:
                        gdf = gdf.to_crs(target_crs)
                    normalized_gdfs.append(gdf)
                combined = gpd.GeoDataFrame(
                    pd.concat(normalized_gdfs, ignore_index=True), crs=target_crs
                )  # operacje na danych geoprzestrzennych
                for col in combined.select_dtypes(include="object").columns:
                    combined[col] = combined[col].apply(
                        lambda x: str(x) if x is not None else None
                    )
                combined.to_postgis(f"nid_{register_type}_{geometry_type}", engine, schema=schema, if_exists='replace', index=True)
                print(f"Zapisano do bazy PostGIS: nid_{register_type}_{geometry_type}")
