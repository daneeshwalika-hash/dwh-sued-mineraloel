# ========================================================================
# etl/01_lade_staging.py
#
# Zweck      : Lädt die Rohdateien aus data/raw/ unverändert in die Staging-Tabellen stg.*.
# Eingabe    : data/raw/bestellungen.csv, kunden.csv, produkte.json, kunden_update_*.csv;
#              db_config.ini (oder die Datei aus DWH_DB_CONFIG, E-44)
# Ausgabe    : stg.bestellungen, stg.kunden, stg.produkte, stg.kunden_update;
#              logs/ladeprotokoll_staging.csv (wird bei jedem Lauf ergänzt)
# Anforderung:
#   - Jede Rohdatei landet 1:1 in ihrer Staging-Tabelle (alle Fachspalten TEXT).
#   - Keine Zeile geht verloren, keine Zeile kommt dazu (Soll/Ist-Vergleich).
#   - Das Skript kann mehrmals laufen, ohne doppelte Daten.
#   - Nichts wird still gelöscht: Das Leeren der Tabelle steht im Protokoll.
#   - Die Rohdateien werden nur gelesen, nie verändert (R-02).
# Bezug      : E-43, E-44
#   Datennachschub (E-43): Alle Dateien kunden_update_*.csv gehen nach stg.kunden_update,
#   in Datumsreihenfolge, Herkunft je Zeile in _source_file. Die Regel für die Dateinamen
#   steht in etl/kunden_updates.py. Nicht lesbarer Name -> Abbruch, nie still überspringen.
#   Full Load: stg.kunden_update wird bei jedem Lauf geleert und aus ALLEN Dateien neu geladen.
# Voraussetzung: sql/01_create_staging.sql und sql/07_create_stg_kunden_update.sql ausgeführt.
# Aufruf     : .venv\Scripts\python.exe etl\01_lade_staging.py   (im Projektordner)
#              Erwartet: je Datei "Ergebnis: OK", am Ende Kontrollsumme Soll gesamt = Ist gesamt.
#              Bei einer Abweichung: Abbruch (AssertionError oder RuntimeError), Exit-Code != 0.
# ========================================================================

import configparser
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ------------------------------------------------------------------------
# 1. Pfade
# ------------------------------------------------------------------------
PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
from etl import kunden_updates   # noqa: E402  Regel für Update-Dateien (E-43)

ROH_ORDNER = PROJEKT / "data" / "raw"
# DWH_DB_CONFIG (optional): andere Konfigurationsdatei, z. B. für eine Test-Datenbank (E-44).
# Ohne die Variable gilt db_config.ini im Projektordner.
CONFIG_DATEI = Path(os.environ.get("DWH_DB_CONFIG", PROJEKT / "db_config.ini"))
PROTOKOLL_DATEI = PROJEKT / "logs" / "ladeprotokoll_staging.csv"


# ------------------------------------------------------------------------
# 2. Welche Datei geht in welche Tabelle?
#    Gleiche Zuordnung wie im Kopf von sql/01_create_staging.sql
# ------------------------------------------------------------------------
QUELLEN = [
    {"datei": "bestellungen.csv",          "tabelle": "bestellungen",          "typ": "csv"},
    {"datei": "kunden.csv",                "tabelle": "kunden",                "typ": "csv"},
    {"datei": "produkte.json",             "tabelle": "produkte",              "typ": "json"},
]
# Kunden-Updates: keine feste Datei, sondern alle kunden_update_*.csv (E-43, Abschnitt 11).
TABELLE_UPDATE = "kunden_update"


# ------------------------------------------------------------------------
# 3. Verbindung zur Datenbank
# ------------------------------------------------------------------------
def verbindung_aufbauen():
    """Liest db_config.ini und gibt eine SQLAlchemy-Engine zurück.

    Die Datei kommt aus DWH_DB_CONFIG oder ist db_config.ini im Projektordner (E-44).
    Fehlt sie: Abbruch mit FileNotFoundError.
    """
    if not CONFIG_DATEI.exists():
        raise FileNotFoundError(f"{CONFIG_DATEI} fehlt. Vorlage: db_config.example.ini")

    konfig = configparser.ConfigParser()
    konfig.read(CONFIG_DATEI, encoding="utf-8")
    db = konfig["postgres"]

    # URL.create statt f-String: Sonderzeichen im Passwort (z. B. @ : /) werden richtig behandelt.
    url = URL.create(
        "postgresql+psycopg",
        username=db["user"],
        password=db["password"],
        host=db["host"],
        port=int(db["port"]),
        database=db["dbname"],
    )
    return create_engine(url)


# ------------------------------------------------------------------------
# 4. Spalten der Staging-Tabelle aus der Datenbank lesen
# ------------------------------------------------------------------------
def spalten_aus_datenbank(engine, tabelle):
    """Gibt die Fachspalten von stg.<tabelle> in der richtigen Reihenfolge zurück.

    Die Spalten kommen aus der Tabelle in PostgreSQL, nicht aus einer Liste im Code.
    Technische Spalten (_source_file, _loaded_at) fehlen in der Liste:
    Die Datenbank füllt sie selbst über DEFAULT.
    Tabelle nicht gefunden: Abbruch mit RuntimeError.
    """
    sql = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'stg'
          AND table_name   = :tabelle
        ORDER BY ordinal_position
    """)

    spalten = []
    with engine.connect() as conn:
        ergebnis = conn.execute(sql, {"tabelle": tabelle})
        for zeile in ergebnis:
            name = zeile[0]
            if not name.startswith("_"):
                spalten.append(name)

    if len(spalten) == 0:
        raise RuntimeError(
            f"Tabelle stg.{tabelle} nicht gefunden. Zuerst sql/01_create_staging.sql ausführen."
        )
    return spalten


# ------------------------------------------------------------------------
# 5. Soll-Wert: Zeilen in der Datei zählen, OHNE pandas
# ------------------------------------------------------------------------
def zeilen_in_csv_zaehlen(pfad):
    """Zählt die nicht leeren Zeilen der Datei und zieht 1 für die Kopfzeile ab.

    Ohne pandas, damit der Soll-Wert unabhängig ist: Verliert pandas eine Zeile,
    zeigt der Soll/Ist-Vergleich das.
    """
    anzahl = 0
    with open(pfad, encoding="utf-8-sig") as f:
        for zeile in f:
            if zeile.strip() != "":
                anzahl = anzahl + 1
    return anzahl - 1


# ------------------------------------------------------------------------
# 6. CSV lesen: alles als Text, nichts umwandeln
# ------------------------------------------------------------------------
def csv_lesen(pfad):
    """Liest eine CSV-Datei (Trennzeichen Semikolon) vollständig als Text.

    Text statt Zahl: 01067 bleibt 01067, 12,50 bleibt 12,50. Leere Zellen bleiben "",
    "NA" bleibt "NA" (kein NaN). utf-8-sig entfernt das BOM am Dateianfang.
    """
    df = pd.read_csv(
        pfad,
        sep=";",
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    return df


# ------------------------------------------------------------------------
# 7. JSON lesen und flach machen
# ------------------------------------------------------------------------
def json_wert_als_text(wert):
    """Ein JSON-Wert als Text, so nah wie möglich an der Datei (null -> NULL)."""
    if wert is None:
        return None
    if isinstance(wert, str):
        return wert
    # true/false und Listen wieder in JSON-Schreibweise ("true", nicht "True")
    return json.dumps(wert, ensure_ascii=False)


def json_lesen(pfad, db_spalten):
    """Liest produkte.json und macht aus jedem Artikel eine flache Zeile.

    Verschachtelt -> flach:  kategorie.haupt -> kategorie_haupt
                             lieferant.name  -> lieferant_name
    Gibt (DataFrame, Anzahl Artikel in der Datei, Liste mit Hinweisen) zurück.
    Ein Feld ohne Spalte in stg.produkte führt zum Abbruch (RuntimeError).
    """
    with open(pfad, encoding="utf-8-sig") as f:
        # Zahlen bleiben Text wie in der Datei (sonst würde aus 12.50 die Zahl 12.5)
        daten = json.load(f, parse_float=str, parse_int=str)

    artikel_liste = daten["artikel"]   # Datensätze unter $.artikel (siehe sql/01_create_staging.sql)
    hinweise = []
    unbekannte_spalten = []
    flache_zeilen = []

    for artikel in artikel_liste:
        zeile = {}
        for schluessel, wert in artikel.items():
            if isinstance(wert, dict):
                for unter_schluessel, unter_wert in wert.items():
                    neuer_name = schluessel + "_" + unter_schluessel
                    zeile[neuer_name] = json_wert_als_text(unter_wert)
            elif wert is None and schluessel not in db_spalten:
                # z. B. "lieferant": null -> lieferant_name und lieferant_land bleiben NULL.
                # Kein Datenverlust (der Wert ist leer), aber ein Hinweis im Protokoll.
                hinweise.append(f"{artikel.get('artikel_nr')}: '{schluessel}' ist null -> Unterspalten NULL")
            else:
                zeile[schluessel] = json_wert_als_text(wert)

        # Prüfung: Jeder Schlüssel hat eine Spalte in stg.produkte.
        # Sonst nicht still weglassen, sondern nach der Schleife Abbruch.
        for name in zeile:
            if name not in db_spalten and name not in unbekannte_spalten:
                unbekannte_spalten.append(name)

        flache_zeilen.append(zeile)

    if len(unbekannte_spalten) > 0:
        raise RuntimeError(f"produkte.json hat Felder ohne Spalte in stg.produkte: {unbekannte_spalten}")

    tabelle_werte = []
    for zeile in flache_zeilen:
        werte = []
        for spalte in db_spalten:
            werte.append(zeile.get(spalte))   # fehlendes Feld (z. B. kein Lieferant) -> NULL
        tabelle_werte.append(werte)

    df = pd.DataFrame(tabelle_werte, columns=db_spalten, dtype=object)
    return df, len(artikel_liste), hinweise


# ------------------------------------------------------------------------
# 8. Tabelle leeren und neu laden (in EINER Transaktion)
# ------------------------------------------------------------------------
def tabelle_neu_laden(engine, tabelle, df):
    """TRUNCATE + INSERT in einer Transaktion. Gibt die Zeilenzahl VOR dem Leeren zurück.

    Bei einem Fehler: ROLLBACK, die alten Daten bleiben erhalten.
    Der Tabellenname kommt aus der festen Liste QUELLEN, nicht von außen;
    deshalb ist der f-String hier zulässig.
    """
    with engine.begin() as conn:
        vorher = conn.execute(text(f"SELECT COUNT(*) FROM stg.{tabelle}")).scalar()
        conn.execute(text(f"TRUNCATE TABLE stg.{tabelle}"))
        # "append" schreibt in die vorhandene Tabelle. "replace" würde sie neu anlegen,
        # ohne _source_file, _loaded_at und ohne die Kommentare aus der DDL.
        df.to_sql(tabelle, conn, schema="stg", if_exists="append", index=False)
    return vorher


# ------------------------------------------------------------------------
# 9. Ist-Werte aus der Datenbank
# ------------------------------------------------------------------------
def ist_pruefen(engine, tabelle, datei):
    """Zählt die Zeilen in stg.<tabelle> und prüft die Spalte _source_file."""
    with engine.connect() as conn:
        anzahl = conn.execute(text(f"SELECT COUNT(*) FROM stg.{tabelle}")).scalar()
        # Erwartet: _source_file = Dateiname in jeder Zeile (NULL zählt als falsch)
        falsche_quelle = conn.execute(
            text(f"SELECT COUNT(*) FROM stg.{tabelle} WHERE _source_file IS DISTINCT FROM :datei"),
            {"datei": datei},
        ).scalar()
    return anzahl, falsche_quelle


# ------------------------------------------------------------------------
# 10. Ladeprotokoll schreiben (wird bei jedem Lauf ergänzt)
# ------------------------------------------------------------------------
def protokoll_schreiben(eintrag):
    PROTOKOLL_DATEI.parent.mkdir(exist_ok=True)
    datei_ist_neu = not PROTOKOLL_DATEI.exists()
    with open(PROTOKOLL_DATEI, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if datei_ist_neu:
            schreiber.writerow([
                "zeitpunkt", "datei", "tabelle", "soll_datei", "gelesen",
                "ist_db", "vorher_geloescht", "grund_loeschen", "ergebnis", "hinweise",
            ])
        schreiber.writerow(eintrag)


# ------------------------------------------------------------------------
# 11. Kunden-Updates: alle Dateien in EINER Transaktion nach stg.kunden_update (E-43)
# ------------------------------------------------------------------------
def kunden_updates_laden(engine, dateien):
    """Leert stg.kunden_update und lädt alle Update-Dateien in Datumsreihenfolge.

    dateien = Liste (Pfad, gueltig_von) aus kunden_updates.finde_update_dateien().
    Erst ALLE Dateien lesen und prüfen (Soll = gelesen, Spalten), DANN in einer Transaktion
    leeren und laden. Ein Fehler in einer Datei lädt keine Datei (alles oder nichts).
    Gibt (vorher, Liste je Datei {datei, soll, gelesen}) zurück.
    """
    db_spalten = spalten_aus_datenbank(engine, TABELLE_UPDATE)
    teile, ergebnis = [], []
    for pfad, _von in dateien:
        soll = zeilen_in_csv_zaehlen(pfad)
        df = csv_lesen(pfad)
        if list(df.columns) != db_spalten:
            raise RuntimeError(
                f"{pfad.name}: Spalten passen nicht!\n  Datei:   {list(df.columns)}\n  Tabelle: {db_spalten}")
        assert soll == len(df), f"{pfad.name}: Datei hat {soll} Zeilen, pandas hat {len(df)} gelesen"
        # Herkunft je Zeile: Die Tabelle hat für _source_file keinen DEFAULT (sql/07).
        df["_source_file"] = pfad.name
        teile.append(df)
        ergebnis.append({"datei": pfad.name, "soll": soll, "gelesen": len(df)})

    with engine.begin() as conn:
        vorher = conn.execute(text(f"SELECT COUNT(*) FROM stg.{TABELLE_UPDATE}")).scalar()
        conn.execute(text(f"TRUNCATE TABLE stg.{TABELLE_UPDATE}"))
        for df in teile:
            df.to_sql(TABELLE_UPDATE, conn, schema="stg", if_exists="append", index=False)
    return vorher, ergebnis


# ========================================================================
# Hauptprogramm
# ========================================================================
print("=" * 72)
print("Staging laden: data/raw/  ->  stg.*")
print("=" * 72)

engine = verbindung_aufbauen()
zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
summe_soll = 0
summe_ist = 0

for quelle in QUELLEN:
    datei = quelle["datei"]
    tabelle = quelle["tabelle"]
    pfad = ROH_ORDNER / datei
    print(f"\n--- {datei}  ->  stg.{tabelle}")

    if not pfad.exists():
        raise FileNotFoundError(f"Rohdatei fehlt: {pfad}")

    # Schritt 1: Spalten aus der Tabelle in der Datenbank
    db_spalten = spalten_aus_datenbank(engine, tabelle)

    # Schritt 2: Datei lesen und Soll-Wert bestimmen
    hinweise = []
    if quelle["typ"] == "csv":
        soll = zeilen_in_csv_zaehlen(pfad)
        df = csv_lesen(pfad)
        # Prüfung: Spalten der Datei = Spalten der Tabelle (Namen UND Reihenfolge), sonst Abbruch
        datei_spalten = list(df.columns)
        if datei_spalten != db_spalten:
            raise RuntimeError(
                f"Spalten passen nicht!\n  Datei:   {datei_spalten}\n  Tabelle: {db_spalten}"
            )
    else:
        df, soll, hinweise = json_lesen(pfad, db_spalten)

    gelesen = len(df)
    print(f"Soll (Datei): {soll:>5}   gelesen (pandas): {gelesen:>5}")

    # Schritt 3: Erst prüfen, DANN laden. Soll != gelesen -> Abbruch, nichts wird geladen.
    assert soll == gelesen, f"{datei}: Datei hat {soll} Zeilen, pandas hat {gelesen} gelesen"

    # Schritt 4: Laden
    vorher = tabelle_neu_laden(engine, tabelle, df)

    # Schritt 5: Ist-Werte aus der Datenbank. Erwartet: Soll = gelesen = Ist, sonst Abbruch (unten).
    ist, falsche_quelle = ist_pruefen(engine, tabelle, datei)
    print(f"Ist (DB):     {ist:>5}   vorher gelöscht (Neuladen): {vorher}")

    if soll == gelesen and gelesen == ist and falsche_quelle == 0:
        ergebnis = "OK"
    else:
        ergebnis = "FEHLER"
    print(f"Ergebnis: {ergebnis}")
    for h in hinweise:
        print(f"  Hinweis: {h}")

    # Schritt 6: Protokoll (auch das Leeren steht darin, mit Grund)
    protokoll_schreiben([
        zeitpunkt, datei, f"stg.{tabelle}", soll, gelesen, ist, vorher,
        "Neuladen aus data/raw (Staging ist nur eine Kopie)" if vorher > 0 else "",
        ergebnis, " | ".join(hinweise),
    ])

    assert ergebnis == "OK", f"{datei}: Soll {soll}, gelesen {gelesen}, Ist {ist}, falsche _source_file {falsche_quelle}"
    summe_soll = summe_soll + soll
    summe_ist = summe_ist + ist

# Kunden-Updates (E-43): Dateien suchen, Datum aus dem Namen. UpdateDateiFehler -> Abbruch.
update_dateien = kunden_updates.finde_update_dateien(ROH_ORDNER)
print(f"\n--- Kunden-Updates ({kunden_updates.SUCHMUSTER})  ->  stg.{TABELLE_UPDATE}")
for pfad, von in update_dateien:
    print(f"  {pfad.name:<32} gueltig_von {von}")
vorher_update, je_datei = kunden_updates_laden(engine, update_dateien)
with engine.connect() as conn:
    ist_gesamt = conn.execute(text(f"SELECT COUNT(*) FROM stg.{TABELLE_UPDATE}")).scalar()
    ist_je_datei = dict(conn.execute(text(
        f"SELECT _source_file, COUNT(*) FROM stg.{TABELLE_UPDATE} GROUP BY _source_file")).all())
print(f"vorher gelöscht (Neuladen): {vorher_update}")
for d in je_datei:
    ist = ist_je_datei.get(d["datei"], 0)
    ergebnis = "OK" if d["soll"] == d["gelesen"] == ist else "FEHLER"
    print(f"  {d['datei']:<32} Soll {d['soll']:>5}  gelesen {d['gelesen']:>5}  Ist (DB) {ist:>5}  {ergebnis}")
    # Das Leeren steht einmal im Protokoll (bei der ersten Datei), mit Anzahl und Grund.
    erste = d is je_datei[0]
    protokoll_schreiben([
        zeitpunkt, d["datei"], f"stg.{TABELLE_UPDATE}", d["soll"], d["gelesen"], ist,
        vorher_update if erste else 0,
        "Neuladen aller Update-Dateien aus data/raw (E-43)" if erste and vorher_update > 0 else "",
        ergebnis, f"gueltig_von {kunden_updates.gueltig_von_aus_dateiname(d['datei'])}",
    ])
    assert ergebnis == "OK", f"{d['datei']}: Soll {d['soll']}, gelesen {d['gelesen']}, Ist {ist}"
    summe_soll = summe_soll + d["soll"]
    summe_ist = summe_ist + ist
# Prüfung: keine Zeile mit fremder Herkunft (Summe je Datei = Zeilen der Tabelle), sonst Abbruch
assert sum(ist_je_datei.values()) == ist_gesamt and set(ist_je_datei) <= {d["datei"] for d in je_datei}, \
    f"stg.{TABELLE_UPDATE}: Zeilen ohne passende Datei {ist_je_datei}"

# Kontrollsumme über alle Dateien: Soll gesamt = Ist gesamt, sonst Abbruch
print("\n" + "=" * 72)
print(f"Kontrollsumme: Soll gesamt {summe_soll} = Ist gesamt {summe_ist}")
assert summe_soll == summe_ist
print("Ergebnis: alle Dateien vollständig in stg.* geladen")
print(f"Protokoll: {PROTOKOLL_DATEI}")
print("=" * 72)
