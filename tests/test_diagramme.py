"""
tests/test_diagramme.py

Zweck      : Tests für das deutsche Zahlenformat zahl_de() aus etl/06_erstelle_diagramme.py
             (keine Datenbank nötig).
Eingabe    : keine (Testdaten stehen im Code)
Ausgabe    : pytest-Ergebnis
Anforderung: Q-05 gleiches Ergebnis bei jedem Lauf (unabhängig von den Windows-Einstellungen)
Bezug      : E-41
Aufruf     : .venv\\Scripts\\python.exe -m pytest tests -v
             Erwartet: alle Tests "PASSED". Ein "FAILED" heißt: Die Beschriftung der
             Diagramme weicht vom dokumentierten Format ab.
"""
import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Warum importlib: Der Dateiname beginnt mit einer Ziffer (06_...).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
d = importlib.import_module("etl.06_erstelle_diagramme")


# Tausenderpunkt, Dezimalkomma, kaufmännisch gerundet (0,5 -> auf), auch bei Decimal aus der Datenbank
@pytest.mark.parametrize("wert, nachkomma, erwartet", [
    (0, 0, "0"),
    (999, 0, "999"),
    (1000, 0, "1.000"),
    (Decimal("1112492.50"), 0, "1.112.493"),
    (Decimal("1112492.50"), 2, "1.112.492,50"),
    (Decimal("2212834.69"), 2, "2.212.834,69"),
    (2.5, 0, "3"),            # round() in Python ergäbe 2 (Banker's Rounding)
    (91.25, 1, "91,3"),
    (-1234.5, 1, "-1.234,5"),
])
def test_zahl_de(wert, nachkomma, erwartet):
    assert d.zahl_de(wert, nachkomma) == erwartet


def test_euro_achse():
    assert d.euro_achse(150000.0, None) == "150.000 €"
