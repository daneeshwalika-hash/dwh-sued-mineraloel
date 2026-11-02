"""
explore/01_explore.py

Zweck      : Datenexploration (Data Profiling) der Rohdaten. Die Rohdaten werden nur GELESEN,
             Qualitätsprobleme werden gefunden und gezählt. Nichts wird bereinigt oder gelöscht;
             die Bereinigung steht in etl/03_bereinige_quellen.py.
Eingabe    : data/raw/kunden.csv, bestellungen.csv, kunden_update_2026-01.csv, produkte.json (nur lesen, R-02)
Ausgabe    : docs/data_quality_issues.csv  (Tabelle aller gefundenen Probleme mit Anzahl und Beispielen)
             docs/data_quality_issues.md   (dieselbe Tabelle als Markdown)
Anforderung: Grundlage für Q-04 (jede Bereinigungsregel ist dokumentiert)
Bezug      : E-02, E-06; die Nummern Nr 1-47 in docs/data_quality_issues.md
Aufruf     : .venv\\Scripts\\python.exe explore\\01_explore.py
             Erwartet: Konsolenbericht, am Ende "7) 47 Probleme gefunden", Exit 0.
"""
import json
from pathlib import Path

import pandas as pd

from plz_pruefung import ORT_ABK, pruefe_plz_bereich   # explore/plz_pruefung.py

# ---------------------------------------------------------------------------
# 0) Pfade relativ zum Projektordner
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
DOCS = BASE / "docs"

# Stichtag des Exports (steht in produkte.json -> "export_datum")
EXPORT_DATUM = pd.Timestamp("2026-01-05")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


# ---------------------------------------------------------------------------
# 1) Einlesen: ALLES als Text, damit pandas nichts umwandelt.
#    Leere Felder bleiben "" und werden nicht zu NaN.
# ---------------------------------------------------------------------------
def lade_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / name, sep=";", dtype=str, keep_default_na=False, encoding="utf-8")


kunden = lade_csv("kunden.csv")
bestellungen = lade_csv("bestellungen.csv")
kunden_update = lade_csv("kunden_update_2026-01.csv")

with open(RAW / "produkte.json", encoding="utf-8") as f:
    produkte_roh = json.load(f)
# Verschachtelte Felder werden zu Spalten, z. B. "kategorie.haupt"
produkte = pd.json_normalize(produkte_roh["artikel"])

print("=" * 80)
print("1) Größe der Dateien")
for name, df in [("kunden", kunden), ("bestellungen", bestellungen),
                 ("kunden_update", kunden_update), ("produkte", produkte)]:
    print(f"   {name:15s} {df.shape[0]:5d} Zeilen, {df.shape[1]:2d} Spalten")


# ---------------------------------------------------------------------------
# 2) Hilfsfunktionen
# ---------------------------------------------------------------------------
issues = []   # jedes gefundene Problem als Dictionary


def melde(datei: str, spalte: str, problem: str, maske: pd.Series, werte: pd.Series,
          vorschlag: str) -> None:
    """Ein Problem mit Anzahl und bis zu 4 Beispielwerten notieren."""
    anzahl = int(maske.sum())
    if anzahl == 0:
        return
    beispiele = werte[maske].astype(str).drop_duplicates().head(4).tolist()
    issues.append({
        "datei": datei,
        "spalte": spalte,
        "problem": problem,
        "anzahl": anzahl,
        "beispiele": " | ".join(repr(b) for b in beispiele),
        "loesungsvorschlag": vorschlag,
    })


def datumsformat(s: pd.Series) -> pd.Series:
    """Ersetzt jede Ziffer durch 9 und zeigt so das Muster: '15.06.2021' -> '99.99.9999'."""
    return s.str.replace(r"\d", "9", regex=True)


def parse_datum(s: pd.Series) -> pd.Series:
    """Nur zum Prüfen: jedes bekannte Format ausdrücklich parsen (kein format='mixed')."""
    ergebnis = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    formate = [
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),     # ISO
        (r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y"),   # deutsch
        (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y"),     # US-Format (siehe Prüfung in Abschnitt 5)
        (r"\d{2}\.\d{2}\.\d{2}", "%d.%m.%y"),   # deutsch, 2-stelliges Jahr
    ]
    for muster, fmt in formate:
        treffer = s.str.fullmatch(muster)
        ergebnis[treffer] = pd.to_datetime(s[treffer], format=fmt, errors="coerce")
    return ergebnis


# ---------------------------------------------------------------------------
# 3) kunden.csv
# ---------------------------------------------------------------------------
print("=" * 80)
print("3) kunden.csv")
k = kunden

melde("kunden.csv", "(ganze Zeile)", "exakte Dublette",
      k.duplicated(), k["kunden_nr"], "drop_duplicates() + Anzahl protokollieren")

k1 = k.drop_duplicates()   # Basis für die weiteren Prüfungen: ohne exakte Dubletten
melde("kunden.csv", "kunden_nr", "Business Key nach Entfernen exakter Dubletten nicht eindeutig",
      k1["kunden_nr"].duplicated(keep=False), k1["kunden_nr"], "prüfen, ggf. rejected")

# Near Duplicates: gleiche Person (Vorname + Nachname + E-Mail), aber andere kunden_nr
schluessel = (k1["vorname"].str.strip().str.lower() + "|" + k1["nachname"].str.strip().str.lower()
              + "|" + k1["email"].str.strip().str.lower())
near = schluessel.duplicated(keep=False) & (k1["email"].str.strip() != "")
melde("kunden.csv", "kunden_nr", "mögliche Near Duplicates (gleicher Name + E-Mail, andere Nummer)",
      near, k1["kunden_nr"] + " " + k1["vorname"] + " " + k1["nachname"],
      "NICHT automatisch zusammenführen, als Warnung protokollieren (siehe Entscheidung E-06)")

typ = k1["kundentyp"]
melde("kunden.csv", "kundentyp", "uneinheitliche Schreibweise",
      ~typ.isin(["Gewerbe", "Privat"]), typ, "Mapping: G/gewerbe -> Gewerbe, P/privat -> Privat")

ort = k1["ort"]
ort_norm = ort.str.strip().str.lower()
anzahl_varianten = ort.groupby(ort_norm).transform("nunique")
melde("kunden.csv", "ort", "gleiche Stadt in mehreren Schreibweisen (Groß/klein, Leerzeichen)",
      anzahl_varianten > 1, ort, "strip() + Mapping-Tabelle auf offiziellen Ortsnamen")
# ORT_ABK (Abkürzung -> offizieller Ortsname) steht in explore/plz_pruefung.py
melde("kunden.csv", "ort", "Abkürzung / Umschrift statt Ortsname",
      ort_norm.isin(ORT_ABK.keys()),
      ort, "Mapping: Stgt. -> Stuttgart, Boeblingen -> Böblingen usw.")

plz = k1["plz"]
melde("kunden.csv", "plz", "leer", plz.str.strip() == "", plz, "aus Ort ableiten oder NULL + Warnung")
melde("kunden.csv", "plz", "führende Null fehlt (4-stellig)", plz.str.fullmatch(r"\d{4}"), plz, "zfill(5)")
melde("kunden.csv", "plz", "Länderpräfix 'D-'", plz.str.startswith("D-"), plz, "Präfix entfernen")
melde("kunden.csv", "plz", "Leerzeichen am Rand", plz != plz.str.strip(), plz, "strip()")

land = k1["bundesland"]
melde("kunden.csv", "bundesland", "uneinheitlich (BW, Wuerttemberg mit ue)",
      land.isin(["BW", "Baden-Wuerttemberg"]), land, "Mapping auf 'Baden-Württemberg'")

tel = k1["telefon"]
melde("kunden.csv", "telefon", "leer", tel.str.strip() == "", tel, "NULL erlauben")
melde("kunden.csv", "telefon", "Format nicht einheitlich (0049, +49, /, -)",
      tel.str.contains(r"^0049|^\+49|/|-", regex=True), tel, "Regex -> +49 7031 123456")

mail = k1["email"]
melde("kunden.csv", "email", "leer", mail.str.strip() == "", mail, "NULL erlauben")
melde("kunden.csv", "email", "ungültig (kein @ oder keine Domain-Endung)",
      (mail.str.strip() != "") & ~mail.str.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}"),
      mail, "Regex-Prüfung, ungültig -> NULL + Warnung")
melde("kunden.csv", "email", "Großbuchstaben", mail != mail.str.lower(), mail, "lower()")

melde("kunden.csv", "vorname", "leer", k1["vorname"].str.strip() == "", k1["kunden_nr"], "NULL erlauben")
melde("kunden.csv", "nachname", "komplett in Großbuchstaben",
      k1["nachname"].str.isupper(), k1["nachname"], "title() – Achtung bei 'von', 'Mc' usw.")

melde("kunden.csv", "erstellt_am", "mehrere Datumsformate (nicht ISO)",
      datumsformat(k1["erstellt_am"]) != "9999-99-99", k1["erstellt_am"],
      "jedes Format explizit parsen -> DATE")
print(datumsformat(k1["erstellt_am"]).value_counts().to_string())


# ---------------------------------------------------------------------------
# 4) produkte.json
# ---------------------------------------------------------------------------
print("=" * 80)
print("4) produkte.json")
p = produkte
art = p["artikel_nr"].astype(str)
melde("produkte.json", "artikel_nr", "Format abweichend (klein / Leerzeichen)",
      ~art.str.fullmatch(r"A-\d{3}"), art, "strip().upper()")
melde("produkte.json", "artikel_nr", "Dublette nach Normalisierung",
      art.str.strip().str.upper().duplicated(keep=False), art, "nur einen Datensatz behalten + protokollieren")

preis = p["preis"]
melde("produkte.json", "preis", "fehlt (null)", preis.isna(), art, "NULL, Preis kommt aus der Bestellung")
melde("produkte.json", "preis", "als Text statt Zahl ('1,74 €' oder '1.62')",
      preis.apply(lambda x: isinstance(x, str)), preis, "€ entfernen, Komma -> Punkt, float()")

melde("produkte.json", "einheit", "uneinheitlich",
      ~p["einheit"].isin(["L", "Stück", "kg"]), p["einheit"], "Mapping: l/ltr/Liter -> L, Stk/pcs -> Stück")
melde("produkte.json", "aktiv", "Typ gemischt (true / 1 / 'ja')",
      ~p["aktiv"].apply(lambda x: x is True), p["aktiv"], "auf bool mappen")
melde("produkte.json", "bezeichnung", "komplett in Großbuchstaben",
      p["bezeichnung"].str.isupper(), p["bezeichnung"], "Schreibweise prüfen (ATF/AdBlue sind Eigennamen!)")
melde("produkte.json", "lieferant", "Lieferant fehlt komplett",
      p["lieferant.name"].isna(), art, "'Unbekannt' oder NULL")
melde("produkte.json", "lieferant.land", "uneinheitlich (DE / Deutschland / Germany)",
      p["lieferant.land"].notna() & (p["lieferant.land"] != "DE"), p["lieferant.land"], "ISO-Code 'DE'")


# ---------------------------------------------------------------------------
# 5) bestellungen.csv
# ---------------------------------------------------------------------------
print("=" * 80)
print("5) bestellungen.csv")
b = bestellungen
melde("bestellungen.csv", "(ganze Zeile)", "exakte Dublette",
      b.duplicated(), b["bestell_nr"] + "/" + b["position"], "drop_duplicates() + protokollieren")
b1 = b.drop_duplicates()
melde("bestellungen.csv", "bestell_nr+position", "Schlüssel nach Dubletten-Entfernung nicht eindeutig",
      b1.duplicated(["bestell_nr", "position"], keep=False), b1["bestell_nr"], "prüfen")

datum = parse_datum(b1["bestelldatum"])
melde("bestellungen.csv", "bestelldatum", "mehrere Datumsformate (nicht ISO)",
      datumsformat(b1["bestelldatum"]) != "9999-99-99", b1["bestelldatum"], "jedes Format explizit parsen")
melde("bestellungen.csv", "bestelldatum", "ungültiges Datum (existiert nicht)",
      datum.isna(), b1["bestelldatum"], "aus anderen Positionen derselben Bestellung übernehmen, sonst rejected")
melde("bestellungen.csv", "bestelldatum", f"Datum in der Zukunft (nach Export {EXPORT_DATUM.date()})",
      datum > EXPORT_DATUM, b1["bestelldatum"], "aus anderen Positionen derselben Bestellung übernehmen")

# Beleg für das Format MM/DD/YYYY: Der erste Teil ist nie > 12, der zweite oft.
slash = b1["bestelldatum"][b1["bestelldatum"].str.contains("/")].str.split("/", expand=True).astype(int)
print(f"   Format xx/yy/yyyy: {len(slash)} Werte | erster Teil > 12: {(slash[0] > 12).sum()} "
      f"| zweiter Teil > 12: {(slash[1] > 12).sum()}  -> es ist MM/DD/YYYY (US)")

# Das Datum gehört zur Bestellung: Hat eine Bestellung mehrere verschiedene Daten?
mehrere_daten = datum.groupby(b1["bestell_nr"]).transform("nunique") > 1
melde("bestellungen.csv", "bestelldatum", "Bestellung hat in ihren Positionen verschiedene Daten",
      mehrere_daten, b1["bestell_nr"], "Datum ist Attribut der Bestellung (Kopf) -> Mehrheitswert")

kn = b1["kunden_nr"]
melde("bestellungen.csv", "kunden_nr", "leer", kn.str.strip() == "", b1["bestell_nr"],
      "Unbekannt-Kunde (kunde_sk = -1)")
melde("bestellungen.csv", "kunden_nr", "Kleinbuchstaben", kn.str.match(r"^k"), kn, "upper()")
alle_kunden = kunden["kunden_nr"].str.strip().str.upper()
melde("bestellungen.csv", "kunden_nr", "Kunde existiert nicht (Orphan)",
      (kn.str.strip() != "") & ~kn.str.strip().str.upper().isin(alle_kunden), kn,
      "Unbekannt-Kunde (kunde_sk = -1) + Protokoll")

an = b1["artikel_nr"]
melde("bestellungen.csv", "artikel_nr", "Format abweichend (a-005 / A005 / Leerzeichen)",
      ~an.str.fullmatch(r"A-\d{3}"), an, "Regex: Buchstabe + 3 Ziffern -> 'A-005'")
an_norm = an.str.strip().str.upper().str.replace(r"^A-?(\d{3})$", r"A-\1", regex=True)
alle_artikel = produkte["artikel_nr"].astype(str).str.strip().str.upper()
melde("bestellungen.csv", "artikel_nr", "Produkt existiert nicht (Orphan)",
      ~an_norm.isin(alle_artikel), an, "rejected (Umsatz ohne Produkt ist nicht auswertbar)")

menge = pd.to_numeric(b1["menge"], errors="coerce")
melde("bestellungen.csv", "menge", "negativ", menge < 0, b1["menge"], "rejected + Rückfrage Fachabteilung")
melde("bestellungen.csv", "menge", "null (0)", menge == 0, b1["menge"], "rejected")

preis_b = b1["einzelpreis"]
melde("bestellungen.csv", "einzelpreis", "leer", preis_b.str.strip() == "", b1["bestell_nr"],
      "Listenpreis aus Produkt, falls vorhanden, sonst rejected")
melde("bestellungen.csv", "einzelpreis", "deutsches Dezimalkomma",
      preis_b.str.contains(","), preis_b, "Komma -> Punkt, float()")

rabatt = b1["rabatt_prozent"]
melde("bestellungen.csv", "rabatt_prozent", "leer", rabatt.str.strip() == "", b1["bestell_nr"],
      "0 annehmen (dokumentieren!)")
melde("bestellungen.csv", "rabatt_prozent", "deutsches Dezimalkomma", rabatt.str.contains(","), rabatt,
      "Komma -> Punkt")

zahl = b1["zahlungsart"]
melde("bestellungen.csv", "zahlungsart", "9 Schreibweisen für 4 Zahlungsarten",
      ~zahl.isin(["Rechnung", "Lastschrift", "Bar", "Vorkasse"]), zahl, "Mapping-Tabelle")
status = b1["lieferstatus"]
melde("bestellungen.csv", "lieferstatus", "Groß-/Kleinschreibung uneinheitlich",
      status != status.str.lower(), status, "lower()")

print("   Anzahl Bestellungen (Köpfe):", b1["bestell_nr"].nunique())
for spalte in ["kunden_nr", "zahlungsart", "lieferstatus", "rabatt_prozent"]:
    werte = b1[spalte].str.strip().str.lower()
    if spalte == "zahlungsart":
        werte = werte.replace({"re": "rechnung", "sepa": "lastschrift",
                               "sepa-lastschrift": "lastschrift", "barzahlung": "bar"})
    n = (werte.groupby(b1["bestell_nr"]).nunique() > 1).sum()
    print(f"   Bestellungen mit mehreren Werten in '{spalte}': {n}"
          f"  -> {'Attribut der POSITION' if n else 'Attribut der BESTELLUNG'}")


# ---------------------------------------------------------------------------
# 6) kunden_update_2026-01.csv: Was ändert sich? (Vorbereitung SCD Typ 2)
# ---------------------------------------------------------------------------
print("=" * 80)
print("6) kunden_update_2026-01.csv")
u = kunden_update.merge(k1, on="kunden_nr", how="left", suffixes=("_neu", "_alt"), indicator=True)
print("   bestehende Kunden:", (u["_merge"] == "both").sum(), "| neue Kunden:", (u["_merge"] == "left_only").sum())
for _, zeile in u[u["_merge"] == "both"].iterrows():
    geaendert = [c for c in ["kundentyp", "firma", "strasse", "plz", "ort", "bundesland", "telefon", "email"]
                 if zeile[c + "_neu"].strip().lower() != zeile[c + "_alt"].strip().lower()]
    print(f"   {zeile['kunden_nr']}: {', '.join(geaendert)}")

# Plausibilität: Passt das Bundesland zur Stadt?
sachsen = kunden_update["ort"].str.strip().str.lower().isin(["dresden", "leipzig"])
widerspruch = (sachsen & (kunden_update["bundesland"] != "Sachsen")) | (~sachsen & (kunden_update["bundesland"] == "Sachsen"))
melde("kunden_update_2026-01.csv", "bundesland", "passt nicht zum Ort (z. B. Leipzig + Baden-Württemberg)",
      widerspruch, kunden_update["kunden_nr"] + " " + kunden_update["ort"] + "/" + kunden_update["bundesland"],
      "Bundesland aus PLZ/Ort ableiten statt aus der Datei")
melde("kunden_update_2026-01.csv", "email", "gleiche E-Mail bei verschiedenen neuen Kunden",
      kunden_update["email"].str.strip().ne("") & kunden_update["email"].duplicated(keep=False),
      kunden_update["kunden_nr"] + " " + kunden_update["email"], "Warnung (Sammeladresse info@)")

# Plausibilität PLZ <-> Ort auf k1, nur aus den Daten selbst (keine externe PLZ-Liste):
# Pro Ort der häufigste PLZ-Bereich (erste 2 Ziffern); ein anderer Bereich ist ein Verdacht.
# Logik in explore/plz_pruefung.py (getestet in explore/test_pruefe_plz_bereich.py).
# Steht am Ende, damit die bestehenden Nummern 1-47 gleich bleiben.
plz_verdacht = pruefe_plz_bereich(k1, ORT_ABK)
erwartet = plz_verdacht["erwarteter_bereich"].reindex(k1.index)
melde("kunden.csv", "plz", "PLZ-Bereich passt nicht zum Ort (Mehrheit im Ort)",
      erwartet.notna(),
      k1["kunden_nr"] + " " + plz + "/" + ort + " (erwartet " + erwartet.fillna("") + "...)",
      "Warnung, mit Fachabteilung klären (nicht automatisch korrigieren)")


# ---------------------------------------------------------------------------
# 7) Ergebnis speichern
# ---------------------------------------------------------------------------
ergebnis = pd.DataFrame(issues)
ergebnis.insert(0, "nr", range(1, len(ergebnis) + 1))
ziel = DOCS / "data_quality_issues.csv"
# utf-8-sig: Excel zeigt die Umlaute richtig; sep=';' für deutsches Excel
ergebnis.to_csv(ziel, sep=";", index=False, encoding="utf-8-sig")

# Zusätzlich als Markdown-Tabelle (ohne Zusatzpaket 'tabulate')
zeilen = ["| Nr | Datei | Spalte | Problem | Anzahl | Beispiele | Lösungsvorschlag |",
          "|---|---|---|---|---|---|---|"]
for _, r in ergebnis.iterrows():
    zellen = [str(r[c]).replace("|", "/") for c in
              ["nr", "datei", "spalte", "problem", "anzahl", "beispiele", "loesungsvorschlag"]]
    zeilen.append("| " + " | ".join(zellen) + " |")
kopf = ("# Data Quality Issues (automatisch erzeugt von explore/01_explore.py)\n\n"
        "Nicht von Hand bearbeiten – Skript erneut ausführen.\n\n")
(DOCS / "data_quality_issues.md").write_text(kopf + "\n".join(zeilen) + "\n", encoding="utf-8")

print("=" * 80)
print(f"7) {len(ergebnis)} Probleme gefunden -> {ziel.relative_to(BASE)} (+ .md)")
print(ergebnis.groupby("datei")["anzahl"].agg(["count", "sum"]).rename(
    columns={"count": "probleme", "sum": "betroffene_werte"}).to_string())
