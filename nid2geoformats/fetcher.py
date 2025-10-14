# nid2geoformats/fetcher.py
import os
import requests
import pandas as pd
from tqdm import tqdm
from pathlib import Path

def fetch_archives(archive_list_path: Path, download_dir: Path):  # funkcja pobierająca pliki ZIP z listy linków
    """
    Pobiera archiwa ZIP z listy i zapisuje je w podanym katalogu.
    """
    download_dir.mkdir(parents=True, exist_ok=True)
    
    df = pd.read_csv(archive_list_path, sep='\t')

    for _, row in tqdm(df.iterrows(), total=df.shape[0], desc="Pobieranie archiwów"):
        url = row['link_do_pobrania']
        jpt_kod = row['JPT_KOD_JE']
        register_type = row['typ_rejestru']
        
        # Tworzenie podkatalogu dla typu rejestru
        register_dir = download_dir / register_type
        register_dir.mkdir(parents=True, exist_ok=True)

        # Nazwa pliku na podstawie JPT_KOD_JE
        filename = f"{jpt_kod}.zip"
        file_path = register_dir / filename

        # Pobieranie pliku
        response = requests.get(url, stream=True)  # wysłanie zapytania HTTP do serwera WMS
        if response.status_code == 200:
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        else:
            print(f"Błąd podczas pobierania {url}: Status {response.status_code}")

    print(f"Zakończono pobieranie. Pliki zapisano w: {download_dir}")