# Anforderungen – DWH Süd-Mineralöl Handel GmbH

Stand: Analysephase, F-08 ergänzt am 19.10.2026 · Autor: Daneesh Walika

> Grundsatz: **erst die Anforderung, dann das Werkzeug.**
> Jede Anforderung muss **überprüfbar** sein. Sonst ist sie nur ein Wunsch.
>
> Kennungen: **F** = fachliche Frage (Business Question), **Q** = Qualitätsanforderung,
> **R** = Rahmenbedingung, **O** = offene Frage an die Fachabteilung.

## 1. Ausgangslage

Die Süd-Mineralöl Handel GmbH (Großhandel für Kraftstoffe, Heizöl, Schmierstoffe und Zubehör, Raum Böblingen) exportiert ihre Daten aus dem Warenwirtschaftssystem (WaWi) als CSV und JSON. Die Dateien sind uneinheitlich und fehlerhaft. Die Geschäftsleitung kann einfache Fragen zu Umsatz, Kunden und Produkten nicht beantworten.

**Ziel:** Ein Data Warehouse (Star Schema) auf PostgreSQL, das die Fragen in Abschnitt 3 zuverlässig und nachvollziehbar beantwortet.

## 2. Datenquellen

| Datei | Inhalt | Zeilen (roh) |
|---|---|---|
| `kunden.csv` | Kundenstamm | 157 |
| `produkte.json` | Artikelstamm (verschachtelt) | 25 |
| `bestellungen.csv` | Bestellpositionen (1 Zeile = 1 Artikel in 1 Bestellung) | 2.181 |
| `kunden_update_2026-01.csv` | Änderungen und neue Kunden, Stand 10.01.2026 | 20 |

## 3. Fachliche Anforderungen (Business Questions)

| ID | Frage der Geschäftsleitung | Präzisierte, überprüfbare Anforderung |
|---|---|---|
| F-01 | Wie viel Umsatz pro Monat 2024 und 2025? | Summe `umsatz_netto` je Kalendermonat 2024-01 bis 2025-12. Netto = Menge × Einzelpreis − Rabatt, **ohne** stornierte Positionen, ohne MwSt. |
| F-02 | Top-10-Kunden nach Umsatz? | Die 10 Kunden mit der höchsten Summe `umsatz_netto` im Gesamtzeitraum. Der Unbekannt-Kunde (−1) wird nicht mitgezählt. |
| F-03 | Umsatz nach Produktkategorie? | Summe `umsatz_netto` je Haupt- und Unterkategorie. |
| F-04 | Umsatz nach Stadt / Region? | Summe `umsatz_netto` je Ort und Bundesland, **zum Zeitpunkt der Bestellung** (siehe F-07). |
| F-05 | Anteil stornierter Bestellungen? | Anteil der **Positionen** mit Status `storniert` an allen Positionen, zusätzlich der Anteil der Bestellungen, die **vollständig** storniert sind. |
| F-06 | Häufigste Zahlungsart? | Anzahl Bestellungen und Umsatz je Zahlungsart (Rechnung, Lastschrift, Bar, Vorkasse). |
| F-07 | Wo wohnte der Kunde zum Zeitpunkt der Bestellung? | Historisierung der Kundenadresse mit SCD Typ 2 (`gueltig_von`, `gueltig_bis`, `ist_aktuell`). |
| F-08 | Welche Kunden bestellen wiederholt? | Kunden (`kunden_nr`, ohne −1) mit **mindestens 2** Bestellungen, die mindestens eine nicht stornierte Position haben, mit Bestellungen und Umsatz; dazu die Wiederkaufquote = Wiederholungskunden / Kunden mit mindestens einer Bestellung (E-40, ergänzt 19.10.2026). |

## 4. Qualitätsanforderungen

| ID | Anforderung | Prüfung |
|---|---|---|
| Q-01 | Keine Zeile geht still verloren | Kontrollsumme: Zeilen roh = geladen + rejected + entfernte Dubletten |
| Q-02 | Jede abgewiesene Zeile hat einen Grund | Spalte `grund` in `data/rejected/*.csv` ist nie leer |
| Q-03 | Referenzielle Integrität im DWH | Jeder Fremdschlüssel in `fact_verkauf` existiert in seiner Dimension (FK-Constraints) |
| Q-04 | Nachvollziehbarkeit | Jede Bereinigungsregel steht in `docs/entscheidungen.md` |
| Q-05 | Reproduzierbarkeit | Ein erneuter ETL-Lauf mit denselben Dateien liefert dasselbe Ergebnis |

## 5. Rahmenbedingungen

| ID | Rahmenbedingung |
|---|---|
| R-01 | Werkzeuge: Python 3.12 + pandas (PyCharm, `.venv`), PostgreSQL 18 + pgAdmin 4 (siehe E-11) |
| R-02 | Rohdateien in `data/raw/` werden **nie** verändert |
| R-03 | DSGVO: Personenbezogene Daten (Name, Telefon, E-Mail) nur, wenn für eine Frage nötig. Für F-01 bis F-07 werden Telefon und E-Mail nicht gebraucht. |

## 6. Offene Fragen an die Fachabteilung

Bis zur Antwort gilt je Frage eine dokumentierte Annahme (`entscheidungen.md`, Stand der Antworten in `offene_fragen.md`).

| ID | Frage | Warum wichtig |
|---|---|---|
| O-01 | Zählen Positionen mit Status `offen` schon zum Umsatz? | Ändert F-01 bis F-04 |
| O-02 | Sind negative Mengen Retouren oder Erfassungsfehler? | Retouren müssten den Umsatz senken, Fehler müssen raus |
| O-03 | „Stornierte Bestellungen“: pro Bestellung oder pro Position? | Der Status steht in der Quelle **pro Position** |
| O-04 | Sind Kunden mit gleichem Namen und gleicher E-Mail dieselbe Person? | Beeinflusst F-02 (Top-10) |
| O-05 | Sind die 25 doppelten Zeilen in bestellungen.csv ein doppelter Export? | Immer Paare, nie direkt untereinander (min. 34 Zeilen Abstand). Betrifft die Ladeprüfung |
| O-06 | Wie viel wurde bei `teilgeliefert` tatsächlich geliefert? | Die Quelle hat nur die bestellte Menge. Siehe E-13 |
| O-07 | Bedeutet ein leerer Rabatt „0 %“ oder „unbekannt“? | 324 Positionen. Beeinflusst Netto-Umsatz. Siehe E-08 |
| O-08 | K0105 im Kunden-Update ohne Telefon und E-Mail: bewusst gelöscht oder unvollständiger Export? | Entscheidet, ob leere Werte im Update alte Werte überschreiben |
