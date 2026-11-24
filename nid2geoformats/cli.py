# nid2geoformats/cli.py
"""Interfejs wiersza poleceń."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import DEFAULT_LEVEL, LEVELS, STATIC_SOURCES, UNITS_FILES, get_session_id, load_dotenv_if_present
from .writers import FORMATS, PostgisParams


def _add_pg_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("PostGIS (domyślnie ze zmiennych PGHOST, PGPORT, PGUSER, PGPASSWORD, "
                             "PGDATABASE, PGSCHEMA lub pliku .env)")
    g.add_argument("--host")
    g.add_argument("--port", type=int)
    g.add_argument("--user")
    g.add_argument("--password", help="Niezalecane (zostaje w historii powłoki) - użyj PGPASSWORD/.env.")
    g.add_argument("--database")
    g.add_argument("--schema")
    g.add_argument("--if-exists", choices=["replace", "append", "fail"], default="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nid2geoformats",
                                     description="Narzędzie do pobierania i przetwarzania danych z NID.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Więcej komunikatów.")
    sub = parser.add_subparsers(dest="command", help="Dostępne komendy")

    p = sub.add_parser("wms-test", help="Testuje połączenie z usługą WMS NID i ważność sid.")
    p.add_argument("--session", help="Identyfikator sesji (domyślnie zmienna NID_SID).")

    p = sub.add_parser("init", help="Tworzy listę archiwów ZIP do pobrania.",
                       description="Bez sid linki są budowane z kodów TERYT i weryfikowane (HEAD). "
                                   "Z sid (--session lub NID_SID) linki są odczytywane z usługi WMS.")
    p.add_argument("--session", help="Identyfikator sesji WMS (domyślnie zmienna NID_SID).")
    p.add_argument("--offline", action="store_true", help="Wymuś tryb bez WMS, nawet gdy ustawiono NID_SID.")
    p.add_argument("--no-verify", action="store_true", help="Tryb offline: nie sprawdzaj dostępności linków.")
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL, help="Poziom agregacji danych.")
    p.add_argument("--input", type=Path, help="Plik TSV z punktami jednostek (domyślnie wg poziomu).")
    p.add_argument("--output", type=Path, help="Plik wyjściowy (domyślnie archiwa_<poziom>.tsv).")
    p.add_argument("--layer", help="Nazwa warstwy WMS (domyślnie wg poziomu).")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--raw-dir", type=Path, help="Katalog na surowe odpowiedzi WMS (diagnostyka).")

    p = sub.add_parser("units", help="Aktualizuje listę gmin (jednostek ewidencyjnych) z PRG GUGiK.")
    p.add_argument("--output", type=Path, default=Path(UNITS_FILES["gminy"]))
    p.add_argument("--cache-dir", type=Path, default=Path("data/prg"))
    p.add_argument("--refresh", action="store_true", help="Pobierz ponownie granice z PRG.")

    p = sub.add_parser("fetch", help="Pobiera archiwa ZIP.")
    p.add_argument("--input", type=Path, default=Path(f"archiwa_{DEFAULT_LEVEL}.tsv"), help="Plik z listą archiwów.")
    p.add_argument("--outdir", type=Path, default=Path("data/raw"), help="Katalog do zapisu plików.")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--force", action="store_true", help="Pobierz ponownie istniejące pliki.")
    p.add_argument("--static", action="store_true",
                   help=f"Pobierz także zbiory krajowe ({', '.join(STATIC_SOURCES)}).")
    p.add_argument("--static-only", action="store_true", help="Pobierz wyłącznie zbiory krajowe.")

    p = sub.add_parser("convert", help="Konwertuje pobrane dane do GeoParquet, GeoPackage lub PostGIS.")
    p.add_argument("--indir", type=Path, default=Path("data/raw"), help="Katalog z pobranymi plikami ZIP.")
    p.add_argument("--outdir", type=Path, default=Path("data/processed"), help="Katalog na przetworzone pliki.")
    p.add_argument("--format", choices=FORMATS, default="parquet", help="Format wyjściowy.")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-dedupe", action="store_true", help="Nie usuwaj obiektów powtórzonych w paczkach.")
    p.add_argument("--make-valid", action="store_true", help="Napraw niepoprawne geometrie (make_valid).")
    _add_pg_args(p)
    return parser


def _require_sid(value: str | None) -> str:
    sid = get_session_id(value)
    if not sid:
        from .wms import SessionExpiredError
        sys.exit("Brak identyfikatora sesji. " + str(SessionExpiredError()).split("\n", 1)[1])
    return sid


def main(argv: list[str] | None = None) -> int:
    load_dotenv_if_present()
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("numexpr", "urllib3", "pyogrio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.command == "wms-test":
        from .http import make_session
        from .wms import test_wms_availability
        return 0 if test_wms_availability(make_session(), _require_sid(args.session)) else 1

    if args.command == "init":
        from .initializer import initialize_archives_list, initialize_offline
        from .wms import SessionExpiredError
        units = args.input or Path(UNITS_FILES[args.level])
        output = args.output or Path(f"archiwa_{args.level}.tsv")
        sid = None if args.offline else get_session_id(args.session)
        try:
            if sid:
                initialize_archives_list(sid, units, output, level=args.level, layer=args.layer,
                                         workers=args.workers, raw_dir=args.raw_dir)
            else:
                initialize_offline(units, output, level=args.level, verify=not args.no_verify,
                                   workers=max(args.workers, 8))
        except SessionExpiredError as e:
            logging.error(str(e))
            return 2
        return 0

    if args.command == "units":
        from .units import update_units
        update_units(args.output, args.cache_dir, args.refresh)
        return 0

    if args.command == "fetch":
        from .fetcher import fetch_archives, fetch_static
        failed = 0
        if not args.static_only:
            failed += len(fetch_archives(args.input, args.outdir, args.workers, args.force).failed)
        if args.static or args.static_only:
            failed += len(fetch_static(args.outdir, force=args.force).failed)
        return 1 if failed else 0

    if args.command == "convert":
        from .converter import convert_data
        writer = None
        if args.format == "postgis":
            from .writers import PostgisWriter
            pg = PostgisParams.from_env(host=args.host, port=args.port, user=args.user, password=args.password,
                                        database=args.database, schema=args.schema)
            writer = PostgisWriter(pg, if_exists=args.if_exists)
        convert_data(args.indir, args.outdir, args.format, workers=args.workers, dedupe=not args.no_dedupe,
                     writer=writer, make_valid=args.make_valid)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
