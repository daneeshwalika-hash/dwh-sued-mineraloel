"""
tests/test_dimensionen.py

Zweck      : Tests für baue_kundenversionen() aus etl/04_lade_dimensionen.py (SCD 2, ohne Datenbank).
Eingabe    : keine (Testdaten im Code)
Ausgabe    : pytest-Ergebnis
Anforderung: F-07 Adresse zum Bestellzeitpunkt, Q-05 gleiches Ergebnis bei jedem Lauf
Bezug      : E-14, E-15, E-31, E-32
Aufruf     : .venv\\Scripts\\python.exe -m pytest tests -v
             Erwartet: alle Tests "PASSED". Ein "FAILED" heißt: die SCD-Regel weicht von der
             Entscheidung ab -> Code prüfen, nicht den Test anpassen.
"""
import datetime as dt
import importlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
lade = importlib.import_module("etl.04_lade_dimensionen")


def _kunde(kunden_nr, **abweichung):
    zeile = {"kunden_nr": kunden_nr, "kundentyp": "Privat", "firma": None, "vorname": "Anna",
             "nachname": "Braun", "plz": "70173", "ort": "Stuttgart", "bundesland": "Baden-Württemberg",
             "erstellt_am": dt.date(2022, 5, 1)}
    zeile.update(abweichung)
    return zeile


def _versionen():
    stamm = pd.DataFrame([_kunde("K0001", firma="Alt GmbH"), _kunde("K0002"), _kunde("K0003")])
    update = pd.DataFrame([
        # K0001 zieht um, wird Gewerbe, Firma leer im Update (E-15: alte Firma bleibt)
        _kunde("K0001", kundentyp="Gewerbe", firma=None, plz="01067", ort="Dresden", bundesland="Sachsen"),
        # K0002 ohne Änderung
        _kunde("K0002"),
        # K0009 ist neu
        _kunde("K0009", erstellt_am=dt.date(2026, 1, 10)),
    ])
    return lade.baue_kundenversionen(stamm, update)


def test_umzug_erzeugt_zwei_versionen_ohne_luecke():
    df, kz = _versionen()
    k1 = df[df["kunden_nr"] == "K0001"].reset_index(drop=True)
    assert len(k1) == 2 and kz["neue_versionen"] == 1
    # E-31: alt bis 2026-01-09, neu ab 2026-01-10 -> keine Überlappung, keine Lücke
    assert k1.loc[0, "gueltig_bis"] == dt.date(2026, 1, 9) and not k1.loc[0, "ist_aktuell"]
    assert k1.loc[1, "gueltig_von"] == dt.date(2026, 1, 10) and k1.loc[1, "ist_aktuell"]
    assert (k1.loc[0, "ort"], k1.loc[1, "ort"]) == ("Stuttgart", "Dresden")


def test_scd1_und_e15():
    df, kz = _versionen()
    k1 = df[df["kunden_nr"] == "K0001"]
    # E-32: kundentyp in BEIDEN Versionen mit dem neuen Wert
    assert list(k1["kundentyp"]) == ["Gewerbe", "Gewerbe"]
    # E-15: leere Firma im Update überschreibt nicht
    assert list(k1["firma"]) == ["Alt GmbH", "Alt GmbH"] and kz["e15_nicht_ueberschrieben"] == 1


def test_ohne_aenderung_und_neuer_kunde():
    df, kz = _versionen()
    assert kz["ohne_aenderung"] == 1 and kz["neue_kunden"] == 1
    for kunden_nr in ["K0002", "K0003", "K0009"]:
        v = df[df["kunden_nr"] == kunden_nr]
        # E-14: genau eine Version von 1900-01-01 bis 9999-12-31, auch für den neuen Kunden
        assert len(v) == 1
        assert v.iloc[0]["gueltig_von"] == dt.date(1900, 1, 1) and v.iloc[0]["gueltig_bis"] == dt.date(9999, 12, 31)
