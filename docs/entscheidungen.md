# Entscheidungen (Decision Log)

Jede Entscheidung folgt dem Schema **Problem → Optionen → Entscheidung → Begründung → Folgen**.
Die Zahlen stammen aus `explore/01_explore.py` bzw. `docs/data_quality_issues.csv`, wenn nicht anders angegeben.
Eine Entscheidung wird nie geändert. Ersetzt eine neue Entscheidung eine alte, steht das bei beiden.

---

## E-01 · Grain der Faktentabelle

- **Entscheidung:** 1 Zeile in `fact_verkauf` = **1 Bestellposition** (1 Artikel in 1 Bestellung).
- **Begründung:** Das ist die feinste Ebene der Quelle. Rabatt und Lieferstatus unterscheiden sich innerhalb einer Bestellung (514 bzw. 493 von 700 Bestellungen haben mehrere Werte). Auf Bestellebene gingen diese Informationen verloren, und F-03 (Umsatz je Kategorie) wäre nicht beantwortbar.

## E-02 · Format `xx/yy/yyyy` im Bestelldatum

- **Problem:** `09/03/2024` kann der 3. September (US) oder der 9. März (DE) sein.
- **Beleg aus den Daten:** Bei 198 Werten dieses Formats ist der **erste** Teil nie größer als 12, der **zweite** Teil 118-mal größer als 12 (z. B. `04/26/2025`).
- **Entscheidung:** Das Format ist **MM/DD/YYYY** und wird explizit mit `format="%m/%d/%Y"` geparst. Kein `format="mixed"`, kein `dayfirst=True`.
- **Begründung:** Entscheidung anhand der Daten statt anhand einer Vermutung. Der Test ist im Explore-Skript und kann jederzeit wiederholt werden.

## E-03 · Datum gehört zur Bestellung, nicht zur Position

- **Problem:** 2 Bestellungen haben eine Position mit Datum 15.08.2027 (Zukunft), 1 Position hat das unmögliche Datum `2027-02-30`.
- **Beobachtung:** Die anderen Positionen derselben Bestellung haben ein gültiges, einheitliches Datum. Kunde und Zahlungsart sind pro Bestellung immer eindeutig.
- **Entscheidung:** Bestelldatum, Kunde und Zahlungsart sind Attribute der **Bestellung** (Kopf). Ein ungültiges oder zukünftiges Datum wird durch das Datum der übrigen Positionen derselben Bestellung ersetzt und **protokolliert**. Nur wenn keine gültige Position existiert: rejected.
- **Begründung:** Im ERM der Quelle (siehe `erm_quelle.drawio`) sind Bestellung und Bestellposition getrennte Entitäten. Die CSV ist denormalisiert und wiederholt die Kopfdaten in jeder Zeile.

## E-04 · Bestellungen ohne gültigen Kunden (Orphans)

- **Problem:** 42 Positionen ohne `kunden_nr`, 33 Positionen mit `K9999` (existiert nicht).
- **Optionen:** (a) löschen, (b) dem Kunden „Unbekannt“ zuordnen.
- **Entscheidung:** (b) – eigene Zeile in `dim_kunde` mit `kunde_sk = -1`, `kunden_nr = 'UNBEKANNT'` (Kimball-Methode). Jede Zuordnung wird protokolliert.
- **Begründung:** Der Umsatz ist real und gehört in F-01, F-03 und F-06. Löschen würde den Gesamtumsatz verfälschen. F-02 (Top-10) schließt −1 aus.

## E-05 · Negative Menge und Menge 0

- **Problem:** 40 Positionen mit negativer Menge, 17 mit Menge 0.
- **Beobachtung:** Die negativen Mengen haben ganz normale Status (`geliefert`, `offen` …). Es gibt kein Retouren-Kennzeichen in der Quelle.
- **Entscheidung:** Beide Fälle gehen nach `data/rejected/` mit Grund. Offene Frage O-02 an die Fachabteilung.
- **Begründung:** Ohne Kennzeichen ist eine Retoure nicht von einem Tippfehler zu unterscheiden (z. B. `-2000`). Lieber sichtbar abweisen als falsch rechnen.

## E-06 · Mögliche Dubletten mit verschiedenen Kundennummern (Near Duplicates)

- **Problem:** 18 Kundenzeilen haben den gleichen Vornamen, Nachnamen und die gleiche E-Mail wie eine andere Kundennummer.
- **Beobachtung:** Einige sind offensichtlich dieselbe Person (K0099/K0153 Anna Braun, alle Felder gleich). Andere wohl nicht (K0014 Becker Bau GmbH in Esslingen vs. K0042 Privatkunde in Dresden).
- **Entscheidung:** **Nicht** automatisch zusammenführen. Als Warnung in ein Protokoll schreiben, beide Kundennummern bleiben.
- **Begründung:** Ein falsches Zusammenführen ist schwer rückgängig zu machen und verändert F-02. Die Entscheidung gehört der Fachabteilung (O-04).

## E-07 · Fehlender Einzelpreis

- **Problem:** 56 Positionen ohne Einzelpreis. 4 Produkte (A-007, A-017, A-018, A-019) haben auch keinen Listenpreis.
- **Entscheidung:** Wenn das Produkt einen Listenpreis hat → Listenpreis übernehmen und Kennzeichen `preis_aus_listenpreis = TRUE` setzen. Sonst → rejected.
- **Begründung:** Der Verkaufspreis ist ein Attribut der Position (Preise ändern sich, Rabatte). Der Listenpreis ist nur eine Näherung, deshalb das Kennzeichen.
- **Beleg (11.10.2026, `sql/01b_typpruefung_staging.sql` P9, ohne Dubletten):** Von den 56 Positionen ohne Einzelpreis
  bekommen **49** den Listenpreis (`preis_aus_listenpreis = TRUE`), **7** gehen nach rejected (Produkt ohne Listenpreis).
  Keine dieser 56 Positionen hat ein unbekanntes Produkt.
- **Korrektur 11.10.2026:** Vorher stand hier `= 1`. Nach E-11 ist das Kennzeichen `BOOLEAN`. Seit E-18 steht es in `dim_status`, nicht mehr in `fact_verkauf`.

## E-08 · Leerer Rabatt

- **Problem:** 324 Positionen ohne Rabatt.
- **Entscheidung:** Leer = 0 %.
- **Begründung:** Bei den gefüllten Werten ist 0 der häufigste Wert. **Annahme, zu bestätigen** (O-07).
- **Korrektur 11.10.2026:** Der Verweis lautete vorher „O-01 ff.“, die passende Frage ist O-07.

## E-09 · Bundesland im Kunden-Update

- **Problem:** 4 Kunden im Update haben ein Bundesland, das nicht zum Ort passt (z. B. Leipzig + Baden-Württemberg, Stuttgart + Sachsen). Vermutlich wurde beim Umzug nur die Adresse geändert.
- **Entscheidung:** Das Bundesland wird aus der PLZ abgeleitet (Mapping-Tabelle PLZ-Bereich → Bundesland) und nicht aus der Datei übernommen.
- **Begründung:** Für die Daten gilt eine Quelle der Wahrheit. PLZ und Ort sind konsistent, das Bundesland nicht.

## E-10 · Rohdaten und Staging nur als Text

- **Entscheidung:** Alle Rohdateien werden mit `dtype=str` gelesen, und die Staging-Tabellen haben nur `TEXT`-Spalten.
- **Begründung:** Sonst verliert pandas die führende Null der PLZ (`01067` → `1067`), und Fehler werden beim Laden verschluckt statt beim Prüfen gefunden.

## E-11 · Datenbank: PostgreSQL statt SQL Server

- **Problem:** Der Projektplan nennt SQL Server. Lokal installiert und laufend ist PostgreSQL 18, SQL Server nicht.
- **Entscheidung:** PostgreSQL 18 mit pgAdmin 4. Python-Anbindung über SQLAlchemy + psycopg 3.
- **Begründung:** Keine zusätzliche Installation nötig. SQL Server ist aus der Praxis bekannt, PostgreSQL ist eine neue, im Data Engineering weit verbreitete Kompetenz. Die Modellierung (Star Schema, SCD 2) ist unabhängig vom Datenbanksystem.
- **Geklärt (14.10.2026):** Zielsystem bleibt PostgreSQL 18.
- **Folgen:** Namen klein schreiben (`dwh_sued`), `TEXT` statt `NVARCHAR`, `BOOLEAN` statt `BIT`, `GENERATED ALWAYS AS IDENTITY` für Surrogate Keys (präzisiert durch E-21: Datum, Zahlung und Status haben feste Schlüssel). Zugangsdaten stehen in `db_config.ini` (nicht in Git).

## E-12 · Lieferstatus: Spalte in der Faktentabelle oder Junk Dimension?

- **Status:** **Ersetzt durch E-18** (11.10.2026, nach dem Kimball-Grundsatz für Faktentabellen, siehe E-18). Der Text unten bleibt als Historie stehen.
- **Problem:** `lieferstatus` ist ein Attribut der Position. In der Quelle gibt es 6 Schreibweisen
  für 4 Werte: `geliefert` (374 + `GELIEFERT` 366 + `Geliefert` 343 = 1083), `offen` 369,
  `storniert` 353, `teilgeliefert` 351. Summe 2156 = Positionen nach Dublettenentfernung.
- **Optionen:** (a) Spalte in `fact_verkauf` mit CHECK-Constraint,
  (b) Junk Dimension `dim_status` (Lieferstatus + Flag `preis_aus_listenpreis`).
- **Entscheidung:** (a) – Spalte `lieferstatus TEXT NOT NULL` in `fact_verkauf` mit
  `CHECK (lieferstatus IN ('geliefert', 'teilgeliefert', 'offen', 'storniert'))`.
  Die Schreibweise wird im ETL vereinheitlicht (Mapping, wie bei `kundentyp`).
- **Begründung:** Nur 4 Werte und ein weiteres Flag. Eine Junk Dimension lohnt sich erst bei
  vielen kleinen Attributen. Die Spalte macht F-01 bis F-05 einfacher (kein zusätzlicher JOIN).
  Der CHECK-Constraint sichert die erlaubten Werte genauso wie ein Fremdschlüssel.
- **Verworfen:** (b) – mehr Aufwand (eigene Tabelle, Surrogate Key, JOIN) ohne Nutzen bei dieser Größe.

## E-13 · Welche Positionen zählen zum Umsatz? (O-01)

- **Problem:** F-01 bis F-04 brauchen eine klare Regel, welche Lieferstatus zum Umsatz zählen.
  Nach Vereinheitlichung (E-12): `geliefert` 1083, `offen` 369, `teilgeliefert` 351,
  `storniert` 353 (Summe 2156). Etwa ein Drittel der Positionen ist betroffen.
- **Beobachtung:** Bei `teilgeliefert` ist unbekannt, wie viel geliefert wurde.
  Die Quelle hat nur die bestellte `menge`, keine gelieferte Menge.
  Eine Position kann also nur ganz oder gar nicht zählen.
- **Optionen:** (a) alles außer `storniert` (Auftragsumsatz),
  (b) nur `geliefert`, (c) `geliefert` + `teilgeliefert`.
- **Entscheidung:** (a) – Der Standard-Umsatz in F-01 bis F-04 ist der **Auftragsumsatz**:
  alle Positionen außer `storniert`.
  Alle Positionen werden in `fact_verkauf` geladen, auch `storniert` (wird für F-05 gebraucht).
  Gefiltert wird erst in der Auswertung über `lieferstatus` (seit E-18 in `dim_status`).
  Zum Vergleich zeigt die Auswertung zusätzlich den Anteil „vollständig geliefert“ (F-05).
- **Begründung:** (a) entspricht der Formulierung von F-01 („ohne stornierte Positionen“)
  und braucht keine Schätzung bei `teilgeliefert`. Weil der Status pro Position im DWH steht
  (seit E-18 über `status_sk` → `dim_status`), kann die Fachabteilung später eine andere Regel wählen, ohne dass neu geladen werden muss.
- **Korrektur 11.10.2026:** Begründung an E-18 angepasst (vorher: „Weil der Status in der Faktentabelle steht“). Die Entscheidung selbst ist unverändert.
- **Annahme, zu bestätigen:** O-01 bleibt offen. Neue Frage O-06: gelieferte Menge bei `teilgeliefert`.

## E-14 · Beginn der ersten Version in SCD Typ 2

- **Problem:** Jede Kundenversion in `dim_kunde` braucht `gueltig_von`. Für die erste Version
  bietet sich `erstellt_am` an. Eine Bestellung findet ihre Kundenversion über
  `bestelldatum BETWEEN gueltig_von AND gueltig_bis`.
- **Beleg aus den Daten:** 76 Positionen von 15 Kunden haben ein Bestelldatum **vor** `erstellt_am`
  (z. B. K0006: `erstellt_am` 25.10.2024, Bestellung 101022 vom 04.08.2024). Mit `gueltig_von = erstellt_am` fänden sie keine Version.
- **Optionen:** (a) `gueltig_von = erstellt_am`, (b) `gueltig_von = 1900-01-01` für die erste Version.
- **Entscheidung:** (b) – Die erste Version gilt ab `1900-01-01`. Die aktuelle Version gilt bis
  `9999-12-31` (statt NULL), `ist_aktuell = TRUE`. `erstellt_am` bleibt als normales Attribut erhalten.
- **Begründung:** Jede Bestellung findet sicher eine Kundenversion, keine künstlichen Orphans.
  `9999-12-31` statt NULL macht den BETWEEN-Vergleich einfach, ohne Sonderfall für NULL.
  Kimball-Standard.

## E-15 · Leere Werte im Kunden-Update (O-08)

- **Problem:** Im Kunden-Update hat K0105 kein Telefon und keine E-Mail (`kunden_update_2026-01.csv`, Zeile 3).
  Unklar ist, ob die Werte bewusst gelöscht wurden oder der Export unvollständig ist.
- **Beobachtung:** Telefon und E-Mail werden laut R-03 (DSGVO) nicht ins DWH geladen
  und stehen nicht in `dim_kunde` (siehe `docs/star_schema.drawio`).
- **Entscheidung:** Leere Werte im Update überschreiben **nicht** die alten Werte.
- **Begründung:** O-08 hat deshalb keine Auswirkung auf F-01 bis F-07.
  Die Annahme gilt nur, falls die Felder später doch gebraucht werden.
- **Annahme, zu bestätigen:** O-08 bleibt offen.

## E-16 · Normalisierung der Quelle, Star statt Snowflake im DWH

- **Problem:** Das ERM der Quelle ist normalisiert, das Star Schema nicht.
  Das muss begründet sein, sonst sieht es wie ein Widerspruch aus.
- **Analyse der Quelle:**
  - 1NF: `produkte.json` ist verschachtelt (`lieferant: {name, land}`). Wird beim Laden in `stg` abgeflacht.
  - 2NF: `bestellungen.csv` verletzt 2NF. Schlüssel `(bestell_nr, position)`, aber Kunde, Datum und
    Zahlungsart hängen nur von `bestell_nr` ab (Beleg: E-03). Rabatt und Lieferstatus hängen von der
    Position ab (Beleg: E-01). -> Im ERM Bestellung und Bestellposition getrennt.
  - 3NF: `artikel_nr -> lieferant -> land` -> im ERM Lieferant als eigene Entität.
    Nicht aufgelöst (Quelle beschrieben, wie sie ist): `kategorie_unter -> kategorie_haupt`, `ort -> bundesland`.
- **Optionen:** (a) Star Schema, Dimensionen denormalisiert, (b) Snowflake Schema, Dimensionen in 3NF.
- **Entscheidung:** (a) – `dim_produkt` enthält Kategorie und Lieferant, `dim_kunde` enthält PLZ, Ort, Bundesland.
  Die Kopfdaten der Bestellung stehen als Fremdschlüssel in jeder Zeile von `fact_verkauf` (Grain E-01),
  `bestell_nr` bleibt als Degenerate Dimension.
- **Begründung:** Ein JOIN pro Dimension, einfachere Abfragen für F-01 bis F-07, verständlich für BI-Tools.
  Die Dimensionen sind klein, die Redundanz ist unkritisch. Konsistenz sichert der ETL-Prozess,
  der als einziger in `dwh` schreibt. Kimball-Empfehlung.
- **Verworfen:** (b) – mehr Tabellen und JOINs ohne Nutzen bei dieser Datenmenge.

## E-17 · Ladestrategie für Staging: komplett neu laden

- **Problem:** Das Laden nach `stg.*` muss man mehrmals starten können (Q-05), ohne doppelte Zeilen.
- **Optionen:** (a) jedes Mal leeren und komplett neu laden (Full Reload),
  (b) nur neue Zeilen anhängen (inkrementell), (c) Tabelle mit pandas neu bauen (`if_exists="replace"`).
- **Entscheidung:** (a) – `TRUNCATE` + `INSERT` in einer Transaktion (`etl/01_lade_staging.py`).
  Jede Staging-Tabelle hat zwei technische Spalten: `_source_file` und `_loaded_at`.
- **Begründung:** Die Dateien sind klein (zusammen 2383 Zeilen), und `data/raw/` ändert sich nie (R-02).
  Deshalb ist Staging nur eine Kopie und darf jederzeit neu entstehen.
  Für (b) fehlt in der Quelle ein Merkmal wie „geändert am“.
  (c) ist verworfen: pandas löscht dabei die vorhandene Tabelle und baut sie ohne `_source_file`,
  `_loaded_at` und ohne Kommentare neu.
- **Kein stilles Löschen:** Die Zahl der geleerten Zeilen und der Grund stehen bei jedem Lauf
  in `logs/ladeprotokoll_staging.csv`.
- **Beleg:** 2. Lauf am 07.10.2026: vorher 2181 / 157 / 20 / 25, danach wieder 2383 = 2383.

## E-18 · Junk Dimension `dim_status` für Lieferstatus und Preis-Kennzeichen (ersetzt E-12)

- **Problem:** E-12 hat `lieferstatus TEXT` und das Kennzeichen `preis_aus_listenpreis` direkt in
  `fact_verkauf` gelegt. Grundsatz nach Kimball (07.10.2026): Die Faktentabelle enthält nur Schlüssel und
  Messwerte, Text nur als Degenerate Dimension. Flags und Statuswerte, die zu keiner echten Dimension
  gehören, kommen in eine Junk Dimension.
- **Beleg aus den Daten:** `lieferstatus` hat nach Vereinheitlichung 4 Werte (E-12: `geliefert` 1083,
  `offen` 369, `storniert` 353, `teilgeliefert` 351, Summe 2156, kein leerer Wert).
  `preis_aus_listenpreis` hat 2 Werte (E-07). Alle Kombinationen: 4 × 2 = **8**.
  Prüfabfrage: `sql/01b_typpruefung_staging.sql`, P7 und P9. P9 ergab 49 Positionen mit `preis_aus_listenpreis = TRUE`.
- **Optionen:** (a) E-12 beibehalten (Text und Flag in der Faktentabelle),
  (b) Junk Dimension `dim_status` mit beiden Attributen,
  (c) zwei Mini-Dimensionen (eine für den Status, eine für das Flag).
- **Entscheidung:** (b) – `dwh.dim_status (status_sk SMALLINT, lieferstatus TEXT, preis_aus_listenpreis BOOLEAN)`.
  Alle 8 Kombinationen werden beim Anlegen fest eingefügt (`sql/02_create_dwh.sql`), Schlüssel 1–8 fest vergeben (E-21).
  `fact_verkauf` bekommt `status_sk SMALLINT NOT NULL` als Fremdschlüssel.
- **Keine Zeile −1:** Beide Attribute sind nach dem ETL immer bekannt. Das Flag setzt das ETL (TRUE/FALSE);
  Positionen ohne Preis und ohne Listenpreis gehen nach rejected (E-07). Ein unbekannter Lieferstatus kommt
  in den Daten nicht vor (0 von 2156). Falls er später auftritt, geht die Zeile mit Grund nach rejected (Q-02),
  weil E-13 ohne Status nicht entscheiden kann, ob sie zum Umsatz zählt.
- **Warum alle 8 Kombinationen vorab:** Der Lookup findet immer einen Partner. Eine Kombination, die heute
  nicht vorkommt (z. B. `storniert` + Listenpreis), braucht später keinen neuen Ladeschritt.
  Die Tabelle ändert sich nur, wenn ein neuer Status eingeführt wird.
- **Begründung:** Die Faktentabelle bleibt schmal (nur Schlüssel und Zahlen). Status und Flag werden ein
  normales Filter- und Gruppierkriterium wie jede andere Dimension. Kosten: ein JOIN mehr in F-01 bis F-05,
  bei 8 Zeilen vernachlässigbar. Der CHECK-Constraint aus E-12 bleibt, jetzt in `dim_status`.
- **Beispiel F-05 (Anteil stornierter Positionen):**
  ```sql
  SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE s.lieferstatus = 'storniert') / COUNT(*), 1) AS anteil_storniert_prozent
  FROM dwh.fact_verkauf f
  JOIN dwh.dim_status s ON s.status_sk = f.status_sk;
  ```
- **Verworfen:** (a) widerspricht dem Grundsatz nach Kimball (Text in der Faktentabelle). (c) zwei Tabellen für zusammen
  6 Werte: mehr JOINs ohne Nutzen.
- **Folgen:** E-12 ist ersetzt. E-13 filtert über `dim_status.lieferstatus`. `docs/star_schema.drawio` angepasst.

## E-19 · Geschäftsprozess und Messwerte von `fact_verkauf`

- **Geschäftsprozess:** **Verkauf** (Auftragseingang auf Positionsebene). Das ist Schritt 1 der vier
  Kimball-Schritte (Prozess → Grain E-01 → Dimensionen → Fakten).
- **Messwerte und Additivität:**

  | Spalte | additiv? | Bemerkung |
  |---|---|---|
  | `menge` | ja | |
  | `einzelpreis` | **nein** | Preis je Einheit. Fakt zum Bestellzeitpunkt (kopierter Preis), nicht `listenpreis` |
  | `rabatt_prozent` | **nein** | Prozentwert. Durchschnitt = `SUM(rabatt_betrag) / SUM(umsatz_brutto)`, nie `AVG(rabatt_prozent)` |
  | `umsatz_brutto` | ja | `ROUND(menge × einzelpreis, 2)` |
  | `rabatt_betrag` | ja | `ROUND(menge × einzelpreis × rabatt_prozent / 100, 2)` |
  | `umsatz_netto` | ja | `umsatz_brutto − rabatt_betrag`, Grundlage für F-01 bis F-04 |

- **Problem:** `umsatz_brutto`, `rabatt_betrag` und `umsatz_netto` sind abgeleitete Werte.
  Abgeleitete Zahlen in der Faktentabelle sind ein Risiko: Wer rechnet sie, und bleiben sie konsistent?
- **Optionen:** (a) im ETL berechnen und als normale Spalten speichern,
  (b) von der Datenbank berechnen lassen (`GENERATED ALWAYS AS (...) STORED`),
  (c) nicht speichern, nur in einer View berechnen.
- **Entscheidung:** (b) – generierte, gespeicherte Spalten in `fact_verkauf`.
- **Begründung:** Die Rechenregel steht genau einmal (im DDL). Die Datenbank garantiert die Konsistenz:
  Das ETL kann keine falsche Summe schreiben, ein Schreibversuch wird abgewiesen.
  Die Werte sind gespeichert, Auswertungen und Reconciliation summieren direkt.
  Gerundet wird pro Position auf Cent, damit die Summe der Positionen den Rechnungsbeträgen entspricht.
- **Verworfen:** (a) Konsistenz hinge allein am ETL. (c) Die Regel müsste in jeder Abfrage oder View
  stehen; bei mehreren Views droht Abweichung.
- **Folgen für das ETL:** Das ETL schreibt nur `menge`, `einzelpreis`, `rabatt_prozent`. Die drei generierten
  Spalten dürfen beim Laden nicht im DataFrame bzw. im INSERT stehen.
  PostgreSQL 18: Ohne `STORED` wäre eine generierte Spalte `VIRTUAL` (neuer Standard), deshalb steht `STORED` ausdrücklich da.

## E-20 · Primärschlüssel von `fact_verkauf`

- **Problem:** Das bisherige Design hatte `verkauf_sk IDENTITY` als PK. Fachliche Grundlage (07.10.2026):
  Zum Lesen braucht die Faktentabelle nicht zwingend einen PK; oft nimmt man die Fremdschlüssel plus die
  Degenerate Dimensions. Die Fremdschlüssel allein sind nicht sicher eindeutig.
- **Beleg aus den Daten:** `(bestell_nr, position)` ist nach Entfernen der 25 exakten Dubletten eindeutig
  (Datenexploration, 01.10.2026). Das ist genau der Grain (E-01). Die Fremdschlüssel allein sind es nicht garantiert:
  z. B. landen alle 75 Positionen ohne gültigen Kunden auf `kunde_sk = -1`.
- **Optionen:** (a) `verkauf_sk IDENTITY` + `UNIQUE (bestell_nr, position)`,
  (b) `PRIMARY KEY (bestell_nr, position)`,
  (c) PK aus den Fremdschlüsseln.
- **Entscheidung:** (b) – `PRIMARY KEY (bestell_nr, position)`, Typen `INTEGER` und `SMALLINT`
  (Grundsatz: numerische Bestellnummern als Zahl speichern; belegt durch `sql/01b_typpruefung_staging.sql`, P1 und P2).
- **Begründung:** Die Datenbank schützt den Grain selbst: Eine doppelte Position (z. B. eine übersehene
  Dublette, O-05) wird beim Laden abgewiesen statt doppelt gezählt. Keine zusätzliche Spalte ohne Nutzen:
  Es gibt keine Updates einzelner Faktzeilen (Full Reload) und keine Tabelle, die auf eine Faktzeile verweist.
- **Verworfen:** (a) funktioniert auch, aber `verkauf_sk` hätte keinen Verwendungszweck.
  (c) schützt den Grain nicht und ist nicht eindeutig (siehe Beleg).
- **Folgen:** `verkauf_sk` entfällt in `docs/star_schema.drawio`.

## E-21 · Schlüssel der Dimensionen und Zeile −1 mit IDENTITY

- **Problem:** E-11 sieht `GENERATED ALWAYS AS IDENTITY` für alle Surrogate Keys vor. Das passt nicht
  für jede Dimension, und die Zeile −1 (E-04) ist mit `ALWAYS` nicht direkt einfügbar.
- **Entscheidung pro Dimension:**

  | Dimension | Schlüssel | Grund |
  |---|---|---|
  | `dim_datum` | `INTEGER` JJJJMMTT, z. B. 20250317 | kein Zähler, lesbar, sortiert richtig, stabil. Ein CHECK prüft, dass Schlüssel und Datum zusammenpassen |
  | `dim_zahlung` | `SMALLINT` 1–4, fest | statisch, 4 Werte (F-06), im DDL eingefügt |
  | `dim_status` | `SMALLINT` 1–8, fest | statisch, 8 Kombinationen (E-18), im DDL eingefügt |
  | `dim_kunde` | `INTEGER GENERATED ALWAYS AS IDENTITY` | E-11; SCD 2 erzeugt laufend neue Versionen |
  | `dim_produkt` | `INTEGER GENERATED ALWAYS AS IDENTITY` | E-11 |

- **Zeile −1 – Optionen:** (a) `GENERATED ALWAYS` + einmaliges `INSERT ... OVERRIDING SYSTEM VALUE`,
  (b) `GENERATED BY DEFAULT AS IDENTITY` (eigene Werte immer erlaubt).
- **Entscheidung:** (a) – Die Zeile −1 wird im DDL einmal mit `OVERRIDING SYSTEM VALUE` eingefügt.
- **Begründung:** `ALWAYS` weist jeden anderen selbst gesetzten Schlüssel ab. Ein Fehler im ETL
  (z. B. eine Business-Key-Spalte versehentlich als Schlüssel geschrieben) fällt sofort auf, statt still
  mit dem Zähler zu kollidieren. Die eine Ausnahme ist sichtbar und dokumentiert.
  Der Zähler beginnt bei 1, −1 kann also nie kollidieren. Getestet in Kontrolle 5, Test 3.
- **Verworfen:** (b) erlaubt eigene Werte überall; spätere Kollisionen mit dem Zähler wären möglich.
- **Inhalt der Zeile −1:** `kunden_nr = 'UNBEKANNT'`, `kundentyp`, `ort`, `bundesland` = `'Unbekannt'`,
  gültig von `1900-01-01` bis `9999-12-31`, `ist_aktuell = TRUE` (E-14). So erscheint ihr Umsatz in F-04
  als Ort „Unbekannt“ und verschwindet nicht.
- **Nur `dim_kunde` hat −1:** Unbekannte Produkte gehen nach rejected (Nr 37), ein Datum wird immer
  aufgelöst oder die Zeile rejected (E-03), Zahlung und Status sind immer bekannt (E-18).
- **Folgen für das ETL:** Beim Neuladen von `dim_kunde`: erst `fact_verkauf` leeren (Fremdschlüssel),
  dann `TRUNCATE dwh.dim_kunde RESTART IDENTITY`, danach die Zeile −1 mit demselben INSERT wie im DDL neu anlegen.

## E-22 · Datumsdimension: Zeitraum, Feiertagsquelle und Ladeart

- **Problem:** `dwh.dim_datum` wird nicht aus den Quelldaten geladen, sondern erzeugt (konforme Dimension
  „par excellence“). Dafür braucht es drei Festlegungen: Zeitraum, Quelle der Feiertage, Ladeart.
- **Zeitraum:** **2021-01-01 bis 2027-12-31** = 2556 Tage (2024 ist Schaltjahr).
  Die Bestellungen liegen 2024 bis Anfang 2026 (F-01; Export am 2026-01-05, Nr 31). Ein Datum außerhalb
  des Zeitraums fällt beim Laden der Fakten durch den Fremdschlüssel sofort auf (Q-03), es geht nicht still verloren.
  Reserve nach vorne (bis 2027) für spätere Lieferungen, nach hinten ab 2021 für ältere Daten.
- **Feiertage – Optionen:** (a) Liste von Hand oder aus dem Gedächtnis, (b) eigene Berechnung (Osterformel),
  (c) Python-Paket `holidays` mit `subdiv="BW"`.
- **Entscheidung:** (c), Version fest auf **`holidays==0.106`** in `requirements.txt`.
- **Begründung:** Grounding: keine Feiertage aus dem Gedächtnis. Das Paket ist eine gepflegte, offene Quelle
  und berechnet auch die beweglichen Feiertage (Ostern). Die feste Version macht das Ergebnis reproduzierbar (Q-05):
  Eine neue Paketversion könnte Feiertage ändern; das soll eine bewusste Änderung sein, kein Zufall.
  Ergebnis mit 0.106: **12 Feiertage pro Jahr**, 84 von 2021 bis 2027 (7 feste, 5 bewegliche pro Jahr).
  Zusätzlicher Sichtvergleich eines Jahres mit einer amtlichen Liste: `sql/03_kontrolle_dim_datum.sql`, Teil B.
- **Feiertag am Wochenende:** Bleibt Feiertag (`ist_feiertag_bw = TRUE`, `ist_wochenende = TRUE`).
  Beide Merkmale sind unabhängig. 2021–2027 betrifft das 17 Tage.
- **Ladeart – Optionen:** (a) leeren und neu laden wie Staging (E-17), (b) UPSERT (`INSERT ... ON CONFLICT DO UPDATE`).
- **Entscheidung:** (b) UPSERT in einer Transaktion. Eine Zeile wird nur aktualisiert, wenn sich ihr Inhalt
  wirklich ändert (`IS DISTINCT FROM`).
- **Begründung:** `fact_verkauf` verweist nach dem Laden der Fakten auf `dim_datum`. Leeren ginge dann nur mit den Fakten
  zusammen. UPSERT löscht nie etwas (Regel: nichts still löschen). Das Protokoll
  `logs/ladeprotokoll_dwh.csv` zeigt pro Lauf: vorher, eingefügt, geändert, gelöscht (immer 0), Paketversion.
- **Verworfen:** (a) wegen der Fremdschlüssel. Feiertage aus Wissen oder von Hand: nicht überprüfbar, fehleranfällig.
- **Beleg:** `etl/02_lade_dim_datum.py`, Testlauf 11.10.2026 (Testdatenbank): 1. Lauf 2556 eingefügt,
  2. Lauf 0 eingefügt / 0 geändert, nach künstlicher Änderung eines Tages 1 geändert.

## E-23 · Fehlender Lieferant in `dim_produkt`

- **Problem:** 3 Artikel haben keinen Lieferanten: A-001, A-017, A-020 (`data_quality_issues` Nr 26).
  Das Feld `lieferant` fehlt in `produkte.json` ganz (nicht `null`). In `stg.produkte` sind
  `lieferant_name` und `lieferant_land` deshalb `NULL`.
- **Optionen:** (a) `NULL` in `dim_produkt`, (b) `'Unbekannt'`.
- **Entscheidung:** (b) – `lieferant = 'Unbekannt'` und `lieferant_land = 'Unbekannt'`.
- **Begründung:** Gleiche Regel wie die Zeile −1 für den unbekannten Kunden (E-21: `ort`, `bundesland` = `'Unbekannt'`),
  also einheitlich im ganzen DWH. Auswertungen zeigen eine klare Gruppe „Unbekannt“ statt einer leeren Gruppe.
  Filter wie `WHERE lieferant = ...` oder `WHERE lieferant <> ...` überspringen keine Zeilen still, was bei `NULL` passiert.
  Kimball: `NULL` in Attributen von Dimensionen vermeiden. Jede Ersetzung wird im Ladeprotokoll gezählt (Soll 3), keine stille Änderung.
- **Abgrenzung zu E-21:** Dort geht ein *unbekanntes Produkt* nach rejected. Hier ist das Produkt bekannt, nur ein Attribut fehlt.
- **Auswirkung:** Keine der Fragen F-01 bis F-07 nutzt den Lieferanten.
- **Gefundener Konflikt (14.10.2026):** `ck_dim_produkt_land` in `sql/02_create_dwh.sql` erlaubte nur `^[A-Z]{2}$`
  (ISO-Code, Nr 27). `'Unbekannt'` wäre abgewiesen worden, `NULL` wäre still durchgekommen (ein CHECK lässt `NULL` immer zu).
  Außerdem sagte der Spaltenkommentar zu `lieferant`: „NULL, wenn in der Quelle das Feld fehlt“.
- **Lösung:** Der CHECK wird erweitert: ISO-Code aus 2 Großbuchstaben **oder** `'Unbekannt'`.
  Alle anderen Werte (z. B. `'Deutschland'`, `'de'`) werden weiter abgewiesen. Umgesetzt als Migration
  `sql/02c_aendere_ck_dim_produkt_land.sql` (nicht in `02_create_dwh.sql`, weil dieses Skript bei bestehenden Tabellen abbricht, B4),
  zusammen mit neuen Spaltenkommentaren.
  **Beleg (14.10.2026, `dwh_sued`):** Test `'DE'` und `'Unbekannt'` angenommen, `'Deutschland'` und `'de'` abgewiesen,
  Kontrollen M1–M5 OK, zweiter Lauf gleiches Ergebnis, `dim_produkt` danach 0 Zeilen.
- **Folgen:** `dim_produkt.lieferant` und `lieferant_land` erlauben weiterhin `NULL` (kein `NOT NULL` im DDL).
  Ein späteres `NOT NULL` ist sinnvoll: Dann prüft die Datenbank selbst, dass das ETL keine Lücke vergisst (Q-03),
  statt dass ein `NULL` am CHECK vorbei durchkommt. Sinnvoller Zeitpunkt: als eigene Migration nach dem ersten
  erfolgreichen Laden von `dim_produkt` (`SET NOT NULL` prüft dabei alle vorhandenen Zeilen). Jetzt nicht geändert.

## E-24 · Ladeweg für `fact_verkauf`: pandas + SQL

- **Problem:** Das Laden der Fakten hat zwei verschiedene Aufgaben:
  (1) Bereinigung und Validierung: Datumsformate (E-02, E-03), deutsches Dezimalkomma (Nr 41, Nr 43), Mappings,
  abgewiesene Zeilen mit Grund (E-05, Q-02);
  (2) Lookup der Surrogate Keys: `kunde_sk` mit SCD 2 (`bestelldatum BETWEEN gueltig_von AND gueltig_bis`, E-14),
  `produkt_sk`, `zahlung_sk`, `status_sk`, `datum_sk`.
- **Optionen:** (a) nur SQL (`INSERT ... SELECT` aus `stg`), (b) nur pandas,
  (c) pandas bereinigt und validiert, SQL löst die Schlüssel auf und lädt.
- **Entscheidung:** (c).
  - pandas: Bereinigung, Validierung, abgewiesene Zeilen nach `data/rejected/` mit Grund.
  - Die sauberen Zeilen kommen in eine temporäre Tabelle, gleiches Muster wie bei `dim_datum` (E-22).
  - SQL: `INSERT ... SELECT` mit JOINs zu den Dimensionen, in einer Transaktion.
  - Am Ende prüft die Datenbank: Primärschlüssel (E-20), Fremdschlüssel, CHECK-Constraints.
- **Begründung:** Jedes Werkzeug für das, was es am besten kann. Aufwendige Textbereinigung und Dateien für
  abgewiesene Zeilen sind in pandas einfach. Der Schlüssel-Lookup mit SCD 2 ist als SQL-JOIN einfach und sicher.
  Bewährtes Muster aus E-22. Nur das ETL schreibt in `dwh` (E-16).
- **Verworfen:** (a) Datums- und Textbereinigung in SQL ist lang und schwer zu testen, Dateien für abgewiesene
  Zeilen sind in SQL nicht natürlich. (b) Der SCD-2-Lookup per pandas `merge` ist fehleranfällig (Datumsbereiche).
- **Folgen:** Das ETL schreibt nur `menge`, `einzelpreis`, `rabatt_prozent` (E-19) und die Schlüssel; die drei
  generierten Spalten stehen nicht im INSERT. Die JOINs zu den Dimensionen als `LEFT JOIN`: Findet ein Schlüssel keinen
  Partner, bleibt er `NULL`, und `NOT NULL` in `fact_verkauf` bricht den Lauf sichtbar ab, statt dass die Zeile wie bei
  einem inneren JOIN still verschwindet. Reconciliation nach dem Laden:
  Zeilen roh = geladen + rejected + entfernte Dubletten (Q-01).

## E-25 · Zweistellige Jahre und Format `xx/yy/yyyy` in `erstellt_am`

- **Problem:** `bestelldatum` und `erstellt_am` enthalten Daten mit zweistelligem Jahr (`18.03.24`, Nr 18, Nr 29).
  E-02 regelt das Format `xx/yy/yyyy` nur für `bestelldatum`; `erstellt_am` hat dasselbe Format (Nr 18).
- **Beleg aus den Daten (`stg.*`, 14.10.2026):**
  - Zweistellige Jahre: `bestelldatum` nur `24` und `25`, `erstellt_am` nur `21` bis `24` (Update: `22`).
  - `erstellt_am` im Format `xx/yy/yyyy`: `kunden` 15 Werte, erster Teil nie > 12, zweiter Teil 8-mal > 12;
    `kunden_update` 2 Werte, erster Teil nie > 12, zweiter Teil 2-mal > 12.
- **Entscheidung:** Zweistellige Jahre werden mit `format="%d.%m.%y"` gelesen: `21`–`25` → 2021–2025.
  `xx/yy/yyyy` in `erstellt_am` ist **MM/DD/YYYY** (`format="%m/%d/%Y"`), gleiche Regel wie E-02.
- **Begründung:** Entscheidung aus den Daten, nicht vermutet. Alle zweistelligen Jahre liegen im Zeitraum der übrigen Daten
  (Bestellungen 2024–2025, Kunden ab 2021). Jedes Format wird ausdrücklich geparst, nichts wird geraten.
- **Folgen:** Ein Wert, der zu keinem der vier Formate passt, ist in `bestellungen` ein ungültiges Datum (E-03),
  in den Kundendaten führt er zum Abbruch (Stammdaten).

## E-26 · Bundesland aus dem PLZ-Bereich, abgeleitet aus den eigenen Daten

- **Problem:** E-09 legt fest, dass das Bundesland aus der PLZ abgeleitet wird (Mapping PLZ-Bereich → Bundesland).
  Offen war, woher die Zuordnung kommt. Eine Liste aus dem Gedächtnis ist nicht überprüfbar.
- **Beleg aus den Daten:** In `kunden.csv` (ohne Dubletten, 151 Zeilen mit PLZ) gehört jeder PLZ-Bereich
  (erste 2 Ziffern) zu genau einem Bundesland: `01`, `04` → Sachsen; `70`, `71`, `72`, `73`, `75`, `89` → Baden-Württemberg.
- **Optionen:** (a) Zuordnung aus den eigenen Daten, (b) externe PLZ-Referenz (z. B. GeoNames).
- **Entscheidung:** (a) – feste Tabelle mit diesen 8 Bereichen in `etl/abbildungsregeln.py`. Ein unbekannter Bereich führt zum Abbruch.
- **Kunden ohne PLZ** (K0055, K0076, Nr 6): Das Bundesland kommt über den Ort aus den eigenen Daten
  (Bundesland der anderen Kunden desselben Orts mit PLZ; muss eindeutig sein, sonst Abbruch). Die PLZ bleibt `NULL`,
  es wird keine PLZ erfunden. Jeder Fall steht als Warnung im Protokoll.
- **Begründung:** Grounding: keine Zuordnung aus dem Gedächtnis. Die Tabelle ist aus den Daten belegt und klein.
  Der Abbruch bei einem unbekannten Bereich verhindert eine stille Fehlzuordnung.
- **Einschränkung (zu prüfen):** Die Tabelle gilt nur für die aktuellen Daten. Ein zweistelliger PLZ-Bereich kann
  Landesgrenzen überschreiten. Ob z. B. der Bereich `89` auch Orte außerhalb Baden-Württembergs enthält, ist **nicht geprüft**.
- **Ausblick:** Vor dem Laden neuer Kunden durch eine externe PLZ-Referenz ersetzen (z. B. GeoNames, Lizenz vorher prüfen).
- **Folgen:** Das Bundesland aus der Datei wird nur verglichen. Abweichungen stehen als Warnung im Protokoll
  (`kunden_update`: 4 Fälle, Nr 46). E-09 bleibt unverändert.

## E-27 · Mehrere Ablehnungsgründe pro Zeile

- **Problem:** Eine Position kann aus mehreren Gründen abgewiesen werden (z. B. Produkt `A-999` und Menge 0).
- **Optionen:** (a) nur der erste Grund, (b) alle Gründe.
- **Entscheidung:** (b) – Spalte `grund` enthält alle Gründe, getrennt durch ` | `. Der Soll/Ist-Bericht zählt pro Grund.
- **Begründung:** Jede Zahl aus `docs/data_quality_issues.md` bleibt einzeln überprüfbar. Bei (a) hinge die Zählung
  von der Reihenfolge der Prüfungen ab. Q-02 (Grund nie leer) bleibt erfüllt.

## E-28 · Großschreibung in `nachname` und `bezeichnung` bleibt (Nr 17, Nr 25)

- **Problem:** 2 Nachnamen (Nr 17) und 4 Bezeichnungen (Nr 25) sind komplett in Großbuchstaben (z. B. `ADBLUE`, `SUPER E5`).
- **Optionen:** (a) automatisch umwandeln (`title()`), (b) Werte unverändert lassen.
- **Entscheidung:** (b) – keine automatische Änderung, jede Zeile steht als Warnung im Protokoll.
- **Begründung:** Automatische Umwandlung hat Nebenwirkungen (z. B. `ADBLUE` → `Adblue` statt `AdBlue`,
  `HVO100`, `GmbH`). Es sind nur 6 Werte, keine der Fragen F-01 bis F-07 hängt davon ab.

## E-29 · Zusätzliche Prüfungen der Bestellpositionen

- **Problem:** Die Datenbank prüft Werte erst beim Laden (CHECK in `fact_verkauf`). Ein Verstoß würde den ganzen Lauf abbrechen.
  Außerdem sind Kunde und Zahlungsart Attribute der Bestellung (E-03).
- **Entscheidung:**
  - Rabatt außerhalb 0–100 oder negativer Einzelpreis → rejected mit Grund (erwartet 0, belegt durch P6 in `sql/01b_typpruefung_staging.sql`).
  - Pro Bestellung genau ein Kunde und eine Zahlungsart → nur Warnung (erwartet 0).
- **Begründung:** Ein einzelner fehlerhafter Wert soll sichtbar abgewiesen werden, nicht den Lauf stoppen (Q-02).
  Die Kopfprüfung ist eine Kontrolle der Annahme aus E-03, keine Bereinigungsregel.

## E-30 · Exakte Dubletten in den Stammdaten

- **Problem:** `kunden.csv` hat 4 exakte Dubletten (Nr 1), `produkte.json` 1 Dublette nach Vereinheitlichung der Artikelnummer (Nr 20).
- **Entscheidung:** Entfernen und zählen, gleiche Regel wie bei den Bestellungen (O-05).
  Bleibt danach ein Business Key doppelt (gleiche Nummer, anderer Inhalt), bricht das Skript ab.
- **Begründung:** Exakte Kopien enthalten keine zusätzliche Information. Der Abbruch verhindert, dass bei
  verschiedenem Inhalt still eine Version gewählt wird.

## E-31 · Gültigkeitsdatum der neuen Kundenversion

- **Problem:** Für SCD 2 (E-14) braucht jede neue Version ein `gueltig_von`, die alte ein `gueltig_bis`.
  `BETWEEN gueltig_von AND gueltig_bis` schließt beide Grenzen ein, die Versionen dürfen sich also nicht überlappen.
- **Beleg:** `docs/anforderungen.md` (Abschnitt 2): `kunden_update_2026-01.csv` hat den „Stand 10.01.2026“.
  Die 5 neuen Kunden im Update haben `erstellt_am = 2026-01-10`.
- **Entscheidung:** Neue Version `gueltig_von = 2026-01-10`, alte Version `gueltig_bis = 2026-01-09`, `ist_aktuell = FALSE`.
- **Begründung:** Das Datum stammt aus den Unterlagen und den Daten, nicht geschätzt. Lückenlos und ohne Überlappung.
- **Einschränkung:** 2026-01-10 ist das Lieferdatum des Updates. Das echte Umzugsdatum steht nicht in der Quelle.
  Eine Bestellung zwischen Umzug und Lieferung würde der alten Adresse zugeordnet.
- **Folgen:** Alle Bestellungen liegen 2024–2025 (Nr 31: Export 2026-01-05). Sie finden heute alle die alte Version
  oder die Zeile −1. Die Wirkung von SCD 2 zeigt sich erst bei künftigen Bestellungen.

## E-32 · Welche Kundenattribute erzeugen eine neue Version?

- **Problem:** `docs/star_schema.drawio` markiert nur `plz, ort, bundesland` als historisiert. Für `kundentyp`, `firma`,
  `vorname`, `nachname`, `erstellt_am` gab es keine Regel. Im Update ändert K0065 zusätzlich `kundentyp` (Privat → Gewerbe).
- **Optionen:** (a) SCD 1 für diese Attribute: neue Version nur bei `plz`, `ort`, `bundesland`; die anderen Attribute
  werden in **allen** Versionen des Kunden mit dem aktuellen Wert überschrieben. (b) SCD 2 für alle Attribute.
- **Entscheidung:** (a), wie im Star-Schema-Entwurf.
- **Begründung:** Keine der Fragen F-01 bis F-07 wertet `kundentyp`, `firma` oder Namen zum Bestellzeitpunkt aus.
  F-04 und F-07 brauchen nur die historisierte Adresse. Leere Werte im Update überschreiben nicht (E-15).
- **Folge im Beispiel:** K0065 steht in beiden Versionen als `Gewerbe` (alte Adresse Ulm, neue Ludwigsburg).
- **Ausblick:** `kundentyp` kann SCD 2 werden, wenn die Fachabteilung Umsatz nach Kundentyp zum Bestellzeitpunkt braucht.

## E-33 · Neuladen der Dimensionen `dim_produkt` und `dim_kunde`

- **Problem:** Das Laden muss wiederholbar sein (Q-05). E-21 sieht für `dim_kunde` vor: erst `fact_verkauf` leeren,
  dann `TRUNCATE ... RESTART IDENTITY`, dann die Zeile −1 mit demselben INSERT wie im DDL.
  PostgreSQL lässt `TRUNCATE` auf einer referenzierten Tabelle nur zu, wenn die verweisende Tabelle im selben Befehl steht.
- **Entscheidung:**
  - Vorher Prüfung: `fact_verkauf` muss 0 Zeilen haben, sonst Abbruch mit klarer Meldung (Fakten werden nie still gelöscht).
  - Dann `TRUNCATE dwh.fact_verkauf, dwh.dim_kunde, dwh.dim_produkt RESTART IDENTITY` in **einem** Befehl.
  - Beide Dimensionen in **einer** Transaktion, Soll/Ist-Prüfungen **vor** dem COMMIT. Bei einer Abweichung ROLLBACK,
    der alte Stand bleibt erhalten.
  - Einfügen sortiert (`artikel_nr`; `kunden_nr`, `gueltig_von`), damit die Schlüssel bei jedem Lauf gleich sind.
  - Die Zahl der geleerten Zeilen steht mit Grund in `logs/ladeprotokoll_dwh.csv`.
- **Begründung:** Eine gemeinsame Transaktion, weil ein `TRUNCATE` beide Tabellen leert: Getrennte Transaktionen
  könnten `dim_kunde` ohne Zeile −1 zurücklassen. Gleiche Schlüssel bei jedem Lauf machen Läufe vergleichbar.
- **Folgen:** Sobald Fakten geladen sind, muss zum Neuladen die ganze Strecke in Reihenfolge laufen:
  Fakten leeren, Dimensionen laden, Fakten laden.

## E-34 · Laden von `fact_verkauf`: Schlüssel-Lookup und Neuladen

- **Problem:** E-24 legt den Ladeweg fest (pandas → temporäre Tabelle → SQL). Offen waren der Lookup im Detail,
  der Umgang mit fehlenden Schlüsseln und das Neuladen.
- **Entscheidung:**
  - `INSERT INTO dwh.fact_verkauf … SELECT` aus `tmp_fakt` mit `LEFT JOIN` auf alle 5 Dimensionen:
    `datum_sk` über `datum`; `kunde_sk` über `kunden_nr` + `bestelldatum BETWEEN gueltig_von AND gueltig_bis` (E-14, E-31);
    `produkt_sk` über `artikel_nr`; `zahlung_sk` über `zahlungsart`; `status_sk` über `lieferstatus` + `preis_aus_listenpreis` (E-18).
  - Geschrieben werden nur `menge`, `einzelpreis`, `rabatt_prozent` und die Schlüssel (E-19).
  - **Kein `COALESCE(kunde_sk, -1)`:** Unbekannte Kunden kommen schon aus der Bereinigung als `'UNBEKANNT'` (E-04, protokolliert)
    und finden so die Zeile −1. Ein `COALESCE` würde einen Fehler im Lookup verdecken.
  - Fehlender Schlüssel: zuerst Vorprüfung mit Zählung pro Dimension → Abbruch mit Namen der Dimension;
    zusätzlich verhindert `NOT NULL` jedes stille Durchrutschen. Doppelte Treffer (z. B. überlappende Versionen) verletzen den PK → Abbruch.
  - Neuladen: `TRUNCATE dwh.fact_verkauf` und Einfügen in **einer** Transaktion, sortiert nach `bestell_nr, position`.
    Die Zahl der geleerten Zeilen steht im Protokoll.
- **Begründung:** Keine Zeile kann still verschwinden (LEFT JOIN statt JOIN) oder still falsch zugeordnet werden (kein COALESCE).
  Der natürliche Schlüssel `(bestell_nr, position)` (E-20) macht jeden Lauf vergleichbar.

## E-35 · Gesamttest mit Reaktion

- **Problem:** Eine Prüfung ohne festgelegte Reaktion ist nur Dekoration. Jede Prüfung braucht ein belegtes Soll,
  eine Reaktion und eine verantwortliche Rolle.
- **Entscheidung:** Drei Arten von Prüfungen, ausgeführt **vor dem COMMIT** in `etl/05_lade_fakten.py`:
  - **A · Abgleich zweier Wege → Abbruch:** Soll rechnet pandas mit `Decimal` aus den bereinigten Daten (Rundung pro Position
    wie E-19), Ist liefert die Datenbank nach SQL-Lookup und generierten Spalten. Zeilen, Bestellungen, `SUM(menge)`,
    `SUM(umsatz_brutto)`, `SUM(rabatt_betrag)`, `SUM(umsatz_netto)`, Verteilung Status × Kennzeichen, Zahlungsart, Positionen auf −1.
    Vergleich **exakt auf den Cent**, ohne Toleranz.
  - **C · Regeln, die immer gelten → Abbruch:** Q-01 (roh = Fakten + rejected + Dubletten), Q-02 (Grund nie leer),
    Menge > 0, Rabatt 0–100, Einzelpreis ≥ 0, kein Datum nach dem Export (Nr 31).
  - **B · Abgleich mit dem dokumentierten Stand → Warnung:** Zeilen 2081, Lieferstatus 1050 / 355 / 340 / 336
    (2156-Basis minus rejected je Status: 33 / 14 / 13 / 15), Listenpreis 49, Positionen auf −1 = 71, Positionen außerhalb F-01 = 0.
    Eine Abweichung heißt: der Inhalt hat sich geändert und muss fachlich geprüft werden, kein Ladefehler.
  - Abbruch → ROLLBACK, nichts bleibt. Warnung → Protokoll, das Laden geht weiter.
  - Nachweis pro Lauf in `logs/gesamttest_<datum>.csv` (Prüfung, Soll, Ist, ok, Reaktion, Rolle).
  - Zweite, unabhängige Prüfung: `sql/04_gesamttest.sql` (nur lesen, jederzeit ausführbar; rechnet Q-01 selbst aus `stg`).
- **Rollen:** Daten-Team, Fachbereich Vertrieb, Controlling. Das sind Rollen der (fiktiven) Firma, keine Personen.
- **Begründung:** „Qualität wird bewiesen, nicht behauptet“: Jede Zahl hat eine Herkunft, und jede Abweichung hat eine Folge.
  Weg A vergleicht zwei unabhängige Rechenwege, deshalb ist dort jede Abweichung ein Fehler. Weg B vergleicht mit einem
  festen Stand von heute, der sich mit neuen Daten ändern darf.

## E-36 · Gesamtlauf mit einem Befehl

- **Problem:** Ab jetzt hängen die Schritte voneinander ab (E-33: Dimensionen nur bei leeren Fakten neu ladbar).
- **Entscheidung:** `etl/00_starte_gesamtlauf.py` startet in fester Reihenfolge: `01` Staging → `02` `dim_datum` →
  Fakten bewusst leeren (mit Protokolleintrag) → `04` Dimensionen → `05` Fakten + Gesamttest → `sql/04_gesamttest.sql`.
  Beim ersten Abbruch stoppt der Lauf und nennt den Schritt. Die Migrationen `02c`/`02d` gehören nicht dazu (einmalig).
- **Begründung:** Eine Reihenfolge, die man vergessen kann, gehört in Code, nicht ins Gedächtnis.
- **Einschränkung:** Jeder Schritt hat seine eigene Transaktion. Bricht `04` oder `05` ab, bleibt `fact_verkauf` leer
  (sichtbar im Protokoll), bis der nächste Gesamtlauf erfolgreich ist.

## E-37 · Lesart der Fragen F-01 bis F-07 in den `mart`-Views

- **Problem:** Einige Fragen in `docs/anforderungen.md` lassen zwei Lesarten zu. E-13 regelt den Umsatz nur für F-01 bis F-04.
- **Entscheidung (eine View pro Frage, Schema `mart`, Namen nach `docs/namenskonventionen.md`):**
  - **Umsatz** = `SUM(umsatz_netto)` ohne `storniert` (Auftragsumsatz, E-13) in F-01, F-02, F-03, F-04 **und F-06**.
    Kontrollsumme: F-01 = F-03 = F-04 = F-06 = Auftragsumsatz aus `fact_verkauf`.
  - **F-01:** je Kalendermonat 2024-01 bis 2025-12. Durchschnittlicher Rabatt nur als `SUM(rabatt_betrag) / SUM(umsatz_brutto)` (E-19).
  - **F-02:** je `kunden_nr` (nicht je SCD-Version), ohne −1, Rang mit `RANK()`: Gleichstände werden mitgezeigt,
    keine versteckte, zufällige Grenze bei 10. Namen aus der aktuellen Version (SCD 1, E-32).
  - **F-03:** eine View auf Ebene Unterkategorie mit Spalte Hauptkategorie, kein `ROLLUP`
    (Zwischensummen würden in der Kontrollsumme doppelt zählen).
  - **F-04:** eine View auf Ebene Ort mit Spalte Bundesland, Adresse zum Bestellzeitpunkt (SCD 2). −1 erscheint als „Unbekannt“ (E-21).
  - **F-05:** beide Anteile aus O-03 (Positionen `storniert`; Bestellungen vollständig `storniert`) und zusätzlich
    der Anteil „vollständig geliefert“ (E-13). Basis: geladene Positionen (rejected zählen nicht).
  - **F-06:** Bestellungen zählen, wenn sie mindestens eine nicht stornierte Position haben; Umsatz ohne `storniert`.
  - **F-07:** eine Zeile pro Bestellung, alle Kunden außer −1, mit Ort/Bundesland zum Bestellzeitpunkt, heute und Kennzeichen `umgezogen`.
- **Begründung:** Eine Umsatzdefinition für alle Fragen, eine überprüfbare Summenprobe, keine Doppelzählung.
- **Hinweis F-02 (keine Änderung an E-06 / O-04):** K0092 und K0109 (gleicher Name und gleiche E-Mail) hätten zusammen
  34 148,38 € und lägen damit in den Top 10. Getrennt gezählt sind sie es nicht. Die Entscheidung über das Zusammenführen
  bleibt beim Fachbereich (O-04).

## E-38 · Ergebnisdokument

- **Entscheidung:** `docs/ergebnisse/ergebnisse_f01_f07.md` mit Datum und Commit-Hash, in Git.
  Kunden erscheinen dort nur mit Kundennummer.
- **Hinweis:** Die Daten sind fiktiv. In einer echten Firma würden veröffentlichte Ergebnisse nur Kundennummern zeigen,
  keine Namen (DSGVO, R-03). Die View `mart.v_f02_top10_kunden` enthält Namen nur für die interne Auswertung.

## E-39 · Kontrolle der `mart`-Views im Gesamtlauf

- **Entscheidung:** Das Anlegen der Views (`sql/05_create_mart.sql`) bleibt ein eigener Schritt, weil es sich nicht ändert.
  Die Kontrolle (`sql/05b_kontrolle_mart.sql`, nur lesen) wird Schritt 7 von `etl/00_starte_gesamtlauf.py`.
  Gleiches Format wie `sql/04_gesamttest.sql`: R = Regel → Abbruch, S = Stand → Warnung.
- **Begründung:** Nach jedem Neuladen ist bewiesen, dass die Antworten auf F-01 bis F-07 zur Faktentabelle passen.

## E-40 · F-08 Wiederholungskunden: Schwelle für den HAVING-Filter

- **Problem:** Anforderung: eine Aggregation mit Filter (HAVING). F-01 bis F-07 enthalten keine. Für eine neue Frage
  F-08 „Welche Kunden bestellen wiederholt?“ braucht der Filter eine Schwelle; in `docs/` gab es dafür keine Regel.
- **Beleg (Datenbank, 19.10.2026):** 149 Kunden mit mindestens einer Bestellung (ohne `storniert`, ohne −1).
  Bestellungen je Kunde: 1 → 13 Kunden, 2 → 25, 3 → 18, 4 → 28, 5 → 24, 6 → 20, 7 → 9, 8 → 8, 9/10/12/13 → je 1.
  Mittelwert 4,30, Median 4.
- **Optionen:** (a) mindestens 2 Bestellungen (Wiederholungskunde, Schwelle aus der Definition) – 136 Kunden;
  (b) mehr Bestellungen als der Median (Schwelle aus den Daten, ändert sich mit jedem Lauf) – heute 65 Kunden;
  (c) Kategorien mit mindestens 10 % des Auftragsumsatzes – heute 3, aber die 10 % wären geschätzt.
- **Entscheidung:** (a), festgelegt vom Projektverantwortlichen am 19.10.2026. View `mart.v_f08_wiederholungskunden`
  (`sql/05c_create_mart_f08.sql`): je `kunden_nr`, ohne −1, eine Bestellung zählt, wenn sie mindestens eine nicht
  stornierte Position hat (wie F-06, E-37), `HAVING COUNT(DISTINCT bestell_nr) >= 2`. Zusätzlich die
  **Wiederkaufquote** = Wiederholungskunden / Kunden mit mindestens einer Bestellung, in jeder Zeile der View.
- **Begründung:** Die Schwelle 2 folgt aus der Bedeutung „mehr als einmal bestellt“ und ist kein geschätzter Wert.
  Gleiche Abgrenzung wie F-02 und F-06, damit die Zahlen zueinander passen.
- **Folgen:** Kontrolle in `sql/05b_kontrolle_mart.sql`: M11 (kein Kunde unter 2 Bestellungen), M12 (zweiter Weg ohne
  HAVING: kleinste ≠ größte `bestell_nr`), M13 (Quote passt zu den Zeilen), S11–S13 (Stand 136 / 149 / 91,3 %).
  Die View muss vor dem Gesamtlauf angelegt sein, sonst stoppt Schritt 7. Keine Namen in der View (E-38).
  Die Quote ist bei 91,3 % wenig trennscharf; eine strengere Schwelle wäre eine neue Entscheidung.

## E-41 · Diagramme: Werkzeug, Datenquelle, Ablage und Reproduzierbarkeit

- **Problem:** Anforderung: mindestens 3 Diagramme, die bei jedem Lauf neu entstehen. Die Zahlen dürfen nicht von den
  Antworten auf F-01 bis F-08 abweichen, und ein zweiter Lauf soll dieselben Dateien erzeugen (Q-05).
- **Optionen Datenquelle:** (a) nur die `mart`-Views; (b) Kennzahlen in Python neu berechnen; (c) CSV-Dateien lesen.
- **Entscheidung (festgelegt vom Projektverantwortlichen am 19.10.2026):**
  - Datenquelle (a): nur `SELECT … FROM mart.v_…`, keine Berechnung in Python. Eine Verdichtung, die die View selbst
    vorsieht, läuft in SQL auf der View (F-03 je Hauptkategorie per `GROUP BY kategorie`, siehe `COMMENT` der View).
  - Diagramme: D1 F-01 Umsatz je Monat (Linie 2024 gegen 2025), D2 F-03 Umsatz je Hauptkategorie (Balken, 8 Kategorien),
    D3 abgewiesene Zeilen je Grund folgt aus einer eigenen `mart`-View (kein Lesen der CSV; umgesetzt mit E-42).
  - Skript `etl/06_erstelle_diagramme.py`, Ablage `docs/diagramme/` (in Git), Protokoll `logs/diagramme.csv`.
  - matplotlib `3.11.2` und Pillow `13.0.0` fest in `requirements.txt` (Pillow schreibt die PNG-Dateien).
  - Reproduzierbar: Backend Agg, `rcdefaults()`, Schrift DejaVu Sans, feste Größe und dpi, PNG ohne Metadaten
    `Software`, kein Laufdatum im Bild, Reihenfolge per `ORDER BY`.
  - Beschriftung Deutsch, Zahlenformat mit eigener Funktion `zahl_de()`, nicht mit `locale.setlocale`.
  - Prüfung je Diagramm: Regel (Abbruch, kein Bild): Summe der gezeichneten Werte = Summe aus einer **anderen**
    `mart`-View (D1 gegen F-03, D2 gegen F-01), D1 genau 24 Monate. Stand (Warnung): Kontrollsumme 2 212 834,69 €, 8 Kategorien.
- **Begründung:** Eine Umsatzdefinition (E-13, E-37) und eine Quelle; die Kontrollsummen in `sql/05b` gelten damit auch
  für die Bilder. `locale` hängt von den Windows-Einstellungen ab, die Datei sähe sonst je Rechner anders aus.
- **Folgen:** Das Skript ist kein Schritt von `etl/00_starte_gesamtlauf.py` (bleibt 7 Schritte); `main.py` startet es nach
  dem Gesamtlauf (E-44). Die md5 der PNG-Dateien gelten nur mit den festen Versionen; ein Update von matplotlib
  oder Pillow darf andere Bytes erzeugen und ist eine bewusste Änderung.

## E-42 · Abgewiesene Zeilen als Protokolltabelle in der Datenbank

- **Problem:** Anforderung: Abgelehnte Zeilen landen mit Grund in einer **Protokolltabelle**. Bisher gab es nur
  `data/rejected/bestellungen_rejected.csv`, und diese schrieb nur `etl/03` im Trockenlauf, nicht der Gesamtlauf.
  Für die Tabelle braucht es einen Schlüssel; `stg` hat keine Zeilennummer der Rohdatei (`etl/03` `lese_staging`).
- **Optionen Schlüssel:** (a) Zeilennummer der Rohdatei: neue Spalte in `stg`, Änderungen an `etl/01` und `etl/03`
  (Dubletten-Entfernung mit `subset`); (b) technischer Schlüssel `(_source_file, lfd_nr)`, `lfd_nr` = 1..N in der festen
  Sortierung über alle Spalten; (c) `IDENTITY` mit `TRUNCATE … RESTART IDENTITY` (hängt an der Einfügereihenfolge).
  Kein Schlüssel auf den Rohwerten `(bestell_nr, position)`: Eine künftige Zeile ohne `bestell_nr` oder mit doppeltem
  Schlüssel würde sonst den ganzen Lauf abbrechen.
- **Entscheidung (festgelegt vom Projektverantwortlichen am 19.10.2026):**
  - Schema `protokoll`, Tabelle `protokoll.abgewiesene_position` (`sql/06_create_protokoll_abgewiesen.sql`, Migration):
    Fachspalten als `TEXT` mit Originalwerten (wie `stg`, E-10), `grund NOT NULL` mit `CHECK (btrim(grund) <> '')` (Q-02),
    Schlüssel (b) `(_source_file, lfd_nr)`, keine Spalte `_loaded_at`.
  - Laden in `etl/05_lade_fakten.py` in **derselben Transaktion** wie `fact_verkauf`: Anzahl lesen, `TRUNCATE`, einfügen.
    Die geleerte Anzahl steht in `logs/ladeprotokoll_dwh.csv` („geleert: N Zeilen“).
  - Die CSV bleibt. `etl/05` schreibt sie **nach dem COMMIT** mit derselben Funktion wie `etl/03`
    (`schreibe_rejected_csv()` in `etl/03_bereinige_quellen.py`).
  - View `mart.v_dq_abgewiesene_zeilen_grund` (`sql/06b_create_mart_dq.sql`): Gründe mit
    `unnest(string_to_array(grund, ' | '))` zerlegt (E-27), Anzahl Zeilen je Grund. Quelle für Diagramm D3 (E-41).
  - Prüfungen: `etl/05` C7 (Tabelle = rejected der Bereinigung, Abbruch), C8 (Grund leer, Abbruch), B6 (Stand 75, Warnung),
    C9 nach dem COMMIT (CSV-Zeilen = Tabelle, Exit 1); `sql/04_gesamttest.sql` R9 (Tabelle = roh − Dubletten − Fakten);
    `sql/05b_kontrolle_mart.sql` M14, M15, S14; D3.1–D3.5 im Diagramm-Skript.
  - **Regel für mehrere Gründe (E-27):** Die Summe je Grund ist die Zahl der **Gründe**, nicht der Zeilen. Geprüft wird
    Summe = `SUM(array_length(string_to_array(grund, ' | '), 1))` aus der Tabelle (Gleichheit) und Summe ≥ Zeilen.
    Gleichheit mit der Zeilenzahl (heute 75 = 75) wird nur als Stand geprüft (Warnung), nie als Regel.
- **Begründung:** (b) erfüllt die Anforderung ohne Änderung an der laufenden Strecke `stg`/`etl/01` und ohne fachliche Änderung an
  `etl/03`; reproduzierbar (Q-05). Gleiche Transaktion: Fakten und Protokoll stammen immer aus demselben Lauf, ein
  ROLLBACK setzt beide zurück. CSV erst nach dem COMMIT: keine CSV, die nicht zur Datenbank passt.
- **Folgen:** `lfd_nr` führt nicht in die Rohdatei zurück; eine Zeile ist nur über ihre Originalwerte zu finden.
  Eine Änderung der Sortierung oder der Rohdaten ändert die `lfd_nr`. `sql/06` muss vor dem Gesamtlauf ausgeführt sein,
  `sql/06b` vor Schritt 7 (Kontrolle) und den Diagrammen.
- **Ausblick (a):** Zeilennummer der Rohdatei im Staging (`stg.bestellungen._zeile_nr`, geschrieben von `etl/01`,
  mitgeführt in `etl/03`, Dubletten mit `keep="first"`). Damit wäre jede abgewiesene Zeile bis in die Rohdatei
  rückverfolgbar. Eigene Entscheidung, falls gebraucht.

## E-43 · Datennachschub: alle Kunden-Update-Dateien, Datum aus dem Dateinamen, Full Load

- **Problem:** Anforderung: Ein erneuter Lauf nach Datennachschub aktualisiert das DWH. Bisher war genau eine Datei
  `kunden_update_2026-01.csv` fest eingetragen (`etl/01`, eigene Tabelle `stg.kunden_update_2026_01`, `etl/03`–`05`),
  und `gueltig_von` 2026-01-10 stand fest im Code (E-31). Für neue Dateien fehlte eine Regel für das Datum.
- **Entscheidung (festgelegt vom Projektverantwortlichen am 19.10.2026):**
  - Neue Dateien heißen `kunden_update_JJJJ-MM-TT.csv`. Das Datum im Namen ist `gueltig_von` der neuen Version,
    die alte Version endet am Tag davor (wie E-31).
  - `kunden_update_2026-01.csv` behält 2026-01-10 (E-31) als dokumentierte Ausnahme.
  - Name nicht lesbar, Datum ungültig oder zwei Dateien mit demselben Datum → Abbruch mit Meldung, nie still überspringen.
  - Mehrere Dateien werden in Datumsreihenfolge angewendet, jede gegen den Stand nach der vorigen.
- **Umsetzung:**
  - Regel an einer Stelle: `etl/kunden_updates.py` (`finde_update_dateien()`, `gueltig_von_aus_dateiname()`).
  - Staging: neue Tabelle `stg.kunden_update` für alle Dateien (`sql/07_create_stg_kunden_update.sql`, Migration),
    Herkunft je Zeile in `_source_file` (ohne DEFAULT, NOT NULL). `etl/01` liest erst alle Dateien und prüft sie
    (Soll = gelesen, Spalten), dann leert und lädt es in einer Transaktion; Soll/Ist je Datei im Staging-Protokoll.
  - Die alte Tabelle `stg.kunden_update_2026_01` wird nicht gelöscht (kein stilles Löschen); sie wird nicht mehr
    geladen und trägt einen Hinweis im `COMMENT`. Entfernen wäre eine eigene Entscheidung.
  - `etl/03`: `lese_kunden_updates()` und `bereinige_kunden_updates()` (je Datei mit den bisherigen Regeln, E-30 je Datei).
  - `etl/04`: `baue_kundenversionen(stamm, updates)` mit Liste `[(gueltig_von, DataFrame)]`; ein DataFrame allein
    bedeutet weiter 2026-01-10 (Tests). Neue Version nur nach dem Beginn der aktuellen Version, sonst Abbruch.
- **Full Load oder Delta (E-17, E-33):** **Full Load.** `stg.kunden_update` wird bei jedem Lauf aus allen Dateien in
  `data/raw/` neu geladen, `dim_kunde` aus Stamm + allen Updates neu gebaut (E-33), `fact_verkauf` neu geladen (E-34).
  Begründung: Die Datenmenge ist klein (Gesamtlauf 4 s laut Konsolenausgabe von `etl/00_starte_gesamtlauf.py`), das Ergebnis hängt nur von den Dateien ab, nicht
  von der Vorgeschichte der Datenbank. Damit ist ein zweiter Lauf auf denselben Bestand immer identisch (Q-05), und
  eine korrigierte alte Datei wirkt sofort. Ein Delta-Load bräuchte ein Verzeichnis der schon geladenen Dateien und
  eine Regel für korrigierte Dateien; das lohnt erst bei großen Mengen.
- **Beleg mit den heutigen Dateien:** md5 `dim_kunde` `b1545016…`, `dim_produkt` `16336422…`, `fact_verkauf` `aa087435…`,
  `protokoll.abgewiesene_position` `07bf289f…` unverändert; `stg.kunden_update` hat denselben Inhalt wie
  `stg.kunden_update_2026_01` (20 Zeilen, md5 über alle Fachspalten `b9ce0857…`).
- **Test mit Nachschub:** nur im Testordner (`tests/test_kunden_updates.py`, pytest `tmp_path`), nie in `data/raw/` (R-02):
  künstliche Datei `kunden_update_2026-04-01.csv`, K0042 zieht ein zweites Mal um → drei Versionen, lückenlos.
- **Folgen:** Die Ausnahme in `AUSNAHMEN` darf nur per Entscheidung erweitert werden. Die Prüfung
  „Positionen in Version ab 2026-01-10“ in `etl/04` bleibt ein Stand von heute (E-31 Folgen).

## E-44 · `main.py`: ein Befehl für alles, Anlegen der Datenbankobjekte ohne Löschen

- **Problem:** Anforderung: ein Lauf `python main.py` ohne manuelle Zwischenschritte:
  einlesen → prüfen → laden → abfragen → Diagramme → Protokoll. Bisher waren die DDL-Skripte und Migrationen
  einmalig von Hand auszuführen (README), die Diagramme ein eigener Aufruf. `sql/01_create_staging.sql` enthält
  `DROP TABLE IF EXISTS`, `sql/02_create_dwh.sql` scheitert an vorhandenen Tabellen, `sql/02d` braucht geladene Produkte.
- **Entscheidung (Ablauf festgelegt vom Projektverantwortlichen am 19.10.2026, Umsetzung hier):**
  - `main.py` im Projektordner, Schritte: 1 Datenbankobjekte anlegen → 2 `etl/00_starte_gesamtlauf.py` (7 Schritte) →
    3 Nachlauf `sql/02d` → 4 `etl/06_erstelle_diagramme.py` → Protokoll. Beim ersten Fehler Stopp, Exit 1.
    `--abbruch-test` wird an den Gesamtlauf weitergereicht.
  - Anlegen ohne Löschen: `sql/01` und `sql/02` nur, wenn **keine** ihrer Tabellen existiert; existiert nur ein Teil,
    bricht `main.py` ab (unklarer Stand). `sql/02c` und `sql/02d` nur, wenn die Bedingung in der Datenbank fehlt
    (CHECK mit 'Unbekannt', NOT NULL). `sql/05`, `05c`, `06`, `06b`, `07` laufen immer (IF NOT EXISTS, CREATE OR REPLACE VIEW).
  - Protokoll: `logs/hauptlauf.csv` (Schritt, Ergebnis, Sekunden, Datenbank) und `logs/hauptlauf_tabellen.csv`
    (Zeilen und md5 je Tabelle); Konsole mit Schritten, Tabellenstand und md5 der Diagramme.
  - Optionale Umgebungsvariable `DWH_DB_CONFIG` (andere Konfigurationsdatei) in `etl/01`, `etl/02`, `etl/03`.
    Ohne die Variable gilt wie bisher `db_config.ini`. Zweck: Beweis auf einer leeren Test-Datenbank.
- **Begründung:** Eine Reihenfolge, die man vergessen kann, gehört in Code (wie E-36). Die Bedingungen kommen aus
  der Datenbank selbst, nicht aus einer Liste „schon erledigt“; deshalb ist ein zweiter Lauf gleich und eine neue
  Datenbank wird vollständig aufgebaut. Laufzeiten stehen in `logs/`, nicht nur in der Konsole (Nachweis).
- **Folgen:** Die Datenbank selbst (`CREATE DATABASE`) und `db_config.ini` bleiben Voraussetzung (README).
  `etl/00_starte_gesamtlauf.py` bleibt einzeln startbar. Die Prüfblöcke (Teil B/C) in `sql/02`, `02c`, `02d` laufen auf
  einer neuen Datenbank mit; ein unerwartetes Ergebnis dort bricht den Lauf ab.

## E-45 · Steckbrief und Star-Schema-Bild aus der Datenbank

- **Status:** **Bild-Teil ersetzt durch E-49**. Der Text unten bleibt als Historie stehen.
- **Problem:** Anforderung: ein Steckbrief mit dem Sternschema als Diagramm. `docs/star_schema.png` / `.drawio` zeigen
  einen älteren Entwurf und **widersprechen** dem umgesetzten Modell: `PK verkauf_sk` statt `PRIMARY KEY (bestell_nr,
  position)` (E-20), `lieferstatus` in der Faktentabelle statt `dim_status` (E-18), `dim_status` fehlt.
- **Optionen:** (a) das alte Bild von Hand nachzeichnen; (b) ein neues Bild per Skript direkt aus der Datenbankstruktur
  (`information_schema`, `pg_constraint`), das alte Bild unverändert lassen.
- **Entscheidung:** (b). `etl/07_zeichne_star_schema.py` schreibt `docs/diagramme/star_schema_dwh.png`, reproduzierbar wie
  die Diagramme (E-41), als Schritt 5 in `main.py`. `docs/star_schema.png` / `.drawio` bleiben als Entwurf aus der Designphase
  (nicht gelöscht, nicht geändert); der Steckbrief nutzt das neue Bild.
- **Begründung:** Ein Bild aus dem Katalog der Datenbank kann nicht veralten; jede Schemaänderung (Migration) erscheint
  beim nächsten Lauf. Kein stilles Ändern eines bestehenden Dokuments.
- **Folgen:** Der Widerspruch im alten Bild ist hiermit gemeldet; ob es angepasst oder archiviert wird, entscheidet der
  Projektverantwortliche. Leitfrage des Steckbriefs festgelegt vom Projektverantwortlichen am 19.10.2026.
  **Offen:** Seed und Name des Generator-Skripts der synthetischen Daten stehen in keiner Projektdatei; der Steckbrief
  nennt sie als Nachtrag.

## E-46 · Löschfristen für Zwischen- und Protokolldaten

- **Problem:** Anforderung: Löschfristen für Zwischen- und Protokolldateien sind zu dokumentieren (Datenschutz,
  Zweckbindung). Die Protokolle enthalten Originalwerte (`logs/bereinigung_aenderungen.csv`: alter und neuer Wert,
  abgewiesene Zeilen mit Kundennummer).
- **Entscheidung (Annahme, festgelegt vom Projektverantwortlichen am 19.10.2026; Bestätigung durch Fachbereich und
  Datenschutz ausstehend):**
  - `stg.*`: bei jedem Lauf ersetzt (wie E-17, E-43).
  - temporäre Tabellen: Ende der Transaktion (`ON COMMIT DROP`).
  - `logs/`: 90 Tage.
  - abgewiesene Zeilen (`protokoll.abgewiesene_position`, `data/rejected/`): bis zur Klärung, höchstens 90 Tage.
- **Begründung:** Zwischendaten haben keinen eigenen Zweck nach dem Lauf; Protokolle dienen dem Nachweis und der
  Klärung von Datenfehlern, dafür reicht ein Quartal.
- **Folgen:** Eine automatische Löschung nach 90 Tagen gibt es noch nicht (offen). `stg.kunden_update_2026_01` wird seit
  E-43 nicht mehr ersetzt und erfüllt die Frist für `stg.*` nicht; Entfernen oder Leeren braucht eine Entscheidung.
  Übersicht in `docs/protokoll.md`, Abschnitt 5.

## E-47 · Ergebnisdatei ohne Fragenbereich im Namen (ersetzt den Dateinamen aus E-38)

- **Problem:** E-38 legt `docs/ergebnisse/ergebnisse_f01_f07.md` fest. Mit F-08 (E-40) stimmt der Name nicht mehr, und
  jede weitere Frage würde wieder eine Umbenennung verlangen.
- **Optionen:** (a) Name behalten, F-08 trotzdem eintragen; (b) `ergebnisse_f01_f08.md`; (c) `ergebnisse.md` ohne Bereich.
- **Entscheidung:** (c) `docs/ergebnisse/ergebnisse.md`, umbenannt mit `git mv` (Historie bleibt, nichts gelöscht).
  Der übrige Inhalt von E-38 gilt weiter (Datum und Commit-Hash, Kunden nur mit Nummer).
- **Begründung:** Ein Name ohne Fragenbereich bleibt richtig, wenn Fragen dazukommen; Links müssen nur einmal angepasst werden.
- **Folgen:** Links in `README.md`, `docs/README.md` und der Kommentar in `etl/06_erstelle_diagramme.py` zeigen auf den neuen
  Namen.

## E-48 · `dim_produkt` als SCD Typ 1

- **Problem:** Anforderung: Jede SCD-Entscheidung hat eine kurze Begründung. `dim_produkt` wird bei jedem Lauf
  überschrieben (E-33), eine eigene SCD-Begründung fehlte.
- **Optionen:** (a) SCD Typ 1: Produktattribute überschreiben, keine Historie; (b) SCD Typ 2 mit Versionen je Artikel.
- **Entscheidung (festgelegt vom Projektverantwortlichen am 19.10.2026):** (a) SCD Typ 1.
- **Begründung:** Keine Frage F-01 bis F-08 braucht den Produktstand zum Bestellzeitpunkt; der Verkaufspreis steht als
  Fakt in `fact_verkauf` (`einzelpreis`), Änderungen am Listenpreis verfälschen also keine alten Umsätze.
- **Folgen:** Eine Kategorie- oder Bezeichnungsänderung wirkt rückwirkend auf alle Auswertungen (F-03). Braucht eine
  künftige Frage den Stand zum Bestellzeitpunkt, ist das eine neue Entscheidung (SCD 2 wie `dim_kunde`).

## E-49 · Ein Star-Schema-Bild: `docs/star_schema.drawio` ist die Quelle (ersetzt den Bild-Teil von E-45)

- **Problem:** Nach E-45 gab es zwei Bilder: `docs/star_schema.png` (Export der `.drawio`) und
  `docs/diagramme/star_schema_dwh.png` (gezeichnet von `etl/07_zeichne_star_schema.py`). Es darf nur ein Bild geben.
  Der Projektverantwortliche hat am 19.10.2026 `docs/star_schema.drawio` / `.png` korrigiert, die alten Stände lagen in
  einem Archivordner (nicht im Repository).
- **Prüfung (19.10.2026):** `.drawio` gegen `sql/02_create_dwh.sql`, Spalte für Spalte: 6 Tabellen, 51 Spalten, Namen und
  Reihenfolge gleich; alle in der `.drawio` genannten Typen gleich; IDENTITY (`dim_kunde`, `dim_produkt`), berechnete
  Spalten (G), PK `bestell_nr` + `position`, 5 Fremdschlüssel-Kanten, 4 Zahlungsarten, 8 Status – 0 Abweichungen.
  Das PNG zeigt dieselben Inhalte.
- **Entscheidung (Quelle festgelegt vom Projektverantwortlichen):** `docs/star_schema.drawio` ist die einzige Quelle,
  `docs/star_schema.png` das einzige Bild. `etl/07_zeichne_star_schema.py` und `docs/diagramme/star_schema_dwh.png` werden
  entfernt (`git rm`), Schritt 5 entfällt in `main.py` (jetzt 4 Schritte). Verweise in `README.md`, `docs/README.md`,
  `docs/steckbrief.md` zeigen auf `docs/star_schema.png`.
- **Begründung:** Ein Bild, eine Quelle – keine zwei Darstellungen, die auseinanderlaufen können.
- **Folgen:** Nach einer Schemaänderung (Migration) muss die `.drawio` von Hand nachgezogen und neu exportiert werden.
  Die Spaltenprüfung oben lässt sich dann wiederholen.

## E-50 · Alte Staging-Tabelle `stg.kunden_update_2026_01` entfernen

- **Problem:** Seit E-43 lädt `etl/01` alle Update-Dateien nach `stg.kunden_update`. Die alte Tabelle wurde nicht mehr
  ersetzt und widersprach der Löschfrist für `stg.*` (E-46).
- **Entscheidung (festgelegt vom Projektverantwortlichen am 19.10.2026):** Entfernen per Migration
  `sql/08_entferne_stg_kunden_update_2026_01.sql`, aber nur, wenn ihr Inhalt vollständig in `stg.kunden_update` steht
  (gleiche Zeilenzahl aus `kunden_update_2026-01.csv` und `EXCEPT ALL` in beide Richtungen = 0); sonst Abbruch.
  Anzahl als Meldung. `sql/01` und `sql/07` bleiben unverändert: `main.py` führt `sql/07` nur aus, wenn
  `stg.kunden_update` fehlt (07 kommentiert die alte Tabelle), und `sql/08` danach bei jedem Lauf (wiederholbar).
- **Begründung:** Kein Datenverlust (Inhalt doppelt belegt), Löschfrist für `stg.*` jetzt erfüllt, nichts still gelöscht.
- **Folgen:** Auf einer neuen Datenbank legt `sql/01` die alte Tabelle leer an und `sql/08` entfernt sie sofort wieder
  (0 = 0 Zeilen). Ergebnis am 19.10.2026: 20 Zeilen geprüft und entfernt.
