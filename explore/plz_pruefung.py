"""
explore/plz_pruefung.py

Zweck      : Plausibilitätsprüfung PLZ <-> Ort (genutzt von explore/01_explore.py,
             getestet in explore/test_pruefe_plz_bereich.py).
             Keine externe PLZ-Liste, nur die Daten selbst: Pro Ort wird der häufigste
             PLZ-Bereich (erste 2 Ziffern) bestimmt; eine Zeile mit anderem Bereich ist ein
             Verdacht. Es wird nichts geändert, nur gemeldet.
Eingabe    : DataFrame mit den Spalten kunden_nr, plz, ort (Text)
Ausgabe    : DataFrame der Verdachtszeilen
Aufruf     : wird importiert:  from plz_pruefung import ORT_ABK, pruefe_plz_bereich
"""
import pandas as pd

# Abkürzung oder Umschrift (wie in den Daten) -> offizieller Ortsname (klein); auch für Regel B in 01_explore.py
ORT_ABK = {"stgt.": "stuttgart", "boeblingen": "böblingen", "gaertringen": "gärtringen",
           "tuebingen": "tübingen", "esslingen a.n.": "esslingen am neckar",
           "esslingen": "esslingen am neckar", "ulm/donau": "ulm"}


def pruefe_plz_bereich(df: pd.DataFrame, ort_abk: dict) -> pd.DataFrame:
    """
    Gibt die Verdachtszeilen zurück (Index wie df) mit den Spalten
    kunden_nr, plz, ort, bereich, erwarteter_bereich. df bleibt unverändert.

    Ein Bereich gilt für einen Ort nur als "erwartet", wenn er mindestens 2 Zeilen hat
    UND eine echte Mehrheit (> 50 %) der gültigen PLZ des Orts ausmacht.
    """
    # Normalisierung nur für die Prüfung: strip, Leerzeichen und 'D-' weg, 4-stellig -> zfill(5)
    plz_norm = df["plz"].str.strip().str.replace(" ", "").str.removeprefix("D-")
    plz_norm = plz_norm.mask(plz_norm.str.fullmatch(r"\d{4}"), plz_norm.str.zfill(5))
    gueltig = plz_norm.str.fullmatch(r"\d{5}")   # leere PLZ werden nicht bewertet
    bereich = plz_norm.str[:2]
    ort_ziel = df["ort"].str.strip().str.lower().replace(ort_abk)

    zaehlung = pd.crosstab(ort_ziel[gueltig], bereich[gueltig])
    gestuetzt = (zaehlung.max(axis=1) >= 2) & (zaehlung.max(axis=1) > zaehlung.sum(axis=1) / 2)
    erwartet = ort_ziel.map(zaehlung.idxmax(axis=1)[gestuetzt])

    verdacht = gueltig & erwartet.notna() & (bereich != erwartet)
    return pd.DataFrame({
        "kunden_nr": df["kunden_nr"], "plz": df["plz"], "ort": df["ort"],
        "bereich": bereich, "erwarteter_bereich": erwartet,
    })[verdacht]
