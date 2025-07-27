# nid2geoformats/initializer.py
import requests  # importowanie modułów zewnętrznych i standardowych
import re  # importowanie modułów zewnętrznych i standardowych
import csv  # importowanie modułów zewnętrznych i standardowych
from tqdm import tqdm


# Szablon URL GetFeatureInfo do serwera NID
URL_TEMPLATE = (
    "https://usluga.zabytek.gov.pl/DaneZabytki/service.svc/get?"
    "sid={session_id}&VERSION=1.3.0&SERVICE=WMS&"
    "REQUEST=GetFeatureInfo&INFO_FORMAT=text/xml&LAYERS=Dane_do_pobrania&"
    "QUERY_LAYERS=Dane_do_pobrania&FORMAT=image/png&CRS=EPSG:2180&WIDTH=100&"
    "HEIGHT=100&I=50&J=50&styles=&BBOX={bbox}"
)

# Wzorzec wykrywania linków do ZIP
ZIP_PATTERN = re.compile(r"/dane/([A-Z]{3})/([A-F0-9]{32})\.zip")


def test_wms_availability(session_id):  # test połączenia z usługą WMS i ważność session_id
    """
    Testuje dostępność usługi WMS i ważność podanego SESSION_ID.
    Zwraca True, jeśli połączenie jest poprawne, False w przeciwnym razie.
    """
    test_url = f"https://usluga.zabytek.gov.pl/DaneZabytki/service.svc/get?REQUEST=GetCapabilities&VERSION=1.3.0&SERVICE=WMS&sid={session_id}"
    try:
        test_response = requests.get(test_url, timeout=10)  # wysłanie zapytania HTTP do serwera WMS
        if test_response.status_code == 200:
            print("Połączenie z usługą WMS powiodło się.")
            return True
        else:
            print(f"Błąd połączenia z usługą WMS: kod HTTP {test_response.status_code}")
            print("Prawdopodobnie session_id jest nieaktualny.")
            return False
    except Exception as e:
        print(f"Nie można połączyć się z usługą WMS: {e}")
        return False




def initialize_archives_list(session_id, input_path, output_path):  # inicjalizacja listy archiwów ZIP do pobrania z NID
    """
    Dla każdego punktu (XCoord, YCoord) pobiera listę dostępnych ZIP-ów z usługi WMS GetFeatureInfo 
    a na końcu zapisuje wszystkie pobrane adresy do pliku tekstowego.
    """
    
    results = []

    with open(input_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter='\t')  # operacje na plikach CSV/TSV
        rows = list(reader)

    for row in tqdm(rows, desc="Punkty"):
        try:
            jpt_kod_je = row["JPT_KOD_JE"]
            x = float(row["XCoord"])
            y = float(row["YCoord"])
            minx = x - 50
            maxx = x + 50
            miny = y - 50
            maxy = y + 50
            # uwaga: geoportal ma zamienione współrzędne X/Y
            bbox = f"{miny},{minx},{maxy},{maxx}"

            url = URL_TEMPLATE.format(session_id=session_id, bbox=bbox)
            response = requests.get(url, timeout=10)  # wysłanie zapytania HTTP do serwera WMS
            if response.status_code == 200:
                matches = ZIP_PATTERN.findall(response.text)
                for register_type, zip_name in set(matches):  # set() usuwa duplikaty
                    zip_url = f"https://mapy.zabytek.gov.pl/dane/{register_type}/{zip_name}.zip"
                    results.append([jpt_kod_je, register_type, zip_url])
        except Exception as e:
            print(f"Błąd przy {jpt_kod_je}: {e}")

    # Zapisz wyniki do pliku CSV w formacie TSV (rozdzielny tabulatorami)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")  # operacje na plikach CSV/TSV
        writer.writerow(["JPT_KOD_JE", "typ_rejestru", "link_do_pobrania"])
        writer.writerows(results)
    print(f"Zapisano {len(results)} rekordów do pliku {output_path}")