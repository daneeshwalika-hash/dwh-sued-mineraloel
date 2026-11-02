# Namenskonventionen – DWH Süd-Mineralöl

Stand: 11.10.2026 · Gilt für alle neuen Tabellen, Spalten, Constraints und Skripte.

> Vereinbarung seit 07.10.2026: deutsche, sprechende Namen und Tabellen im Singular.
> In vielen Firmen sind Namen englisch. Entscheidend ist eine **einheitliche** Konvention.

## 1. Allgemein

| Regel | Beispiel | Grund |
|---|---|---|
| Alles klein, Wörter mit `_` (snake_case) | `kunden_nr`, `ist_aktuell` | PostgreSQL wandelt Namen ohne Anführungszeichen ohnehin in Kleinbuchstaben um |
| Keine Umlaute, kein ß in Namen | `gueltig_von`, nicht `gültig_von` | Manche Werkzeuge brauchen sonst Anführungszeichen |
| Deutsche, sprechende Namen | `bestelldatum`, nicht `bdat` | Vereinbarung im Projekt; lesbar ohne Data Dictionary |
| In **Werten** sind Umlaute erlaubt | `'Baden-Württemberg'`, `'März'` | Werte sind Daten, keine Namen |

## 2. Schemas (Schichten)

| Schema | Inhalt | Regel |
|---|---|---|
| `stg` | Rohdaten 1:1 als `TEXT` (E-10, E-17) | Tabellenname = Dateiname, deshalb Plural erlaubt (`stg.bestellungen`) |
| `dwh` | Star Schema (Dimensionen und Fakten) | Nur das ETL schreibt hier (E-16) |
| `mart` | Views für F-01 bis F-08 und die Datenqualität (E-37, E-40, E-42) | Eine View pro Auswertung: `mart.v_f01_umsatz_monat` |
| `protokoll` | Protokolltabellen der Ladestrecke (E-42) | Keine Dimensionen, keine Fakten: `protokoll.abgewiesene_position` |

## 3. Tabellen

| Art | Präfix | Form | Beispiel |
|---|---|---|---|
| Dimension | `dim_` | Singular | `dim_kunde`, `dim_produkt` |
| Junk Dimension | `dim_` | Singular, nach Inhalt | `dim_status` |
| Faktentabelle | `fact_` | Name des Geschäftsprozesses | `fact_verkauf` |
| View | `v_` | | `v_f01_umsatz_monat` |

## 4. Spalten

| Art | Regel | Beispiel |
|---|---|---|
| Surrogatschlüssel | `<dimension>_sk` | `kunde_sk`, `produkt_sk` |
| Fremdschlüssel | gleicher Name wie der PK der Dimension | `fact_verkauf.kunde_sk` |
| Business Key | Name aus der Quelle | `kunden_nr`, `artikel_nr` |
| Boolean | `ist_` oder sprechend als Aussage | `ist_aktuell`, `ist_feiertag_bw`, `preis_aus_listenpreis` |
| Gültigkeit (SCD 2) | `gueltig_von`, `gueltig_bis` | |
| Technische Spalten | Unterstrich am Anfang | `_source_file`, `_loaded_at` |

## 5. Constraints und Indizes

| Art | Muster | Beispiel |
|---|---|---|
| Primärschlüssel | `pk_<tabelle>` | `pk_fact_verkauf` |
| Fremdschlüssel | `fk_<tabelle>_<ziel>` | `fk_fact_verkauf_kunde` |
| UNIQUE | `uq_<tabelle>_<spalte(n)>` | `uq_dim_produkt_artikel_nr` |
| CHECK | `ck_<tabelle>_<spalte/regel>` | `ck_fact_verkauf_menge` |
| Index | `ix_<tabelle>_<spalte>` | `ix_fact_verkauf_datum` |
| Eindeutiger Index | `ux_<tabelle>_<regel>` | `ux_dim_kunde_aktuell` |

Grund: Eine Fehlermeldung wie `violates check constraint "ck_fact_verkauf_menge"` sagt sofort, welche Regel verletzt wurde.

## 6. Dateien

| Ordner | Muster | Beispiel |
|---|---|---|
| `sql/` | `NN_verb_objekt.sql`, Reihenfolge der Ausführung | `02_create_dwh.sql`, `01b_typpruefung_staging.sql` |
| `etl/` | `NN_verb_objekt.py` | `01_lade_staging.py` |
| `docs/` | Thema klein geschrieben | `entscheidungen.md`, `namenskonventionen.md` |

## 7. Code

- Variablen, Funktionen und Kommentare auf Deutsch (`lade_staging()`, `anzahl_soll`).
- Python: `snake_case` für Variablen und Funktionen, Konstanten in GROSSBUCHSTABEN (`ORT_ABK`).
- SQL-Schlüsselwörter in GROSSBUCHSTABEN, Namen klein (`SELECT kunden_nr FROM dwh.dim_kunde`).
