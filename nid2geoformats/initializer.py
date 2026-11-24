# nid2geoformats/initializer.py
"""Budowanie listy archiwów ZIP do pobrania.

Dwa tryby:
- offline (domyślny bez sid): linki budowane z kodów TERYT według schematu NID
  (województwa: /dane/<REJ>/WOJ/<REJ>_<TERYT2>.zip, gminy: /dane/<REJ>/<TERYT7>.zip),
  opcjonalnie weryfikowane zapytaniem HEAD;
- WMS (gdy podano sid): linki odczytywane z GetFeatureInfo warstwy Wojewodztwa/Gminy w punktach jednostek.
"""
from __future__ import annotations

import csv
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from tqdm import tqdm

from .config import DEFAULT_LEVEL, DOWNLOAD_BASE, LEVELS, REGISTERS, WMS_HALF_SIZE, WMS_LAYERS
from .http import DEFAULT_TIMEOUT, make_session
from .wms import SessionExpiredError, find_update_date, find_zip_links, get_feature_info

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = ["poziom", "JPT_KOD_JE", "JPT_NAZWA", "typ_rejestru", "link_do_pobrania", "data_aktualizacji"]


def read_units(path: Path | str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def teryt7(jpt_kod_je: str) -> str:
    """'020101_1' -> '0201011' (kod gminy TERYT z rodzajem gminy).

    Dzielnice Warszawy (_8) i delegatury/dzielnice miast (_9) NID publikuje jako całe miasto,
    np. '146502_8' -> '1465011', '106102_9' -> '1061011'.
    """
    base, _, kind = jpt_kod_je.partition("_")
    if kind in ("8", "9"):
        return f"{base[:4]}011"
    return base + kind


def build_link(level: str, code: str, register: str) -> str:
    if level == "wojewodztwa":
        return f"{DOWNLOAD_BASE}/{register}/WOJ/{register}_{code[:2]}.zip"
    return f"{DOWNLOAD_BASE}/{register}/{teryt7(code)}.zip"


def _write(results: list[list[str]], output_path: Path | str) -> None:
    results.sort(key=lambda r: (r[1], r[3]))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(OUTPUT_COLUMNS)
        writer.writerows(results)


def _parallel(items, fn, workers: int, desc: str):
    """Uruchamia fn(item) równolegle; zwraca listę (item, wynik | wyjątek). SessionExpiredError przerywa."""
    out = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn, it): it for it in items}
        for future in tqdm(as_completed(futures), total=len(futures), desc=desc):
            try:
                out.append((futures[future], future.result()))
            except SessionExpiredError:
                for f in futures:
                    f.cancel()
                raise
            except Exception as e:  # noqa: BLE001 - błąd pojedynczej pozycji nie przerywa całości
                out.append((futures[future], e))
    return out


def initialize_offline(
    input_path: Path | str,
    output_path: Path | str,
    level: str = DEFAULT_LEVEL,
    verify: bool = True,
    workers: int = 8,
    session: requests.Session | None = None,
) -> list[list[str]]:
    """Buduje linki z kodów TERYT; przy verify=True sprawdza ich dostępność (HEAD) i pomija niedostępne."""
    if level not in LEVELS:
        raise ValueError(f"Nieznany poziom: {level} (dostępne: {', '.join(LEVELS)})")
    units = read_units(input_path)
    candidates = [
        [level, u["JPT_KOD_JE"], u.get("JPT_NAZWA", ""), reg, build_link(level, u["JPT_KOD_JE"], reg), ""]
        for u in units for reg in REGISTERS
    ]
    if not verify:
        results = candidates
    else:
        session = session or make_session(pool_size=workers * 2)

        def head(row):
            r = session.head(row[4], timeout=DEFAULT_TIMEOUT, allow_redirects=True)
            return r.status_code, r.headers.get("Last-Modified", "")

        results, missing = [], []
        for row, res in _parallel(candidates, head, workers, f"Weryfikacja linków ({level})"):
            if isinstance(res, Exception) or res[0] != 200:
                missing.append(f"{row[1]}/{row[3]}")
                continue
            results.append([*row[:5], res[1]])
        if missing:
            log.warning("Niedostępne archiwa (%d): %s", len(missing), ", ".join(sorted(missing)[:20]))
    _write(results, output_path)
    log.info("Zapisano %d linków dla %d jednostek do %s", len(results), len(units), output_path)
    return results


def initialize_archives_list(
    session_id: str,
    input_path: Path | str,
    output_path: Path | str,
    level: str = DEFAULT_LEVEL,
    layer: str | None = None,
    workers: int = 4,
    raw_dir: Path | str | None = None,
    session: requests.Session | None = None,
) -> list[list[str]]:
    """Dla każdego punktu jednostki odpytuje GetFeatureInfo i zapisuje linki do ZIP-ów (TSV).

    raw_dir - opcjonalny katalog na surowe odpowiedzi WMS (diagnostyka).
    """
    if level not in LEVELS:
        raise ValueError(f"Nieznany poziom: {level} (dostępne: {', '.join(LEVELS)})")
    layer = layer or WMS_LAYERS[level]
    session = session or make_session()
    units = read_units(input_path)
    if raw_dir:
        raw_dir = Path(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)

    def query(unit: dict) -> str:
        text = get_feature_info(session, session_id, layer, float(unit["XCoord"]), float(unit["YCoord"]),
                                half_size=WMS_HALF_SIZE[level])
        if raw_dir:
            (raw_dir / f"{level}_{unit['JPT_KOD_JE']}.xml").write_text(text, encoding="utf-8")
        return text

    results: list[list[str]] = []
    missing: list[str] = []
    errors: list[str] = []
    for unit, res in _parallel(units, query, workers, f"Jednostki ({level})"):
        code = unit["JPT_KOD_JE"]
        if isinstance(res, Exception):
            errors.append(code)
            log.warning("Błąd przy %s: %s", code, res)
            continue
        links = find_zip_links(res)
        if not links:
            missing.append(code)
        date = find_update_date(res) or ""
        for register, url in links:
            results.append([level, code, unit.get("JPT_NAZWA", ""), register, url, date])

    _write(results, output_path)
    log.info("Zapisano %d linków dla %d jednostek do %s", len(results), len(units), output_path)
    if missing:
        log.warning("Brak linków dla %d jednostek: %s", len(missing), ", ".join(sorted(missing)[:20]))
    if errors:
        log.warning("Błędy zapytań dla %d jednostek: %s", len(errors), ", ".join(sorted(errors)[:20]))
    return results
