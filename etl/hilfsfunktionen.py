# =============================================================================
# etl/hilfsfunktionen.py
#
# Zweck      : Wiederverwendbare Hilfsfunktionen für Datenanalyse und ETL mit pandas.
#              Die Funktionen sind allgemein gehalten: Sie kennen keine Spalten- oder
#              Dateinamen dieses Projekts.
# Eingabe    : DataFrames, Series oder Dateipfade (je Funktion)
# Ausgabe    : Rückgabewerte und Konsolenausgabe; speichere_protokoll() schreibt eine CSV-Datei
# Anforderung: Q-01 Kontrollsumme (gelesen = übernommen + abgelehnt), Q-02 Grund je abgelehnter Zeile
# Bezug      : genutzt von etl/03_bereinige_quellen.py (kontrollsumme, vergleiche)
# Aufruf     : wird importiert:  from etl.hilfsfunktionen import kontrollsumme, vergleiche
#              Selbsttest:       .venv\Scripts\python.exe etl\hilfsfunktionen.py
#              Erwartet: Selbsttest läuft durch, am Ende "Selbsttest fertig."
#
# Inhalt:
#   A) Ausgabe
#        abschnitt()                  Überschrift in der Konsole
#   B) Einlesen und erste Prüfung
#        zeige_rohzeilen()            erste Zeilen einer Datei roh ansehen
#        lese_csv_als_text()          CSV sicher als Text einlesen
#        pruefe_spalten()             erwartete Spaltennamen prüfen
#        zaehle_leere()               leere Werte pro Spalte zählen
#   C) Vergleich und Kontrolle
#        vergleiche()                 erwarteten mit tatsächlichem Wert vergleichen
#        kontrollsumme()              gelesen = übernommen + abgelehnt prüfen
#   D) Duplikate und Schlüssel
#        zeige_duplikate()            Duplikate zählen und anzeigen
#        pruefe_schluessel()          ist ein (zusammengesetzter) Schlüssel eindeutig?
#   E) Text und Schreibweisen
#        normalisiere_text()          strip + lower + Unicode NFC
#        finde_schreibvarianten()     gleiche Werte in mehreren Schreibweisen
#        zeige_unsichtbare_zeichen()  Leerzeichen / Unicode-Unterschiede sichtbar machen
#   F) Protokoll (nichts still löschen)
#        trenne_mit_protokoll()       Zeilen aufteilen in gut / abgelehnt + Grund
#        speichere_protokoll()        abgelehnte Zeilen als CSV speichern
# =============================================================================

import unicodedata
from pathlib import Path

import pandas as pd


# =============================================================================
# A) Ausgabe
# =============================================================================
def abschnitt(titel, breite=78, zeichen="="):
    """
    Gibt eine gut sichtbare Überschrift in der Konsole aus.

    Parameter:
        titel   : Text der Überschrift
        breite  : Länge der Linie (Standard 78)
        zeichen : Zeichen der Linie (Standard "=")

    Beispiel:
        abschnitt("4) Duplikate")
        abschnitt("Details", breite=40, zeichen="-")
    """
    linie = zeichen * breite
    print("\n" + linie)
    print(titel)
    print(linie)


# =============================================================================
# B) Einlesen und erste Prüfung
# =============================================================================
def zeige_rohzeilen(pfad, anzahl=5, encoding="utf-8"):
    """
    Zeigt die ersten Zeilen einer Textdatei OHNE pandas.
    repr() macht versteckte Zeichen sichtbar: \\n, \\t, Leerzeichen am Rand.
    errors="replace" bricht nicht ab: Falsche Bytes erscheinen als '�'
    (ein Hinweis auf eine falsche Kodierung).

    Beispiel:
        zeige_rohzeilen(roh / "kunden.csv", anzahl=3)
    """
    pfad = Path(pfad)
    print(f"\n--- Rohzeilen: {pfad.name} ---")
    with open(pfad, encoding=encoding, errors="replace") as f:
        for _ in range(anzahl):
            zeile = f.readline()
            if zeile == "":          # Dateiende erreicht
                break
            print(repr(zeile))


def lese_csv_als_text(pfad, sep=";", encoding="utf-8"):
    """
    Liest eine CSV-Datei als Text ein und zeigt sofort die Zahl der Zeilen.

    dtype=str: Nichts wird umgewandelt (PLZ 01067 bleibt 01067).
    keep_default_na=False: Leere Felder bleiben "" statt NaN, Texte wie "NA" oder "null" bleiben Text.

    Rückgabe:
        DataFrame (alle Spalten Text)

    Beispiel:
        kunden = lese_csv_als_text(roh / "kunden.csv")
    """
    df = pd.read_csv(pfad, sep=sep, encoding=encoding, dtype=str, keep_default_na=False)
    # Direkt nach dem Lesen zählen: Grundlage für den späteren Soll/Ist-Vergleich
    print(f"Gelesen: {Path(pfad).name:<30} {len(df):>6} Zeilen, {df.shape[1]:>3} Spalten")
    return df


def pruefe_spalten(df, erwartet, name="DataFrame"):
    """
    Prüft, ob die Spalten genau den erwarteten Namen entsprechen.
    Wenn nicht: Abbruch mit ValueError und klarer Meldung (falsches Trennzeichen,
    Tippfehler im Export, neue Spalte ...).

    Beispiel:
        pruefe_spalten(kunden, ["kunden_nr", "plz", "ort"], name="kunden")
    """
    ist = list(df.columns)
    fehlen = [s for s in erwartet if s not in ist]
    zusaetzlich = [s for s in ist if s not in erwartet]
    if fehlen or zusaetzlich:
        raise ValueError(f"{name}: Spalten stimmen nicht.\n"
                         f"  fehlen:      {fehlen}\n"
                         f"  zusätzlich:  {zusaetzlich}")
    print(f"Spalten {name}: OK ({len(ist)})")


def zaehle_leere(df):
    """
    Zählt leere Werte pro Spalte. Erkennt beide Arten:
        - NaN / None   (beim normalen Einlesen)
        - "" oder nur Leerzeichen (bei keep_default_na=False)
    Rückgabe:
        DataFrame mit Anzahl und Prozent, sortiert (meiste zuerst)

    Beispiel:
        print(zaehle_leere(kunden))
    """
    leer = df.isna() | df.apply(lambda s: s.astype(str).str.strip() == "")
    ergebnis = pd.DataFrame({
        "leer": leer.sum(),
        "prozent": (leer.mean() * 100).round(1),
    })
    return ergebnis.sort_values("leer", ascending=False)


# =============================================================================
# C) Vergleich und Kontrolle
# =============================================================================
def vergleiche(ergebnisse, nr, thema, erwartet, ist, hinweis=""):
    """
    Vergleicht einen erwarteten Wert mit dem tatsächlichen Wert und hängt
    das Ergebnis als Dictionary an die Liste 'ergebnisse' an.
    Eine Abweichung bricht nicht ab: Sie wird als "weicht ab" angezeigt.

    Parameter:
        ergebnisse : Liste, in die gesammelt wird
        nr         : Nummer/Kennung, z. B. Zeile in data_quality_issues.md
        thema      : kurze Beschreibung
        erwartet   : Sollwert (z. B. aus einer Tabelle)
        ist        : eigener Wert (z. B. maske.sum())
        hinweis    : optionale Erklärung
    Rückgabe:
        True, wenn gleich, sonst False

    Beispiel:
        ergebnisse = []
        vergleiche(ergebnisse, 28, "Dubletten", 25, maske.sum())
        print(pd.DataFrame(ergebnisse))
    """
    ist = int(ist)                      # numpy.int64 -> int
    status = "passt" if ist == erwartet else "weicht ab"
    ergebnisse.append({"Nr": nr, "Thema": thema, "erwartet": erwartet,
                       "ist": ist, "Status": status, "Hinweis": hinweis})
    zeichen = "OK" if status == "passt" else "!!"
    print(f"[{zeichen}] {nr!s:>3} | {thema:<42} | erwartet = {erwartet:>5} | "
          f"ist = {ist:>5} -> {status}")
    return status == "passt"


def kontrollsumme(gelesen, uebernommen, abgelehnt, name=""):
    """
    Prüft die wichtigste ETL-Regel (Q-01): gelesen = übernommen + abgelehnt.
    Wenn Zeilen fehlen oder dazukommen: Abbruch mit AssertionError.

    Die Parameter dürfen Zahlen ODER DataFrames sein (dann zählt len()).

    Beispiel:
        kontrollsumme(2181, gut, abgelehnt, name="bestellungen")
    """
    def anzahl(x):
        return len(x) if hasattr(x, "__len__") else int(x)

    g, u, a = anzahl(gelesen), anzahl(uebernommen), anzahl(abgelehnt)
    assert g == u + a, f"Kontrollsumme {name} FALSCH: {g} != {u} + {a} (Differenz {g - u - a})"
    print(f"Kontrollsumme {name}: {g} = {u} + {a}  OK")


# =============================================================================
# D) Duplikate und Schlüssel
# =============================================================================
def zeige_duplikate(df, spalten=None, anzeigen=10):
    """
    Zählt Duplikate und zeigt Original und Kopie nebeneinander.

    Parameter:
        spalten  : None = ganze Zeile vergleichen,
                   Liste = nur diese Spalten (z. B. Schlüssel)
        anzeigen : wie viele beteiligte Zeilen gezeigt werden
    Rückgabe:
        Maske (True = Kopie, keep="first") zum Weiterarbeiten

    Beispiel:
        maske = zeige_duplikate(bestellungen)
        maske = zeige_duplikate(bestellungen, ["bestell_nr", "position"])
    """
    kopien = df.duplicated(subset=spalten)
    beteiligt = df[df.duplicated(subset=spalten, keep=False)]
    sortierung = spalten if spalten else list(df.columns)
    beteiligt = beteiligt.sort_values(sortierung)

    art = f"Schlüssel {spalten}" if spalten else "ganze Zeile"
    print(f"Duplikate ({art}): {kopien.sum()} Kopien, {len(beteiligt)} beteiligte Zeilen")
    if len(beteiligt):
        # Häufigkeit: Wie oft kommt jede doppelte Kombination vor?
        haeufigkeit = beteiligt.groupby(sortierung).size().value_counts()
        print("Häufigkeit (wie oft -> wie viele):",
              {int(k): int(v) for k, v in haeufigkeit.items()})
        print(beteiligt.head(anzeigen))
    return kopien


def pruefe_schluessel(df, spalten, name=""):
    """
    Prüft, ob ein Schlüssel (eine oder mehrere Spalten) eindeutig und
    nicht leer ist – wie ein PRIMARY KEY in SQL.
    Rückgabe:
        True, wenn eindeutig und vollständig

    Beispiel:
        pruefe_schluessel(kunden, ["kunden_nr"], name="kunden")
        pruefe_schluessel(bestellungen, ["bestell_nr", "position"])
    """
    leer = (df[spalten].isna() | (df[spalten].astype(str).apply(lambda s: s.str.strip()) == "")).any(axis=1)
    doppelt = df.duplicated(subset=spalten, keep=False)
    ok = not leer.any() and not doppelt.any()
    zeichen = "OK" if ok else "!!"
    print(f"[{zeichen}] Schlüssel {spalten} {name}: {leer.sum()} leer, {doppelt.sum()} doppelt beteiligt")
    if doppelt.any():
        print(df[doppelt].sort_values(spalten).head(10))
    return ok


# =============================================================================
# E) Text und Schreibweisen
# =============================================================================
def normalisiere_text(serie):
    """
    Vereinheitlicht Text für VERGLEICHE (nicht zum Speichern):
        1. Unicode NFC  -> 'ö' als ein Zeichen (statt 'o' + '¨')
        2. strip()      -> Leerzeichen am Rand weg
        3. lower()      -> alles klein
    Hinweis: 'ae' wird NICHT zu 'ä'. Dafür ist eine Mapping-Tabelle nötig.

    Beispiel:
        ort_norm = normalisiere_text(kunden["ort"])
    """
    return (serie.astype(str)
                 .map(lambda s: unicodedata.normalize("NFC", s))
                 .str.strip()
                 .str.lower())


def finde_schreibvarianten(serie):
    """
    Findet Werte, die nach normalisiere_text() gleich sind, aber im
    Original verschieden geschrieben werden (z. B. Stuttgart / STUTTGART).
    Rückgabe:
        DataFrame: pro normalisiertem Wert Anzahl Schreibweisen,
        Anzahl Zeilen, Liste der Varianten. Nur Gruppen mit > 1 Variante.

    Beispiel:
        print(finde_schreibvarianten(kunden["ort"]))
    """
    norm = normalisiere_text(serie)
    gruppen = (pd.DataFrame({"original": serie, "norm": norm})
               .groupby("norm")["original"]
               .agg(schreibweisen="nunique",
                    zeilen="size",
                    varianten=lambda s: sorted(set(s))))
    gruppen = gruppen[gruppen["schreibweisen"] > 1]
    print(f"Gruppen mit mehreren Schreibweisen: {len(gruppen)}, "
          f"betroffene Zeilen: {gruppen['zeilen'].sum()}")
    return gruppen.sort_values("zeilen", ascending=False)


def zeige_unsichtbare_zeichen(serie):
    """
    Zeigt alle verschiedenen Werte mit repr(), Länge und Markierung für:
        - Leerzeichen am Rand
        - Unicode nicht in NFC-Form (Umlaut aus 2 Zeichen)
    Hilft, wenn value_counts() scheinbar gleiche Werte zweimal zeigt.

    Beispiel:
        zeige_unsichtbare_zeichen(kunden["ort"])
    """
    werte = serie.astype(str)
    for wert in sorted(werte.unique()):
        hinweise = []
        if wert != wert.strip():
            hinweise.append("Leerzeichen am Rand")
        if not unicodedata.is_normalized("NFC", wert):
            hinweise.append("Unicode NFD")
        markierung = ("  <- " + ", ".join(hinweise)) if hinweise else ""
        print(f"  {wert!r:<30} Länge={len(wert):>3}  Anzahl={(werte == wert).sum():>4}{markierung}")


# =============================================================================
# F) Protokoll – nichts still löschen
# =============================================================================
def trenne_mit_protokoll(df, maske_fehler, grund, protokoll=None):
    """
    Teilt einen DataFrame in gute und abgelehnte Zeilen.
    Die abgelehnten Zeilen bekommen eine Spalte 'grund' und werden an
    'protokoll' angehängt. Danach Kontrollsumme (Abbruch, wenn eine Zeile fehlt).

    Parameter:
        maske_fehler : True = Zeile wird abgelehnt
        grund        : Text, warum (steht später im Protokoll)
        protokoll    : bisheriges Protokoll (DataFrame) oder None
    Rückgabe:
        (gut, protokoll) als zwei DataFrames

    Beispiel:
        protokoll = None
        gut, protokoll = trenne_mit_protokoll(best, best.duplicated(), "exakte Dublette", protokoll)
        gut, protokoll = trenne_mit_protokoll(gut, gut["menge"] == "0", "Menge 0", protokoll)
    """
    abgelehnt = df[maske_fehler].copy()
    abgelehnt["grund"] = grund
    gut = df[~maske_fehler].copy()

    # Kontrollsumme direkt hier: Keine Zeile darf verloren gehen
    kontrollsumme(df, gut, abgelehnt, name=f"'{grund}'")

    if protokoll is None:
        protokoll = abgelehnt
    else:
        protokoll = pd.concat([protokoll, abgelehnt])
    return gut, protokoll


def speichere_protokoll(protokoll, pfad):
    """
    Speichert das Protokoll als CSV (Semikolon, UTF-8 mit BOM, damit Excel
    die Umlaute richtig zeigt). Legt den Ordner an, falls er fehlt.
    index=True: Die ursprüngliche Zeilennummer bleibt erhalten.

    Beispiel:
        speichere_protokoll(protokoll, basis / "data/rejected/bestellungen_rejected.csv")
    """
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    protokoll.to_csv(pfad, sep=";", encoding="utf-8-sig", index=True, index_label="zeile_original")
    print(f"Protokoll gespeichert: {pfad} ({len(protokoll)} Zeilen)")
    if len(protokoll):
        print("Gründe:", {k: int(v) for k, v in protokoll["grund"].value_counts().items()})


# =============================================================================
# Selbsttest: läuft nur, wenn diese Datei direkt gestartet wird, nicht beim Import.
# =============================================================================
if __name__ == "__main__":
    abschnitt("Selbsttest hilfsfunktionen.py")

    # Kleine Beispieldaten (alles Text, wie nach lese_csv_als_text)
    demo = pd.DataFrame({
        "bestell_nr": ["1", "1", "2", "2", "3", ""],
        "position":   ["1", "1", "1", "2", "1", "1"],
        "ort":        ["Stuttgart", "Stuttgart", "STUTTGART", " Stuttgart", "Ulm", "ulm"],
        "menge":      ["5", "5", "0", "3", "2", "1"],
    })
    print(demo)

    abschnitt("leere Werte", zeichen="-")
    print(zaehle_leere(demo))

    abschnitt("Duplikate", zeichen="-")
    maske = zeige_duplikate(demo)
    zeige_duplikate(demo, ["bestell_nr", "position"])

    abschnitt("Schlüssel", zeichen="-")
    pruefe_schluessel(demo, ["bestell_nr", "position"], name="demo")

    abschnitt("Schreibweisen", zeichen="-")
    print(finde_schreibvarianten(demo["ort"]))
    zeige_unsichtbare_zeichen(demo["ort"])

    abschnitt("Vergleich", zeichen="-")
    ergebnisse = []
    vergleiche(ergebnisse, 1, "Kopien", 1, maske.sum())
    vergleiche(ergebnisse, 2, "Zeilen", 99, len(demo), "absichtlich falsch")
    print(pd.DataFrame(ergebnisse))

    abschnitt("Protokoll", zeichen="-")
    protokoll = None
    gut, protokoll = trenne_mit_protokoll(demo, demo.duplicated(), "exakte Dublette", protokoll)
    gut, protokoll = trenne_mit_protokoll(gut, gut["menge"] == "0", "Menge 0", protokoll)
    kontrollsumme(demo, gut, protokoll, name="gesamt")
    print(protokoll)

    print("\nSelbsttest fertig.")
