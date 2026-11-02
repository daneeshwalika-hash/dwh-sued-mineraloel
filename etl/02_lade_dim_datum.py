# ========================================================================
# etl/02_lade_dim_datum.py
#
# Zweck      : Erzeugt die Datumsdimension dwh.dim_datum und lädt sie per UPSERT.
# Eingabe    : Zeitraum START..ENDE (E-22), Feiertage aus dem Paket holidays (DE-BW),
#              db_config.ini (oder die Datei aus DWH_DB_CONFIG, E-44)
# Ausgabe    : dwh.dim_datum; logs/ladeprotokoll_dwh.csv (wird bei jedem Lauf ergänzt)
# Anforderung:
#   - Jeder Tag von 2021-01-01 bis 2027-12-31 steht genau einmal in dwh.dim_datum:
#     keine Lücke, keine Dublette (Soll 2556 Tage).
#   - Die Feiertage in Baden-Württemberg kommen aus dem Python-Paket "holidays"
#     (subdiv="BW"), also aus einer prüfbaren Quelle. Die Paketversion steht im Protokoll.
#   - Das Skript kann mehrmals laufen: kein doppelter Tag, nichts wird gelöscht
#     (UPSERT statt DELETE, E-22).
#   - Die abgeleiteten Spalten prüft die Datenbank selbst
#     (CHECK-Constraints aus sql/02_create_dwh.sql).
#   - Soll/Ist nach dem Laden: Tage, Wochenendtage, Feiertage pro Jahr.
# Bezug      : E-22, E-44
# Voraussetzung: sql/02_create_dwh.sql ausgeführt, Paket holidays installiert (requirements.txt).
# Aufruf     : .venv\Scripts\python.exe etl\02_lade_dim_datum.py   (im Projektordner)
#              Erwartet: alle Soll/Ist-Zeilen [OK], am Ende "dwh.dim_datum vollständig und geprüft".
#              Bei einer Abweichung: Protokolleintrag "FEHLER", dann Abbruch (AssertionError).
# ========================================================================

import configparser
import csv
import os
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import holidays
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ------------------------------------------------------------------------
# 1. Pfade und feste Werte
# ------------------------------------------------------------------------
PROJEKT = Path(__file__).resolve().parent.parent
# DWH_DB_CONFIG (optional): andere Konfigurationsdatei, z. B. für eine Test-Datenbank (E-44).
# Ohne die Variable gilt db_config.ini im Projektordner.
CONFIG_DATEI = Path(os.environ.get("DWH_DB_CONFIG", PROJEKT / "db_config.ini"))
PROTOKOLL_DATEI = PROJEKT / "logs" / "ladeprotokoll_dwh.csv"

# Zeitraum der Datumsdimension (E-22)
START = date(2021, 1, 1)
ENDE = date(2027, 12, 31)

# Bundesland für die Feiertage: BW = Baden-Württemberg (Sitz der Firma)
LAND = "DE"
BUNDESLAND = "BW"

# Deutsche Monatsnamen als feste Liste, nicht über die Systemsprache (locale):
# Unter Windows ist sie oft anders eingestellt, dann käme "March" statt "März" heraus.
MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


# ------------------------------------------------------------------------
# 2. Verbindung zur Datenbank (wie in etl/01_lade_staging.py)
# ------------------------------------------------------------------------
def verbindung_aufbauen():
    """Liest db_config.ini und gibt eine SQLAlchemy-Engine zurück."""
    if not CONFIG_DATEI.exists():
        raise FileNotFoundError(f"{CONFIG_DATEI} fehlt. Vorlage: db_config.example.ini")

    konfig = configparser.ConfigParser()
    konfig.read(CONFIG_DATEI, encoding="utf-8")
    db = konfig["postgres"]

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
# 3. Feiertage aus dem Paket holen
# ------------------------------------------------------------------------
def feiertage_holen():
    """Gibt ein Dictionary {Datum: Name} mit allen Feiertagen in BW zurück.

    Die Feiertage kommen aus dem Paket "holidays". Zur Kontrolle kann man die Liste
    mit einer amtlichen Quelle vergleichen (Feiertagsgesetz Baden-Württemberg).
    """
    jahre = range(START.year, ENDE.year + 1)
    feiertage = holidays.country_holidays(LAND, subdiv=BUNDESLAND, years=jahre)
    return dict(feiertage)


# ------------------------------------------------------------------------
# 4. Eine Zeile pro Tag erzeugen
# ------------------------------------------------------------------------
def tage_erzeugen(feiertage):
    """Erzeugt eine Liste mit einem Dictionary pro Tag.

    Nur einfache Python-Typen (int, bool, date): psycopg kann sie direkt an PostgreSQL
    schicken. Mit numpy-Typen (numpy.int64) gäbe es Fehler oder stille Umwandlungen.
    """
    zeilen = []
    tag = START
    while tag <= ENDE:
        iso = tag.isocalendar()
        zeilen.append({
            "datum_sk":        tag.year * 10000 + tag.month * 100 + tag.day,   # 20250317
            "datum":           tag,
            "jahr":            tag.year,
            "quartal":         (tag.month - 1) // 3 + 1,
            "monat":           tag.month,
            "monat_name":      MONATSNAMEN[tag.month - 1],
            "kalenderwoche":   iso.week,                                       # ISO-Woche 1..53
            "wochentag":       iso.weekday,                                    # 1 = Montag ... 7 = Sonntag
            "ist_wochenende":  iso.weekday >= 6,
            "ist_feiertag_bw": tag in feiertage,
        })
        tag = tag + timedelta(days=1)
    return zeilen


# ------------------------------------------------------------------------
# 5. Laden mit UPSERT (in EINER Transaktion, E-22)
# ------------------------------------------------------------------------
# Warum UPSERT und nicht "leeren und neu laden" wie im Staging?
#   - dwh.fact_verkauf verweist auf dwh.dim_datum. Leeren ginge dann nicht
#     (Fremdschlüssel) oder müsste die Fakten mitlöschen.
#   - Ein Tag ändert sich nur, wenn sich eine Feiertagsregel ändert
#     (z. B. neue Paketversion). Genau dann wird die Zeile aktualisiert.
#
# Ablauf:
#   1. Alle Tage in eine temporäre Tabelle schreiben (wird beim COMMIT gelöscht).
#   2. EIN Befehl INSERT ... ON CONFLICT:
#        neuer Tag             -> einfügen
#        Tag vorhanden, gleich -> nichts tun
#        Tag vorhanden, anders -> aktualisieren
#      rowcount = eingefügt + geändert
SQL_TEMP_TABELLE = """
    CREATE TEMP TABLE tmp_dim_datum
        (LIKE dwh.dim_datum INCLUDING DEFAULTS)
        ON COMMIT DROP
"""

SQL_TEMP_EINFUEGEN = """
    INSERT INTO tmp_dim_datum
        (datum_sk, datum, jahr, quartal, monat, monat_name,
         kalenderwoche, wochentag, ist_wochenende, ist_feiertag_bw)
    VALUES
        (:datum_sk, :datum, :jahr, :quartal, :monat, :monat_name,
         :kalenderwoche, :wochentag, :ist_wochenende, :ist_feiertag_bw)
"""

SQL_UPSERT = """
    INSERT INTO dwh.dim_datum AS d
        (datum_sk, datum, jahr, quartal, monat, monat_name,
         kalenderwoche, wochentag, ist_wochenende, ist_feiertag_bw)
    SELECT datum_sk, datum, jahr, quartal, monat, monat_name,
           kalenderwoche, wochentag, ist_wochenende, ist_feiertag_bw
    FROM tmp_dim_datum
    ON CONFLICT (datum_sk) DO UPDATE
       SET datum           = EXCLUDED.datum,
           jahr            = EXCLUDED.jahr,
           quartal         = EXCLUDED.quartal,
           monat           = EXCLUDED.monat,
           monat_name      = EXCLUDED.monat_name,
           kalenderwoche   = EXCLUDED.kalenderwoche,
           wochentag       = EXCLUDED.wochentag,
           ist_wochenende  = EXCLUDED.ist_wochenende,
           ist_feiertag_bw = EXCLUDED.ist_feiertag_bw
     -- Nur aktualisieren, wenn sich wirklich etwas geändert hat
     WHERE (d.datum, d.jahr, d.quartal, d.monat, d.monat_name,
            d.kalenderwoche, d.wochentag, d.ist_wochenende, d.ist_feiertag_bw)
           IS DISTINCT FROM
           (EXCLUDED.datum, EXCLUDED.jahr, EXCLUDED.quartal, EXCLUDED.monat, EXCLUDED.monat_name,
            EXCLUDED.kalenderwoche, EXCLUDED.wochentag, EXCLUDED.ist_wochenende, EXCLUDED.ist_feiertag_bw)
"""


def dim_datum_laden(engine, zeilen):
    """Lädt alle Tage per UPSERT. Gibt (vorher, eingefügt, geändert) zurück.

    Eine Transaktion: COMMIT am Ende, ROLLBACK bei einem Fehler.
    """
    with engine.begin() as conn:
        vorher = conn.execute(text("SELECT COUNT(*) FROM dwh.dim_datum")).scalar()
        conn.execute(text(SQL_TEMP_TABELLE))
        conn.execute(text(SQL_TEMP_EINFUEGEN), zeilen)
        betroffen = conn.execute(text(SQL_UPSERT)).rowcount
        nachher = conn.execute(text("SELECT COUNT(*) FROM dwh.dim_datum")).scalar()

    eingefuegt = nachher - vorher                      # neue Tage
    geaendert = betroffen - eingefuegt                 # vorhandene Tage mit neuem Inhalt
    return vorher, eingefuegt, geaendert


# ------------------------------------------------------------------------
# 6. Ist-Werte aus der Datenbank
# ------------------------------------------------------------------------
def ist_werte_holen(engine):
    """Zählt in dwh.dim_datum für den Zeitraum START..ENDE."""
    parameter = {"start": START, "ende": ENDE}
    with engine.connect() as conn:
        tage = conn.execute(text(
            "SELECT COUNT(*) FROM dwh.dim_datum WHERE datum BETWEEN :start AND :ende"
        ), parameter).scalar()
        # Lücken: (letzter Tag - erster Tag + 1) muss gleich der Anzahl Tage sein
        spanne = conn.execute(text(
            "SELECT MAX(datum) - MIN(datum) + 1 FROM dwh.dim_datum WHERE datum BETWEEN :start AND :ende"
        ), parameter).scalar()
        wochenende = conn.execute(text(
            "SELECT COUNT(*) FROM dwh.dim_datum WHERE ist_wochenende AND datum BETWEEN :start AND :ende"
        ), parameter).scalar()
        feiertage_pro_jahr = dict(conn.execute(text(
            "SELECT jahr, COUNT(*) FROM dwh.dim_datum "
            "WHERE ist_feiertag_bw AND datum BETWEEN :start AND :ende "
            "GROUP BY jahr ORDER BY jahr"
        ), parameter).all())
        ausserhalb = conn.execute(text(
            "SELECT COUNT(*) FROM dwh.dim_datum WHERE datum NOT BETWEEN :start AND :ende"
        ), parameter).scalar()
    return tage, spanne, wochenende, feiertage_pro_jahr, ausserhalb


# ------------------------------------------------------------------------
# 7. Ladeprotokoll (wird bei jedem Lauf ergänzt)
# ------------------------------------------------------------------------
def protokoll_schreiben(eintrag):
    PROTOKOLL_DATEI.parent.mkdir(exist_ok=True)
    datei_ist_neu = not PROTOKOLL_DATEI.exists()
    with open(PROTOKOLL_DATEI, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if datei_ist_neu:
            schreiber.writerow([
                "zeitpunkt", "tabelle", "quelle", "soll", "ist_db",
                "vorher", "eingefuegt", "geaendert", "geloescht", "ergebnis", "hinweise",
            ])
        schreiber.writerow(eintrag)


# ========================================================================
# Hauptprogramm
# ========================================================================
print("=" * 72)
print(f"Datumsdimension laden: {START} bis {ENDE}  ->  dwh.dim_datum")
print("=" * 72)

zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
quelle = f"Python-Paket holidays {holidays.__version__}, {LAND}-{BUNDESLAND}"
print(f"Feiertagsquelle: {quelle}")

# Schritt 1: Feiertage holen und zur Kontrolle anzeigen
feiertage = feiertage_holen()
soll_feiertage_pro_jahr = dict(sorted(Counter(t.year for t in feiertage).items()))
print(f"\nFeiertage pro Jahr laut Paket: {soll_feiertage_pro_jahr}")
print(f"Feiertage {ENDE.year} (zum Vergleich mit einer amtlichen Liste):")
for tag, name in sorted(feiertage.items()):
    if tag.year == ENDE.year:
        print(f"  {tag}  {MONATSNAMEN[tag.month - 1]:<10} {name}")

# Schritt 2: Tage erzeugen und VOR dem Laden prüfen.
# Erwartet: Anzahl = Soll (unabhängig berechnet) und datum_sk eindeutig, sonst Abbruch.
zeilen = tage_erzeugen(feiertage)
soll_tage = (ENDE - START).days + 1
soll_wochenende = sum(1 for z in zeilen if z["wochentag"] >= 6)
print(f"\nErzeugt: {len(zeilen)} Tage   Soll: {soll_tage}")
assert len(zeilen) == soll_tage, "Anzahl erzeugter Tage stimmt nicht"
assert len({z["datum_sk"] for z in zeilen}) == soll_tage, "datum_sk ist nicht eindeutig"

# Schritt 3: Laden
engine = verbindung_aufbauen()
vorher, eingefuegt, geaendert = dim_datum_laden(engine, zeilen)
print(f"Vorher in DB: {vorher}   eingefügt: {eingefuegt}   geändert: {geaendert}   gelöscht: 0")

# Schritt 4: Soll/Ist. Erwartet: alle Zeilen gleich, sonst Abbruch nach dem Protokoll.
ist_tage, spanne, ist_wochenende, ist_feiertage_pro_jahr, ausserhalb = ist_werte_holen(engine)
pruefungen = [
    ("Tage im Zeitraum",            soll_tage,               ist_tage),
    ("keine Lücke (Spanne)",        soll_tage,               spanne),
    ("Wochenendtage",               soll_wochenende,         ist_wochenende),
    ("Tage außerhalb des Zeitraums", 0,                      ausserhalb),
]
for jahr, anzahl in soll_feiertage_pro_jahr.items():
    pruefungen.append((f"Feiertage BW {jahr}", anzahl, ist_feiertage_pro_jahr.get(jahr, 0)))

print("\nSoll/Ist:")
alles_ok = True
for name, soll, ist in pruefungen:
    ok = soll == ist
    alles_ok = alles_ok and ok
    print(f"  [{'OK' if ok else '!!'}] {name:<30} Soll {soll:>5}   Ist {ist:>5}")

ergebnis = "OK" if alles_ok else "FEHLER"

# Schritt 5: Protokoll (auch bei einem Fehler)
protokoll_schreiben([
    zeitpunkt, "dwh.dim_datum", quelle, soll_tage, ist_tage,
    vorher, eingefuegt, geaendert, 0, ergebnis,
    f"Feiertage pro Jahr {soll_feiertage_pro_jahr}",
])

print("\n" + "=" * 72)
assert alles_ok, "Soll/Ist weicht ab, siehe Liste oben"
print("Ergebnis: dwh.dim_datum vollständig und geprüft")
print(f"Protokoll: {PROTOKOLL_DATEI}")
print("=" * 72)
