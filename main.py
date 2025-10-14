# main.py
import argparse  # importowanie modułów zewnętrznych i standardowych
from nid2geoformats.initializer import test_wms_availability, initialize_archives_list
from nid2geoformats.fetcher import fetch_archives
from nid2geoformats.converter import convert_data
from nid2geoformats.importer import to_postgis
from pathlib import Path
import dotenv


# Stała: identyfikator sesji WMS (należy uaktualniać w razie zmian po stronie NID)
SESSION_ID = "7c9f8364-f23c-46d4-b5e4-a02e4fc1bf4f"



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

    # Komenda 'postgis' - konwertowanie pobranych archiwów ZIP do tabeli PostGIS
    parser_postgis = subparsers.add_parser("postgis", help="Konwertuje dane do tabeli PostGIS.")  # definicja nowej komendy CLI
    parser_postgis.add_argument("--indir", default="data/raw", help="Katalog z pobranymi plikami ZIP.")  # dodanie opcji/argumentu do komendy
    parser_postgis.add_argument("--host", help="Adres hosta bazy danych PostGIS.")  # dodanie opcji/argumentu do komendy
    parser_postgis.add_argument("--port", help="Port bazy danych PostGIS.")  # dodanie opcji/argumentu do komendy
    parser_postgis.add_argument("--user", help="Użytkownik bazy danych PostGIS.")  # dodanie opcji/argumentu do komendy
    parser_postgis.add_argument("--password", help="Hasło do bazy danych PostGIS.")  # dodanie opcji/argumentu do komendy
    parser_postgis.add_argument("--database", help="Nazwa bazy danych PostGIS.")  # dodanie opcji/argumentu do komendy
    parser_postgis.add_argument("--schema", help="Nazwa schematu bazy danych PostGIS.")  # dodanie opcji/argumentu do komendy

    args = parser.parse_args()
    
    
    # Przetwarzanie argumentów na ściezki
    indir = Path(args.indir) if hasattr(args, 'indir') and args.indir else None
    outdir = Path(args.outdir) if hasattr(args, 'outdir') and args.outdir else None
    input_file = Path(args.input) if hasattr(args, 'input') and args.input else None
    output_file = Path(args.output) if hasattr(args, 'output') and args.output else None

    # Ustawienia bazy PostGIS z pliku .env, jeśli nie podano w argumentach
    pg_host = args.host if hasattr(args, 'host') and args.host else dotenv.get_key(dotenv.find_dotenv(), "PGHOST")
    pg_port = args.port if hasattr(args, 'port') and args.port else dotenv.get_key(dotenv.find_dotenv(), "PGPORT")
    pg_user = args.user if hasattr(args, 'user') and args.user else dotenv.get_key(dotenv.find_dotenv(), "PGUSER")
    pg_password = args.password if hasattr(args, 'password') and args.password else dotenv.get_key(dotenv.find_dotenv(), "PGPASSWORD")
    pg_database = args.database if hasattr(args, 'database') and args.database else dotenv.get_key(dotenv.find_dotenv(), "PGDATABASE")
    pg_schema = args.schema if hasattr(args, 'schema') and args.schema else dotenv.get_key(dotenv.find_dotenv(), "PGSCHEMA")
                                                                                 
    if args.command == "wms-test":
        test_wms_availability(args.session)
    elif args.command == "fetch":
        fetch_archives(input_file, outdir)
    elif args.command == "convert":
        convert_data(indir, outdir, args.format)
    elif args.command == "postgis":
        to_postgis(indir, pg_host, pg_port, pg_user, pg_password, pg_database, pg_schema)
    elif args.command == "init":
        initialize_archives_list(args.session, input_file, output_file)
    else:
        parser.print_help()

if __name__ == "__main__":  # punkt wejścia do aplikacji CLI
    main()