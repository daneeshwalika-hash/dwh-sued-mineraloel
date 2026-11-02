"""
etl/04_lade_dimensionen.py

Zweck      : Lädt dwh.dim_produkt und dwh.dim_kunde (SCD Typ 2) aus den bereinigten Daten.
             Erster Schritt, der in dwh SCHREIBT. Die Bereinigung wird nicht neu programmiert,
             sondern aus etl/03_bereinige_quellen.py aufgerufen (E-24).
Eingabe    : stg.produkte, stg.kunden, stg.kunden_update (alle Update-Dateien, E-43), stg.bestellungen
             (über die Funktionen aus etl/03_bereinige_quellen.py)
Ausgabe    : dwh.dim_produkt, dwh.dim_kunde (neu geladen, E-33)
             logs/ladeprotokoll_dwh.csv (eine Zeile pro Tabelle und Lauf, wird ergänzt)
Anforderung: B2/Q-03 die Datenbank prüft (PK, UNIQUE, CHECK, Index für die aktuelle Version),
             Q-05 zweiter Lauf = gleiches Ergebnis, F-04/F-07 Adresse zum Bestellzeitpunkt
Bezug      : E-04, E-14, E-15, E-16, E-21, E-23, E-24, E-31, E-32, E-33, E-43
Aufruf     : .venv\\Scripts\\python.exe etl\\04_lade_dimensionen.py
             Erwartet: alle Soll/Ist-Zeilen [OK], "COMMIT", Exit 0.
             Bei einer Abweichung: ROLLBACK (dwh bleibt wie vorher), Protokollzeile FEHLER, Exit 1.
             Danach einmalig: sql/02d_setze_not_null_dim_produkt_lieferant.sql (E-23 Folgen).

Ablauf (eine Transaktion, E-33):
  1. fact_verkauf muss leer sein, sonst Abbruch (Fakten nie still löschen).
  2. TRUNCATE fact_verkauf, dim_kunde, dim_produkt RESTART IDENTITY in einem Befehl.
  3. dim_produkt: pandas -> temporäre Tabelle -> INSERT ... SELECT (sortiert).
  4. dim_kunde: Zeile -1 wie im DDL, dann alle Versionen über eine temporäre Tabelle.
  5. Soll/Ist VOR dem COMMIT. Eine Abweichung löst eine Exception aus -> ROLLBACK.
"""
import contextlib
import csv
import importlib
import io
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))   # damit "etl. ..." auch beim Start als Skript gefunden wird

# Warum importlib: Der Dateiname beginnt mit einer Ziffer, "import etl.03_…" ist kein gültiger Befehl.
bereinigung = importlib.import_module("etl.03_bereinige_quellen")

PROTOKOLL_DATEI = PROJEKT / "logs" / "ladeprotokoll_dwh.csv"

# ------------------------------------------------------------------------
# SCD 2 (E-14, E-31, E-32)
# ------------------------------------------------------------------------
ERSTE_VERSION_AB = date(1900, 1, 1)      # E-14: jede Bestellung findet eine Version
OFFEN_BIS = date(9999, 12, 31)           # E-14: statt NULL, BETWEEN ohne Sonderfall
# E-31: Stand von kunden_update_2026-01.csv laut docs/anforderungen.md. Seit E-43 kommt das Datum je Datei
# aus etl/kunden_updates.py; diese Werte gelten nur noch für den Aufruf mit EINEM DataFrame (Tests).
GUELTIG_AB_UPDATE = date(2026, 1, 10)
GUELTIG_BIS_ALT = date(2026, 1, 9)       # E-31: Tag davor, BETWEEN schließt beide Grenzen ein
HISTORISIERT = ["plz", "ort", "bundesland"]                               # neue Version (drawio, E-32)
SCD1 = ["kundentyp", "firma", "vorname", "nachname", "erstellt_am"]        # überschreiben (E-32)

# Soll-Werte aus der Planung, vor dem Laden aus den Quelldaten ermittelt.
# Fest eingetragen, damit sie unabhängig vom ladenden Code sind.
SOLL = {
    "dim_produkt": 24,                  # 25 roh - 1 Dublette (Nr 20)
    "lieferant_unbekannt": 3,           # Nr 26, E-23
    "dim_kunde": 173,                   # 1 (-1) + 153 Stamm + 14 neue Versionen + 5 neue Kunden
    "kunden_nr": 159,                   # 1 + 153 + 5, je genau eine aktuelle Version
    "kunden_mit_2_versionen": 14,       # Umzüge im Update
    "positionen_sauber": 2081,          # Trockenlauf etl/03
}

# Zeile -1 wörtlich wie in sql/02_create_dwh.sql (E-21 Folgen: "mit demselben INSERT wie im DDL").
SQL_ZEILE_MINUS_1 = """
INSERT INTO dwh.dim_kunde
       (kunde_sk, kunden_nr, kundentyp, ort, bundesland,
        gueltig_von, gueltig_bis, ist_aktuell)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNBEKANNT', 'Unbekannt', 'Unbekannt', 'Unbekannt',
        DATE '1900-01-01', DATE '9999-12-31', TRUE);
"""


def ist_leer(wert):
    """None, NaN oder '' gilt als leer (E-15: leer im Update überschreibt nicht)."""
    return wert is None or wert is pd.NA or (isinstance(wert, float) and math.isnan(wert)) or wert == ""


def gleich(a, b):
    """Vergleich, bei dem zwei leere Werte gleich sind (None == NaN)."""
    return (ist_leer(a) and ist_leer(b)) or a == b


# ========================================================================
# 1. Kundenversionen bauen (SCD 2) – reine pandas-Logik, getestet in tests/test_dimensionen.py
# ========================================================================
def baue_kundenversionen(stamm, updates):
    """Erzeugt alle Versionen für dim_kunde (ohne Zeile -1).

    stamm: bereinigte Kunden aus bereinige_kunden() (eine Zeile pro kunden_nr).
    updates: Liste [(gueltig_von, DataFrame)] aus den Update-Dateien (E-43), oder EIN DataFrame
             (dann gilt gueltig_von 2026-01-10 aus E-31, so rufen die Tests auf).
    Gibt (DataFrame der Versionen, Kennzahlen) zurück.

    Regeln (Updates in Datumsreihenfolge, jedes gegen den Stand NACH dem vorigen):
      - Kunde nur im Stamm: eine Version 1900-01-01 bis 9999-12-31 (E-14).
      - Kunde im Update: leere Update-Werte überschreiben nicht (E-15).
        Ändert sich plz, ort oder bundesland: aktuelle Version endet am Tag vor gueltig_von,
        neue Version ab gueltig_von (E-31, E-43). SCD-1-Attribute stehen in ALLEN Versionen
        mit dem neuen Wert (E-32).
      - Kunde zum ersten Mal in einem Update (neu): eine Version ab 1900-01-01 (E-14, wie jede erste Version).
      - gueltig_von muss nach dem Beginn der aktuellen Version liegen, sonst Abbruch (ValueError).
    """
    if isinstance(updates, pd.DataFrame):
        updates = [(GUELTIG_AB_UPDATE, updates)]
    updates = sorted(updates, key=lambda u: u[0])
    alt_df = stamm.set_index("kunden_nr")
    attribute = SCD1 + HISTORISIERT
    kz = {"stamm": len(alt_df), "update": sum(len(df) for _, df in updates), "neue_kunden": 0,
          "neue_versionen": 0, "ohne_aenderung": 0, "scd1_geaendert": 0, "e15_nicht_ueberschrieben": 0}

    # Zustand je Kunde: Liste von Versionen [werte, gueltig_von, gueltig_bis], die letzte ist aktuell.
    zustand = {kunden_nr: [[{a: alt[a] for a in attribute}, ERSTE_VERSION_AB, OFFEN_BIS]]
               for kunden_nr, alt in alt_df.iterrows()}

    for gueltig_von, update in updates:
        for kunden_nr, roh_neu in update.set_index("kunden_nr").iterrows():
            if kunden_nr not in zustand:
                zustand[kunden_nr] = [[{a: roh_neu[a] for a in attribute}, ERSTE_VERSION_AB, OFFEN_BIS]]
                kz["neue_kunden"] += 1
                continue
            versionen_kunde = zustand[kunden_nr]
            aktuell, aktuell_von, _ = versionen_kunde[-1]
            # E-15: leerer Wert im Update -> bisheriger Wert bleibt
            neu = {}
            for a in attribute:
                if ist_leer(roh_neu[a]) and not ist_leer(aktuell[a]):
                    kz["e15_nicht_ueberschrieben"] += 1
                    neu[a] = aktuell[a]
                else:
                    neu[a] = roh_neu[a]
            if any(not gleich(aktuell[a], neu[a]) for a in SCD1):
                kz["scd1_geaendert"] += 1
            historisiert_geaendert = any(not gleich(aktuell[a], neu[a]) for a in HISTORISIERT)
            # SCD 1 (E-32): alle bisherigen Versionen bekommen die neuen Werte der nicht historisierten Attribute
            for v in versionen_kunde:
                v[0].update({a: neu[a] for a in SCD1})
            if historisiert_geaendert:
                if gueltig_von <= aktuell_von:
                    raise ValueError(f"{kunden_nr}: Update ab {gueltig_von} liegt nicht nach der aktuellen "
                                     f"Version ab {aktuell_von} (E-43)")
                versionen_kunde[-1][2] = gueltig_von - timedelta(days=1)    # Tag davor (E-31)
                versionen_kunde.append([dict(neu), gueltig_von, OFFEN_BIS])
                kz["neue_versionen"] += 1
            else:
                kz["ohne_aenderung"] += 1

    versionen = [{"kunden_nr": kunden_nr, **{a: werte[a] for a in attribute},
                  "gueltig_von": von, "gueltig_bis": bis, "ist_aktuell": bis == OFFEN_BIS}
                 for kunden_nr, liste in zustand.items() for werte, von, bis in liste]

    # Sortiert: gleiche Reihenfolge -> gleiche kunde_sk bei jedem Lauf (E-33)
    df = pd.DataFrame(versionen).sort_values(["kunden_nr", "gueltig_von"]).reset_index(drop=True)
    return df, kz


def zeilen_fuer_db(df):
    """DataFrame -> Liste von Dictionaries mit reinen Python-Werten.

    Warum: Fehlende Texte sind in pandas NaN (float). psycopg würde NaN als Zahl schicken
    und die TEXT-Spalte lehnt ab. Hier wird jeder leere Wert zu None (= SQL NULL).
    """
    return [{k: (None if ist_leer(v) else v) for k, v in z.items()} for z in df.to_dict("records")]


# ========================================================================
# 2. SQL
# ========================================================================
# ON COMMIT DROP: Die temporäre Tabelle verschwindet am Ende der Transaktion von selbst.
SQL_TMP_PRODUKT = """
CREATE TEMP TABLE tmp_dim_produkt (
    artikel_nr TEXT, bezeichnung TEXT, kategorie TEXT, unterkategorie TEXT, einheit TEXT,
    listenpreis NUMERIC(12,2), lieferant TEXT, lieferant_land TEXT, aktiv BOOLEAN
) ON COMMIT DROP
"""
SPALTEN_PRODUKT = ["artikel_nr", "bezeichnung", "kategorie", "unterkategorie", "einheit",
                   "listenpreis", "lieferant", "lieferant_land", "aktiv"]

SQL_TMP_KUNDE = """
CREATE TEMP TABLE tmp_dim_kunde (
    kunden_nr TEXT, kundentyp TEXT, firma TEXT, vorname TEXT, nachname TEXT,
    plz TEXT, ort TEXT, bundesland TEXT, erstellt_am DATE,
    gueltig_von DATE, gueltig_bis DATE, ist_aktuell BOOLEAN
) ON COMMIT DROP
"""
SPALTEN_KUNDE = ["kunden_nr", "kundentyp", "firma", "vorname", "nachname", "plz", "ort",
                 "bundesland", "erstellt_am", "gueltig_von", "gueltig_bis", "ist_aktuell"]

# Vorschau auf das Laden der Fakten (etl/05): Findet jede saubere Position genau eine Kundenversion?
SQL_TMP_BESTELLUNG = """
CREATE TEMP TABLE tmp_bestellung (bestell_nr INTEGER, position SMALLINT, kunden_nr TEXT, bestelldatum DATE)
ON COMMIT DROP
"""


def einfuegen(conn, tabelle_tmp, tabelle_ziel, spalten, zeilen, sortierung):
    """Zeilen in die temporäre Tabelle (executemany), dann INSERT ... SELECT sortiert in dwh.

    Tabellen- und Spaltennamen kommen aus den festen Listen oben, nicht von außen -> f-String zulässig.
    Gibt die Anzahl eingefügter Zeilen zurück.
    """
    liste = ", ".join(spalten)
    platzhalter = ", ".join(f":{s}" for s in spalten)
    conn.execute(text(f"INSERT INTO {tabelle_tmp} ({liste}) VALUES ({platzhalter})"), zeilen)
    return conn.execute(text(
        f"INSERT INTO {tabelle_ziel} ({liste}) SELECT {liste} FROM {tabelle_tmp} ORDER BY {sortierung}"
    )).rowcount


# Soll/Ist-Abfragen. Jede liefert genau eine Zahl.
PRUEFUNGEN_SQL = {
    "produkt_zeilen":        "SELECT COUNT(*) FROM dwh.dim_produkt",
    "produkt_unbekannt":     "SELECT COUNT(*) FROM dwh.dim_produkt WHERE lieferant = 'Unbekannt' AND lieferant_land = 'Unbekannt'",
    "produkt_null":          "SELECT COUNT(*) FROM dwh.dim_produkt WHERE lieferant IS NULL OR lieferant_land IS NULL",
    "kunde_zeilen":          "SELECT COUNT(*) FROM dwh.dim_kunde",
    "zeile_minus_1":         "SELECT COUNT(*) FROM dwh.dim_kunde WHERE kunde_sk = -1 AND kunden_nr = 'UNBEKANNT'",
    "kunden_nr":             "SELECT COUNT(DISTINCT kunden_nr) FROM dwh.dim_kunde",
    # genau eine aktuelle Version pro Kunde (zusätzlich schützt ux_dim_kunde_aktuell)
    "nicht_genau_1_aktuell": "SELECT COUNT(*) FROM (SELECT kunden_nr FROM dwh.dim_kunde GROUP BY kunden_nr "
                             "HAVING COUNT(*) FILTER (WHERE ist_aktuell) <> 1) x",
    # zwei Versionen desselben Kunden, deren Zeiträume sich schneiden
    "ueberlappungen":        "SELECT COUNT(*) FROM dwh.dim_kunde a JOIN dwh.dim_kunde b "
                             "ON a.kunden_nr = b.kunden_nr AND a.kunde_sk < b.kunde_sk "
                             "AND a.gueltig_von <= b.gueltig_bis AND b.gueltig_von <= a.gueltig_bis",
    # Lücke: neue Version beginnt nicht genau einen Tag nach dem Ende der vorigen
    "luecken":               "SELECT COUNT(*) FROM (SELECT gueltig_von, LAG(gueltig_bis) OVER "
                             "(PARTITION BY kunden_nr ORDER BY gueltig_von) AS bis_vorher FROM dwh.dim_kunde) x "
                             "WHERE bis_vorher IS NOT NULL AND gueltig_von <> bis_vorher + 1",
    # jede erste Version beginnt 1900-01-01 (E-14)
    "erste_nicht_1900":      "SELECT COUNT(*) FROM (SELECT kunden_nr, MIN(gueltig_von) AS von FROM dwh.dim_kunde "
                             "GROUP BY kunden_nr) x WHERE von <> DATE '1900-01-01'",
    "kunden_2_versionen":    "SELECT COUNT(*) FROM (SELECT kunden_nr FROM dwh.dim_kunde GROUP BY kunden_nr "
                             "HAVING COUNT(*) = 2) x",
    # E-32: K0065 ist in beiden Versionen Gewerbe
    "k0065_gewerbe":         "SELECT COUNT(*) FROM dwh.dim_kunde WHERE kunden_nr = 'K0065' AND kundentyp = 'Gewerbe'",
    # Vorschau auf etl/05: Positionen, die NICHT genau eine Version finden
    "position_nicht_genau_1": "SELECT COUNT(*) FROM tmp_bestellung b WHERE (SELECT COUNT(*) FROM dwh.dim_kunde k "
                              "WHERE k.kunden_nr = b.kunden_nr AND b.bestelldatum BETWEEN k.gueltig_von AND k.gueltig_bis) <> 1",
    "positionen":            "SELECT COUNT(*) FROM tmp_bestellung",
    # E-31 Folgen: keine heutige Bestellung landet in einer Version ab 2026-01-10
    "position_neue_version": "SELECT COUNT(*) FROM tmp_bestellung b JOIN dwh.dim_kunde k ON k.kunden_nr = b.kunden_nr "
                             "AND b.bestelldatum BETWEEN k.gueltig_von AND k.gueltig_bis WHERE k.gueltig_von = DATE '2026-01-10'",
    "position_minus_1":      "SELECT COUNT(*) FROM tmp_bestellung WHERE kunden_nr = 'UNBEKANNT'",
    "dim_datum":             "SELECT COUNT(*) FROM dwh.dim_datum",
    "fact_verkauf":          "SELECT COUNT(*) FROM dwh.fact_verkauf",
}

# Fingerabdruck des Inhalts: gleicher Hash = gleicher Inhalt inkl. Schlüssel (Q-05)
SQL_FINGERABDRUCK = {
    "dim_produkt": "SELECT md5(string_agg(t::text, '|' ORDER BY produkt_sk)) FROM dwh.dim_produkt t",
    "dim_kunde":   "SELECT md5(string_agg(t::text, '|' ORDER BY kunde_sk)) FROM dwh.dim_kunde t",
}

# Beispiel für die Doku: ein umgezogener Kunde mit beiden Versionen
SQL_BEISPIEL = """
SELECT kunde_sk, kunden_nr, kundentyp, plz, ort, bundesland, gueltig_von, gueltig_bis, ist_aktuell
FROM dwh.dim_kunde WHERE kunden_nr = :kunden_nr ORDER BY gueltig_von
"""


class PruefungFehlgeschlagen(Exception):
    """Soll/Ist weicht ab. Wird in der Transaktion ausgelöst -> ROLLBACK."""


# ========================================================================
# 3. Laden in EINER Transaktion (E-33)
# ========================================================================
def lade_dimensionen(engine, produkte, versionen, bestellungen):
    """Leert und lädt beide Dimensionen, prüft Soll/Ist vor dem COMMIT. Gibt ein Ergebnis-dict zurück."""
    with engine.begin() as conn:                 # COMMIT am Ende, ROLLBACK bei jeder Exception
        # Schritt 1: Fakten müssen leer sein. Sonst Abbruch, nichts wurde geändert.
        fakten = conn.execute(text("SELECT COUNT(*) FROM dwh.fact_verkauf")).scalar()
        if fakten:
            raise RuntimeError(f"Abbruch (E-33): dwh.fact_verkauf hat {fakten} Zeilen. "
                               "Fakten zuerst bewusst leeren (E-21), dann Dimensionen neu laden.")
        vorher = {t: conn.execute(text(f"SELECT COUNT(*) FROM dwh.{t}")).scalar()
                  for t in ["dim_produkt", "dim_kunde"]}

        # Schritt 2: ein TRUNCATE für alle drei Tabellen (Fremdschlüssel verlangen das, E-33).
        # RESTART IDENTITY: Zähler wieder bei 1 -> gleiche Schlüssel bei jedem Lauf.
        conn.execute(text("TRUNCATE dwh.fact_verkauf, dwh.dim_kunde, dwh.dim_produkt RESTART IDENTITY"))

        # Schritt 3: dim_produkt (sortiert nach artikel_nr -> produkt_sk 1..24 immer gleich)
        conn.execute(text(SQL_TMP_PRODUKT))
        n_produkt = einfuegen(conn, "tmp_dim_produkt", "dwh.dim_produkt", SPALTEN_PRODUKT,
                              zeilen_fuer_db(produkte[SPALTEN_PRODUKT]), "artikel_nr")

        # Schritt 4: dim_kunde, zuerst Zeile -1 (E-04, E-21), dann alle Versionen
        conn.execute(text(SQL_ZEILE_MINUS_1))
        conn.execute(text(SQL_TMP_KUNDE))
        n_kunde = 1 + einfuegen(conn, "tmp_dim_kunde", "dwh.dim_kunde", SPALTEN_KUNDE,
                                zeilen_fuer_db(versionen[SPALTEN_KUNDE]), "kunden_nr, gueltig_von")

        # Schritt 5: Soll/Ist in derselben Transaktion
        conn.execute(text(SQL_TMP_BESTELLUNG))
        conn.execute(text("INSERT INTO tmp_bestellung VALUES (:bestell_nr, :position, :kunden_nr, :bestelldatum)"),
                     zeilen_fuer_db(bestellungen[["bestell_nr", "position", "kunden_nr", "bestelldatum"]]))
        ist = {name: conn.execute(text(sql)).scalar() for name, sql in PRUEFUNGEN_SQL.items()}
        fingerabdruck = {t: conn.execute(text(sql)).scalar() for t, sql in SQL_FINGERABDRUCK.items()}
        beispiel = conn.execute(text(SQL_BEISPIEL), {"kunden_nr": "K0042"}).mappings().all()

        pruefungen = [
            ("dim_produkt Zeilen", SOLL["dim_produkt"], ist["produkt_zeilen"]),
            ("Lieferant 'Unbekannt' (E-23)", SOLL["lieferant_unbekannt"], ist["produkt_unbekannt"]),
            ("Lieferant/Land NULL", 0, ist["produkt_null"]),
            ("dim_kunde Zeilen", SOLL["dim_kunde"], ist["kunde_zeilen"]),
            ("Zeile -1 vorhanden", 1, ist["zeile_minus_1"]),
            ("verschiedene kunden_nr", SOLL["kunden_nr"], ist["kunden_nr"]),
            ("Kunden ohne genau 1 aktuelle Version", 0, ist["nicht_genau_1_aktuell"]),
            ("Überlappende Versionen", 0, ist["ueberlappungen"]),
            ("Lücken zwischen Versionen", 0, ist["luecken"]),
            ("erste Version nicht ab 1900-01-01", 0, ist["erste_nicht_1900"]),
            ("Kunden mit 2 Versionen", SOLL["kunden_mit_2_versionen"], ist["kunden_2_versionen"]),
            ("K0065 Gewerbe in beiden Versionen (E-32)", 2, ist["k0065_gewerbe"]),
            ("saubere Positionen (etl/03)", SOLL["positionen_sauber"], ist["positionen"]),
            ("Positionen ohne genau 1 Version", 0, ist["position_nicht_genau_1"]),
            ("Positionen in Version ab 2026-01-10", 0, ist["position_neue_version"]),
            ("dim_datum unverändert", 2556, ist["dim_datum"]),
            ("fact_verkauf leer", 0, ist["fact_verkauf"]),
        ]
        alle_ok = all(soll == wert for _, soll, wert in pruefungen)
        ergebnis = {"vorher": vorher, "eingefuegt": {"dim_produkt": n_produkt, "dim_kunde": n_kunde},
                    "ist": ist, "pruefungen": pruefungen, "fingerabdruck": fingerabdruck, "beispiel": beispiel}
        if not alle_ok:
            # Exception IN der Transaktion -> ROLLBACK, alter Stand bleibt
            raise PruefungFehlgeschlagen(ergebnis)
    return ergebnis


def protokoll_schreiben(zeilen):
    """Gleiches Format wie etl/02_lade_dim_datum.py, Datei wird ergänzt."""
    PROTOKOLL_DATEI.parent.mkdir(exist_ok=True)
    neu = not PROTOKOLL_DATEI.exists()
    with open(PROTOKOLL_DATEI, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if neu:
            schreiber.writerow(["zeitpunkt", "tabelle", "quelle", "soll", "ist_db", "vorher",
                                "eingefuegt", "geaendert", "geloescht", "ergebnis", "hinweise"])
        schreiber.writerows(zeilen)


def zeige_pruefungen(pruefungen):
    for name, soll, wert in pruefungen:
        print(f"  [{'OK' if soll == wert else '!!'}] {name:<42} Soll {soll:>5}   Ist {wert:>5}")


# ========================================================================
# Hauptprogramm
# ========================================================================
def main():
    print("=" * 78)
    print("Dimensionen laden: dwh.dim_produkt, dwh.dim_kunde (SCD 2)")
    print("=" * 78)
    engine = bereinigung.verbindung_aufbauen()
    zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quelle = "stg.* über etl/03_bereinige_quellen.py"

    # Bereinigung aus etl/03 aufrufen, nicht neu programmieren (E-24). Ihre Konsolenausgabe
    # wird hier ausgeblendet, die Kontrollsummen (assert, Abbruch) laufen trotzdem.
    with contextlib.redirect_stdout(io.StringIO()):
        stg = {t: bereinigung.lese_staging(engine, t)
               for t in ["produkte", "kunden", "bestellungen"]}
        produkte = bereinigung.bereinige_produkte(stg["produkte"])["sauber"]
        stamm = bereinigung.bereinige_kunden(stg["kunden"], "kunden")["sauber"]
        # Alle Update-Dateien je Datei bereinigt, mit gueltig_von aus dem Dateinamen (E-43)
        updates, update_gesamt = bereinigung.bereinige_kunden_updates(bereinigung.lese_kunden_updates(engine))
        bekannte = set(stamm["kunden_nr"]) | set(update_gesamt["sauber"]["kunden_nr"])
        bestellungen = bereinigung.bereinige_bestellungen(stg["bestellungen"], produkte, bekannte)["sauber"]

    versionen, kz = baue_kundenversionen(stamm, [(u["gueltig_von"], u["sauber"]) for u in updates])
    print("Update-Dateien: " + (", ".join(f"{u['datei']} (ab {u['gueltig_von']})" for u in updates) or "keine"))
    print(f"Produkte: {len(produkte)}   Kundenversionen: {len(versionen)} (+ Zeile -1)")
    print(f"SCD 2: Stamm {kz['stamm']}, Update {kz['update']} -> neue Versionen {kz['neue_versionen']}, "
          f"ohne Änderung {kz['ohne_aenderung']}, neue Kunden {kz['neue_kunden']}, "
          f"SCD-1-Änderung {kz['scd1_geaendert']}, E-15 nicht überschrieben {kz['e15_nicht_ueberschrieben']}")

    try:
        e = lade_dimensionen(engine, produkte, versionen, bestellungen)
        status = "OK"
    except PruefungFehlgeschlagen as fehler:
        e, status = fehler.args[0], "FEHLER"

    print("\nSoll/Ist (vor dem COMMIT geprüft):")
    zeige_pruefungen(e["pruefungen"])
    print(f"\nFingerabdruck (md5): dim_produkt {e['fingerabdruck']['dim_produkt']}  "
          f"dim_kunde {e['fingerabdruck']['dim_kunde']}")
    print("\nBeispiel K0042 (umgezogen):")
    for z in e["beispiel"]:
        print("  " + "  ".join(str(z[s]) for s in ["kunde_sk", "kunden_nr", "kundentyp", "plz", "ort",
                                                   "bundesland", "gueltig_von", "gueltig_bis", "ist_aktuell"]))

    # Protokoll in beiden Fällen. Bei FEHLER wurde zurückgerollt: eingefügt/gelöscht dann 0.
    zeilen = []
    for tabelle, soll in [("dim_produkt", SOLL["dim_produkt"]), ("dim_kunde", SOLL["dim_kunde"])]:
        ok = status == "OK"
        vorher = e["vorher"][tabelle]
        hinweis = f"Neuladen TRUNCATE ... RESTART IDENTITY (E-33); gelöscht {vorher}"
        # Kein stilles Löschen im Protokoll: In dim_kunde ist immer die Zeile -1 dabei
        # (aus der DDL oder dem letzten Lauf). Sie wird sofort mit demselben INSERT neu angelegt.
        if tabelle == "dim_kunde" and vorher:
            hinweis += " (davon Zeile -1, sofort neu angelegt, E-21)"
        hinweis += f"; md5 {e['fingerabdruck'][tabelle]}" + ("" if ok else "; ROLLBACK, nichts geändert")
        zeilen.append([zeitpunkt, f"dwh.{tabelle}", quelle, soll, e["ist"][tabelle.replace("dim_", "") + "_zeilen"],
                       vorher, e["eingefuegt"][tabelle] if ok else 0, 0,
                       vorher if ok else 0, status, hinweis])
    protokoll_schreiben(zeilen)

    print("\n" + "=" * 78)
    if status != "OK":
        print("Ergebnis: Soll/Ist weicht ab -> ROLLBACK, dwh unverändert")
        sys.exit(1)
    print("Ergebnis: COMMIT, beide Dimensionen geladen und geprüft")
    print(f"Protokoll: {PROTOKOLL_DATEI}")
    print("=" * 78)


if __name__ == "__main__":
    main()
