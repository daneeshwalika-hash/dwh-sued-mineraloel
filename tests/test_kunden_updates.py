"""
tests/test_kunden_updates.py

Zweck      : Tests für den Datennachschub (E-43): Dateinamen-Regel (etl/kunden_updates.py) und
             SCD 2 mit mehreren Update-Dateien (baue_kundenversionen in etl/04_lade_dimensionen.py).
             Die künstliche zweite Update-Datei entsteht NUR im Testordner (pytest tmp_path),
             nie in data/raw/ (R-02).
Eingabe    : data/raw/kunden.csv und data/raw/kunden_update_2026-01.csv (nur lesen, werden kopiert)
Ausgabe    : pytest-Ergebnis
Anforderung: erneuter Lauf nach Datennachschub aktualisiert, Q-05 heutiger Bestand = gleiches Ergebnis
Bezug      : E-14, E-15, E-31, E-32, E-43
Aufruf     : .venv\\Scripts\\python.exe -m pytest tests -v
             Erwartet: alle Tests "PASSED". Ein "FAILED" heißt: Die Regel für Update-Dateien oder SCD 2
             weicht von E-43 ab -> Code prüfen, nicht den Test anpassen.
"""
import contextlib
import datetime as dt
import importlib
import io
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
from etl import kunden_updates as ku                     # noqa: E402
b = importlib.import_module("etl.03_bereinige_quellen")
lade = importlib.import_module("etl.04_lade_dimensionen")

ROH = PROJEKT / "data" / "raw"


# --- Dateinamen-Regel (E-43) -------------------------------------------------
@pytest.mark.parametrize("name, erwartet", [
    ("kunden_update_2026-01.csv", dt.date(2026, 1, 10)),       # Ausnahme E-31
    ("kunden_update_2026-04-01.csv", dt.date(2026, 4, 1)),
    ("kunden_update_2027-12-31.csv", dt.date(2027, 12, 31)),
])
def test_datum_aus_dateiname(name, erwartet):
    assert ku.gueltig_von_aus_dateiname(name) == erwartet


@pytest.mark.parametrize("name", [
    "kunden_update_2026-02.csv",          # Monat ohne Tag, keine dokumentierte Ausnahme
    "kunden_update_Feb2026.csv",
    "kunden_update_2026-02-30.csv",       # ungültiges Datum
    "kunden_update_2026-4-1.csv",         # nicht zweistellig
])
def test_nicht_lesbarer_name_bricht_ab(name):
    with pytest.raises(ku.UpdateDateiFehler):
        ku.gueltig_von_aus_dateiname(name)


def _leere_datei(ordner, name):
    (ordner / name).write_text("kunden_nr\n", encoding="utf-8")


def test_reihenfolge_nach_datum(tmp_path):
    for name in ["kunden_update_2026-05-01.csv", "kunden_update_2026-01.csv", "kunden_update_2026-03-15.csv"]:
        _leere_datei(tmp_path, name)
    _leere_datei(tmp_path, "kunden.csv")                       # passt nicht zum Suchmuster -> ignoriert
    namen = [p.name for p, _ in ku.finde_update_dateien(tmp_path)]
    assert namen == ["kunden_update_2026-01.csv", "kunden_update_2026-03-15.csv", "kunden_update_2026-05-01.csv"]


def test_falscher_name_im_ordner_wird_nicht_uebersprungen(tmp_path):
    _leere_datei(tmp_path, "kunden_update_2026-01.csv")
    _leere_datei(tmp_path, "kunden_update_maerz.csv")
    with pytest.raises(ku.UpdateDateiFehler, match="kunden_update_maerz.csv"):
        ku.finde_update_dateien(tmp_path)


def test_gleiches_datum_bricht_ab(tmp_path):
    # 2026-01.csv ist per Ausnahme 2026-01-10 -> Konflikt mit einer Datei vom selben Tag
    _leere_datei(tmp_path, "kunden_update_2026-01.csv")
    _leere_datei(tmp_path, "kunden_update_2026-01-10.csv")
    with pytest.raises(ku.UpdateDateiFehler, match="demselben"):
        ku.finde_update_dateien(tmp_path)


def test_heutiger_ordner_data_raw():
    """Heute liegt genau eine Update-Datei in data/raw: 2026-01.csv ab 2026-01-10 (E-31)."""
    assert [(p.name, von) for p, von in ku.finde_update_dateien(ROH)] == \
        [("kunden_update_2026-01.csv", dt.date(2026, 1, 10))]


# --- SCD 2 mit einer zweiten, künstlichen Update-Datei im Testordner --------
def _lese_csv(pfad):
    # gleiche Leseweise wie etl/01_lade_staging.py csv_lesen(): alles Text, nichts umwandeln
    return pd.read_csv(pfad, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig")


@pytest.fixture
def testordner(tmp_path):
    """Kopie der echten Kundendateien plus kunden_update_2026-04-01.csv (nur im Testordner).

    Inhalt der neuen Datei: K0042 zieht ein zweites Mal um; die neue Adresse ist die von K0009
    aus dem ersten Update (gültige Werte, die die Bereinigung kennt).
    """
    shutil.copy(ROH / "kunden.csv", tmp_path / "kunden.csv")
    shutil.copy(ROH / "kunden_update_2026-01.csv", tmp_path / "kunden_update_2026-01.csv")
    erstes = _lese_csv(tmp_path / "kunden_update_2026-01.csv")
    k0042 = erstes[erstes["kunden_nr"] == "K0042"].copy()
    k0009 = erstes[erstes["kunden_nr"] == "K0009"].iloc[0]
    for spalte in ["plz", "ort", "bundesland"]:
        k0042[spalte] = k0009[spalte]
    k0042.to_csv(tmp_path / "kunden_update_2026-04-01.csv", sep=";", index=False, encoding="utf-8-sig")
    return tmp_path


def _versionen(ordner, nur_erste=False):
    with contextlib.redirect_stdout(io.StringIO()):
        stamm = b.bereinige_kunden(_lese_csv(ordner / "kunden.csv"), "kunden")["sauber"]
        dateien = ku.finde_update_dateien(ordner)[:1 if nur_erste else None]
        updates = [(von, b.bereinige_kunden(_lese_csv(p), "kunden_update")["sauber"]) for p, von in dateien]
    return lade.baue_kundenversionen(stamm, updates), stamm, updates


def test_eine_datei_als_liste_gleich_wie_bisher(testordner):
    """Q-05: Mit der heutigen Datei liefert die Liste genau das Ergebnis des bisherigen Aufrufs."""
    (df_liste, kz_liste), stamm, updates = _versionen(testordner, nur_erste=True)
    df_alt, kz_alt = lade.baue_kundenversionen(stamm, updates[0][1])     # bisheriger Aufruf (E-31)
    pd.testing.assert_frame_equal(df_liste, df_alt)
    assert kz_liste == kz_alt
    assert len(df_liste) == 172 and kz_liste["neue_versionen"] == 14      # SOLL dim_kunde 173 = 172 + Zeile -1


def test_zweite_datei_erzeugt_dritte_version(testordner):
    (df1, _), _, _ = _versionen(testordner, nur_erste=True)
    (df2, kz2), _, updates = _versionen(testordner)
    assert [von for von, _ in updates] == [dt.date(2026, 1, 10), dt.date(2026, 4, 1)]
    k = df2[df2["kunden_nr"] == "K0042"].reset_index(drop=True)
    assert len(k) == 3 and kz2["neue_versionen"] == 15
    # Lückenlos, ohne Überlappung: alt bis 2026-01-09, Update 1 bis 2026-03-31, Update 2 ab 2026-04-01
    assert list(k["gueltig_von"]) == [dt.date(1900, 1, 1), dt.date(2026, 1, 10), dt.date(2026, 4, 1)]
    assert list(k["gueltig_bis"]) == [dt.date(2026, 1, 9), dt.date(2026, 3, 31), dt.date(9999, 12, 31)]
    assert list(k["ist_aktuell"]) == [False, False, True]
    # Alle anderen Kunden bleiben genau wie mit einer Datei
    andere = lambda df: df[df["kunden_nr"] != "K0042"].reset_index(drop=True)   # noqa: E731
    pd.testing.assert_frame_equal(andere(df2), andere(df1))


def test_update_vor_aktueller_version_bricht_ab():
    stamm = pd.DataFrame([{"kunden_nr": "K0001", "kundentyp": "Privat", "firma": None, "vorname": "A",
                           "nachname": "B", "plz": "70173", "ort": "Stuttgart", "bundesland": "Baden-Württemberg",
                           "erstellt_am": dt.date(2022, 1, 1)}])
    umzug = stamm.assign(plz="01067", ort="Dresden", bundesland="Sachsen")
    zurueck = stamm.copy()
    # Zweites Update mit Umzug, aber Datum vor dem Beginn der aktuellen Version -> Abbruch
    with pytest.raises(ValueError, match="E-43"):
        lade.baue_kundenversionen(stamm, [(dt.date(2026, 4, 1), umzug), (dt.date(2026, 4, 1), zurueck)])
