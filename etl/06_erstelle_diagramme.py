"""
etl/06_erstelle_diagramme.py

Zweck      : Erzeugt die Diagramme für die Auswertung als PNG (E-41). Die Daten kommen
             NUR aus den mart-Views: Das Skript rechnet keine Kennzahl neu, es zeichnet
             nur, was die View liefert (eine Umsatzdefinition, E-13, E-37).
               D1  F-01 Auftragsumsatz je Monat, Linie 2024 gegen 2025  (mart.v_f01_umsatz_monat)
               D2  F-03 Auftragsumsatz je Hauptkategorie, Balken        (mart.v_f03_umsatz_kategorie)
               D3  Datenqualität: abgewiesene Zeilen je Grund, Balken   (mart.v_dq_abgewiesene_zeilen_grund)
             Kontrollzahlen (zweiter Weg) kommen aus einer anderen mart-View oder direkt aus der
             Tabelle, die die View liest (D3: protokoll.abgewiesene_position, E-42).
Eingabe    : mart.v_f01_umsatz_monat, mart.v_f03_umsatz_kategorie, mart.v_dq_abgewiesene_zeilen_grund,
             protokoll.abgewiesene_position (nur Kontrollzahlen), db_config.ini
Ausgabe    : docs/diagramme/d1_f01_umsatz_monat.png, docs/diagramme/d2_f03_umsatz_kategorie.png,
             docs/diagramme/d3_dq_abgewiesene_zeilen_grund.png (werden bei jedem Lauf neu geschrieben)
             logs/diagramme.csv (eine Zeile pro Diagramm und Lauf, wird ergänzt)
Anforderung: mindestens 3 Diagramme, Kontrollzahlen, Q-05 zweiter Lauf = gleiche Dateien (md5)
Bezug      : E-13, E-27, E-37, E-41, E-42
Aufruf     : .venv\\Scripts\\python.exe etl\\06_erstelle_diagramme.py
             Voraussetzung: Gesamtlauf etl/00_starte_gesamtlauf.py erfolgreich (7 von 7).
             Erwartet: je Diagramm alle Prüfungen [OK], Dateiname und md5, Exit 0.
             Abbruch (Regel verletzt, z. B. View leer oder Summe passt nicht): Meldung,
             KEIN Bild wird geschrieben, Exit 1.
             Warnung (Stand hat sich geändert): wird angezeigt und protokolliert, Bild entsteht.

Reproduzierbar (Q-05, E-41):
  - Backend Agg und matplotlib-Standardwerte (rcdefaults): keine persönliche matplotlibrc wirkt.
  - PNG ohne Metadaten "Software" (sonst Versionstext in der Datei). PNG aus matplotlib
    enthält kein Erstellungsdatum. Kein Laufdatum im Bild.
  - Feste Größe und dpi, Schrift DejaVu Sans (mit matplotlib ausgeliefert, nicht von Windows).
  - Reihenfolge immer per ORDER BY in SQL, nie aus der Datenbank "zufällig".
  - Zahlenformat mit eigener Funktion zahl_de(), NICHT mit locale.setlocale (hängt von Windows ab).
"""
import csv
import hashlib
import importlib
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import matplotlib

# Agg = Bilder ohne Fenster; muss VOR pyplot gesetzt werden.
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib.ticker import FuncFormatter        # noqa: E402
from sqlalchemy import text                        # noqa: E402

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
bereinigung = importlib.import_module("etl.03_bereinige_quellen")   # verbindung_aufbauen()

AUSGABE_ORDNER = PROJEKT / "docs" / "diagramme"
PROTOKOLL_DATEI = PROJEKT / "logs" / "diagramme.csv"

# Feste Bildgröße: 8 x 4,5 Zoll bei 150 dpi = 1200 x 675 Pixel.
GROESSE_ZOLL = (8, 4.5)
DPI = 150

# Farben (helle Fläche): Text in Text-Farben, Serien in festen Farben, Gitter zurückhaltend.
FARBE_FLAECHE = "#fcfcfb"
FARBE_TEXT = "#0b0b0b"
FARBE_TEXT_2 = "#52514e"
FARBE_GITTER = "#e4e3df"
FARBE_SERIE = {"2024": "#2a78d6", "2025": "#eb6834"}   # Farbe folgt dem Jahr, nicht dem Rang
FARBE_BALKEN = "#2a78d6"


class PruefFehler(Exception):
    """Eine Regel ist verletzt. Das Diagramm wird nicht geschrieben."""


# ========================================================================
# 1. Zahlenformat Deutsch (eigene Funktion, Q-05)
# ========================================================================
def zahl_de(wert, nachkomma=0):
    """Formatiert eine Zahl deutsch: Tausenderpunkt, Dezimalkomma.

    WARUM eigene Funktion: locale.setlocale hängt von den Windows-Einstellungen ab.
    Dann sähe das Bild auf einem anderen Rechner anders aus (anderes md5, Q-05).
    Beispiel: zahl_de(1112492.5) -> '1.112.493', zahl_de(91.25, 1) -> '91,3'.
    """
    # Decimal + quantize: kaufmännisch runden (0,5 -> auf), nicht "Banker's Rounding" wie round().
    d = Decimal(str(wert)).quantize(Decimal(1).scaleb(-nachkomma), rounding="ROUND_HALF_UP")
    text_en = f"{d:,.{nachkomma}f}"                       # 1,112,492.50
    return text_en.replace(",", "_").replace(".", ",").replace("_", ".")


def euro_achse(wert, _position):
    """Beschriftung der Euro-Achse, z. B. '150.000 €'."""
    return f"{zahl_de(wert)} €"


# ========================================================================
# 2. Prüfungen mit Reaktion (wie E-35: Regel -> Abbruch, Stand -> Warnung)
# ========================================================================
def pruefe(ergebnisse, nr, art, pruefung, soll, ist):
    """Vergleicht Soll und Ist und merkt sich das Ergebnis.

    art 'R' = Regel: gilt bei allen Daten, Abweichung -> Abbruch (kein Bild).
    art 'S' = Stand 19.10.2026: Abweichung -> Warnung, das Bild entsteht trotzdem.
    """
    ok = soll == ist
    reaktion = "Abbruch" if art == "R" else "Warnung"
    ergebnisse.append((nr, art, pruefung, soll, ist, "OK" if ok else "FEHLER", reaktion))
    print(f"  [{'OK' if ok else 'FEHLER'}] {nr:<4} {pruefung:<55} Soll {soll!s:>12}  Ist {ist!s:>12}  {reaktion}")


def regel_verletzt(ergebnisse):
    return any(e[5] == "FEHLER" and e[1] == "R" for e in ergebnisse)


# ========================================================================
# 3. Gemeinsamer Rahmen für alle Diagramme
# ========================================================================
def neue_abbildung(titel, untertitel):
    """Leere Abbildung mit einheitlichem Aussehen (Titel, Fläche, Achsen zurückhaltend)."""
    fig, ax = plt.subplots(figsize=GROESSE_ZOLL, dpi=DPI)
    fig.patch.set_facecolor(FARBE_FLAECHE)
    ax.set_facecolor(FARBE_FLAECHE)
    fig.suptitle(titel, x=0.02, y=0.97, ha="left", fontsize=13, fontweight="bold", color=FARBE_TEXT)
    fig.text(0.02, 0.885, untertitel, ha="left", fontsize=9.5, color=FARBE_TEXT_2)
    for seite in ("top", "right", "left"):
        ax.spines[seite].set_visible(False)
    ax.spines["bottom"].set_color(FARBE_TEXT_2)
    ax.tick_params(colors=FARBE_TEXT_2, labelsize=9, length=0)
    return fig, ax


HINWEIS_UMSATZ = "Auftragsumsatz netto ohne Storno (E-13)"


def speichere(fig, dateiname, quelle, hinweis=HINWEIS_UMSATZ):
    """Speichert die Abbildung reproduzierbar und gibt Pfad und md5 zurück.

    metadata={'Software': None}: kein Versionstext in der PNG-Datei (Q-05).
    Keine bbox_inches='tight': feste Pixelgröße bei jedem Lauf.
    """
    fig.text(0.02, 0.02, f"Quelle: {quelle} · {hinweis}",
             ha="left", fontsize=8, color=FARBE_TEXT_2)
    AUSGABE_ORDNER.mkdir(parents=True, exist_ok=True)
    pfad = AUSGABE_ORDNER / dateiname
    fig.savefig(pfad, dpi=DPI, facecolor=FARBE_FLAECHE, metadata={"Software": None})
    plt.close(fig)
    md5 = hashlib.md5(pfad.read_bytes()).hexdigest()
    return pfad, md5


# ========================================================================
# 4. D1: F-01 Umsatz je Monat, 2024 gegen 2025
# ========================================================================
def diagramm_d1(verbindung):
    """Linie je Jahr über die 12 Monate. Daten 1:1 aus mart.v_f01_umsatz_monat."""
    print("\nD1 F-01 Umsatz je Monat (mart.v_f01_umsatz_monat)")
    zeilen = verbindung.execute(text(
        "SELECT jahr, monat, monat_name, umsatz_netto FROM mart.v_f01_umsatz_monat ORDER BY jahr, monat"
    )).all()
    # Kontrollsumme aus einer ANDEREN mart-View (F-03). M1/M2 in sql/05b beweisen F-01 = F-03.
    kontrolle = verbindung.execute(text("SELECT SUM(umsatz_netto) FROM mart.v_f03_umsatz_kategorie")).scalar()

    ergebnisse = []
    summe = sum((z.umsatz_netto for z in zeilen), Decimal(0))
    # R: F-01 umfasst laut docs/anforderungen.md genau 2024-01 bis 2025-12 = 24 Monate.
    pruefe(ergebnisse, "D1.1", "R", "Monate in der View (2024-01 bis 2025-12)", 24, len(zeilen))
    # R: Was gezeichnet wird, ergibt dieselbe Summe wie F-03 (kein Wert geht verloren).
    pruefe(ergebnisse, "D1.2", "R", "Summe der Punkte = Summe F-03", kontrolle, summe)
    # S: Stand 19.10.2026 (docs/ergebnisse/ergebnisse.md, Kontrollsumme).
    pruefe(ergebnisse, "D1.3", "S", "Summe Auftragsumsatz (Stand 19.10.2026)", Decimal("2212834.69"), summe)
    if regel_verletzt(ergebnisse):
        raise PruefFehler("D1: Regel verletzt, kein Bild geschrieben")

    # Je Jahr eine Reihe; Monatsnamen aus der View (dim_datum), gekürzt auf 3 Buchstaben.
    jahre = sorted({str(z.jahr) for z in zeilen})
    monate = [z.monat_name[:3] for z in zeilen if str(z.jahr) == jahre[0]]
    summe_jahr = {j: sum((z.umsatz_netto for z in zeilen if str(z.jahr) == j), Decimal(0)) for j in jahre}

    # Summen mit 2 Nachkommastellen: genau vergleichbar mit der Kontrollsumme (E-37).
    untertitel = " · ".join(f"Summe {j}: {zahl_de(summe_jahr[j], 2)} €" for j in jahre)
    fig, ax = neue_abbildung("F-01 · Auftragsumsatz je Monat, 2024 und 2025", untertitel)
    for j in jahre:
        werte = [float(z.umsatz_netto) for z in zeilen if str(z.jahr) == j]
        ax.plot(range(1, 13), werte, color=FARBE_SERIE[j], linewidth=2, marker="o", markersize=5,
                markeredgecolor=FARBE_FLAECHE, markeredgewidth=1.5, label=j)
        # Direkte Beschriftung am Linienende: Identität nicht nur über die Farbe.
        ax.annotate(j, (12, werte[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9, color=FARBE_TEXT)
    ax.set_xticks(range(1, 13), monate)
    ax.set_xlim(0.6, 12.9)
    ax.set_ylim(0, None)
    ax.yaxis.set_major_formatter(FuncFormatter(euro_achse))
    ax.grid(axis="y", color=FARBE_GITTER, linewidth=0.8)
    ax.set_axisbelow(True)
    # Legende über der Fläche: verdeckt keinen Datenpunkt (z. B. die Spitze im April).
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=9, ncols=2,
              labelcolor=FARBE_TEXT, borderaxespad=0.2)
    fig.subplots_adjust(left=0.11, right=0.95, top=0.78, bottom=0.14)

    pfad, md5 = speichere(fig, "d1_f01_umsatz_monat.png", "mart.v_f01_umsatz_monat")
    return pfad, md5, len(zeilen), summe, ergebnisse


# ========================================================================
# 5. D2: F-03 Umsatz je Hauptkategorie
# ========================================================================
def diagramm_d2(verbindung):
    """Waagrechte Balken je Hauptkategorie, größter oben.

    Summe je Hauptkategorie per GROUP BY auf die View (so im COMMENT der View vorgesehen, E-37):
    die View bleibt die einzige Quelle, Python rechnet nichts.
    """
    print("\nD2 F-03 Umsatz je Hauptkategorie (mart.v_f03_umsatz_kategorie)")
    zeilen = verbindung.execute(text(
        "SELECT kategorie, SUM(umsatz_netto) AS umsatz_netto "
        "FROM mart.v_f03_umsatz_kategorie GROUP BY kategorie ORDER BY umsatz_netto DESC, kategorie"
    )).all()
    # Kontrollsumme aus einer ANDEREN mart-View (F-01).
    kontrolle = verbindung.execute(text("SELECT SUM(umsatz_netto) FROM mart.v_f01_umsatz_monat")).scalar()

    ergebnisse = []
    summe = sum((z.umsatz_netto for z in zeilen), Decimal(0))
    # R: Ohne Kategorien gäbe es kein Diagramm.
    pruefe(ergebnisse, "D2.1", "R", "View liefert mindestens eine Kategorie", True, len(zeilen) > 0)
    # R: GROUP BY verliert keinen Wert: Summe der Balken = Summe F-01.
    pruefe(ergebnisse, "D2.2", "R", "Summe der Balken = Summe F-01", kontrolle, summe)
    # S: Stand 19.10.2026: 8 Hauptkategorien.
    pruefe(ergebnisse, "D2.3", "S", "Hauptkategorien (Stand 19.10.2026)", 8, len(zeilen))
    if regel_verletzt(ergebnisse):
        raise PruefFehler("D2: Regel verletzt, kein Bild geschrieben")

    namen = [z.kategorie for z in zeilen][::-1]                 # barh zeichnet von unten: größter oben
    werte = [float(z.umsatz_netto) for z in zeilen][::-1]
    fig, ax = neue_abbildung("F-03 · Auftragsumsatz je Hauptkategorie",
                             f"Summe aller Kategorien: {zahl_de(summe, 2)} € · {len(zeilen)} Hauptkategorien")
    ax.barh(namen, werte, color=FARBE_BALKEN, height=0.62)
    # Wert direkt am Balkenende: genaue Zahl ohne Ablesen an der Achse.
    for y, w in enumerate(werte):
        ax.annotate(f"{zahl_de(w)} €", (w, y), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color=FARBE_TEXT)
    # 15 % Platz rechts für die Wertbeschriftung des längsten Balkens.
    ax.set_xlim(0, max(werte) * 1.15)
    ax.xaxis.set_major_formatter(FuncFormatter(euro_achse))
    ax.grid(axis="x", color=FARBE_GITTER, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", labelcolor=FARBE_TEXT)
    fig.subplots_adjust(left=0.17, right=0.94, top=0.82, bottom=0.14)

    pfad, md5 = speichere(fig, "d2_f03_umsatz_kategorie.png", "mart.v_f03_umsatz_kategorie")
    return pfad, md5, len(zeilen), summe, ergebnisse


# ========================================================================
# 6. D3: Datenqualität, abgewiesene Zeilen je Grund
# ========================================================================
def diagramm_d3(verbindung):
    """Waagrechte Balken je Ablehnungsgrund, häufigster oben. Daten 1:1 aus der View.

    E-27: Eine Zeile kann mehrere Gründe haben und zählt dann bei jedem Grund. Die Summe der
    Balken ist die Zahl der GRÜNDE, nicht der Zeilen. Die Prüfungen sind darauf ausgelegt.
    """
    print("\nD3 Abgewiesene Zeilen je Grund (mart.v_dq_abgewiesene_zeilen_grund)")
    zeilen = verbindung.execute(text(
        "SELECT grund, zeilen FROM mart.v_dq_abgewiesene_zeilen_grund ORDER BY zeilen DESC, grund"
    )).all()
    # Kontrollzahlen direkt aus der Tabelle, die die View liest (zweiter Weg, E-42):
    # Anzahl Zeilen und Anzahl Gründe (je Zeile die Zahl ihrer " | "-getrennten Gründe).
    kontrolle = verbindung.execute(text(
        "SELECT COUNT(*) AS zeilen, "
        "       COALESCE(SUM(array_length(string_to_array(grund, ' | '), 1)), 0) AS gruende "
        "FROM protokoll.abgewiesene_position")).one()

    ergebnisse = []
    summe = sum(z.zeilen for z in zeilen)
    # R: Summe der Balken = Anzahl Gründe in der Tabelle (NICHT Anzahl Zeilen, E-27).
    pruefe(ergebnisse, "D3.1", "R", "Summe der Balken = Anzahl Gründe (Tabelle)", kontrolle.gruende, summe)
    # R: Jede Zeile hat mindestens einen Grund (Q-02) -> Summe der Balken >= Zeilen.
    pruefe(ergebnisse, "D3.2", "R", "Summe der Balken >= abgewiesene Zeilen", True, summe >= kontrolle.zeilen)
    # R: Kein leerer Grund nach dem Zerlegen (Q-02).
    pruefe(ergebnisse, "D3.3", "R", "Leere Gründe", 0, sum(1 for z in zeilen if not (z.grund or "").strip()))
    # S: Stand 19.10.2026 (docs/protokoll.md): 75 Zeilen, 4 verschiedene Gründe.
    pruefe(ergebnisse, "D3.4", "S", "Abgewiesene Zeilen (Stand 19.10.2026)", 75, kontrolle.zeilen)
    pruefe(ergebnisse, "D3.5", "S", "Verschiedene Gründe (Stand 19.10.2026)", 4, len(zeilen))
    if regel_verletzt(ergebnisse):
        raise PruefFehler("D3: Regel verletzt, kein Bild geschrieben")

    namen = [z.grund for z in zeilen][::-1]                     # barh zeichnet von unten: häufigster oben
    werte = [z.zeilen for z in zeilen][::-1]
    fig, ax = neue_abbildung(
        "Datenqualität · Abgewiesene Bestellpositionen je Grund",
        f"{kontrolle.zeilen} abgewiesene Zeilen, {kontrolle.gruende} Gründe "
        f"(eine Zeile kann mehrere Gründe haben und zählt dann bei jedem, E-27)")
    ax.barh(namen, werte, color=FARBE_BALKEN, height=0.55)
    for y, w in enumerate(werte):
        ax.annotate(zahl_de(w), (w, y), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=9, color=FARBE_TEXT)
    ax.set_xlim(0, max(werte) * 1.12)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda wert, _pos: zahl_de(wert)))
    ax.grid(axis="x", color=FARBE_GITTER, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", labelcolor=FARBE_TEXT)
    fig.subplots_adjust(left=0.36, right=0.95, top=0.82, bottom=0.14)

    pfad, md5 = speichere(fig, "d3_dq_abgewiesene_zeilen_grund.png", "mart.v_dq_abgewiesene_zeilen_grund",
                          "Anzahl Zeilen je Grund (protokoll.abgewiesene_position, E-42)")
    return pfad, md5, len(zeilen), summe, ergebnisse


# ========================================================================
# 7. Ablauf
# ========================================================================
def main():
    # Standardwerte von matplotlib: eine persönliche matplotlibrc darf das Bild nicht ändern (Q-05).
    matplotlib.rcdefaults()
    plt.rcParams["font.family"] = "DejaVu Sans"

    lauf = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    protokoll = []
    warnungen = 0
    engine = bereinigung.verbindung_aufbauen()
    try:
        # Nur lesen: eine Verbindung ohne Transaktion zum Schreiben.
        with engine.connect() as verbindung:
            for erzeuge in (diagramm_d1, diagramm_d2, diagramm_d3):
                pfad, md5, punkte, summe, ergebnisse = erzeuge(verbindung)
                warnungen += sum(1 for e in ergebnisse if e[5] == "FEHLER")
                rel = pfad.relative_to(PROJEKT).as_posix()
                print(f"  -> {rel}  md5 {md5}")
                protokoll.append([lauf, rel, md5, punkte, summe,
                                  sum(1 for e in ergebnisse if e[5] == "OK"), len(ergebnisse)])
    except PruefFehler as fehler:
        print(f"\nABBRUCH: {fehler}")
        return 1
    finally:
        engine.dispose()

    bereinigung.protokoll_anhaengen(
        PROTOKOLL_DATEI,
        ["lauf", "datei", "md5", "punkte", "summe_umsatz", "pruefungen_ok", "pruefungen"],
        protokoll)
    print(f"\nDiagramme erstellt: {len(protokoll)}, Warnungen: {warnungen}, Protokoll: logs/diagramme.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
