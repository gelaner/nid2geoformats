# nid2geoformats/fetcher.py
"""Pobieranie archiwów ZIP z serwera NID."""
from __future__ import annotations

import logging
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

from .config import STATIC_SOURCES
from .http import DEFAULT_TIMEOUT, make_session

log = logging.getLogger(__name__)

STATIC_LEVEL = "krajowe"


@dataclass
class FetchReport:
    downloaded: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"pobrano: {len(self.downloaded)}, pominięto (już są): {len(self.skipped)}, "
            f"błędy: {len(self.failed)}"
        )


def is_valid_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def download_file(session: requests.Session, url: str, target: Path, force: bool = False) -> bool:
    """Pobiera plik atomowo (przez plik .part). Zwraca False, jeśli poprawny plik już istniał."""
    if not force and target.exists() and is_valid_zip(target):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    with session.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as response:
        response.raise_for_status()
        with open(part, "wb") as f:
            for chunk in response.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    if not is_valid_zip(part):
        part.unlink(missing_ok=True)
        raise ValueError("pobrany plik nie jest poprawnym archiwum ZIP")
    os.replace(part, target)
    return True


def _run(jobs: list[tuple[str, Path]], workers: int, force: bool, desc: str) -> FetchReport:
    session = make_session(pool_size=max(workers, 1) * 2)
    report = FetchReport()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_file, session, url, path, force): (url, path) for url, path in jobs}
        for future in tqdm(as_completed(futures), total=len(futures), desc=desc):
            url, path = futures[future]
            try:
                (report.downloaded if future.result() else report.skipped).append(path)
            except Exception as e:  # noqa: BLE001
                report.failed.append((url, str(e)))
                log.warning("Błąd podczas pobierania %s: %s", url, e)
    log.info("Zakończono pobieranie (%s)", report.summary())
    return report


def fetch_archives(
    archive_list_path: Path | str, download_dir: Path | str, workers: int = 4, force: bool = False
) -> FetchReport:
    """Pobiera archiwa ZIP z listy (TSV z kolumnami typ_rejestru, link_do_pobrania i opcjonalnie poziom)
    do katalogu <download_dir>/<poziom>/<typ_rejestru>/<nazwa archiwum z linku>.
    """
    download_dir = Path(download_dir)
    df = pd.read_csv(archive_list_path, sep="\t", dtype=str)
    if "poziom" not in df.columns:  # listy z wersji 0.1 dotyczyły wyłącznie gmin
        df["poziom"] = "gminy"
    # nazwa pliku = nazwa archiwum z linku (np. 1601035.zip, ZEN_16.zip); ten sam link pobierany raz
    jobs = list({
        (row.link_do_pobrania,
         download_dir / row.poziom / row.typ_rejestru / row.link_do_pobrania.rsplit("/", 1)[-1])
        for row in df.itertuples(index=False)
    })
    return _run(jobs, workers, force, "Pobieranie archiwów")


def fetch_static(
    download_dir: Path | str, names: list[str] | None = None, force: bool = False
) -> FetchReport:
    """Pobiera zbiory krajowe (Pomniki Historii, UNESCO) do <download_dir>/krajowe/<nazwa>/<nazwa>.zip."""
    download_dir = Path(download_dir)
    names = names or list(STATIC_SOURCES)
    jobs = [(STATIC_SOURCES[n], download_dir / STATIC_LEVEL / n / f"{n}.zip") for n in names]
    return _run(jobs, 2, force, "Pobieranie zbiorów krajowych")
