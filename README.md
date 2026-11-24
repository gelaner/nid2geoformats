# 🏛️ nid2geoformats

`nid2geoformats` to aplikacja do pobierania, przetwarzania i aktualizacji danych przestrzennych udostępnianych przez **Narodowy Instytut Dziedzictwa (NID)**: rejestru i ewidencji zabytków nieruchomych i archeologicznych, Pomników Historii oraz obiektów z Listy Światowego Dziedzictwa UNESCO.

## 🧭 1. Czym jest ten projekt?

To narzędzie służy do:

- budowania aktualnej listy paczek ZIP z danymi NID — dla **województw** (domyślnie) albo **gmin**,
- seryjnego pobierania paczek ZIP z serwera NID,
- konwersji danych (SHP) do nowoczesnych formatów: **GeoParquet**, **GeoPackage** oraz do bazy **PostGIS**,
- aktualizacji listy gmin na podstawie Państwowego Rejestru Granic (PRG, GUGiK).

Projekt może być wykorzystywany jako **program z linii poleceń (CLI)** albo **biblioteka Python**.

### Rejestry NID

| Kod | Zasób |
|-----|-------|
| `ZRN` | rejestr zabytków nieruchomych |
| `ZRA` | rejestr zabytków archeologicznych |
| `ZEN` | ewidencja zabytków nieruchomych |
| `ZEA` | ewidencja zabytków archeologicznych |
| `PomnikiHistorii`, `UNESCO` | zbiory krajowe (`fetch --static`) |

### Województwa czy gminy?

NID udostępnia te same dane w dwóch podziałach (stan na wydanie 2026-09-30):

- **województwa** — 16 paczek na rejestr (64 pliki, ok. 310 MB), adresy `https://mapy.zabytek.gov.pl/dane/<REJ>/WOJ/<REJ>_<TERYT_WOJ>.zip`;
- **gminy** — ok. 3200 paczek na rejestr (ok. 12 800 plików), adresy `https://mapy.zabytek.gov.pl/dane/<REJ>/<TERYT7>.zip`. Paczki gminne zawierają dodatkowo kolumny `TERYT_WOJ`, `TERYT_POW`, `TERYT_GM`, `TYP_ADM`; obiekty leżące na granicy gmin występują w kilku paczkach (są usuwane przy konwersji).

Porównanie dla województwa opolskiego wykazało, że paczka wojewódzka zawiera dokładnie sumę obiektów z paczek gminnych (identyczne geometrie i atrybuty), dlatego domyślnym poziomem są **województwa**. Poziom gmin przydaje się do pobierania wycinków.

---

## 🛠️ 2. Szybki start (CLI)

```bash
pip install .                      # lub: pip install -r requirements.txt
pip install ".[postgis]"           # opcjonalnie: eksport do PostGIS

# 1. lista paczek wojewódzkich (bez sid: linki budowane z kodów TERYT i sprawdzane zapytaniem HEAD)
nid2geoformats init                               # -> archiwa_wojewodztwa.tsv

# 2. pobranie paczek (+ Pomniki Historii i UNESCO)
nid2geoformats fetch --input archiwa_wojewodztwa.tsv --outdir data/raw --static

# 3. konwersja
nid2geoformats convert --indir data/raw --outdir data/processed --format parquet
nid2geoformats convert --indir data/raw --outdir data/processed --format gpkg
nid2geoformats convert --indir data/raw --format postgis --schema zabytki      # parametry z PG* / .env
```

`python main.py <komenda>` działa tak samo jak `nid2geoformats <komenda>`.

### Komendy

| Komenda | Opis |
|---------|------|
| `init` | Tworzy listę archiwów (`--level wojewodztwa\|gminy`). Bez `sid` buduje linki z TERYT i weryfikuje je (`--no-verify` pomija weryfikację). Z `sid` odczytuje linki z usługi WMS NID (`--raw-dir` zapisuje surowe odpowiedzi). |
| `fetch` | Pobiera archiwa do `<outdir>/<poziom>/<rejestr>/`. Pomija poprawnie pobrane pliki (`--force` wymusza), ponawia nieudane próby, `--static` / `--static-only` pobiera Pomniki Historii i UNESCO. |
| `convert` | Łączy paczki w zbiory krajowe i zapisuje do `parquet`, `gpkg` lub `postgis`. Struktura wyjścia odzwierciedla wejście, np. `data/processed/wojewodztwa/ZEN_area.parquet`. Usuwa duplikaty (ten sam `INSPIRE_ID` i geometria; `--no-dedupe` wyłącza). |
| `units` | Aktualizuje `jednostki_gminy.tsv` z PRG (WFS GUGiK, ok. 180 MB). Potrzebne po zmianach podziału administracyjnego (np. 1.01.2026 r. sześć gmin uzyskało status miejsko-wiejski). |
| `wms-test` | Sprawdza ważność `sid` i wypisuje warstwy usługi WMS. |

Każda paczka daje do trzech warstw: `area`, `line`, `point` (geometrie ujednolicone do typów Multi*). Niepoprawne geometrie ze źródła są zgłaszane w logu; `--make-valid` je naprawia. Do danych dodawana jest kolumna `nid_jednostka` (nazwa paczki źródłowej). Układ współrzędnych: **EPSG:2180** (PUWG 1992).

---

## 🐍 3. Użycie jako biblioteka

```python
from nid2geoformats.initializer import initialize_offline
from nid2geoformats.fetcher import fetch_archives, fetch_static
from nid2geoformats.converter import convert_data

initialize_offline("jednostki_wojewodztwa.tsv", "archiwa_wojewodztwa.tsv", level="wojewodztwa")
fetch_archives("archiwa_wojewodztwa.tsv", "data/raw")
fetch_static("data/raw")

convert_data("data/raw", "data/processed", "parquet")
```

PostGIS:

```python
from nid2geoformats.converter import convert_data
from nid2geoformats.writers import PostgisParams

pg = PostgisParams.from_env(host="127.0.0.1", database="dane_gis", schema="zabytki")  # reszta z PG*
convert_data("data/raw/wojewodztwa", None, "postgis", pg=pg)   # tabele nid_zen_area, nid_zra_point, ...
```

W PostGIS tabele mają nazwy `nid_[<poziom>_]<zbiór>_<geometria>` (małe litery, także nazwy kolumn), kolumnę `geom` z typem Multi* i SRID 2180, indeks GiST oraz klucz główny `gid`. Schemat jest tworzony, jeśli nie istnieje; `--if-exists replace|append|fail`.

---|---:|---:|---:|---:|
| ZRN | 68 882 | 81 279 | 19 475 | 7 078 (głównie obszary i elementy układów) |
| ZRA | 7 843 | 7 843 | 0 | 0 |
| ZEN | 197 380 | 197 347 | 0 | 33 |
| ZEA | 491 635 | 472 977 | 77 | 18 735 |

---

## ⚙️ 4. Konfiguracja: plik `.env`

Ustawienia można zapisać w pliku `.env` w katalogu roboczym (wzór: `.env.example`). Argumenty CLI mają pierwszeństwo.

```text
NID_SID=...              # identyfikator sesji WMS (tylko dla init w trybie WMS i wms-test)
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=qgisowiec
PGPASSWORD=...
PGDATABASE=dane_gis
PGSCHEMA=zabytki
```

Hasła do bazy nie podawaj w linii poleceń (`--password` zostaje w historii powłoki) — użyj `PGPASSWORD` lub `.env`.

### Identyfikator sesji (`sid`) usługi WMS NID

`sid` **nie jest potrzebny** do pobierania danych — linki mają stały schemat. Przydaje się do weryfikacji listy paczek bezpośrednio w usłudze WMS (`init` z `--session`/`NID_SID`) oraz `wms-test`. `sid` wygasa po pewnym czasie. Aby go uzyskać:

1. otwórz [Portal mapowy NID](https://mapy.zabytek.gov.pl/nid/) i zaczekaj na załadowanie mapy,
2. w tej samej przeglądarce otwórz [dokument GetCapabilities usługi „Dane do pobrania”](https://mapy.zabytek.gov.pl/nid/XsltApplicator.WebClient.ashx?action=WMSGetCapabilitiesHTML&mapServiceId=dbcff7fd-7902-4f57-b088-128db66682fb&link=https%3A%2F%2Fusluga.zabytek.gov.pl%2FDaneZabytki%2FService.svc%2Fget%3Fservice%3DWMS%26request%3DGetCapabilities)
   (alternatywnie w portalu: warstwa `Dane do pobrania` → `Źródła danych` → `Pokaż zdefiniowane źródła danych` → `Dokument GetCapabilities`),
3. skopiuj wartość parametru `sid=...`.

![Pozyskanie identyfikatora sesji](docs/sess_id.png)

---

## 📦 5. Wymagania

Python ≥ 3.10, `geopandas`, `pyogrio`, `pyarrow`, `pandas`, `requests`, `tqdm`, `python-dotenv`; dla PostGIS: `sqlalchemy`, `psycopg`, `geoalchemy2` (`pip install ".[postgis]"`). Testy: `pip install ".[dev]" && pytest`.

---

## 🧾 6. Licencjonowanie danych źródłowych

Korzystając z danych akceptujesz warunki/komunikaty opisane na [stronie NID](https://mapy.zabytek.gov.pl/dane/notaPrawna.html). Udostępnione przez NID dane mają charakter poglądowy; wiążące są rejestry i ewidencje prowadzone przez wojewódzkich konserwatorów zabytków.

Wszystkie dane zamieszczane w katalogu [dane.gov.pl](https://dane.gov.pl/) pochodzące z [Narodowego Instytutu Dziedzictwa](https://dane.gov.pl/pl/institution/64,narodowy-instytut-dziedzictwa) udostępniane są na licencji [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode.pl).

Granice jednostek administracyjnych: Państwowy Rejestr Granic, [GUGiK](https://www.geoportal.gov.pl/).

Udostępnianie otwartych danych reguluje ustawa z dnia 11 sierpnia 2021 r. o otwartych danych i ponownym wykorzystywaniu informacji sektora publicznego ([Dz. U. z 2023 r. poz. 1524](https://dziennikustaw.gov.pl/DU/2021/1641)).

---

## 📚 7. Więcej informacji

Szczegółowy opis działania oraz przykłady wykorzystania aplikacji znajdziesz na blogu:

👉 [GeoInfor: o GIS, informacji i mapach](https://geoinfor.pl/)

---

🛠 Projekt rozwijany przez [Jakuba Bobrowskiego](https://www.linkedin.com/in/jakubbobrowski/) od lipca 2025. Obsługa PostGIS i plików `.env` na podstawie propozycji [Tomasza Rychlickiego](https://github.com/miszokienka) (PR #2).
