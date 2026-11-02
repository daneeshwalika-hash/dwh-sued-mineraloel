"""
etl/kunden_updates.py

Zweck      : Findet alle Kunden-Update-Dateien kunden_update_*.csv und bestimmt aus dem
             Dateinamen das Gültigkeitsdatum der neuen Kundenversion (E-43).
             Eine Stelle für die Regel: etl/01 (Staging) und etl/03 (Bereinigung) benutzen sie.
Eingabe    : Ordner mit Rohdateien (data/raw/ oder ein Testordner)
Ausgabe    : Liste (Pfad, gueltig_von), sortiert nach gueltig_von
Anforderung: erneuter Lauf nach Datennachschub aktualisiert, Q-05 gleiche Dateien = gleiches Ergebnis
Bezug      : E-14, E-31, E-43
Aufruf     : kein eigener Start; import in etl/01_lade_staging.py und etl/03_bereinige_quellen.py

Regel (E-43):
  - Neue Dateien heißen kunden_update_JJJJ-MM-TT.csv. Das Datum im Namen ist gueltig_von der
    neuen Version (die alte Version endet am Tag davor).
  - Ausnahme: kunden_update_2026-01.csv behält 2026-01-10 (E-31, Datum aus den Unterlagen).
  - Name nicht lesbar oder Datum ungültig -> Abbruch (UpdateDateiFehler). Nie still überspringen.
  - Zwei Dateien mit demselben Datum -> Abbruch (die Reihenfolge wäre nicht eindeutig).
"""
import re
from datetime import date
from pathlib import Path

# Suchmuster für alle Kandidaten. Bewusst weit: Jede Datei, die so beginnt, wird geprüft.
# Eine falsch benannte Datei (z. B. kunden_update_Feb.csv) fällt so auf, statt still zu fehlen.
SUCHMUSTER = "kunden_update_*.csv"

# Genaues Namensmuster für neue Dateien: kunden_update_JJJJ-MM-TT.csv (Groß-/Kleinschreibung genau).
MUSTER_DATEINAME = re.compile(r"kunden_update_(\d{4})-(\d{2})-(\d{2})\.csv")

# Dokumentierte Ausnahmen mit Datum aus den Unterlagen (E-31). Neue Ausnahmen nur per Entscheidung.
AUSNAHMEN = {"kunden_update_2026-01.csv": date(2026, 1, 10)}


class UpdateDateiFehler(Exception):
    """Eine Update-Datei passt nicht zur Regel E-43. Der Lauf bricht ab."""


def gueltig_von_aus_dateiname(name):
    """Gibt das Gültigkeitsdatum zu einem Dateinamen zurück oder wirft UpdateDateiFehler.

    Beispiel: 'kunden_update_2026-04-01.csv' -> date(2026, 4, 1);
              'kunden_update_2026-01.csv'    -> date(2026, 1, 10) (Ausnahme E-31).
    """
    if name in AUSNAHMEN:
        return AUSNAHMEN[name]
    treffer = MUSTER_DATEINAME.fullmatch(name)
    if not treffer:
        raise UpdateDateiFehler(
            f"Dateiname '{name}' nicht lesbar. Erwartet: kunden_update_JJJJ-MM-TT.csv (E-43). "
            "Datei umbenennen oder aus dem Ordner nehmen; sie wird NICHT übersprungen.")
    jahr, monat, tag = (int(x) for x in treffer.groups())
    try:
        return date(jahr, monat, tag)
    except ValueError as fehler:
        raise UpdateDateiFehler(f"Dateiname '{name}': ungültiges Datum ({fehler}) (E-43).") from None


def finde_update_dateien(ordner):
    """Alle Kunden-Update-Dateien im Ordner als Liste (Pfad, gueltig_von), nach Datum sortiert.

    Abbruch (UpdateDateiFehler) bei nicht lesbarem Namen oder doppeltem Datum.
    Keine Datei gefunden -> leere Liste (dann gibt es nur den Kundenstamm).
    """
    dateien = []
    # sorted(): feste Reihenfolge der Prüfung und der Fehlermeldungen (Q-05)
    for pfad in sorted(Path(ordner).glob(SUCHMUSTER)):
        dateien.append((pfad, gueltig_von_aus_dateiname(pfad.name)))

    nach_datum = {}
    for pfad, von in dateien:
        if von in nach_datum:
            raise UpdateDateiFehler(
                f"Zwei Update-Dateien mit demselben Gültigkeitsdatum {von}: "
                f"'{nach_datum[von].name}' und '{pfad.name}' (E-43). Reihenfolge nicht eindeutig.")
        nach_datum[von] = pfad
    return sorted(dateien, key=lambda d: d[1])
