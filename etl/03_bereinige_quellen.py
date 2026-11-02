"""
etl/03_bereinige_quellen.py

Zweck      : Bereinigung und Validierung aller Quellen aus stg.* mit pandas (erster Teil von E-24).
             Eine Funktion pro Quelle: bereinige_produkte(), bereinige_kunden() (auch für das
             Kunden-Update), bereinige_bestellungen(). Das Hauptprogramm ist ein TROCKENLAUF:
             Es schreibt NICHTS in dwh.* (das Laden übernehmen etl/04 und etl/05).
Eingabe    : stg.bestellungen, stg.kunden, stg.kunden_update (alle Update-Dateien, E-43), stg.produkte
             (nur SELECT)
Ausgabe    : data/rejected/bestellungen_rejected.csv  (Originalwerte + Spalte "grund")
             logs/bereinigungsprotokoll.csv           (eine Zeile pro Quelle und Lauf, wird ergänzt)
             logs/bereinigung_aenderungen.csv         (jede Ersetzung und Warnung, wird ergänzt)
             Konsole: Soll/Ist-Bericht
Anforderung: Q-01 roh = sauber + rejected + Dubletten, Q-02 jede Ablehnung hat einen Grund,
             Q-04 jede Regel ist dokumentiert (etl/abbildungsregeln.py), Q-05 reproduzierbar,
             R-02 Rohdaten nur lesen (hier sogar nur stg.*), R-03 kein Telefon/E-Mail ins DWH
Bezug      : E-02 bis E-10, E-12, E-18, E-21, E-23 bis E-30, O-05, O-07;
             data_quality_issues Nr 1-47
Aufruf     : .venv\\Scripts\\python.exe etl\\03_bereinige_quellen.py
             Erwartet: Soll/Ist-Tabelle, Kontrollsumme Q-01 "OK", Exit 0.
             Abbruch (Exception), wenn Stammdaten einen unbekannten Wert haben
             oder die Kontrollsumme nicht stimmt.

Grundregel: Ein Wert, den keine Regel kennt, wird nie still zu NaN.
  Bestellungen -> rejected mit Grund "unbekannter Wert in <spalte>".
  Stammdaten (Kunden, Produkte) -> Abbruch mit klarer Meldung, weil eine falsche
  Dimension alle Fakten verfälschen würde.
"""
import csv
import os
import re
import sys
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

# Projektordner in den Suchpfad, damit "from etl import ..." auch beim Start als Skript funktioniert.
PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from etl import abbildungsregeln as regeln                   # noqa: E402
from etl import kunden_updates                               # noqa: E402
from etl.hilfsfunktionen import kontrollsumme, vergleiche    # noqa: E402

REJECTED_ORDNER = PROJEKT / "data" / "rejected"
PROTOKOLL_DATEI = PROJEKT / "logs" / "bereinigungsprotokoll.csv"
AENDERUNGEN_DATEI = PROJEKT / "logs" / "bereinigung_aenderungen.csv"
# DWH_DB_CONFIG (optional): andere Konfigurationsdatei, z. B. für eine Test-Datenbank (E-44).
# Ohne die Variable gilt db_config.ini im Projektordner.
CONFIG_DATEI = Path(os.environ.get("DWH_DB_CONFIG", PROJEKT / "db_config.ini"))


# ========================================================================
# 1. Kleine Bausteine (werden auch in tests/test_bereinigung.py geprüft)
# ========================================================================
def schluessel(wert):
    """Form eines Werts zum Nachschlagen in den Mapping-Tabellen: NFC, strip, lower.

    Nur zum Vergleichen, nicht zum Speichern (gleiche Idee wie normalisiere_text()
    in etl/hilfsfunktionen.py). None bleibt None.
    """
    if not isinstance(wert, str):
        return None
    return unicodedata.normalize("NFC", wert).strip().lower()


def abbilden(serie, mapping):
    """Schlägt jeden Wert in einer Mapping-Tabelle nach. Unbekannt -> None.

    Der Aufrufer MUSS danach auf None prüfen: Hier wird nichts entschieden,
    nur nachgeschlagen (Grundregel oben).
    """
    return serie.map(lambda w: mapping.get(schluessel(w)))


def parse_datum(wert):
    """Text -> datetime.date nach den festen Formaten (E-02, E-25). Ungültig -> None.

    Das Format wird über das Muster erkannt, nicht durch Ausprobieren. So kann
    '03/04/2024' nie still als 3. April gelesen werden.
    Ein Datum, das es nicht gibt ('2027-02-30', Nr 30), passt zum Muster, aber
    strptime wirft ValueError -> None.
    """
    if not isinstance(wert, str):
        return None
    for muster, fmt in regeln.DATUMSFORMATE:
        if re.fullmatch(muster, wert):
            try:
                return datetime.strptime(wert, fmt).date()
            except ValueError:
                return None
    return None


def parse_dezimal(wert):
    """Text mit deutschem Dezimalkomma -> Decimal (Nr 41, Nr 43). Ungültig -> None.

    Warum Decimal und nicht float: Geldbeträge sollen exakt bleiben
    (float macht aus 0,1 + 0,2 den Wert 0.30000000000000004). Die DB-Spalten sind NUMERIC.
    Erlaubt sind nur Ziffern mit höchstens einem Komma oder Punkt, optional mit Minus.
    """
    if not isinstance(wert, str) or not re.fullmatch(r"-?\d+([.,]\d+)?", wert):
        return None
    try:
        return Decimal(wert.replace(",", "."))
    except InvalidOperation:
        return None


def parse_produktpreis(wert):
    """Preis aus produkte.json: '1,74 €' oder '1.62' -> Decimal (Nr 22). Ungültig -> None."""
    if not isinstance(wert, str):
        return None
    return parse_dezimal(wert.replace("€", "").strip())


def vereinheitliche_artikel_nr(wert):
    """'a005 ', 'A005', 'a-005' -> 'A-005' (Nr 19, Nr 36). Passt das Muster nicht -> None."""
    if not isinstance(wert, str):
        return None
    kompakt = wert.upper().replace(" ", "")
    treffer = re.fullmatch(regeln.MUSTER_ARTIKEL_NR, kompakt)
    if treffer is None:
        return None
    return f"{treffer.group(1)}-{treffer.group(2)}"


def text_bereinigen(df):
    """Unicode NFC + strip für alle Textzellen. Gibt (neuer DataFrame, Anzahl geänderter Zellen) zurück.

    Warum NFC: 'ö' kann als ein Zeichen oder als 'o' + '¨' gespeichert sein. Beides
    sieht gleich aus, ist für einen Vergleich aber verschieden.
    None (SQL NULL) bleibt None.
    """
    neu = df.copy()
    geaendert = 0
    for spalte in neu.columns:
        alt = neu[spalte]
        neu[spalte] = alt.map(lambda w: unicodedata.normalize("NFC", w).strip() if isinstance(w, str) else w)
        # fillna nur für den Vergleich: None != None wäre sonst True
        geaendert += int((alt.fillna("<NULL>") != neu[spalte].fillna("<NULL>")).sum())
    return neu, geaendert


def stammdaten_abbruch(maske, werte, spalte, regel):
    """Abbruch, wenn Stammdaten einen Wert haben, den keine Regel kennt.

    Erwartet: maske ist überall False. Sonst ValueError mit allen betroffenen Werten.
    Grund: Eine falsche oder leere Dimension würde jede Auswertung verfälschen.
    """
    if maske.any():
        beispiele = sorted({str(w) for w in werte[maske]})
        raise ValueError(f"Abbruch ({regel}): {int(maske.sum())} unbekannte Werte in '{spalte}': {beispiele}")


def aenderung(liste, quelle, schluessel_wert, spalte, regel, alt, neu):
    """Eine Ersetzung oder Warnung für logs/bereinigung_aenderungen.csv merken (nichts still ändern)."""
    liste.append({"quelle": quelle, "schluessel": schluessel_wert, "spalte": spalte,
                  "regel": regel, "wert_alt": alt, "wert_neu": neu})


# ========================================================================
# 2. Produkte (stg.produkte)
# ========================================================================
def bereinige_produkte(roh):
    """Bereinigt den Artikelstamm. Gibt dict mit sauber, kennzahlen, aenderungen zurück.

    Stammdaten: Jeder unbekannte Wert führt zum Abbruch (stammdaten_abbruch).
    """
    kz, aend = {"roh": len(roh)}, []

    # Kennzahlen auf den Rohwerten, gleiche Definition wie explore/01_explore.py
    kz["nr23_einheit_uneinheitlich"] = int((~roh["einheit"].isin(["L", "Stück", "kg"])).sum())
    kz["nr24_aktiv_nicht_true"] = int((roh["aktiv"] != "true").sum())
    kz["nr26_lieferant_fehlt"] = int(roh["lieferant_name"].isna().sum())
    kz["nr27_land_nicht_de"] = int((roh["lieferant_land"].notna() & (roh["lieferant_land"] != "DE")).sum())

    p, kz["text_geaendert"] = text_bereinigen(roh)

    # Artikelnummer vereinheitlichen (Nr 19). Passt sie nicht zum Muster -> Abbruch.
    artikel = p["artikel_nr"].map(vereinheitliche_artikel_nr)
    stammdaten_abbruch(artikel.isna(), p["artikel_nr"], "artikel_nr", "Nr 19")
    kz["nr19_artikel_nr_geaendert"] = int((artikel != roh["artikel_nr"]).sum())
    p["artikel_nr"] = artikel

    # Dublette nach Vereinheitlichung (Nr 20, E-30): exakte Kopie entfernen und zählen.
    # Bleibt die Nummer danach doppelt (anderer Inhalt) -> Abbruch, keine stille Auswahl.
    dublette = p.duplicated()
    kz["dubletten"] = int(dublette.sum())
    p = p[~dublette]
    stammdaten_abbruch(p["artikel_nr"].duplicated(keep=False), p["artikel_nr"], "artikel_nr",
                       "E-30: gleiche Nummer, anderer Inhalt")

    # Listenpreis (Nr 21, Nr 22): None bleibt NULL (E-07), sonst '€' weg, Komma -> Punkt.
    # Mehr als 2 Nachkommastellen -> Abbruch: NUMERIC(12,2) würde sonst still runden.
    preis = p["preis"].map(parse_produktpreis)
    stammdaten_abbruch(p["preis"].notna() & preis.isna(), p["preis"], "preis", "Nr 22")
    zu_genau = preis.map(lambda x: x is not None and x.as_tuple().exponent < -2)
    stammdaten_abbruch(zu_genau, p["preis"], "preis", "mehr als 2 Nachkommastellen")
    kz["nr21_preis_fehlt"] = int(preis.isna().sum())
    kz["preis_mit_euro_oder_komma"] = int(p["preis"].fillna("").str.contains("€|,").sum())

    einheit = abbilden(p["einheit"], regeln.EINHEIT)
    stammdaten_abbruch(einheit.isna(), p["einheit"], "einheit", "Nr 23")
    aktiv = abbilden(p["aktiv"], regeln.AKTIV)
    stammdaten_abbruch(aktiv.isna(), p["aktiv"], "aktiv", "Nr 24")

    # Fehlender Lieferant -> 'Unbekannt' für Name UND Land (E-23). Jeder Fall wird protokolliert.
    fehlt = p["lieferant_name"].isna()
    for nr in p.loc[fehlt, "artikel_nr"]:
        aenderung(aend, "produkte", nr, "lieferant", "E-23", None, regeln.LIEFERANT_UNBEKANNT)
    lieferant = p["lieferant_name"].where(~fehlt, regeln.LIEFERANT_UNBEKANNT)
    land = abbilden(p["lieferant_land"], regeln.LIEFERANT_LAND).where(~fehlt, regeln.LIEFERANT_UNBEKANNT)
    stammdaten_abbruch(land.isna(), p["lieferant_land"], "lieferant_land", "Nr 27")

    # Pflichtfelder in dim_produkt (NOT NULL): leer -> Abbruch
    for spalte in ["bezeichnung", "kategorie_haupt", "kategorie_unter"]:
        stammdaten_abbruch(p[spalte].fillna("") == "", p[spalte], spalte, "NOT NULL in dim_produkt")

    # Großschreibung bleibt (E-28), nur Warnung
    gross = p["bezeichnung"].str.isupper()
    kz["nr25_bezeichnung_gross"] = int(gross.sum())
    for nr, wert in p.loc[gross, ["artikel_nr", "bezeichnung"]].itertuples(index=False):
        aenderung(aend, "produkte", nr, "bezeichnung", "E-28 Warnung: komplett groß", wert, wert)

    # Spaltennamen wie in dwh.dim_produkt
    sauber = pd.DataFrame({
        "artikel_nr": p["artikel_nr"],
        "bezeichnung": p["bezeichnung"],
        "kategorie": p["kategorie_haupt"],
        "unterkategorie": p["kategorie_unter"],
        "einheit": einheit,
        "listenpreis": preis,
        "lieferant": lieferant,
        "lieferant_land": land,
        "aktiv": aktiv,
    })
    kz["sauber"] = len(sauber)
    # Q-01 für Stammdaten: roh = sauber + Dubletten (rejected gibt es hier nicht, nur Abbruch)
    kontrollsumme(kz["roh"], kz["sauber"], kz["dubletten"], name="produkte")
    return {"sauber": sauber, "kennzahlen": kz, "aenderungen": aend}


# ========================================================================
# 3. Kunden und Kunden-Updates (stg.kunden, stg.kunden_update)
# ========================================================================
def bereinige_kunden(roh, quelle):
    """Bereinigt Kundenstamm oder Kunden-Update (gleiche Regeln). quelle = Name fürs Protokoll.

    Gibt dict mit sauber, kennzahlen, aenderungen zurück. Unbekannte Werte -> Abbruch.
    Das Zusammenführen von Stamm und Update (SCD 2, E-14, E-15) ist NICHT Teil davon
    (siehe etl/04_lade_dimensionen.py).
    """
    kz, aend = {"roh": len(roh)}, []

    # Exakte Dubletten (Nr 1, E-30): auf den Rohwerten, wie in explore/01_explore.py gezählt
    dublette = roh.duplicated()
    kz["dubletten"] = int(dublette.sum())
    k_roh = roh[~dublette]

    # Kennzahlen auf den Rohwerten ohne Dubletten (Basis k1 aus explore/01_explore.py)
    kz["nr3_kundentyp_uneinheitlich"] = int((~k_roh["kundentyp"].isin(["Gewerbe", "Privat"])).sum())
    ort_norm = k_roh["ort"].str.strip().str.lower()
    kz["nr4_ort_mehrere_schreibweisen"] = int((k_roh["ort"].groupby(ort_norm).transform("nunique") > 1).sum())
    # Abkürzungen/Umschriften = Mapping-Einträge, deren Schlüssel nicht der Zielname ist
    abkuerzungen = {s for s, ziel in regeln.ORT.items() if schluessel(ziel) != s}
    kz["nr5_ort_abkuerzung"] = int(ort_norm.isin(abkuerzungen).sum())
    kz["nr6_plz_leer"] = int((k_roh["plz"].str.strip() == "").sum())
    kz["nr7_plz_4stellig"] = int(k_roh["plz"].str.fullmatch(r"\d{4}").sum())
    kz["nr8_plz_praefix_d"] = int(k_roh["plz"].str.startswith("D-").sum())
    kz["nr9_plz_rand"] = int((k_roh["plz"] != k_roh["plz"].str.strip()).sum())
    kz["nr10_bundesland_schreibweise"] = int(k_roh["bundesland"].isin(["BW", "Baden-Wuerttemberg"]).sum())
    kz["nr16_vorname_leer"] = int((k_roh["vorname"].str.strip() == "").sum())
    kz["nr18_erstellt_am_nicht_iso"] = int((~k_roh["erstellt_am"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")).sum())

    k, kz["text_geaendert"] = text_bereinigen(k_roh)

    # Kundennummer: upper (Nr 34), Muster K + 4 Ziffern, eindeutig (E-30). Sonst Abbruch.
    kunden_nr = k["kunden_nr"].str.upper()
    stammdaten_abbruch(~kunden_nr.str.fullmatch(regeln.MUSTER_KUNDEN_NR), kunden_nr, "kunden_nr", "Nr 34")
    stammdaten_abbruch(kunden_nr.duplicated(keep=False), kunden_nr, "kunden_nr",
                       "E-30: gleiche Nummer, anderer Inhalt")

    kundentyp = abbilden(k["kundentyp"], regeln.KUNDENTYP)
    stammdaten_abbruch(kundentyp.isna(), k["kundentyp"], "kundentyp", "Nr 3")
    ort = abbilden(k["ort"], regeln.ORT)
    stammdaten_abbruch(ort.isna(), k["ort"], "ort", "Nr 4, Nr 5")

    # PLZ (Nr 6-9): Leerzeichen und 'D-' weg, 4-stellig -> führende Null.
    # Leer -> None (keine PLZ erfinden, E-26). Danach muss sie 5 Ziffern haben, sonst Abbruch.
    plz = k["plz"].str.replace(" ", "").str.removeprefix("D-")
    plz = plz.mask(plz.str.fullmatch(r"\d{4}"), plz.str.zfill(5))
    plz = plz.mask(plz == "", None)
    stammdaten_abbruch(plz.notna() & ~plz.fillna("").str.fullmatch(r"\d{5}"), k["plz"], "plz", "Nr 6-9")

    # Bundesland aus dem PLZ-Bereich (E-09, E-26). Unbekannter Bereich -> Abbruch.
    bundesland = plz.str[:2].map(regeln.PLZ_BEREICH_BUNDESLAND)
    stammdaten_abbruch(plz.notna() & bundesland.isna(), plz, "plz", "E-26: unbekannter PLZ-Bereich")

    # Ohne PLZ: Bundesland über den Ort aus den eigenen Daten (E-26). Der Ort muss
    # bei allen Kunden mit PLZ genau ein Bundesland haben, sonst Abbruch.
    ort_bundesland = bundesland[plz.notna()].groupby(ort[plz.notna()]).agg(lambda s: set(s))
    for i in k.index[plz.isna()]:
        laender = ort_bundesland.get(ort[i], set())
        if len(laender) != 1:
            raise ValueError(f"Abbruch (E-26): {kunden_nr[i]} ohne PLZ, Ort {ort[i]} hat Bundesländer {laender}")
        bundesland[i] = next(iter(laender))
        aenderung(aend, quelle, kunden_nr[i], "bundesland", "E-26 Warnung: keine PLZ, Bundesland über Ort",
                  k.at[i, "bundesland"], bundesland[i])

    # Bundesland aus der Datei nur vergleichen (Nr 46), nie übernehmen (E-09)
    datei = abbilden(k["bundesland"], regeln.BUNDESLAND_DATEI)
    abweichung = datei != bundesland
    kz["bundesland_abweichend"] = int(abweichung.sum())
    for i in k.index[abweichung]:
        aenderung(aend, quelle, kunden_nr[i], "bundesland", "E-09 Warnung: Datei passt nicht zur PLZ",
                  k.at[i, "bundesland"], bundesland[i])

    # erstellt_am (Nr 18, E-25): nicht lesbar -> Abbruch
    erstellt_am = k["erstellt_am"].map(parse_datum)
    stammdaten_abbruch(erstellt_am.isna(), k["erstellt_am"], "erstellt_am", "Nr 18, E-25")

    # Leerer Text wird NULL: '' -> None in optionalen Textspalten (Nr 16)
    leer_zu_null = {s: k[s].mask(k[s] == "", None) for s in ["firma", "vorname", "nachname"]}

    # Großschreibung bleibt (E-28), nur Warnung
    gross = k["nachname"].str.isupper()
    kz["nr17_nachname_gross"] = int(gross.sum())
    for i in k.index[gross]:
        aenderung(aend, quelle, kunden_nr[i], "nachname", "E-28 Warnung: komplett groß",
                  k.at[i, "nachname"], k.at[i, "nachname"])

    # Near Duplicates (Nr 2, E-06): gleicher Name + E-Mail, andere Nummer -> nur Warnung.
    # Die E-Mail wird nur hier zum Vergleich genutzt und danach nicht übernommen (R-03).
    name_mail = k["vorname"].str.lower() + "|" + k["nachname"].str.lower() + "|" + k["email"].str.lower()
    near = name_mail.duplicated(keep=False) & (k["email"] != "")
    kz["nr2_near_duplicates"] = int(near.sum())
    for i in k.index[near]:
        aenderung(aend, quelle, kunden_nr[i], "kunden_nr", "E-06 Warnung: möglicher Near Duplicate",
                  f"{k.at[i, 'vorname']} {k.at[i, 'nachname']}", kunden_nr[i])

    # Spalten wie in dwh.dim_kunde, ohne strasse/telefon/email (R-03).
    # Die SCD-2-Spalten (gueltig_von, gueltig_bis, ist_aktuell) setzt erst etl/04_lade_dimensionen.py.
    sauber = pd.DataFrame({
        "kunden_nr": kunden_nr,
        "kundentyp": kundentyp,
        "firma": leer_zu_null["firma"],
        "vorname": leer_zu_null["vorname"],
        "nachname": leer_zu_null["nachname"],
        "plz": plz,
        "ort": ort,
        "bundesland": bundesland,
        "erstellt_am": erstellt_am,
    })
    assert not set(regeln.KUNDEN_SPALTEN_NICHT_UEBERNEHMEN) & set(sauber.columns), "R-03 verletzt"
    kz["sauber"] = len(sauber)
    kontrollsumme(kz["roh"], kz["sauber"], kz["dubletten"], name=quelle)
    return {"sauber": sauber, "kennzahlen": kz, "aenderungen": aend}


# ========================================================================
# 4. Bestellungen (stg.bestellungen)
# ========================================================================
def bereinige_bestellungen(roh, produkte, kunden_nrn):
    """Bereinigt und validiert die Bestellpositionen.

    produkte  : sauberer Artikelstamm (Ergebnis von bereinige_produkte)
    kunden_nrn: alle bekannten Kundennummern (Stamm + Update, bereinigt)
    Gibt dict mit sauber, rejected, kennzahlen, aenderungen zurück.

    Eine Position wird abgewiesen, wenn mindestens eine Regel sie ablehnt. ALLE Gründe
    werden gesammelt und mit " | " verbunden (E-27). Abgewiesene Zeilen behalten ihre
    Originalwerte aus stg (nicht die bereinigten), damit man sie mit der Quelle vergleichen kann.
    """
    kz, aend = {"roh": len(roh)}, []

    # Exakte Dubletten (Nr 28, O-05): auf den Rohwerten entfernen und zählen
    dublette = roh.duplicated()
    kz["dubletten"] = int(dublette.sum())
    b_roh = roh[~dublette]
    kz["nach_dubletten"] = len(b_roh)
    b, kz["text_geaendert"] = text_bereinigen(b_roh)

    gruende = {i: [] for i in b.index}

    def ablehnen(maske, grund):
        for i in b.index[maske]:
            gruende[i].append(grund)

    def pos(i):
        return f"{b.at[i, 'bestell_nr']}/{b.at[i, 'position']}"

    # Schlüssel (E-20, P1, P2): Ziffern und eindeutig. Doppelter Schlüssel mit anderem
    # Inhalt hat keine Regel -> Abbruch statt stiller Auswahl.
    for spalte in ["bestell_nr", "position"]:
        ablehnen(~b[spalte].str.fullmatch(r"\d+"), f"unbekannter Wert in {spalte}")
    doppelt = b.duplicated(["bestell_nr", "position"], keep=False)
    if doppelt.any():
        raise ValueError(f"Abbruch (E-20): {int(doppelt.sum())} Positionen mit gleichem Schlüssel, anderem Inhalt")

    # --- Bestelldatum (Nr 29-32, E-02, E-03, E-25) ---------------------------
    datum = b["bestelldatum"].map(parse_datum)
    ungueltig = datum.isna()
    zukunft = datum.map(lambda d: d is not None and d > regeln.EXPORT_STICHTAG)
    kz["nr29_datum_nicht_iso"] = int((~b["bestelldatum"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")).sum())
    kz["nr30_datum_ungueltig"] = int(ungueltig.sum())
    kz["nr31_datum_zukunft"] = int(zukunft.sum())
    # Nr 32 wie in explore/01_explore.py gezählt: Positionen in Bestellungen mit mehr als einem lesbaren Datum
    kz["nr32_positionen_mehrere_daten"] = int((datum.groupby(b["bestell_nr"]).transform("nunique") > 1).sum())

    # Das Datum gehört zur Bestellung (E-03): pro Bestellung die Menge der GÜLTIGEN Daten.
    gueltig = datum.where(~(ungueltig | zukunft), None)
    kopf = gueltig.groupby(b["bestell_nr"]).agg(lambda s: {d for d in s if d is not None})
    # Zwei verschiedene gültige Daten in einer Bestellung: keine Regel entschieden
    # (Nr 32 "Mehrheitswert" ist nur ein Vorschlag) -> Abbruch, erwartet 0.
    mehrdeutig = kopf[kopf.map(len) > 1]
    if len(mehrdeutig):
        raise ValueError(f"Abbruch (E-03): Bestellungen mit mehreren gültigen Daten: {list(mehrdeutig.index)}")
    kopf_datum = kopf.map(lambda s: next(iter(s)) if s else None)
    bestelldatum = b["bestell_nr"].map(kopf_datum)
    ersetzt = (ungueltig | zukunft) & bestelldatum.notna()
    kz["datum_aus_bestellung"] = int(ersetzt.sum())
    for i in b.index[ersetzt]:
        aenderung(aend, "bestellungen", pos(i), "bestelldatum", "E-03", b.at[i, "bestelldatum"], bestelldatum[i])
    ablehnen(bestelldatum.isna(), "kein gültiges Bestelldatum in der Bestellung (E-03)")

    # --- Kunde (Nr 33-35, E-04) -----------------------------------------------
    kunden_nr = b["kunden_nr"].str.upper()
    kz["nr34_kunden_nr_klein"] = int(b["kunden_nr"].str.match(r"k").sum())
    leer = kunden_nr == ""
    unbekannt = ~leer & ~kunden_nr.isin(kunden_nrn)
    kz["nr33_kunde_leer"] = int(leer.sum())
    kz["nr35_kunde_unbekannt"] = int(unbekannt.sum())
    # Warum nicht rejected: Der Umsatz ist real (E-04). Zeile -1 über den Business Key 'UNBEKANNT' (E-21).
    for i in b.index[leer | unbekannt]:
        aenderung(aend, "bestellungen", pos(i), "kunden_nr", "E-04", b.at[i, "kunden_nr"], regeln.KUNDEN_NR_UNBEKANNT)
    kunden_nr = kunden_nr.mask(leer | unbekannt, regeln.KUNDEN_NR_UNBEKANNT)
    kz["kunde_unbekannt_gesamt"] = int((kunden_nr == regeln.KUNDEN_NR_UNBEKANNT).sum())

    # --- Produkt (Nr 36, Nr 37) -----------------------------------------------
    artikel_nr = b["artikel_nr"].map(vereinheitliche_artikel_nr)
    kz["nr36_artikel_nr_format"] = int((~b_roh["artikel_nr"].str.fullmatch(r"A-\d{3}")).sum())
    ablehnen(artikel_nr.isna(), "unbekannter Wert in artikel_nr")
    produkt_fehlt = artikel_nr.notna() & ~artikel_nr.isin(produkte["artikel_nr"])
    kz["nr37_produkt_unbekannt"] = int(produkt_fehlt.sum())
    ablehnen(produkt_fehlt, "Produkt existiert nicht (Nr 37)")

    # --- Menge (Nr 38, Nr 39, E-05) -------------------------------------------
    ganzzahl = b["menge"].str.fullmatch(r"-?\d+")
    ablehnen(~ganzzahl, "unbekannter Wert in menge")
    menge = b["menge"].where(ganzzahl).map(lambda w: int(w) if isinstance(w, str) else None)
    negativ = menge.map(lambda m: m is not None and m < 0)
    null = menge.map(lambda m: m == 0)
    kz["nr38_menge_negativ"], kz["nr39_menge_null"] = int(negativ.sum()), int(null.sum())
    ablehnen(negativ, "Menge negativ (E-05)")
    ablehnen(null, "Menge 0 (E-05)")

    # --- Einzelpreis (Nr 40, Nr 41, E-07, E-29) -------------------------------
    preis_leer = b["einzelpreis"] == ""
    preis = b["einzelpreis"].map(parse_dezimal)
    kz["nr40_preis_leer"] = int(preis_leer.sum())
    kz["nr41_preis_komma"] = int(b["einzelpreis"].str.contains(",").sum())
    ablehnen(~preis_leer & preis.isna(), "unbekannter Wert in einzelpreis")
    preis_negativ = preis.map(lambda x: x is not None and x < 0)
    kz["preis_negativ"] = int(preis_negativ.sum())
    ablehnen(preis_negativ, "Einzelpreis negativ (E-29)")
    # Fehlender Preis -> Listenpreis + Kennzeichen, sonst rejected (E-07)
    listenpreis = artikel_nr.map(produkte.set_index("artikel_nr")["listenpreis"])
    aus_liste = preis_leer & listenpreis.notna()
    kz["e07_listenpreis_uebernommen"] = int(aus_liste.sum())
    kz["e07_kein_listenpreis"] = int((preis_leer & ~produkt_fehlt & artikel_nr.notna() & listenpreis.isna()).sum())
    ablehnen(preis_leer & ~produkt_fehlt & artikel_nr.notna() & listenpreis.isna(),
             "kein Einzelpreis und kein Listenpreis (E-07)")
    ablehnen(preis_leer & (produkt_fehlt | artikel_nr.isna()), "kein Einzelpreis, Produkt unbekannt (E-07)")
    for i in b.index[aus_liste]:
        aenderung(aend, "bestellungen", pos(i), "einzelpreis", "E-07 Listenpreis", "", listenpreis[i])
    einzelpreis = preis.where(~aus_liste, listenpreis)

    # --- Rabatt (Nr 42, Nr 43, E-08, E-29) ------------------------------------
    rabatt_leer = b["rabatt_prozent"] == ""
    kz["nr42_rabatt_leer"] = int(rabatt_leer.sum())
    kz["nr43_rabatt_komma"] = int(b["rabatt_prozent"].str.contains(",").sum())
    rabatt = b["rabatt_prozent"].mask(rabatt_leer, regeln.RABATT_WENN_LEER).map(parse_dezimal)
    ablehnen(rabatt.isna(), "unbekannter Wert in rabatt_prozent")
    ausserhalb = rabatt.map(lambda x: x is not None and not (0 <= x <= 100))
    kz["rabatt_ausserhalb"] = int(ausserhalb.sum())
    ablehnen(ausserhalb, "Rabatt außerhalb 0-100 (E-29)")

    # --- Zahlungsart und Lieferstatus (Nr 44, Nr 45, E-12, E-18) --------------
    zahlungsart = abbilden(b["zahlungsart"], regeln.ZAHLUNGSART)
    ablehnen(zahlungsart.isna(), "unbekannter Wert in zahlungsart")
    lieferstatus = b["lieferstatus"].str.lower()
    lieferstatus = lieferstatus.where(lieferstatus.isin(regeln.LIEFERSTATUS), None)
    ablehnen(lieferstatus.isna(), "unbekannter Wert in lieferstatus")
    kz["zahlungsart_werte"] = zahlungsart.value_counts().to_dict()
    kz["lieferstatus_werte"] = lieferstatus.value_counts().to_dict()

    # --- Kopf-Prüfung (E-03, E-29): ein Kunde, eine Zahlungsart pro Bestellung -> nur Warnung
    for spalte, werte in [("kunden_nr", kunden_nr), ("zahlungsart", zahlungsart)]:
        mehrere = werte.groupby(b["bestell_nr"]).nunique() > 1
        kz[f"kopf_mehrere_{spalte}"] = int(mehrere.sum())
        for bestell_nr in mehrere[mehrere].index:
            aenderung(aend, "bestellungen", bestell_nr, spalte, "E-29 Warnung: mehrere Werte pro Bestellung", "", "")

    # --- Aufteilen in sauber / rejected ---------------------------------------
    grund = pd.Series({i: " | ".join(g) for i, g in gruende.items()})
    abgewiesen = grund != ""
    rejected = b_roh[abgewiesen].copy()
    rejected["grund"] = grund[abgewiesen]
    kz["gruende"] = pd.Series([g for liste in gruende.values() for g in liste]).value_counts().to_dict()

    sauber = pd.DataFrame({
        "bestell_nr": b["bestell_nr"],
        "position": b["position"],
        "bestelldatum": bestelldatum,
        "kunden_nr": kunden_nr,
        "artikel_nr": artikel_nr,
        "menge": menge,
        "einzelpreis": einzelpreis,
        "rabatt_prozent": rabatt,
        "zahlungsart": zahlungsart,
        "lieferstatus": lieferstatus,
        "preis_aus_listenpreis": aus_liste,
    })[~abgewiesen]
    sauber["bestell_nr"] = sauber["bestell_nr"].astype(int)
    sauber["position"] = sauber["position"].astype(int)
    kz["sauber"], kz["rejected"] = len(sauber), len(rejected)
    kz["sauber_listenpreis"] = int(sauber["preis_aus_listenpreis"].sum())

    # Q-01: roh = sauber + rejected + Dubletten. Bei Abweichung AssertionError -> Abbruch.
    kontrollsumme(kz["roh"], kz["sauber"], kz["rejected"] + kz["dubletten"], name="bestellungen (Q-01)")
    return {"sauber": sauber, "rejected": rejected, "kennzahlen": kz, "aenderungen": aend}


# ========================================================================
# 5. Lesen aus stg und Protokolle
# ========================================================================
def verbindung_aufbauen():
    """SQLAlchemy-Engine aus db_config.ini (gleich wie etl/01_lade_staging.py). Passwort wird nie ausgegeben."""
    import configparser
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    if not CONFIG_DATEI.exists():
        raise FileNotFoundError(f"{CONFIG_DATEI} fehlt. Vorlage: db_config.example.ini")
    konfig = configparser.ConfigParser()
    konfig.read(CONFIG_DATEI, encoding="utf-8")
    db = konfig["postgres"]
    url = URL.create("postgresql+psycopg", username=db["user"], password=db["password"],
                     host=db["host"], port=int(db["port"]), database=db["dbname"])
    return create_engine(url)


def lese_staging(engine, tabelle):
    """Liest stg.<tabelle> ohne die technischen Spalten, sortiert über alle Spalten.

    Warum ORDER BY über alle Spalten: stg hat keine Zeilennummer. Ohne feste Reihenfolge
    könnte jeder Lauf die rejected-Datei anders sortieren (Q-05).
    Text bleibt Text (stg ist nur TEXT, E-10), NULL wird None.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        spalten = [z[0] for z in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'stg' AND table_name = :t AND column_name NOT LIKE '\\_%' "
            "ORDER BY ordinal_position"), {"t": tabelle})]
        liste = ", ".join(spalten)
        # Tabellen- und Spaltennamen stammen aus information_schema, nicht von außen -> f-String zulässig
        df = pd.read_sql(text(f"SELECT {liste} FROM stg.{tabelle} ORDER BY {liste}"), conn)
    return df.reset_index(drop=True)


def lese_kunden_updates(engine):
    """Liest stg.kunden_update getrennt nach Datei, in Datumsreihenfolge (E-43).

    Gibt eine Liste [{"datei", "gueltig_von", "roh"}] zurück, sortiert nach gueltig_von.
    roh wie lese_staging(): nur Fachspalten, Text, sortiert über alle Spalten (Q-05).
    gueltig_von kommt aus dem Dateinamen (etl/kunden_updates.py, eine Stelle für die Regel).
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        spalten = [z[0] for z in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'stg' AND table_name = 'kunden_update' AND column_name NOT LIKE '\\_%' "
            "ORDER BY ordinal_position"))]
        liste = ", ".join(spalten)
        dateien = [z[0] for z in conn.execute(text(
            "SELECT DISTINCT _source_file FROM stg.kunden_update ORDER BY 1"))]
        updates = []
        for datei in dateien:
            roh = pd.read_sql(text(f"SELECT {liste} FROM stg.kunden_update WHERE _source_file = :d "
                                   f"ORDER BY {liste}"), conn, params={"d": datei})
            updates.append({"datei": datei, "gueltig_von": kunden_updates.gueltig_von_aus_dateiname(datei),
                            "roh": roh.reset_index(drop=True)})
    return sorted(updates, key=lambda u: u["gueltig_von"])


def bereinige_kunden_updates(updates):
    """Bereinigt jede Update-Datei einzeln mit bereinige_kunden() (gleiche Regeln wie bisher).

    Einzeln, weil derselbe Kunde in mehreren Dateien stehen darf (E-30 gilt je Datei).
    Gibt (Liste [{"datei", "gueltig_von", "sauber"}], gesamt) zurück. gesamt hat die Form von
    bereinige_kunden(): Kennzahlen summiert, sauber und aenderungen aneinandergehängt.
    Mit einer Datei ist gesamt genau das Ergebnis von bereinige_kunden() für diese Datei.
    """
    je_datei, ergebnisse = [], []
    for u in updates:
        e = bereinige_kunden(u["roh"], "kunden_update")
        ergebnisse.append(e)
        je_datei.append({"datei": u["datei"], "gueltig_von": u["gueltig_von"], "sauber": e["sauber"]})
    if len(ergebnisse) == 1:
        return je_datei, ergebnisse[0]
    gesamt = {"sauber": pd.concat([e["sauber"] for e in ergebnisse], ignore_index=True) if ergebnisse
              else pd.DataFrame(columns=["kunden_nr"]),
              "aenderungen": [a for e in ergebnisse for a in e["aenderungen"]],
              "kennzahlen": {}}
    for e in ergebnisse:
        for k, v in e["kennzahlen"].items():
            if isinstance(v, (int, float)):
                gesamt["kennzahlen"][k] = gesamt["kennzahlen"].get(k, 0) + v
    return je_datei, gesamt


def protokoll_anhaengen(pfad, kopf, zeilen):
    """Hängt Zeilen an eine CSV in logs/ an (alte Läufe bleiben erhalten)."""
    pfad.parent.mkdir(exist_ok=True)
    neu = not pfad.exists()
    with open(pfad, "a", newline="", encoding="utf-8") as f:
        schreiber = csv.writer(f, delimiter=";")
        if neu:
            schreiber.writerow(kopf)
        schreiber.writerows(zeilen)


def schreibe_rejected_csv(rejected):
    """Schreibt die abgewiesenen Bestellpositionen nach data/rejected/bestellungen_rejected.csv.

    Eine Funktion für beide Aufrufer (E-42): etl/03 main() (Trockenlauf) und etl/05 (nach dem COMMIT).
    rejected mit Originalwerten und Spalte grund (Q-02). Wird bei jedem Lauf neu geschrieben:
    gleicher Inhalt bei gleichen Daten (Q-05). utf-8-sig, damit Excel die Umlaute richtig zeigt.
    Prüfung: grund nie leer, sonst AssertionError -> Abbruch.
    Gibt den Pfad der Datei zurück.
    """
    REJECTED_ORDNER.mkdir(parents=True, exist_ok=True)
    rejected_datei = REJECTED_ORDNER / "bestellungen_rejected.csv"
    rejected.to_csv(rejected_datei, sep=";", index=False, encoding="utf-8-sig")
    assert (rejected["grund"] != "").all(), "Q-02: Grund leer"
    return rejected_datei


# ========================================================================
# 6. Trockenlauf: bereinigen, Soll/Ist, Protokolle. KEIN Schreiben in dwh.
# ========================================================================
def soll_ist_bericht(e):
    """Vergleicht die Kennzahlen mit den Zahlen aus den Dokumenten.

    Soll = docs/data_quality_issues.md (Basis ohne exakte Dubletten), E-07, E-12, P9.
    Eine Abweichung bricht NICHT ab: Sie wird angezeigt und muss erklärt werden.
    """
    ergebnisse = []
    b, k, u, p = (e[q]["kennzahlen"] for q in ["bestellungen", "kunden", "kunden_update", "produkte"])
    pruefungen = [
        ("B", "bestellungen roh", 2181, b["roh"]),
        (28, "exakte Dubletten (O-05)", 25, b["dubletten"]),
        ("B", "nach Dubletten", 2156, b["nach_dubletten"]),
        (29, "Datum nicht ISO", 997, b["nr29_datum_nicht_iso"]),
        (30, "Datum ungültig", 1, b["nr30_datum_ungueltig"]),
        (31, "Datum Zukunft", 2, b["nr31_datum_zukunft"]),
        (32, "Positionen mit mehreren Daten", 8, b["nr32_positionen_mehrere_daten"]),
        (33, "kunden_nr leer -> -1", 42, b["nr33_kunde_leer"]),
        (34, "kunden_nr klein", 69, b["nr34_kunden_nr_klein"]),
        (35, "Kunde unbekannt -> -1", 33, b["nr35_kunde_unbekannt"]),
        ("E-04", "Kunde -1 gesamt", 75, b["kunde_unbekannt_gesamt"]),
        (36, "artikel_nr Format", 95, b["nr36_artikel_nr_format"]),
        (37, "Produkt unbekannt", 11, b["nr37_produkt_unbekannt"]),
        (38, "Menge negativ", 40, b["nr38_menge_negativ"]),
        (39, "Menge 0", 17, b["nr39_menge_null"]),
        (40, "Einzelpreis leer", 56, b["nr40_preis_leer"]),
        ("E-07", "Listenpreis übernommen (P9)", 49, b["e07_listenpreis_uebernommen"]),
        ("E-07", "kein Listenpreis -> rejected (P9)", 7, b["e07_kein_listenpreis"]),
        (41, "Einzelpreis mit Komma", 2100, b["nr41_preis_komma"]),
        (42, "Rabatt leer -> 0", 324, b["nr42_rabatt_leer"]),
        (43, "Rabatt mit Komma", 304, b["nr43_rabatt_komma"]),
        ("E-29", "Rabatt außerhalb 0-100", 0, b["rabatt_ausserhalb"]),
        ("E-29", "Einzelpreis negativ", 0, b["preis_negativ"]),
        ("E-29", "Bestellungen mit >1 Kunde", 0, b["kopf_mehrere_kunden_nr"]),
        ("E-29", "Bestellungen mit >1 Zahlungsart", 0, b["kopf_mehrere_zahlungsart"]),
        ("E-12", "geliefert", 1083, b["lieferstatus_werte"].get("geliefert", 0)),
        ("E-12", "offen", 369, b["lieferstatus_werte"].get("offen", 0)),
        ("E-12", "storniert", 353, b["lieferstatus_werte"].get("storniert", 0)),
        ("E-12", "teilgeliefert", 351, b["lieferstatus_werte"].get("teilgeliefert", 0)),
        ("P8", "Zahlungsarten nach Mapping", 4, len(b["zahlungsart_werte"])),
        ("K", "kunden roh", 157, k["roh"]),
        (1, "kunden exakte Dubletten (E-30)", 4, k["dubletten"]),
        (2, "Near Duplicates (E-06)", 18, k["nr2_near_duplicates"]),
        (3, "kundentyp uneinheitlich", 84, k["nr3_kundentyp_uneinheitlich"]),
        (4, "ort mehrere Schreibweisen", 105, k["nr4_ort_mehrere_schreibweisen"]),
        (5, "ort Abkürzung/Umschrift", 33, k["nr5_ort_abkuerzung"]),
        (6, "plz leer", 2, k["nr6_plz_leer"]),
        (7, "plz 4-stellig", 20, k["nr7_plz_4stellig"]),
        (8, "plz 'D-'", 7, k["nr8_plz_praefix_d"]),
        (9, "plz Leerzeichen am Rand", 6, k["nr9_plz_rand"]),
        (10, "bundesland Schreibweise", 69, k["nr10_bundesland_schreibweise"]),
        ("E-26", "kunden: Bundesland Datei != PLZ", 0, k["bundesland_abweichend"]),
        (16, "vorname leer", 3, k["nr16_vorname_leer"]),
        (17, "nachname komplett groß (E-28)", 2, k["nr17_nachname_gross"]),
        (18, "erstellt_am nicht ISO", 70, k["nr18_erstellt_am_nicht_iso"]),
        ("U", "kunden_update roh", 20, u["roh"]),
        (46, "Update: Bundesland Datei != PLZ", 4, u["bundesland_abweichend"]),
        ("P", "produkte roh", 25, p["roh"]),
        (19, "artikel_nr vereinheitlicht", 1, p["nr19_artikel_nr_geaendert"]),
        (20, "Dublette nach Normalisierung (E-30)", 1, p["dubletten"]),
        (21, "Listenpreis fehlt (ohne Dublette)", 4, p["nr21_preis_fehlt"]),
        (23, "einheit uneinheitlich", 18, p["nr23_einheit_uneinheitlich"]),
        (24, "aktiv nicht true", 8, p["nr24_aktiv_nicht_true"]),
        (25, "bezeichnung komplett groß (E-28)", 4, p["nr25_bezeichnung_gross"]),
        (26, "Lieferant fehlt -> Unbekannt (E-23)", 3, p["nr26_lieferant_fehlt"]),
        (27, "Land nicht DE", 12, p["nr27_land_nicht_de"]),
    ]
    for nr, thema, soll, ist in pruefungen:
        vergleiche(ergebnisse, nr, thema, soll, ist)
    return pd.DataFrame(ergebnisse)


def main():
    print("=" * 78)
    print("Bereinigung und Validierung stg.* (TROCKENLAUF, kein Schreiben in dwh)")
    print("=" * 78)
    engine = verbindung_aufbauen()
    stg = {t: lese_staging(engine, t) for t in ["bestellungen", "kunden", "produkte"]}
    # Kunden-Updates: alle Dateien aus stg.kunden_update, je Datei bereinigt (E-43)
    _, update_gesamt = bereinige_kunden_updates(lese_kunden_updates(engine))

    # Reihenfolge: erst Stammdaten, denn die Bestellungen brauchen Produkte und Kundennummern
    e = {"produkte": bereinige_produkte(stg["produkte"]),
         "kunden": bereinige_kunden(stg["kunden"], "kunden"),
         "kunden_update": update_gesamt}
    # Bekannte Kunden = Stamm + Update (neue Kunden K0160-K0164 stehen nur im Update)
    kunden_nrn = set(e["kunden"]["sauber"]["kunden_nr"]) | set(e["kunden_update"]["sauber"]["kunden_nr"])
    e["bestellungen"] = bereinige_bestellungen(stg["bestellungen"], e["produkte"]["sauber"], kunden_nrn)

    print("\n--- Soll/Ist ---")
    bericht = soll_ist_bericht(e)

    kb = e["bestellungen"]["kennzahlen"]
    print("\n--- Ablehnungsgründe (E-27, eine Zeile kann mehrere haben) ---")
    for grund, anzahl in kb["gruende"].items():
        print(f"  {anzahl:>4}  {grund}")
    print(f"\nbestellungen: roh {kb['roh']} = sauber {kb['sauber']} + rejected {kb['rejected']} "
          f"+ Dubletten {kb['dubletten']}")
    print(f"preis_aus_listenpreis = TRUE in den sauberen Zeilen: {kb['sauber_listenpreis']}")

    rejected_datei = schreibe_rejected_csv(e["bestellungen"]["rejected"])
    print(f"rejected: {rejected_datei} ({kb['rejected']} Zeilen)")

    zeitpunkt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    abweichungen = int((bericht["Status"] != "passt").sum())
    protokoll_anhaengen(
        PROTOKOLL_DATEI,
        ["zeitpunkt", "quelle", "roh", "dubletten", "sauber", "rejected", "soll_ist_abweichungen", "lauf"],
        [[zeitpunkt, q, e[q]["kennzahlen"]["roh"], e[q]["kennzahlen"]["dubletten"],
          e[q]["kennzahlen"]["sauber"], e[q]["kennzahlen"].get("rejected", 0), abweichungen, "Trockenlauf"]
         for q in ["produkte", "kunden", "kunden_update", "bestellungen"]])
    alle_aenderungen = [a for q in e for a in e[q]["aenderungen"]]
    protokoll_anhaengen(
        AENDERUNGEN_DATEI,
        ["zeitpunkt", "quelle", "schluessel", "spalte", "regel", "wert_alt", "wert_neu"],
        [[zeitpunkt, a["quelle"], a["schluessel"], a["spalte"], a["regel"], a["wert_alt"], a["wert_neu"]]
         for a in alle_aenderungen])
    print(f"Protokolle: {PROTOKOLL_DATEI.name}, {AENDERUNGEN_DATEI.name} ({len(alle_aenderungen)} Einträge)")
    print(f"\nSoll/Ist: {len(bericht) - abweichungen} passt, {abweichungen} weicht ab")
    return e, bericht


if __name__ == "__main__":
    main()
