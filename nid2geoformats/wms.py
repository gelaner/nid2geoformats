# nid2geoformats/wms.py
"""Komunikacja z usługą WMS NID "Dane do pobrania"."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

from .config import DOWNLOAD_BASE, SID_HELP_URL, WMS_URL
from .http import DEFAULT_TIMEOUT

log = logging.getLogger(__name__)

# Linki do archiwów ZIP w odpowiedzi GetFeatureInfo (bezwzględne lub względne)
# np. /dane/ZEN/0201011.zip (gminy) lub /dane/ZEN/WOJ/ZEN_16.zip (województwa)
ZIP_LINK_PATTERN = re.compile(
    r"(?:https?://mapy\.zabytek\.gov\.pl)?/dane/([A-Za-z0-9_]+)/((?:[A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-]+)\.zip",
    re.IGNORECASE,
)
UPDATE_DATE_PATTERN = re.compile(r'Name="Data-aktualizacji">([^<]+)<')


class SessionExpiredError(RuntimeError):
    """Identyfikator sesji (sid) jest nieważny lub wygasł."""

    def __init__(self, status: int | None = None):
        msg = (
            "Identyfikator sesji WMS (sid) jest nieważny lub wygasł"
            + (f" (HTTP {status})" if status else "")
            + ".\nOtwórz w przeglądarce portal https://mapy.zabytek.gov.pl/nid/ z włączoną warstwą"
            " 'Dane do pobrania', a następnie stronę:\n  " + SID_HELP_URL
            + "\ni skopiuj wartość parametru sid=... (podaj ją przez --session lub zmienną NID_SID)."
        )
        super().__init__(msg)


def _check(response: requests.Response) -> None:
    if response.status_code in (401, 403):
        raise SessionExpiredError(response.status_code)
    response.raise_for_status()


def get_capabilities(session: requests.Session, sid: str) -> str:
    params = {"REQUEST": "GetCapabilities", "VERSION": "1.3.0", "SERVICE": "WMS", "sid": sid}
    response = session.get(WMS_URL, params=params, timeout=DEFAULT_TIMEOUT)
    _check(response)
    return response.text


def list_layers(capabilities_xml: str) -> list[str]:
    """Zwraca nazwy (Name) wszystkich warstw z dokumentu GetCapabilities."""
    root = ET.fromstring(capabilities_xml)
    names = []
    for el in root.iter():
        if el.tag.endswith("Layer"):
            for child in el:
                if child.tag.endswith("Name") and child.text:
                    names.append(child.text.strip())
    return names


def get_feature_info(
    session: requests.Session, sid: str, layer: str, x: float, y: float, half_size: float = 50.0
) -> str:
    """GetFeatureInfo dla punktu (x=easting, y=northing) w EPSG:2180.

    W WMS 1.3.0 dla EPSG:2180 obowiązuje kolejność osi northing, easting - stąd zamiana w BBOX.
    """
    bbox = f"{y - half_size},{x - half_size},{y + half_size},{x + half_size}"
    params = {
        "sid": sid,
        "VERSION": "1.3.0",
        "SERVICE": "WMS",
        "REQUEST": "GetFeatureInfo",
        "INFO_FORMAT": "text/xml",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "FORMAT": "image/png",
        "CRS": "EPSG:2180",
        "WIDTH": 100,
        "HEIGHT": 100,
        "I": 50,
        "J": 50,
        "STYLES": "",
        "BBOX": bbox,
    }
    response = session.get(WMS_URL, params=params, timeout=DEFAULT_TIMEOUT)
    _check(response)
    # serwer zwraca UTF-8 bez deklaracji charset w nagłówku (requests przyjąłby ISO-8859-1)
    return response.content.decode("utf-8", errors="replace")


def find_update_date(text: str) -> str | None:
    """Data aktualizacji danych podana w odpowiedzi GetFeatureInfo (np. 2026-09-30 lub 30/09/2026)."""
    m = UPDATE_DATE_PATTERN.search(text)
    return m.group(1).strip() if m else None


def find_zip_links(text: str) -> list[tuple[str, str]]:
    """Wyszukuje linki do ZIP-ów; zwraca unikalne pary (typ_rejestru, pełny_url) w kolejności wystąpienia."""
    seen: dict[str, str] = {}
    for register, name in ZIP_LINK_PATTERN.findall(text):
        url = f"{DOWNLOAD_BASE}/{register}/{name}.zip"
        seen.setdefault(url, register.upper())
    return [(register, url) for url, register in seen.items()]


def test_wms_availability(session: requests.Session, sid: str) -> list[str] | None:
    """Sprawdza ważność sid; zwraca listę warstw lub None przy błędzie."""
    try:
        layers = list_layers(get_capabilities(session, sid))
    except SessionExpiredError as e:
        log.error(str(e))
        return None
    except (requests.RequestException, ET.ParseError) as e:
        log.error("Nie można połączyć się z usługą WMS: %s", e)
        return None
    log.info("Połączenie z usługą WMS powiodło się. Warstwy: %s", ", ".join(layers) or "(brak)")
    return layers
