"""
tests/test_bereinigung.py

Zweck      : Kleine Tests für die Bausteine aus etl/03_bereinige_quellen.py mit
             selbst gebauten Beispielwerten (keine Datenbank nötig).
Eingabe    : keine (Testdaten stehen im Code)
Ausgabe    : pytest-Ergebnis
Anforderung: Q-04 Regeln sind überprüfbar, Q-05 gleiches Ergebnis bei jedem Lauf
Bezug      : E-02, E-07, E-25, E-27, Nr 3, Nr 23, Nr 36, Nr 41, Nr 43, Nr 44
Aufruf     : .venv\\Scripts\\python.exe -m pytest tests -v
             Erwartet: alle Tests "PASSED". Ein "FAILED" heißt: eine Regel verhält sich
             anders als dokumentiert -> Regel oder Dokumentation prüfen, nicht den Test anpassen.
"""
import datetime as dt
import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

# Warum importlib: Der Dateiname beginnt mit einer Ziffer (03_...). "import etl.03_..."
# ist deshalb kein gültiger Python-Befehl, import_module mit Text funktioniert.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
b = importlib.import_module("etl.03_bereinige_quellen")
regeln = importlib.import_module("etl.abbildungsregeln")


# --- Datum (E-02, E-25) ------------------------------------------------------
@pytest.mark.parametrize("wert", ["2024-03-17", "17.03.2024", "17.03.24", "03/17/2024"])
def test_datum_alle_formate_ergeben_denselben_tag(wert):
    assert b.parse_datum(wert) == dt.date(2024, 3, 17)


def test_datum_slash_ist_monat_zuerst():
    # E-02: 04/05/2024 ist der 5. April, nicht der 4. Mai
    assert b.parse_datum("04/05/2024") == dt.date(2024, 4, 5)


@pytest.mark.parametrize("wert", ["2027-02-30", "13/01/2024", "2024/03/17", "", None])
def test_datum_ungueltig_wird_none(wert):
    # Nr 30: Datum existiert nicht; Monat 13; unbekanntes Format; leer -> None, kein Raten
    assert b.parse_datum(wert) is None


# --- Dezimalkomma (Nr 41, Nr 43, Nr 22) --------------------------------------
@pytest.mark.parametrize("wert, erwartet", [("14,00", Decimal("14.00")), ("2,5", Decimal("2.5")),
                                            ("10", Decimal("10")), ("-3,10", Decimal("-3.10"))])
def test_dezimalkomma(wert, erwartet):
    assert b.parse_dezimal(wert) == erwartet


@pytest.mark.parametrize("wert", ["abc", "1.234,50", "", None])
def test_dezimal_ungueltig_wird_none(wert):
    assert b.parse_dezimal(wert) is None


def test_produktpreis_mit_euro():
    assert b.parse_produktpreis("1,74 €") == Decimal("1.74")
    assert b.parse_produktpreis("1.62") == Decimal("1.62")


# --- Mappings (Nr 3, Nr 23, Nr 36, Nr 44) ------------------------------------
def test_mapping_zahlungsart():
    werte = pd.Series(["RE", " SEPA ", "Barzahlung", "vorkasse"])
    assert list(b.abbilden(werte, regeln.ZAHLUNGSART)) == ["Rechnung", "Lastschrift", "Bar", "Vorkasse"]


def test_mapping_kundentyp_und_einheit():
    assert list(b.abbilden(pd.Series(["g", "privat"]), regeln.KUNDENTYP)) == ["Gewerbe", "Privat"]
    assert list(b.abbilden(pd.Series(["Kilogramm", "pcs", "ltr"]), regeln.EINHEIT)) == ["kg", "Stück", "L"]


@pytest.mark.parametrize("wert", ["a005 ", "A005", "a-005", " A-005"])
def test_artikel_nr_vereinheitlicht(wert):
    assert b.vereinheitliche_artikel_nr(wert) == "A-005"


# --- Unbekannter Wert: nie still NaN -----------------------------------------
def test_unbekannter_wert_ergibt_none():
    assert b.abbilden(pd.Series(["Kreditkarte"]), regeln.ZAHLUNGSART).isna().all()


def _bestellung(**abweichung):
    """Eine gültige Beispielposition; einzelne Spalten können überschrieben werden."""
    zeile = {"bestell_nr": "1", "position": "1", "bestelldatum": "17.03.2024", "kunden_nr": "K0001",
             "artikel_nr": "A-001", "menge": "2", "einzelpreis": "1,50", "rabatt_prozent": "",
             "zahlungsart": "RE", "lieferstatus": "Geliefert"}
    zeile.update(abweichung)
    return zeile


def test_bestellung_unbekannter_wert_und_mehrere_gruende():
    produkte = pd.DataFrame({"artikel_nr": ["A-001"], "listenpreis": [Decimal("1.60")]})
    roh = pd.DataFrame([
        _bestellung(),
        _bestellung(position="2", zahlungsart="Kreditkarte"),
        _bestellung(position="3", artikel_nr="A-999", menge="0"),
    ])
    e = b.bereinige_bestellungen(roh, produkte, {"K0001"})
    assert e["kennzahlen"]["sauber"] == 1
    gruende = list(e["rejected"]["grund"])
    assert gruende[0] == "unbekannter Wert in zahlungsart"
    # E-27: beide Gründe in einer Zeile, getrennt durch " | "
    assert gruende[1] == "Produkt existiert nicht (Nr 37) | Menge 0 (E-05)"
    # Originalwert bleibt in rejected erhalten (nicht der bereinigte)
    assert e["rejected"].iloc[0]["zahlungsart"] == "Kreditkarte"
    # Leerer Rabatt -> 0 (E-08)
    assert e["sauber"].iloc[0]["rabatt_prozent"] == Decimal("0")


def test_stammdaten_unbekannter_kundentyp_bricht_ab():
    roh = pd.DataFrame([{"kunden_nr": "K0001", "kundentyp": "Verein", "firma": "", "vorname": "A",
                         "nachname": "B", "strasse": "", "plz": "70173", "ort": "Stuttgart",
                         "bundesland": "BW", "telefon": "", "email": "", "erstellt_am": "2024-01-01"}])
    with pytest.raises(ValueError, match="kundentyp"):
        b.bereinige_kunden(roh, "test")
