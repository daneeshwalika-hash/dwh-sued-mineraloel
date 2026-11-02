# Offene Fragen – Stand 19.10.2026

Quelle der Fragen: `docs/anforderungen.md` (Abschnitt 6). Die Annahmen stehen in `docs/entscheidungen.md`.
Die Zahlen stammen aus `docs/entscheidungen.md`, `docs/data_quality_issues.md` und `docs/anforderungen.md`.

Fachliche Fragen an die Fachabteilung (O-01 bis O-08).
Bis zur Antwort gilt bei jeder Frage eine dokumentierte Annahme.

## Fragen an die Fachabteilung

### O-01: Zählt `offen` zum Umsatz?
- **Frage:** Zählen Positionen mit Status `offen` schon zum Umsatz?
- **Befund:** Nach Vereinheitlichung der Schreibweise (E-12): `geliefert` 1083, `offen` 369,
  `teilgeliefert` 351, `storniert` 353 (Summe 2156 Positionen).
- **Auswirkung:** Ändert F-01 bis F-04.
- **Annahme bis zur Antwort:** E-13 – Auftragsumsatz: alle Positionen außer `storniert`.
  Alle Positionen werden geladen, gefiltert wird erst in der Auswertung über `lieferstatus`
  (seit E-18 in `dim_status`).

### O-02: Negative Mengen
- **Frage:** Sind negative Mengen Retouren oder Erfassungsfehler?
- **Befund:** 40 Positionen mit negativer Menge (z. B. `-2000`), 17 mit Menge 0.
  Die negativen Mengen haben normale Status, es gibt kein Retouren-Kennzeichen in der Quelle.
- **Auswirkung:** Retouren müssten den Umsatz senken, Fehler müssen raus.
- **Annahme bis zur Antwort:** E-05 – beide Fälle gehen nach `data/rejected/` mit Grund.

### O-03: Storno pro Bestellung oder pro Position?
- **Frage:** „Stornierte Bestellungen“: pro Bestellung oder pro Position?
- **Befund:** Der Status steht in der Quelle **pro Position**. 353 von 2156 Positionen sind `storniert` (E-12).
- **Auswirkung:** Ergibt zwei verschiedene Kennzahlen für F-05.
- **Annahme bis zur Antwort:** F-05 – beide Anteile werden berechnet: Anteil der stornierten
  **Positionen** und Anteil der **vollständig** stornierten Bestellungen.

### O-04: Gleicher Name und gleiche E-Mail
- **Frage:** Sind Kunden mit gleichem Namen und gleicher E-Mail dieselbe Person?
- **Befund:** 18 Kundenzeilen haben den gleichen Vornamen, Nachnamen und die gleiche E-Mail wie
  eine andere Kundennummer. Einige sind offensichtlich dieselbe Person (K0099/K0153 Anna Braun),
  andere wohl nicht (K0014 Becker Bau GmbH in Esslingen vs. K0042 Privatkunde in Dresden).
- **Auswirkung:** Beeinflusst F-02 (Top-10).
- **Annahme bis zur Antwort:** E-06 – nicht automatisch zusammenführen, als Warnung protokollieren.

### O-05: Doppelte Zeilen in `bestellungen.csv`
- **Frage:** Sind die 25 doppelten Zeilen in `bestellungen.csv` ein doppelter Export?
- **Befund:** 25 exakte Dubletten (Nr 28 in `data_quality_issues.md`), immer Paare,
  nie direkt untereinander (min. 34 Zeilen Abstand).
- **Auswirkung:** Betrifft die Ladeprüfung (Q-01: Zeilen roh = geladen + rejected + entfernte Dubletten).
- **Annahme bis zur Antwort:** Dubletten werden entfernt (`drop_duplicates()`), die Anzahl wird protokolliert.

### O-06: Gelieferte Menge bei `teilgeliefert`
- **Frage:** Wie viel wurde bei `teilgeliefert` tatsächlich geliefert?
- **Befund:** 351 Positionen `teilgeliefert`. Die Quelle hat nur die bestellte `menge`, keine gelieferte Menge.
- **Auswirkung:** Eine Position kann nur ganz oder gar nicht zählen.
- **Annahme bis zur Antwort:** E-13 – `teilgeliefert` zählt ganz zum Auftragsumsatz.

### O-07: Leerer Rabatt
- **Frage:** Bedeutet ein leerer Rabatt „0 %“ oder „unbekannt“?
- **Befund:** 324 Positionen ohne Rabatt. Bei den gefüllten Werten ist 0 der häufigste Wert.
- **Auswirkung:** Beeinflusst den Netto-Umsatz (F-01 bis F-04).
- **Annahme bis zur Antwort:** E-08 – leer = 0 %.

### O-08: K0105 im Kunden-Update ohne Telefon und E-Mail
- **Frage:** K0105 im Kunden-Update ohne Telefon und E-Mail: bewusst gelöscht oder unvollständiger Export?
- **Befund:** In `kunden_update_2026-01.csv` sind bei K0105 Telefon und E-Mail leer.
- **Auswirkung:** Entscheidet, ob leere Werte im Update alte Werte überschreiben.
  Telefon und E-Mail werden laut R-03 (DSGVO) nicht ins DWH geladen und stehen nicht in `dim_kunde`.
  Deshalb keine Auswirkung auf F-01 bis F-07.
- **Annahme bis zur Antwort:** E-15 – leere Werte im Update überschreiben **nicht** die alten Werte.
  Die Annahme gilt nur, falls die Felder später doch gebraucht werden.
