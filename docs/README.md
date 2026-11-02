# docs/ – Projektdokumente

Stand: 21.10.2026

| Datei / Ordner | Inhalt |
|---|---|
| [`steckbrief.md`](steckbrief.md) | Projektsteckbrief: Ziel, Leitfrage, Datenquelle, Datenmodell mit Bild. |
| [`protokoll.md`](protokoll.md) | Protokoll des Laufs: Kontrollzahlen, Zeilenzahlen, Diagramme, doppelte Datenmenge, Löschfristen. |
| [`ergebnisse/ergebnisse.md`](ergebnisse/ergebnisse.md) | Ergebnisse F-01 bis F-08 mit Kontrollsumme (bis 19.10.2026 `ergebnisse_f01_f07.md`, E-47). |
| [`diagramme/`](diagramme/) | Diagramme D1–D3, erzeugt von `main.py` (`etl/06`); nicht von Hand ändern. |
| [`anforderungen.md`](anforderungen.md) | Business Questions F-01 bis F-08, Qualitätsanforderungen Q-01 bis Q-05, Rahmenbedingungen. |
| [`entscheidungen.md`](entscheidungen.md) | Decision Log E-01 bis E-50: Problem, Optionen, Entscheidung, Begründung, Folgen. |
| [`offene_fragen.md`](offene_fragen.md) | Fachliche Fragen an die Fachabteilung, Annahmen bis zur Antwort. |
| [`namenskonventionen.md`](namenskonventionen.md) | Namen für Schemas, Tabellen, Spalten, Constraints und Dateien. |
| [`data_quality_issues.csv`](data_quality_issues.csv) / [`.md`](data_quality_issues.md) | Gefundene Datenprobleme, automatisch erzeugt von `explore/01_explore.py` (nicht von Hand ändern). |
| [`erm_quelle.drawio`](erm_quelle.drawio) / [`.png`](erm_quelle.png) | ERM (Entity-Relationship-Modell) der Quelldaten. |
| [`star_schema.drawio`](star_schema.drawio) / [`.png`](star_schema.png) | Star Schema des DWH, einziges Bild (E-49). Die `.drawio` ist die Quelle, die `.png` wird daraus exportiert; Spalte für Spalte geprüft gegen `sql/02_create_dwh.sql` (19.10.2026). |
