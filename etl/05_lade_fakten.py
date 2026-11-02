"""
etl/05_lade_fakten.py

Zweck      : Lädt dwh.fact_verkauf aus den bereinigten Bestellpositionen (E-24, E-34) und führt
             den Gesamttest mit Reaktion VOR dem COMMIT aus (E-35). In DERSELBEN Transaktion
             werden die abgewiesenen Positionen nach protokoll.abgewiesene_position geladen (E-42).
             Nach dem COMMIT wird data/rejected/bestellungen_rejected.csv geschrieben (E-42).
Eingabe    : stg.* über etl/03_bereinige_quellen.py (sauber + rejected + Kennzahlen; Kunden-Updates aus
             stg.kunden_update, E-43),
             dwh.dim_datum, dim_kunde, dim_produkt, dim_zahlung, dim_status (müssen geladen sein)
Ausgabe    : dwh.fact_verkauf (neu geladen)
             protokoll.abgewiesene_position (neu geladen, E-42)
             data/rejected/bestellungen_rejected.csv (nach dem COMMIT, gleiche Funktion wie etl/03)
             logs/ladeprotokoll_dwh.csv        (eine Zeile pro Lauf, wird ergänzt)
             logs/gesamttest_<JJJJ-MM-TT>.csv  (eine Zeile pro Prüfung und Lauf, wird ergänzt)
Anforderung: Q-01 roh = Fakten + rejected + Dubletten, Q-02 Grund nie leer, Q-03 Fremdschlüssel,
             abgelehnte Zeilen in einer Protokolltabelle (E-42),
             Q-05 zweiter Lauf = gleiches Ergebnis (md5), F-01 bis F-07 (Grundlage)
Bezug      : E-01, E-03, E-04, E-05, E-07, E-18, E-19, E-20, E-24, E-27, E-29, E-31, E-34, E-35, E-42; Nr 31
Aufruf     : .venv\\Scripts\\python.exe etl\\05_lade_fakten.py
             Erwartet: alle Prüfungen der Art A und C [OK], "COMMIT", Exit 0.
             Abbruch (A oder C verletzt): ROLLBACK, fact_verkauf und protokoll.abgewiesene_position
             wie vorher, CSV wird nicht geschrieben, Exit 1.
             C9 (CSV-Zeilen = Tabelle, nach dem COMMIT) verletzt: Meldung, Exit 1.
             Voraussetzung: sql/06_create_protokoll_abgewiesen.sql ist ausgeführt.
             Warnung (B verletzt): wird angezeigt und protokolliert, das Laden geht weiter.
           : .venv\\Scripts\\python.exe etl\\05_lade_fakten.py --abbruch-test
             Beweis, dass ein Abbruch greift: verändert nach dem Einfügen absichtlich eine Menge.
             Erwartet: Abbruch bei SUM(menge), ROLLBACK, Meldung "wie erwartet", Exit 1.
             Im Testmodus wird NIE committet.
Exit-Codes : 0 = COMMIT; 1 = Abbruch, ROLLBACK (im Testmodus: wie erwartet);
             3 = Testmodus hat unerwartet NICHT abgebrochen (trotzdem ROLLBACK).
             Der Exit-Code zeigt immer das Ladeergebnis. So stoppt etl/00_starte_gesamtlauf.py
             auch im Testmodus bei Schritt 5 (E-36).
"""
import argparse
import contextlib
import csv
import importlib
import io
import sys
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import text

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

# Warum importlib: Die Dateinamen beginnen mit Ziffern, "import etl.03_..." ist kein gültiger Befehl.
bereinigung = importlib.import_module("etl.03_bereinige_quellen")
dimensionen = importlib.import_module("etl.04_lade_dimensionen")   # zeilen_fuer_db() wiederverwenden
regeln = importlib.import_module("etl.abbildungsregeln")

PROTOKOLL_DATEI = PROJEKT / "logs" / "ladeprotokoll_dwh.csv"
GESAMTTEST_DATEI = PROJEKT / "logs" / f"gesamttest_{date.today().isoformat()}.csv"

ABBRUCH, WARNUNG = "Abbruch", "Warnung"
DATEN_TEAM, VERTRIEB, CONTROLLING = "Daten-Team", "Fachbereich Vertrieb", "Controlling"

# Art B: dokumentierter Stand vom 14.10.2026 (Bereinigung etl/03 und Laden der Dimensionen).
# Eine Abweichung ist kein Ladefehler, sondern eine inhaltliche Änderung -> Warnung an die Fachrolle (E-35).
BASELINE = {
    "zeilen": 2081,                                       # saubere Positionen nach etl/03
    "lieferstatus": {"geliefert": 1050, "offen": 355,     # 2156-Basis (E-12) minus rejected je Status
                     "storniert": 340, "teilgeliefert": 336},   # 33 / 14 / 13 / 15
    "listenpreis": 49,                                    # E-07 / P9, keine der 49 rejected
    "minus_1": 71,                                        # 75 (Nr 33 + 35) minus 4 rejected
    "rejected": 75,                                       # abgewiesene Positionen nach etl/03 (E-42)
}
F01_VON, F01_BIS = date(2024, 1, 1), date(2025, 12, 31)   # Zeitraum von F-01

CENT = Decimal("0.01")

SQL_TMP_FAKT = """
CREATE TEMP TABLE tmp_fakt (
    bestell_nr INTEGER, position SMALLINT, bestelldatum DATE, kunden_nr TEXT, artikel_nr TEXT,
    menge INTEGER, einzelpreis NUMERIC(12,2), rabatt_prozent NUMERIC(5,2),
    zahlungsart TEXT, lieferstatus TEXT, preis_aus_listenpreis BOOLEAN
) ON COMMIT DROP
"""
SPALTEN_TMP = ["bestell_nr", "position", "bestelldatum", "kunden_nr", "artikel_nr", "menge",
               "einzelpreis", "rabatt_prozent", "zahlungsart", "lieferstatus", "preis_aus_listenpreis"]

# Der Lookup als FROM-Teil, gleich für Vorprüfung und INSERT.
# Warum LEFT JOIN: Eine Position ohne Partner bleibt sichtbar (Schlüssel NULL) statt still
# zu verschwinden wie bei einem inneren JOIN (E-24, E-34).
SQL_LOOKUP = """
FROM tmp_fakt t
LEFT JOIN dwh.dim_datum   d ON d.datum = t.bestelldatum
LEFT JOIN dwh.dim_kunde   k ON k.kunden_nr = t.kunden_nr
                           AND t.bestelldatum BETWEEN k.gueltig_von AND k.gueltig_bis
LEFT JOIN dwh.dim_produkt p ON p.artikel_nr = t.artikel_nr
LEFT JOIN dwh.dim_zahlung z ON z.zahlungsart = t.zahlungsart
LEFT JOIN dwh.dim_status  s ON s.lieferstatus = t.lieferstatus
                           AND s.preis_aus_listenpreis = t.preis_aus_listenpreis
"""

# Vorprüfung: Wie viele Positionen finden in welcher Dimension keinen Schlüssel? Soll überall 0.
SQL_FEHLENDE_SCHLUESSEL = f"""
SELECT COUNT(*) FILTER (WHERE d.datum_sk   IS NULL) AS dim_datum,
       COUNT(*) FILTER (WHERE k.kunde_sk   IS NULL) AS dim_kunde,
       COUNT(*) FILTER (WHERE p.produkt_sk IS NULL) AS dim_produkt,
       COUNT(*) FILTER (WHERE z.zahlung_sk IS NULL) AS dim_zahlung,
       COUNT(*) FILTER (WHERE s.status_sk  IS NULL) AS dim_status
{SQL_LOOKUP}
"""

# Nur Schlüssel und die drei Messwerte; umsatz_brutto/rabatt_betrag/umsatz_netto rechnet die DB (E-19).
SQL_EINFUEGEN = f"""
INSERT INTO dwh.fact_verkauf
       (bestell_nr, position, datum_sk, kunde_sk, produkt_sk, zahlung_sk, status_sk,
        menge, einzelpreis, rabatt_prozent)
SELECT t.bestell_nr, t.position, d.datum_sk, k.kunde_sk, p.produkt_sk, z.zahlung_sk, s.status_sk,
       t.menge, t.einzelpreis, t.rabatt_prozent
{SQL_LOOKUP}
ORDER BY t.bestell_nr, t.position
"""

SQL_FINGERABDRUCK = ("SELECT md5(string_agg(f::text, '|' ORDER BY bestell_nr, position)) "
                     "FROM dwh.fact_verkauf f")

# Protokolltabelle der abgewiesenen Positionen (E-42). Spalten wie die CSV, dazu der technische Schlüssel.
QUELLDATEI_BESTELLUNGEN = "bestellungen.csv"
SPALTEN_REJECTED = ["bestell_nr", "position", "bestelldatum", "kunden_nr", "artikel_nr", "menge",
                    "einzelpreis", "rabatt_prozent", "zahlungsart", "lieferstatus", "grund"]
SQL_EINFUEGEN_REJECTED = (
    "INSERT INTO protokoll.abgewiesene_position (_source_file, lfd_nr, " + ", ".join(SPALTEN_REJECTED) + ") "
    "VALUES (:_source_file, :lfd_nr, " + ", ".join(":" + s for s in SPALTEN_REJECTED) + ")")
SQL_FINGERABDRUCK_REJECTED = ("SELECT md5(string_agg(a::text, '|' ORDER BY _source_file, lfd_nr)) "
                              "FROM protokoll.abgewiesene_position a")


class LadeAbbruch(Exception):
    """Abbruch in der Transaktion -> ROLLBACK. args[0] = Ergebnis-dict (für Protokoll und Anzeige)."""


# ========================================================================
# 1. Soll aus pandas (Weg A) – unabhängig von SQL berechnet
# ========================================================================
def soll_aus_pandas(sauber):
    """Kennzahlen aus den bereinigten Positionen, mit Decimal und Rundung pro Position wie E-19.

    ROUND_HALF_UP entspricht PostgreSQL ROUND(numeric, 2) für positive Werte (alle Werte hier sind > 0,
    belegt durch Menge > 0, Einzelpreis >= 0, Rabatt 0-100).
    """
    brutto = [(Decimal(m) * ep).quantize(CENT, ROUND_HALF_UP)
              for m, ep in zip(sauber["menge"], sauber["einzelpreis"])]
    rabatt = [(Decimal(m) * ep * rp / 100).quantize(CENT, ROUND_HALF_UP)
              for m, ep, rp in zip(sauber["menge"], sauber["einzelpreis"], sauber["rabatt_prozent"])]
    return {
        "zeilen": len(sauber),
        "bestellungen": int(sauber["bestell_nr"].nunique()),
        "sum_menge": sum(int(m) for m in sauber["menge"]),
        "sum_brutto": sum(brutto, Decimal("0")),
        "sum_rabatt": sum(rabatt, Decimal("0")),
        "sum_netto": sum(brutto, Decimal("0")) - sum(rabatt, Decimal("0")),
        "status": {(ls, bool(fl)): int(n) for (ls, fl), n
                   in sauber.groupby(["lieferstatus", "preis_aus_listenpreis"]).size().items()},
        "zahlungsart": {k: int(v) for k, v in sauber["zahlungsart"].value_counts().items()},
        "minus_1": int((sauber["kunden_nr"] == regeln.KUNDEN_NR_UNBEKANNT).sum()),
    }


# ========================================================================
# 2. Ist aus der Datenbank (nach Lookup und generierten Spalten)
# ========================================================================
def ist_aus_db(conn):
    """Gleiche Kennzahlen wie soll_aus_pandas(), aber aus dwh.fact_verkauf und den Dimensionen."""
    def wert(sql):
        return conn.execute(text(sql)).scalar()

    return {
        "zeilen": wert("SELECT COUNT(*) FROM dwh.fact_verkauf"),
        "bestellungen": wert("SELECT COUNT(DISTINCT bestell_nr) FROM dwh.fact_verkauf"),
        "sum_menge": wert("SELECT SUM(menge) FROM dwh.fact_verkauf"),
        "sum_brutto": wert("SELECT SUM(umsatz_brutto) FROM dwh.fact_verkauf"),
        "sum_rabatt": wert("SELECT SUM(rabatt_betrag) FROM dwh.fact_verkauf"),
        "sum_netto": wert("SELECT SUM(umsatz_netto) FROM dwh.fact_verkauf"),
        "status": {(ls, fl): n for ls, fl, n in conn.execute(text(
            "SELECT s.lieferstatus, s.preis_aus_listenpreis, COUNT(*) FROM dwh.fact_verkauf f "
            "JOIN dwh.dim_status s ON s.status_sk = f.status_sk GROUP BY 1, 2"))},
        "zahlungsart": dict(conn.execute(text(
            "SELECT z.zahlungsart, COUNT(*) FROM dwh.fact_verkauf f "
            "JOIN dwh.dim_zahlung z ON z.zahlung_sk = f.zahlung_sk GROUP BY 1")).all()),
        "minus_1": wert("SELECT COUNT(*) FROM dwh.fact_verkauf WHERE kunde_sk = -1"),
        # Art C: Regeln
        "menge_nicht_positiv": wert("SELECT COUNT(*) FROM dwh.fact_verkauf WHERE menge <= 0"),
        "rabatt_ausserhalb": wert("SELECT COUNT(*) FROM dwh.fact_verkauf WHERE rabatt_prozent NOT BETWEEN 0 AND 100"),
        "preis_negativ": wert("SELECT COUNT(*) FROM dwh.fact_verkauf WHERE einzelpreis < 0"),
        "nach_export": conn.execute(text(
            "SELECT COUNT(*) FROM dwh.fact_verkauf f JOIN dwh.dim_datum d ON d.datum_sk = f.datum_sk "
            "WHERE d.datum > :stichtag"), {"stichtag": regeln.EXPORT_STICHTAG}).scalar(),
        # Art B: Zeitraum F-01
        "ausserhalb_f01": conn.execute(text(
            "SELECT COUNT(*) FROM dwh.fact_verkauf f JOIN dwh.dim_datum d ON d.datum_sk = f.datum_sk "
            "WHERE d.datum NOT BETWEEN :von AND :bis"), {"von": F01_VON, "bis": F01_BIS}).scalar(),
    }


# ========================================================================
# 3. Gesamttest: jede Prüfung mit Soll, Herkunft, Reaktion, Rolle (E-35)
# ========================================================================
def gesamttest(soll, ist, kz):
    """Gibt eine Liste von Prüfungen zurück: (nr, art, pruefung, soll, ist, reaktion, rolle, herkunft).

    kz = Kennzahlen der Bereinigung (roh, dubletten, rejected, rejected-Gründe).
    """
    p = []
    # --- Art A: zwei Wege (pandas / Datenbank) -> Abbruch -------------------
    for nr, schluessel, name, rolle in [
        ("A1", "zeilen", "Zeilen fact = saubere Positionen", DATEN_TEAM),
        ("A2", "bestellungen", "Bestellungen (DISTINCT bestell_nr)", DATEN_TEAM),
        ("A3", "sum_menge", "SUM(menge)", DATEN_TEAM),
        ("A4", "sum_brutto", "SUM(umsatz_brutto)", CONTROLLING),
        ("A5", "sum_rabatt", "SUM(rabatt_betrag)", CONTROLLING),
        ("A6", "sum_netto", "SUM(umsatz_netto)", CONTROLLING),
        ("A7", "minus_1", "Positionen auf Kunde -1", DATEN_TEAM),
    ]:
        p.append((nr, "A", name, soll[schluessel], ist[schluessel], ABBRUCH, rolle, "pandas aus bereinigten Daten"))
    for i, schluessel in enumerate(sorted(set(soll["status"]) | set(ist["status"])), start=1):
        p.append((f"A8.{i}", "A", f"Status {schluessel[0]} / Listenpreis {schluessel[1]}",
                  soll["status"].get(schluessel, 0), ist["status"].get(schluessel, 0), ABBRUCH, DATEN_TEAM,
                  "pandas aus bereinigten Daten"))
    for i, schluessel in enumerate(sorted(set(soll["zahlungsart"]) | set(ist["zahlungsart"])), start=1):
        p.append((f"A9.{i}", "A", f"Zahlungsart {schluessel}", soll["zahlungsart"].get(schluessel, 0),
                  ist["zahlungsart"].get(schluessel, 0), ABBRUCH, DATEN_TEAM, "pandas aus bereinigten Daten"))

    # --- Art C: Regeln -> Abbruch ---------------------------------------------
    p.append(("C1", "C", f"Q-01 roh {kz['roh']} = Fakten + rejected {kz['rejected']} + Dubletten {kz['dubletten']}",
              kz["roh"], ist["zeilen"] + kz["rejected"] + kz["dubletten"], ABBRUCH, DATEN_TEAM, "Q-01"))
    p.append(("C2", "C", "Q-02 rejected ohne Grund", 0, kz["rejected_ohne_grund"], ABBRUCH, DATEN_TEAM, "Q-02"))
    p.append(("C3", "C", "Menge <= 0", 0, ist["menge_nicht_positiv"], ABBRUCH, DATEN_TEAM, "E-05"))
    p.append(("C4", "C", "Rabatt außerhalb 0-100", 0, ist["rabatt_ausserhalb"], ABBRUCH, DATEN_TEAM, "E-29"))
    p.append(("C5", "C", "Einzelpreis < 0", 0, ist["preis_negativ"], ABBRUCH, DATEN_TEAM, "E-29"))
    p.append(("C6", "C", f"Datum nach Export {regeln.EXPORT_STICHTAG}", 0, ist["nach_export"], ABBRUCH,
              DATEN_TEAM, "Nr 31"))
    # E-42: Die Protokolltabelle enthält genau die abgewiesenen Zeilen der Bereinigung, jede mit Grund.
    p.append(("C7", "C", "Protokolltabelle = rejected der Bereinigung", kz["rejected"], ist["rejected_tabelle"],
              ABBRUCH, DATEN_TEAM, "E-42"))
    p.append(("C8", "C", "Q-02 Protokolltabelle ohne Grund", 0, ist["rejected_tabelle_ohne_grund"], ABBRUCH,
              DATEN_TEAM, "Q-02, E-42"))

    # --- Art B: dokumentierter Stand -> Warnung -------------------------------
    p.append(("B1", "B", "Zeilen fact (Stand 14.10.2026)", BASELINE["zeilen"], ist["zeilen"], WARNUNG, DATEN_TEAM,
              "Bereinigung etl/03, Stand 14.10.2026"))
    for i, (status, n) in enumerate(BASELINE["lieferstatus"].items(), start=1):
        ist_n = sum(v for (ls, _), v in ist["status"].items() if ls == status)
        p.append((f"B2.{i}", "B", f"Lieferstatus {status}", n, ist_n, WARNUNG, VERTRIEB,
                  "E-12 (2156) minus rejected je Status"))
    ist_listenpreis = sum(v for (_, fl), v in ist["status"].items() if fl)
    p.append(("B3", "B", "preis_aus_listenpreis = TRUE", BASELINE["listenpreis"], ist_listenpreis, WARNUNG,
              VERTRIEB, "E-07 / P9"))
    p.append(("B4", "B", "Positionen auf Kunde -1", BASELINE["minus_1"], ist["minus_1"], WARNUNG, VERTRIEB,
              "75 (Nr 33 + 35) minus 4 rejected"))
    p.append(("B5", "B", "Positionen außerhalb F-01 (2024-2025)", 0, ist["ausserhalb_f01"], WARNUNG, VERTRIEB, "F-01"))
    p.append(("B6", "B", "Protokolltabelle abgewiesene Zeilen", BASELINE["rejected"], ist["rejected_tabelle"],
              WARNUNG, DATEN_TEAM, "Bereinigung etl/03, Stand 14.10.2026"))
    return p


def schreibe_csv(pfad, kopf, zeilen):
    """Hängt Zeilen an eine CSV in logs/ an (alte Läufe bleiben erhalten)."""
    pfad.parent.mkdir(exist_ok=True)
    neu = not pfad.exists()
    with open(pfad, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if neu and kopf:
            schreiber.writerow(kopf)
        schreiber.writerows(zeilen)


# ========================================================================
# 4. Laden in EINER Transaktion (E-34), Gesamttest vor dem COMMIT (E-35)
# ========================================================================
def lade_rejected(conn, rejected):
    """Leert und lädt protokoll.abgewiesene_position in der offenen Transaktion (E-42).

    Gibt (vorher, eingefuegt) zurück. Kein stilles Löschen: "vorher" steht im Ladeprotokoll.
    lfd_nr = 1..N in der Reihenfolge von rejected. Diese ist fest: etl/03 lese_staging sortiert
    über alle Spalten (Q-05). Kein Schlüssel auf Rohwerten: jede schlechte Zeile passt hinein.
    """
    vorher = conn.execute(text("SELECT COUNT(*) FROM protokoll.abgewiesene_position")).scalar()
    conn.execute(text("TRUNCATE protokoll.abgewiesene_position"))
    zeilen = dimensionen.zeilen_fuer_db(rejected[SPALTEN_REJECTED])
    for lfd_nr, zeile in enumerate(zeilen, start=1):
        zeile["_source_file"], zeile["lfd_nr"] = QUELLDATEI_BESTELLUNGEN, lfd_nr
    if zeilen:
        conn.execute(text(SQL_EINFUEGEN_REJECTED), zeilen)
    return vorher, len(zeilen)


def lade_fakten(engine, sauber, kz, rejected, abbruch_test=False):
    """Leert und lädt fact_verkauf und die Protokolltabelle in EINER Transaktion.

    Gibt das Ergebnis-dict zurück oder wirft LadeAbbruch (-> ROLLBACK für beide Tabellen).
    """
    soll = soll_aus_pandas(sauber)
    with engine.begin() as conn:
        vorher = conn.execute(text("SELECT COUNT(*) FROM dwh.fact_verkauf")).scalar()
        # Kein Fremdschlüssel zeigt auf fact_verkauf -> TRUNCATE allein ist möglich.
        conn.execute(text("TRUNCATE dwh.fact_verkauf"))

        conn.execute(text(SQL_TMP_FAKT))
        liste = ", ".join(SPALTEN_TMP)
        conn.execute(text(f"INSERT INTO tmp_fakt ({liste}) VALUES ({', '.join(':' + s for s in SPALTEN_TMP)})"),
                     dimensionen.zeilen_fuer_db(sauber[SPALTEN_TMP]))

        # Vorprüfung: fehlende Schlüssel pro Dimension. Soll überall 0, sonst Abbruch mit Namen.
        fehlend = dict(conn.execute(text(SQL_FEHLENDE_SCHLUESSEL)).mappings().one())
        if any(fehlend.values()):
            raise LadeAbbruch({"grund": f"fehlende Schlüssel: {fehlend}", "vorher": vorher})

        eingefuegt = conn.execute(text(SQL_EINFUEGEN)).rowcount

        # Abgewiesene Positionen in derselben Transaktion (E-42): Fakten und Protokoll stammen
        # immer aus demselben Lauf; ein ROLLBACK setzt beide zurück.
        rej_vorher, rej_eingefuegt = lade_rejected(conn, rejected)

        if abbruch_test:
            # Absichtlicher Fehler (nur mit --abbruch-test): eine Menge +1. pandas kennt diese
            # Änderung nicht -> A3 SUM(menge) muss abweichen -> Abbruch -> ROLLBACK.
            conn.execute(text("UPDATE dwh.fact_verkauf SET menge = menge + 1 "
                              "WHERE (bestell_nr, position) = (SELECT bestell_nr, position FROM dwh.fact_verkauf "
                              "ORDER BY bestell_nr, position LIMIT 1)"))

        ist = ist_aus_db(conn)
        ist["rejected_tabelle"] = conn.execute(text("SELECT COUNT(*) FROM protokoll.abgewiesene_position")).scalar()
        ist["rejected_tabelle_ohne_grund"] = conn.execute(text(
            "SELECT COUNT(*) FROM protokoll.abgewiesene_position WHERE btrim(coalesce(grund, '')) = ''")).scalar()
        pruefungen = gesamttest(soll, ist, kz)
        ergebnis = {"vorher": vorher, "eingefuegt": eingefuegt, "pruefungen": pruefungen,
                    "md5": conn.execute(text(SQL_FINGERABDRUCK)).scalar(),
                    "rej_vorher": rej_vorher, "rej_eingefuegt": rej_eingefuegt,
                    "md5_rejected": conn.execute(text(SQL_FINGERABDRUCK_REJECTED)).scalar()}

        abbrueche = [x for x in pruefungen if x[5] == ABBRUCH and x[3] != x[4]]
        if abbrueche:
            ergebnis["grund"] = "Gesamttest: " + ", ".join(f"{x[0]} {x[2]}" for x in abbrueche)
            raise LadeAbbruch(ergebnis)          # in der Transaktion -> ROLLBACK
        if abbruch_test:
            # Sicherheitsnetz: Im Testmodus nie committen, auch wenn der Test unerwartet nicht abbricht.
            ergebnis["grund"] = "Abbruch-Test hat NICHT abgebrochen (unerwartet)"
            raise LadeAbbruch(ergebnis)
    return ergebnis


def zeige(pruefungen):
    for nr, art, name, soll, ist, reaktion, rolle, _ in pruefungen:
        zeichen = "OK" if soll == ist else ("!!" if reaktion == ABBRUCH else "W ")
        print(f"  [{zeichen}] {nr:<5} {name:<52} Soll {str(soll):>12}  Ist {str(ist):>12}  {reaktion:<8} {rolle}")


# ========================================================================
# Hauptprogramm
# ========================================================================
def main():
    parser = argparse.ArgumentParser(description="fact_verkauf laden mit Gesamttest")
    parser.add_argument("--abbruch-test", action="store_true",
                        help="Beweis: absichtlicher Fehler -> Abbruch -> ROLLBACK (nie COMMIT)")
    args = parser.parse_args()
    lauf = "Abbruch-Test" if args.abbruch_test else "Laden"

    print("=" * 100)
    print(f"Fakten laden: dwh.fact_verkauf ({lauf})")
    print("=" * 100)
    engine = bereinigung.verbindung_aufbauen()
    zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Bereinigung aus etl/03 aufrufen (E-24); ihre Kontrollsumme Q-01 (assert, Abbruch) läuft dabei mit.
    with contextlib.redirect_stdout(io.StringIO()):
        stg = {t: bereinigung.lese_staging(engine, t)
               for t in ["produkte", "kunden", "bestellungen"]}
        produkte = bereinigung.bereinige_produkte(stg["produkte"])["sauber"]
        # Bekannte Kunden = Stamm + alle Update-Dateien (E-43)
        _, update_gesamt = bereinigung.bereinige_kunden_updates(bereinigung.lese_kunden_updates(engine))
        bekannte = (set(bereinigung.bereinige_kunden(stg["kunden"], "kunden")["sauber"]["kunden_nr"])
                    | set(update_gesamt["sauber"]["kunden_nr"]))
        best = bereinigung.bereinige_bestellungen(stg["bestellungen"], produkte, bekannte)
    kz = dict(best["kennzahlen"])
    kz["rejected_ohne_grund"] = int((best["rejected"]["grund"].fillna("") == "").sum())

    try:
        e = lade_fakten(engine, best["sauber"], kz, best["rejected"], abbruch_test=args.abbruch_test)
        status = "OK"
    except LadeAbbruch as fehler:
        e, status = fehler.args[0], "ABBRUCH"

    if "pruefungen" in e:
        print("\nGesamttest (vor dem COMMIT):")
        zeige(e["pruefungen"])
        warnungen = [x for x in e["pruefungen"] if x[5] == WARNUNG and x[3] != x[4]]
        schreibe_csv(GESAMTTEST_DATEI,
                     ["zeitpunkt", "lauf", "status", "nr", "art", "pruefung", "soll", "ist", "ok", "reaktion",
                      "rolle", "herkunft"],
                     [[zeitpunkt, lauf, status, nr, art, name, soll, ist, soll == ist, reaktion, rolle, herkunft]
                      for nr, art, name, soll, ist, reaktion, rolle, herkunft in e["pruefungen"]])
        print(f"\nWarnungen: {len(warnungen)}   Nachweis: {GESAMTTEST_DATEI.name}")
        print(f"md5 fact_verkauf (in der Transaktion): {e.get('md5')}")
        print(f"md5 protokoll.abgewiesene_position (in der Transaktion): {e.get('md5_rejected')}")

    ok = status == "OK"
    schreibe_csv(PROTOKOLL_DATEI,
                 ["zeitpunkt", "tabelle", "quelle", "soll", "ist_db", "vorher", "eingefuegt", "geaendert",
                  "geloescht", "ergebnis", "hinweise"],
                 [[zeitpunkt, "dwh.fact_verkauf", "stg.* über etl/03_bereinige_quellen.py", kz["sauber"],
                   e.get("eingefuegt", 0) if ok else e["vorher"], e["vorher"], e.get("eingefuegt", 0) if ok else 0,
                   0, e["vorher"] if ok else 0, status if not args.abbruch_test else "TEST-ABBRUCH",
                   (f"Neuladen TRUNCATE (E-34); md5 {e.get('md5')}" if ok
                    else f"ROLLBACK, nichts geändert; {e.get('grund')}")]])
    # Zweite Zeile: Protokolltabelle (E-42). Kein stilles Löschen: geleerte Zeilen mit Anzahl und Grund.
    rej_vorher = e.get("rej_vorher", "")
    schreibe_csv(PROTOKOLL_DATEI, None,
                 [[zeitpunkt, "protokoll.abgewiesene_position", "stg.bestellungen über etl/03_bereinige_quellen.py",
                   kz["rejected"], e.get("rej_eingefuegt", 0) if ok else rej_vorher, rej_vorher,
                   e.get("rej_eingefuegt", 0) if ok else 0, 0, rej_vorher if ok else 0,
                   status if not args.abbruch_test else "TEST-ABBRUCH",
                   (f"Neuladen TRUNCATE (E-42), geleert: {rej_vorher} Zeilen; md5 {e.get('md5_rejected')}" if ok
                    else f"ROLLBACK, nichts geändert; {e.get('grund')}")]])

    print("\n" + "=" * 100)
    if args.abbruch_test:
        erwartet = status == "ABBRUCH" and e.get("grund", "").startswith("Gesamttest") and "A3" in e["grund"]
        print(f"Abbruch-Test: {'wie erwartet abgebrochen' if erwartet else 'UNERWARTET'} -> {e.get('grund')}")
        print("ROLLBACK: fact_verkauf ist unverändert.")
        # Exit-Code = Ladeergebnis (Abbruch -> 1), nicht das Testurteil (siehe Kopf)
        sys.exit(1 if erwartet else 3)
    if not ok:
        print(f"Ergebnis: ABBRUCH -> ROLLBACK, fact_verkauf unverändert. Grund: {e.get('grund')}")
        sys.exit(1)
    print("Ergebnis: COMMIT, fact_verkauf und protokoll.abgewiesene_position geladen, Gesamttest bestanden")

    # Nach dem COMMIT: CSV aus denselben Daten, mit DERSELBEN Funktion wie etl/03 (E-42).
    # Warum erst jetzt: Bei einem ROLLBACK bliebe sonst eine CSV, die nicht zur Datenbank passt.
    rejected_datei = bereinigung.schreibe_rejected_csv(best["rejected"])
    # C9: CSV-Zeilen = Zeilen der Protokolltabelle. Erwartet gleich; sonst Exit 1 (die Daten sind
    # committet, nur die CSV ist dann falsch und muss neu geschrieben werden).
    with open(rejected_datei, encoding="utf-8-sig", newline="") as f:
        csv_zeilen = sum(1 for _ in csv.reader(f, delimiter=";")) - 1          # ohne Kopfzeile
    with engine.connect() as conn:
        tabelle = conn.execute(text("SELECT COUNT(*) FROM protokoll.abgewiesene_position")).scalar()
    c9_ok = csv_zeilen == tabelle
    print(f"  [{'OK' if c9_ok else '!!'}] C9    {'CSV ' + rejected_datei.name + ' = Tabelle':<52} "
          f"Soll {tabelle:>12}  Ist {csv_zeilen:>12}  {ABBRUCH:<8} {DATEN_TEAM}")
    if not c9_ok:
        print("Ergebnis: ABBRUCH nach dem COMMIT, CSV passt nicht zur Protokolltabelle.")
        sys.exit(1)
    print("=" * 100)


if __name__ == "__main__":
    main()
