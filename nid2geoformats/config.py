# nid2geoformats/config.py
"""Stałe konfiguracyjne i odczyt ustawień (CLI > zmienne środowiskowe > plik .env)."""
from __future__ import annotations

import os

# Usługa WMS "Dane do pobrania" (wymaga identyfikatora sesji sid)
WMS_URL = "https://usluga.zabytek.gov.pl/DaneZabytki/service.svc/get"

# Strona portalu, z której można odczytać aktualny sid (patrz README)
SID_HELP_URL = (
    "https://mapy.zabytek.gov.pl/nid/XsltApplicator.WebClient.ashx?action=WMSGetCapabilitiesHTML"
    "&mapServiceId=dbcff7fd-7902-4f57-b088-128db66682fb"
    "&link=https%3A%2F%2Fusluga.zabytek.gov.pl%2FDaneZabytki%2FService.svc%2Fget%3Fservice%3DWMS"
    "%26request%3DGetCapabilities"
)

# Bazowy adres serwera z archiwami ZIP
DOWNLOAD_BASE = "https://mapy.zabytek.gov.pl/dane"

# Poziomy agregacji danych i odpowiadające im warstwy WMS
LEVELS = ("wojewodztwa", "gminy")
DEFAULT_LEVEL = "wojewodztwa"
WMS_LAYERS = {"wojewodztwa": "Wojewodztwa", "gminy": "Gminy"}

# Połowa boku okna GetFeatureInfo (m) dobrana do zakresu skal warstwy (obraz 100 px, piksel 0,28 mm):
# Gminy: 1:1 - 1:1 000 000 -> 100 m okna ~ 1:3 600; Wojewodztwa: 1:1 000 001 - 1:6 000 000 -> 56 km ~ 1:2 000 000
WMS_HALF_SIZE = {"wojewodztwa": 28_000.0, "gminy": 50.0}

# Domyślne pliki z punktami jednostek administracyjnych (EPSG:2180)
UNITS_FILES = {"wojewodztwa": "jednostki_wojewodztwa.tsv", "gminy": "jednostki_gminy.tsv"}

# Rejestry NID: rejestr/ewidencja x nieruchome/archeologiczne
REGISTERS = ("ZRN", "ZRA", "ZEN", "ZEA")

# Zbiory krajowe dostępne pod stałymi adresami (bez sid)
STATIC_SOURCES = {
    "PomnikiHistorii": f"{DOWNLOAD_BASE}/PomnikiHistorii/PomnikiHistorii.zip",
    "UNESCO": f"{DOWNLOAD_BASE}/UNESCO/UNESCO.zip",
}

TARGET_CRS = "EPSG:2180"

USER_AGENT = "nid2geoformats (+https://github.com/gelaner/nid2geoformats)"


def load_dotenv_if_present() -> None:
    """Wczytuje plik .env (jeśli istnieje) do zmiennych środowiskowych, nie nadpisując istniejących."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # python-dotenv jest opcjonalny przy użyciu jako biblioteka
        return
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def get_session_id(cli_value: str | None = None) -> str | None:
    """Zwraca sid: z argumentu CLI, a w drugiej kolejności ze zmiennej NID_SID (także z .env)."""
    return cli_value or os.environ.get("NID_SID") or None
