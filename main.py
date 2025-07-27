# main.py
import argparse  # importowanie modułów zewnętrznych i standardowych
from nid2geoformats.initializer import test_wms_availability, initialize_archives_list
from nid2geoformats.fetcher import fetch_archives
from nid2geoformats.converter import convert_data


# Stała: identyfikator sesji WMS (należy uaktualniać w razie zmian po stronie NID)
SESSION_ID = "85dcc7d0-3458-4b78-a1bb-ed65b5513ee6"


def main():
    parser = argparse.ArgumentParser(description="Narzędzie do pobierania i przetwarzania danych z NID.")  # tworzenie parsera argumentów CLI
    subparsers = parser.add_subparsers(dest="command", help="Dostępne komendy")  # dodanie podkomend (subparserów) do CLI

    # Komenda 'wms-test' - testowanie dostępności WMS i ważności session_id
    parser_test = subparsers.add_parser("wms-test", help="Testuje połączenie z usługą WMS NID.")  # definicja nowej komendy CLI
    parser_test.add_argument("--session", default=SESSION_ID, help="Aktualny identyfkator sesji.")  # dodanie opcji/argumentu do komendy

    # Komenda 'fetch' - Pobieranie archiwów ZIP z serwera NID
    parser_fetch = subparsers.add_parser("fetch", help="Pobiera archiwa ZIP.")  # definicja nowej komendy CLI
    parser_fetch.add_argument("--input", default="archiwa_do_pobrania.tsv", help="Plik z listą archiwów.")  # dodanie opcji/argumentu do komendy
    parser_fetch.add_argument("--outdir", default="data/raw", help="Katalog do zapisu plików.")  # dodanie opcji/argumentu do komendy

    # Komenda 'convert' - konwertowanie pobranych archiwów ZIP do wybranego formatu
    parser_convert = subparsers.add_parser("convert", help="Konwertuje dane do formatu przestrzennego.")  # definicja nowej komendy CLI
    parser_convert.add_argument("--indir", default="data/raw", help="Katalog z pobranymi plikami ZIP.")  # dodanie opcji/argumentu do komendy
    parser_convert.add_argument("--outdir", default="data/processed", help="Katalog na przetworzone pliki.")  # dodanie opcji/argumentu do komendy
    parser_convert.add_argument("--format", choices=['gpkg', 'parquet'], default='parquet', help="Format wyjściowy.")  # dodanie opcji/argumentu do komendy

    # Komenda 'init' - aktualizacja listy archiwów do pobrania
    parser_init = subparsers.add_parser("init", help="Inicjalizuje listę archiwów do pobrania.")  # definicja nowej komendy CLI
    parser_init.add_argument("--session", default=SESSION_ID, help="Aktualny identyfkator sesji.")  # dodanie opcji/argumentu do komendy
    parser_init.add_argument("--input", default="jednostki_do_pobrania.tsv", help="Plik wejściowy z jednostkami.")  # dodanie opcji/argumentu do komendy
    parser_init.add_argument("--output", default="archiwa_do_pobrania_nowe.tsv", help="Plik wyjściowy z linkami.")  # dodanie opcji/argumentu do komendy

    args = parser.parse_args()

    if args.command == "wms-test":
        test_wms_availability(args.session)
    elif args.command == "fetch":
        fetch_archives(args.input, args.outdir)
    elif args.command == "convert":
        convert_data(args.indir, args.outdir, args.format)
    elif args.command == "init":
        initialize_archives_list(args.session, args.input, args.output)
    else:
        parser.print_help()

if __name__ == "__main__":  # punkt wejścia do aplikacji CLI
    main()