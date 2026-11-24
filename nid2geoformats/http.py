# nid2geoformats/http.py
"""Wspólna sesja HTTP z ponawianiem zapytań."""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__
from .config import USER_AGENT

DEFAULT_TIMEOUT = (10, 120)  # (połączenie, odczyt) w sekundach


def make_session(retries: int = 5, pool_size: int = 8) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = f"{USER_AGENT} v{__version__}"
    return session
