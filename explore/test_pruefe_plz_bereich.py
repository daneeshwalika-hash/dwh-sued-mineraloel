"""
explore/test_pruefe_plz_bereich.py

Zweck      : Tests für die Prüfung PLZ <-> Ort (explore/plz_pruefung.py).
             Alle Tests rufen die echte Funktion auf, die auch 01_explore.py benutzt.
             Nur Standard-asserts, pytest ist nicht nötig.
Eingabe    : data/raw/kunden.csv (nur lesen)
Aufruf     : .venv\\Scripts\\python.exe explore\\test_pruefe_plz_bereich.py
             Erwartet: "Test A OK", "Test B OK", "Test C OK", am Ende "Alle Tests OK".
             Bei einem Fehler: Abbruch mit AssertionError.
"""
from pathlib import Path

import pandas as pd

from plz_pruefung import ORT_ABK, pruefe_plz_bereich

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# k1 wie in 01_explore.py: alles als Text, leere Felder bleiben "", ohne exakte Dubletten
kunden = pd.read_csv(RAW / "kunden.csv", sep=";", dtype=str, keep_default_na=False, encoding="utf-8")
k1 = kunden.drop_duplicates()

# Test A: echte Daten -> 0 Treffer, df bleibt unverändert
vorher = k1.copy()
treffer = pruefe_plz_bereich(k1, ORT_ABK)
assert len(treffer) == 0, f"Test A: erwartet 0 Treffer, gefunden {len(treffer)}\n{treffer}"
assert k1.equals(vorher), "Test A: df wurde verändert"
assert list(treffer.columns) == ["kunden_nr", "plz", "ort", "bereich", "erwarteter_bereich"]
print("Test A OK: echte kunden.csv (k1) -> 0 Treffer, df unverändert")

# Test B (Negativtest): Kopie von k1, eine Dresdner PLZ auf 70173 -> genau 1 Treffer
k1_b = k1.copy()
zeile = k1_b.index[k1_b["ort"].str.strip().str.lower() == "dresden"][0]
k1_b.loc[zeile, "plz"] = "70173"
treffer = pruefe_plz_bereich(k1_b, ORT_ABK)
assert len(treffer) == 1, f"Test B: erwartet 1 Treffer, gefunden {len(treffer)}\n{treffer}"
t = treffer.iloc[0]
assert treffer.index[0] == zeile, "Test B: falsche Zeile gemeldet"
assert t["bereich"] == "70" and t["erwarteter_bereich"] == "01", f"Test B: {t.to_dict()}"
assert k1.equals(vorher), "Test B: Original-k1 wurde verändert"
print(f"Test B OK: {t['kunden_nr']} Dresden mit 70173 -> 1 Treffer, Bereich 70, erwartet 01")

# Test C (Gleichstand): 2 Zeilen gleicher Ort, Bereiche 72 und 73 -> keine Mehrheit -> 0 Treffer
k1_c = pd.DataFrame({"kunden_nr": ["T001", "T002"], "plz": ["72070", "73728"],
                     "ort": ["Testort", "Testort"]})
treffer = pruefe_plz_bereich(k1_c, ORT_ABK)
assert len(treffer) == 0, f"Test C: erwartet 0 Treffer, gefunden {len(treffer)}\n{treffer}"
print("Test C OK: Gleichstand 72/73 -> 0 Treffer")

print("\nAlle Tests OK")
