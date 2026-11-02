"""
main.py

Zweck      : Ein Befehl macht alles (E-44):
               1. Datenbankobjekte anlegen, falls sie fehlen (idempotent, nichts löschen)
               2. Gesamtlauf etl/00_starte_gesamtlauf.py (einlesen -> prüfen -> laden -> Kontrollen)
               3. Nachlauf-Migration sql/02d (nur auf einer neuen Datenbank, braucht geladene Daten)
               4. Diagramme D1-D3 (etl/06_erstelle_diagramme.py)
               5. Protokoll: Schritte mit Laufzeit, Zeilenzahlen und md5 je Tabelle, md5 der Diagramme
Eingabe    : data/raw/* (nur lesen, R-02), db_config.ini (oder Datei aus DWH_DB_CONFIG), sql/*.sql
Ausgabe    : alle Tabellen in stg, dwh, protokoll; Views in mart; docs/diagramme/*.png;
             logs/hauptlauf.csv (eine Zeile pro Schritt und Lauf, mit Laufzeit, wird ergänzt)
             logs/hauptlauf_tabellen.csv (eine Zeile pro Tabelle und Lauf: Zeilen, md5, wird ergänzt)
Anforderung: ein Lauf macht alles, Wiederholung ändert nichts (Idempotenz, Q-05)
Bezug      : E-17, E-33, E-36, E-39, E-40, E-41, E-42, E-43, E-44, E-49, E-50
Aufruf     : .venv\\Scripts\\python.exe main.py
             Erwartet: alle Schritte OK, am Ende "Hauptlauf erfolgreich", Exit 0.
             Beim ersten Fehler: Meldung mit dem Schritt, Exit 1, die folgenden Schritte laufen NICHT.
           : .venv\\Scripts\\python.exe main.py --abbruch-test
             Reicht --abbruch-test an den Gesamtlauf weiter (Schritt 5 bricht absichtlich ab, ROLLBACK).
             Erwartet: Abbruch im Schritt "Gesamtlauf", keine Diagramme, Exit 1.
             Danach stellt ein normaler Lauf den Stand wieder her (E-36).
Voraussetzung: Die Datenbank (z. B. dwh_sued) existiert und db_config.ini ist ausgefüllt
             (sql/00_verbindung_test.sql, README). Eine Datenbank anzulegen ist kein Teil des Laufs.

Anlegen der Datenbankobjekte (E-44), in dieser Reihenfolge:
  - sql/01_create_staging.sql und sql/02_create_dwh.sql enthalten DROP bzw. scheitern an vorhandenen
    Tabellen. Sie laufen NUR, wenn KEINE ihrer Tabellen existiert. Existiert nur ein Teil, bricht
    main.py ab (unklarer Stand, nichts wird gelöscht).
  - sql/02c läuft nur, wenn der CHECK 'Unbekannt' noch nicht erlaubt (Bedingung aus der Datenbank).
  - sql/07 läuft nur, wenn stg.kunden_update fehlt (07 kommentiert die alte Tabelle, die 08 entfernt, E-50).
  - sql/08, 05, 05c, 06, 06b sind wiederholbar (IF EXISTS / IF NOT EXISTS, CREATE OR REPLACE VIEW) und laufen immer.
  - sql/02d (NOT NULL) braucht geladene Produkte: läuft nach dem Gesamtlauf, nur wenn die Spalte noch NULL erlaubt.
"""
import argparse
import csv
import hashlib
import importlib
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))
bereinigung = importlib.import_module("etl.03_bereinige_quellen")   # verbindung_aufbauen() (E-44: DWH_DB_CONFIG)

SQL = PROJEKT / "sql"
LOG_SCHRITTE = PROJEKT / "logs" / "hauptlauf.csv"
LOG_TABELLEN = PROJEKT / "logs" / "hauptlauf_tabellen.csv"
DIAGRAMME = PROJEKT / "docs" / "diagramme"

# Basis-DDL: nur auf einer leeren Datenbank (siehe Kopf). Liste = Tabellen, die die Datei anlegt.
BASIS_DDL = [
    # stg.kunden_update_2026_01 legt 01 auch an, sql/08 entfernt sie wieder (E-50): nicht Teil der Prüfung.
    ("sql/01_create_staging.sql", ["stg.bestellungen", "stg.kunden", "stg.produkte"]),
    ("sql/02_create_dwh.sql", ["dwh.dim_datum", "dwh.dim_kunde", "dwh.dim_produkt", "dwh.dim_zahlung",
                               "dwh.dim_status", "dwh.fact_verkauf"]),
]
# Bedingte Migration vor dem Gesamtlauf: (Datei, SQL "muss laufen?")
SQL_02C_NOETIG = ("SELECT NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_dim_produkt_land' "
                  "AND pg_get_constraintdef(oid) LIKE '%Unbekannt%')")
# sql/07 nur, wenn stg.kunden_update fehlt: 07 kommentiert auch stg.kunden_update_2026_01, die sql/08 entfernt (E-50).
SQL_07_NOETIG = "SELECT to_regclass('stg.kunden_update') IS NULL"
# Wiederholbare Migrationen, Reihenfolge: alte Staging-Tabelle entfernen (08, nach 07), Schema mart vor den Views,
# protokoll vor 06b.
WIEDERHOLBAR = ["sql/08_entferne_stg_kunden_update_2026_01.sql", "sql/06_create_protokoll_abgewiesen.sql",
                "sql/05_create_mart.sql", "sql/05c_create_mart_f08.sql", "sql/06b_create_mart_dq.sql"]
# Nachlauf: NOT NULL nur, wenn noch nicht gesetzt (neue Datenbank)
SQL_02D_NOETIG = ("SELECT bool_or(is_nullable = 'YES') FROM information_schema.columns "
                  "WHERE table_schema = 'dwh' AND table_name = 'dim_produkt' "
                  "AND column_name IN ('lieferant', 'lieferant_land')")

# Tabellen im Protokoll. md5 nur, wo der Inhalt reproduzierbar ist (stg hat _loaded_at = Ladezeit).
TABELLEN = [
    ("stg.bestellungen", None), ("stg.kunden", None), ("stg.kunden_update", None), ("stg.produkte", None),
    ("dwh.dim_datum", "datum_sk"), ("dwh.dim_zahlung", "zahlung_sk"), ("dwh.dim_status", "status_sk"),
    ("dwh.dim_produkt", "produkt_sk"), ("dwh.dim_kunde", "kunde_sk"),
    ("dwh.fact_verkauf", "bestell_nr, position"), ("protokoll.abgewiesene_position", "_source_file, lfd_nr"),
]


class LaufFehler(Exception):
    """Ein Schritt ist fehlgeschlagen. Der Hauptlauf stoppt hier."""


# ========================================================================
# 1. Datenbank: SQL-Dateien ausführen, Bedingungen prüfen
# ========================================================================
def sql_datei_ausfuehren(engine, datei):
    """Führt eine ganze SQL-Datei aus (mit ihren eigenen BEGIN/COMMIT).

    autocommit: Die Dateien steuern ihre Transaktionen selbst. Ohne Parameter führt psycopg
    mehrere Anweisungen in einem Aufruf aus. Ein Fehler bricht ab (Exception), die offene
    Transaktion der Datei wird von PostgreSQL zurückgerollt.
    """
    roh = engine.raw_connection()
    try:
        verbindung = roh.driver_connection
        verbindung.autocommit = True
        with verbindung.cursor() as cur:
            cur.execute((PROJEKT / datei).read_text(encoding="utf-8"))
    finally:
        roh.close()


def wert(engine, sql):
    from sqlalchemy import text
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def vorhanden(engine, tabelle):
    return wert(engine, f"SELECT to_regclass('{tabelle}') IS NOT NULL")


def objekte_anlegen(engine):
    """Legt fehlende Objekte an. Gibt eine Liste (Datei, Aktion) für das Protokoll zurück."""
    aktionen = []
    for datei, tabellen in BASIS_DDL:
        da = [t for t in tabellen if vorhanden(engine, t)]
        if len(da) == len(tabellen):
            aktionen.append((datei, "vorhanden, übersprungen"))
        elif not da:
            sql_datei_ausfuehren(engine, datei)
            aktionen.append((datei, "angelegt (Datenbank war leer)"))
        else:
            fehlend = sorted(set(tabellen) - set(da))
            raise LaufFehler(f"{datei}: nur ein Teil der Tabellen existiert, fehlend {fehlend}. "
                             "Unklarer Stand: main.py löscht nichts, bitte prüfen.")
    if wert(engine, SQL_02C_NOETIG):
        sql_datei_ausfuehren(engine, "sql/02c_aendere_ck_dim_produkt_land.sql")
        aktionen.append(("sql/02c_aendere_ck_dim_produkt_land.sql", "ausgeführt (CHECK fehlte)"))
    else:
        aktionen.append(("sql/02c_aendere_ck_dim_produkt_land.sql", "vorhanden, übersprungen"))
    if wert(engine, SQL_07_NOETIG):
        sql_datei_ausfuehren(engine, "sql/07_create_stg_kunden_update.sql")
        aktionen.append(("sql/07_create_stg_kunden_update.sql", "ausgeführt (stg.kunden_update fehlte)"))
    else:
        aktionen.append(("sql/07_create_stg_kunden_update.sql", "vorhanden, übersprungen"))
    for datei in WIEDERHOLBAR:
        sql_datei_ausfuehren(engine, datei)
        aktionen.append((datei, "ausgeführt (wiederholbar)"))
    return aktionen


def nachlauf_02d(engine):
    if wert(engine, SQL_02D_NOETIG):
        sql_datei_ausfuehren(engine, "sql/02d_setze_not_null_dim_produkt_lieferant.sql")
        return "ausgeführt (NOT NULL fehlte)"
    return "vorhanden, übersprungen"


# ========================================================================
# 2. Python-Schritte als eigener Prozess (wie etl/00_starte_gesamtlauf.py)
# ========================================================================
def python_skript(skript, *argumente):
    """Startet ein Skript mit DEMSELBEN Interpreter (.venv). Exit-Code != 0 -> LaufFehler."""
    umgebung = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    ergebnis = subprocess.run([sys.executable, str(PROJEKT / skript), *argumente], cwd=PROJEKT, env=umgebung)
    if ergebnis.returncode != 0:
        raise LaufFehler(f"{skript} endete mit Exit-Code {ergebnis.returncode}")


# ========================================================================
# 3. Protokoll
# ========================================================================
def tabellenstand(engine):
    """Zeilen und md5 je Tabelle (md5 wie in etl/04 und etl/05: Zeilen als Text, feste Sortierung)."""
    stand = []
    for tabelle, sortierung in TABELLEN:
        zeilen = wert(engine, f"SELECT COUNT(*) FROM {tabelle}")
        md5 = (wert(engine, f"SELECT md5(string_agg(t::text, '|' ORDER BY {sortierung})) FROM {tabelle} t")
               if sortierung else "")
        stand.append((tabelle, zeilen, md5 or ""))
    return stand


def anhaengen(pfad, kopf, zeilen):
    pfad.parent.mkdir(exist_ok=True)
    neu = not pfad.exists()
    with open(pfad, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if neu:
            schreiber.writerow(kopf)
        schreiber.writerows(zeilen)


def zeile(zeichen="=", breite=78):
    print(zeichen * breite)


# ========================================================================
# 4. Ablauf
# ========================================================================
def main():
    sys.stdout.reconfigure(line_buffering=True)        # richtige Reihenfolge mit den Unterprozessen
    parser = argparse.ArgumentParser(description="Hauptlauf DWH Süd-Mineralöl (E-44)")
    parser.add_argument("--abbruch-test", action="store_true",
                        help="an den Gesamtlauf weiterreichen: Schritt 5 bricht absichtlich ab")
    args = parser.parse_args()
    lauf = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    art = "Abbruch-Test" if args.abbruch_test else "normal"

    zeile("#")
    print(f"Hauptlauf DWH Süd-Mineralöl ({art}) · {lauf}")
    zeile("#")
    engine = bereinigung.verbindung_aufbauen()
    # Datenbankname im Protokoll: Läufe auf einer Test-Datenbank (DWH_DB_CONFIG) sind in logs/ erkennbar.
    art = f"{art} ({engine.url.database})"
    protokoll, status, fehler_text = [], "OK", ""

    schritte = [
        ("1 Datenbankobjekte anlegen", lambda: objekte_anlegen(engine)),
        ("2 Gesamtlauf (7 Schritte)", lambda: python_skript("etl/00_starte_gesamtlauf.py",
                                                            *(["--abbruch-test"] if args.abbruch_test else []))),
        ("3 Nachlauf sql/02d", lambda: nachlauf_02d(engine)),
        ("4 Diagramme D1-D3", lambda: python_skript("etl/06_erstelle_diagramme.py")),
    ]
    for name, ausfuehren in schritte:
        print(f"\n>>> {name}")
        start = time.perf_counter()
        try:
            ergebnis = ausfuehren()
        except Exception as fehler:                       # jeder Fehler stoppt den Lauf (E-44)
            dauer = time.perf_counter() - start
            protokoll.append([lauf, art, name, "ABBRUCH", f"{dauer:.1f}", str(fehler)[:300]])
            status, fehler_text = "ABBRUCH", f"{name}: {fehler}"
            print(f"!!! ABBRUCH in {name}: {fehler}")
            break
        dauer = time.perf_counter() - start
        if name.startswith("1"):
            for datei, aktion in ergebnis:
                print(f"  {datei:<45} {aktion}")
        elif name.startswith("3"):
            print(f"  sql/02d_setze_not_null_dim_produkt_lieferant.sql {ergebnis}")
        hinweis = ergebnis if isinstance(ergebnis, str) else ""
        protokoll.append([lauf, art, name, "OK", f"{dauer:.1f}", hinweis])
        print(f"<<< {name}: OK ({dauer:.1f} s)")

    # Protokoll in jedem Fall (auch nach Abbruch): Schritte mit Laufzeit, Tabellenstand, Diagramme
    stand = tabellenstand(engine)
    gesamt = sum(float(p[4]) for p in protokoll)
    protokoll.append([lauf, art, "Summe", status, f"{gesamt:.1f}", fehler_text[:300]])
    anhaengen(LOG_SCHRITTE, ["lauf", "art", "schritt", "ergebnis", "sekunden", "hinweis"], protokoll)
    anhaengen(LOG_TABELLEN, ["lauf", "art", "tabelle", "zeilen", "md5"], [[lauf, art, *s] for s in stand])
    engine.dispose()

    print()
    zeile()
    print(f"Protokoll Hauptlauf {lauf} ({art})")
    zeile()
    for _, _, name, ergebnis, sekunden, _ in protokoll:
        print(f"  {name:<32} {ergebnis:<8} {sekunden:>6} s")
    print("\n  Tabelle                              Zeilen  md5")
    for tabelle, zeilen, md5 in stand:
        print(f"  {tabelle:<34} {zeilen:>8}  {md5}")
    if status == "OK":
        print("\n  Diagramm                                       md5")
        for png in sorted(DIAGRAMME.glob("*.png")):
            print(f"  {png.name:<45}  {hashlib.md5(png.read_bytes()).hexdigest()}")
    print(f"\n  Nachweis: {LOG_SCHRITTE.relative_to(PROJEKT).as_posix()}, "
          f"{LOG_TABELLEN.relative_to(PROJEKT).as_posix()}")
    zeile("#")
    if status != "OK":
        print(f"Hauptlauf ABGEBROCHEN: {fehler_text}")
        zeile("#")
        return 1
    print(f"Hauptlauf erfolgreich: {len(schritte)} von {len(schritte)} Schritten OK ({gesamt:.1f} s)")
    zeile("#")
    return 0


if __name__ == "__main__":
    sys.exit(main())
