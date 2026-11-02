"""
etl/00_starte_gesamtlauf.py

Zweck      : Startet die ganze Ladestrecke mit einem Befehl in der festen Reihenfolge (E-36):
               1. etl/01_lade_staging.py          data/raw -> stg.*
               2. etl/02_lade_dim_datum.py        dwh.dim_datum (UPSERT)
               3. Fakten bewusst leeren            dwh.fact_verkauf (mit Protokolleintrag, E-33)
               4. etl/04_lade_dimensionen.py      dwh.dim_produkt, dwh.dim_kunde (SCD 2)
               5. etl/05_lade_fakten.py           dwh.fact_verkauf + protokoll.abgewiesene_position + Gesamttest
                                                  (E-35, E-42), danach data/rejected/*.csv
               6. sql/04_gesamttest.sql           unabhängige SQL-Prüfung (nur lesen)
               7. sql/05b_kontrolle_mart.sql      Kontrolle der mart-Views F-01 bis F-08 (nur lesen, E-39, E-40)
             Das Anlegen der Views (sql/05_create_mart.sql) ist kein Schritt: es ändert sich nicht.
             Die Migrationen sql/02c, sql/02d gehören nicht dazu (einmalig ausgeführt).
Eingabe    : data/raw/* (nur lesen, R-02), db_config.ini
Ausgabe    : alle Tabellen in stg und dwh, Protokolle in logs/, Konsolenbericht
Anforderung: Q-05 reproduzierbar mit einem Befehl, Q-01 bis Q-03 über die Schritte 5 und 6
Bezug      : E-17, E-22, E-33, E-34, E-35, E-36, E-39
Aufruf     : .venv\\Scripts\\python.exe etl\\00_starte_gesamtlauf.py
             Erwartet: 7 Schritte "OK", am Ende "Gesamtlauf erfolgreich", Exit 0.
             Beim ersten Abbruch: Meldung mit dem Namen des Schritts, Exit 1, die
             folgenden Schritte laufen NICHT.
           : .venv\\Scripts\\python.exe etl\\00_starte_gesamtlauf.py --abbruch-test
             Beweis, dass der Gesamtlauf beim ersten Abbruch stoppt: Schritt 5 bekommt
             --abbruch-test (absichtlicher Fehler, ROLLBACK, Exit 1).
             Erwartet: Abbruch in Schritt 5, Schritte 6 und 7 laufen nicht, Exit 1.
             Nebenwirkung (E-36): fact_verkauf ist danach leer (Schritt 3 hat geleert).
             Ein normaler Gesamtlauf stellt den Stand wieder her.
Einschränkung (E-36): Jeder Schritt hat seine eigene Transaktion. Bricht Schritt 4 oder 5 ab,
             bleibt fact_verkauf leer, bis der nächste Gesamtlauf erfolgreich ist.
"""
import argparse
import csv
import importlib
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
bereinigung = importlib.import_module("etl.03_bereinige_quellen")   # verbindung_aufbauen()

PROTOKOLL_DATEI = PROJEKT / "logs" / "ladeprotokoll_dwh.csv"
SQL_GESAMTTEST = PROJEKT / "sql" / "04_gesamttest.sql"
SQL_KONTROLLE_MART = PROJEKT / "sql" / "05b_kontrolle_mart.sql"


class SchrittFehler(Exception):
    """Ein Schritt ist fehlgeschlagen. Der Gesamtlauf stoppt hier."""


def python_schritt(skript, *argumente):
    """Startet ein Python-Skript mit DEMSELBEN Interpreter (.venv) als eigenen Prozess.

    Warum eigener Prozess: Die Skripte 01 und 02 laufen beim Start sofort los (kein main()).
    So läuft jedes Skript genau wie von Hand gestartet, und sein Exit-Code entscheidet.
    """
    def ausfuehren():
        # PYTHONIOENCODING: Umlaute in der Ausgabe auch in einer Windows-Konsole
        umgebung = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        ergebnis = subprocess.run([sys.executable, str(PROJEKT / skript), *argumente], cwd=PROJEKT, env=umgebung)
        if ergebnis.returncode != 0:
            raise SchrittFehler(f"{skript} endete mit Exit-Code {ergebnis.returncode}")
    return ausfuehren


def fakten_leeren():
    """Leert dwh.fact_verkauf bewusst, damit Schritt 4 die Dimensionen neu laden darf (E-33).

    Kein stilles Löschen: Die Zahl der Zeilen und der Grund stehen in logs/ladeprotokoll_dwh.csv.
    Schritt 5 lädt die Fakten direkt danach wieder.
    """
    engine = bereinigung.verbindung_aufbauen()
    with engine.begin() as conn:
        vorher = conn.execute(text("SELECT COUNT(*) FROM dwh.fact_verkauf")).scalar()
        conn.execute(text("TRUNCATE dwh.fact_verkauf"))
    PROTOKOLL_DATEI.parent.mkdir(exist_ok=True)
    neu = not PROTOKOLL_DATEI.exists()
    with open(PROTOKOLL_DATEI, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if neu:
            schreiber.writerow(["zeitpunkt", "tabelle", "quelle", "soll", "ist_db", "vorher",
                                "eingefuegt", "geaendert", "geloescht", "ergebnis", "hinweise"])
        schreiber.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "dwh.fact_verkauf",
                            "etl/00_starte_gesamtlauf.py", 0, 0, vorher, 0, 0, vorher, "OK",
                            "bewusst geleert vor dem Neuladen der Dimensionen (E-33, E-36); Schritt 5 lädt neu"])
    print(f"fact_verkauf geleert: {vorher} Zeilen (protokolliert)")


def sql_kontrolle(pfad):
    """Gibt einen Schritt zurück, der eine Kontroll-SQL (eine SELECT-Abfrage) ausführt und auswertet.

    Format wie sql/04_gesamttest.sql und sql/05b_kontrolle_mart.sql: Spalten nr, pruefung, soll, ist,
    ergebnis, reaktion, rolle.
    Erwartet: alle Zeilen 'OK'. Eine Regel (reaktion 'Abbruch') mit 'FEHLER' -> SchrittFehler.
    Ein Stand-Wert (reaktion 'Warnung') mit 'FEHLER' -> nur Meldung, der Lauf gilt als erfolgreich.
    """
    return lambda: _sql_kontrolle_ausfuehren(pfad)


def _sql_kontrolle_ausfuehren(pfad):
    engine = bereinigung.verbindung_aufbauen()
    with engine.connect() as conn:
        zeilen = conn.execute(text(pfad.read_text(encoding="utf-8"))).mappings().all()
    fehler = [z for z in zeilen if z["ergebnis"] != "OK" and z["reaktion"] == "Abbruch"]
    warnungen = [z for z in zeilen if z["ergebnis"] != "OK" and z["reaktion"] == "Warnung"]
    for z in fehler + warnungen:
        print(f"  [{z['reaktion']}] {z['nr']} {z['pruefung']}: Soll {z['soll']} Ist {z['ist']} -> {z['rolle']}")
    print(f"{pfad.name}: {len(zeilen) - len(fehler) - len(warnungen)} von {len(zeilen)} OK, "
          f"{len(fehler)} Abbruch, {len(warnungen)} Warnung")
    if fehler:
        raise SchrittFehler(f"{len(fehler)} Regel(n) verletzt: {[z['nr'] for z in fehler]}")


def schritte(abbruch_test=False):
    """Die Schritte in fester Reihenfolge (E-36). abbruch_test reicht --abbruch-test an Schritt 5 weiter."""
    option_5 = ["--abbruch-test"] if abbruch_test else []
    return [
        ("1 Staging laden",                python_schritt("etl/01_lade_staging.py")),
        ("2 dim_datum laden",              python_schritt("etl/02_lade_dim_datum.py")),
        ("3 Fakten bewusst leeren",        fakten_leeren),
        ("4 Dimensionen laden",            python_schritt("etl/04_lade_dimensionen.py")),
        ("5 Fakten laden + Gesamttest",    python_schritt("etl/05_lade_fakten.py", *option_5)),
        ("6 SQL-Gesamttest",               sql_kontrolle(SQL_GESAMTTEST)),
        ("7 Kontrolle mart-Views",         sql_kontrolle(SQL_KONTROLLE_MART)),
    ]


def main():
    # Warum line_buffering: Wird die Ausgabe in eine Datei umgeleitet, puffert Python sonst die eigenen
    # Zeilen, und die Ausgaben der Unterprozesse erscheinen in falscher Reihenfolge.
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description="Gesamtlauf der Ladestrecke (E-36)")
    parser.add_argument("--abbruch-test", action="store_true",
                        help="Beweis: Schritt 5 bricht absichtlich ab, der Gesamtlauf muss dort stoppen")
    args = parser.parse_args()
    schritt_liste = schritte(args.abbruch_test)
    print("#" * 78)
    print("Gesamtlauf DWH Süd-Mineralöl" + (" (ABBRUCH-TEST)" if args.abbruch_test else ""))
    print("#" * 78)
    start = time.time()
    for name, schritt in schritt_liste:
        print(f"\n>>> Schritt {name}")
        try:
            schritt()
        except Exception as fehler:          # jeder Fehler stoppt den Lauf, mit Namen des Schritts
            print(f"\n!!! ABBRUCH in Schritt {name}: {fehler}")
            print("!!! Die folgenden Schritte wurden NICHT ausgeführt.")
            sys.exit(1)
        print(f"<<< Schritt {name}: OK")
    print("\n" + "#" * 78)
    print(f"Gesamtlauf erfolgreich: {len(schritt_liste)} von {len(schritt_liste)} Schritten OK "
          f"({time.time() - start:.0f} s)")
    print("#" * 78)


if __name__ == "__main__":
    main()
