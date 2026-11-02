# Ergebnisse F-01 bis F-08 · DWH Süd-Mineralöl

Stand F-01 bis F-07: **14.10.2026**, F-08: **19.10.2026** · Datenstand: `python main.py` (4 von 4 Schritten OK,
Gesamtlauf 7 von 7), `fact_verkauf` 2081 Positionen, md5 `aa087435ebc479d434310f8761da74f0` – unverändert seit 14.10.2026
(`docs/protokoll.md`, E-43) · Code-Stand: mart-Views F-01 bis F-07 vom 14.10.2026,
F-08 vom 19.10.2026. Bis 19.10.2026 hieß die Datei `ergebnisse_f01_f07.md` (E-47).

Quelle jeder Zahl: Views in `mart` (`sql/05_create_mart.sql`, `sql/05c_create_mart_f08.sql`), geprüft mit
`sql/05b_kontrolle_mart.sql` (29 von 29 OK, davon F-08: M11–M13, S11–S13). Fragen und Lesart: `docs/anforderungen.md`,
E-13, E-37, E-40. Diagramme: `docs/diagramme/` (E-41).

> **Hinweis Datenschutz:** Die Daten sind fiktiv (Testdaten einer erfundenen Firma). Kunden erscheinen hier nur mit
> Kundennummer. In einer echten Firma würden veröffentlichte Ergebnisse ebenfalls nur Kundennummern zeigen,
> keine Namen (DSGVO, R-03, E-38).

**Umsatz** = Auftragsumsatz: `SUM(umsatz_netto)` ohne stornierte Positionen (E-13), in € ohne MwSt.
**Kontrollsumme:** F-01 = F-03 = F-04 = F-06 = **2 212 834,69 €** (1741 Positionen).

---

## F-01 · Umsatz pro Monat 2024 und 2025

| Jahr | Umsatz |
|---|---|
| 2024 | 1 112 492,50 |
| 2025 | 1 100 342,19 |
| **Summe** | **2 212 834,69** |

| Monat | 2024 | 2025 |
|---|---|---|
| Januar | 101 447,76 | 46 225,25 |
| Februar | 70 917,91 | 72 656,01 |
| März | 72 105,88 | 56 206,51 |
| April | 123 664,71 | 184 274,02 |
| Mai | 105 568,84 | 67 118,71 |
| Juni | 99 057,42 | 85 765,18 |
| Juli | 48 685,95 | 52 613,31 |
| August | 90 574,99 | 125 780,06 |
| September | 101 298,75 | 74 493,65 |
| Oktober | 125 506,82 | 121 262,62 |
| November | 106 401,68 | 108 333,10 |
| Dezember | 67 261,79 | 105 613,77 |

Höchster Monat: April 2025 (184 274,02). Niedrigster: Januar 2025 (46 225,25).
Rabattquote gesamt 2,38 % = `SUM(rabatt_betrag) / SUM(umsatz_brutto)` (E-19, kein Durchschnitt von Prozentwerten).

## F-02 · Top-10-Kunden nach Umsatz (ohne Unbekannt-Kunde −1)

| Rang | Kunde | Kundentyp | Bestellungen | Umsatz |
|---|---|---|---|---|
| 1 | K0061 | Gewerbe | 10 | 54 631,71 |
| 2 | K0015 | Gewerbe | 6 | 42 023,07 |
| 3 | K0003 | Gewerbe | 8 | 35 743,34 |
| 4 | K0143 | Gewerbe | 6 | 35 606,49 |
| 5 | K0008 | Gewerbe | 5 | 35 166,29 |
| 6 | K0041 | Gewerbe | 8 | 34 929,80 |
| 7 | K0123 | Gewerbe | 6 | 34 749,50 |
| 8 | K0031 | Gewerbe | 8 | 34 132,62 |
| 9 | K0009 | Privat | 7 | 33 439,55 |
| 10 | K0048 | Gewerbe | 7 | 32 688,84 |

Rang mit `RANK()`: Gleichstände würden mitgezeigt (heute keiner, Rang 11 hat 32 466,48).

> **Hinweis für den Fachbereich Vertrieb (O-04, E-06):** K0092 und K0109 haben gleichen Namen und gleiche E-Mail.
> Zusammen hätten sie **34 148,38 €** und lägen auf Rang 8. Sie werden **nicht** automatisch zusammengeführt (E-06).
> Ob es dieselbe Person ist, entscheidet der Fachbereich.

## F-03 · Umsatz nach Produktkategorie

| Hauptkategorie | Unterkategorie | Umsatz |
|---|---|---|
| Kraftstoffe | Super | 559 016,98 |
| Kraftstoffe | HVO100 | 390 755,62 |
| Kraftstoffe | Diesel | 239 278,49 |
| **Kraftstoffe** | | **1 189 051,09** |
| Heizöl | Heizöl | 403 257,87 |
| Zubehör | Handpumpe | 214 970,14 |
| Zubehör | Kanister | 66 413,65 |
| Zubehör | Einfüllpistole | 43 643,82 |
| Zubehör | Ölbindemittel | 38 192,67 |
| Zubehör | Ölwanne | 29 057,55 |
| **Zubehör** | | **392 277,83** |
| Motoröle | Motoröl | 79 280,40 |
| Schmierfette | Hochtemperaturfett | 29 850,87 |
| Schmierfette | Mehrzweckfett | 18 030,97 |
| **Schmierfette** | | **47 881,84** |
| Getriebeöle | Getriebeöl | 22 829,79 |
| Getriebeöle | ATF | 20 269,64 |
| **Getriebeöle** | | **43 099,43** |
| Additive | Diesel-Fließverbesserer | 30 343,06 |
| Additive | Kühlerfrostschutz | 9 220,49 |
| Additive | AdBlue | 1 815,15 |
| **Additive** | | **41 378,70** |
| Hydrauliköle | Hydrauliköl | 16 607,53 |

## F-04 · Umsatz nach Ort und Bundesland (Adresse zum Bestellzeitpunkt)

| Bundesland | Ort | Kunden | Umsatz |
|---|---|---|---|
| Baden-Württemberg | Ludwigsburg | 18 | 333 549,27 |
| Baden-Württemberg | Stuttgart | 19 | 287 375,28 |
| Baden-Württemberg | Gärtringen | 14 | 221 041,81 |
| Baden-Württemberg | Herrenberg | 15 | 217 379,19 |
| Sachsen | Dresden | 12 | 178 909,56 |
| Sachsen | Leipzig | 13 | 147 312,47 |
| Baden-Württemberg | Ulm | 10 | 145 320,77 |
| Baden-Württemberg | Böblingen | 9 | 136 252,90 |
| Baden-Württemberg | Pforzheim | 9 | 132 979,80 |
| Baden-Württemberg | Esslingen am Neckar | 16 | 129 862,28 |
| Baden-Württemberg | Tübingen | 6 | 121 075,82 |
| Baden-Württemberg | Sindelfingen | 8 | 82 802,32 |
| Unbekannt | Unbekannt (Kunde −1, E-04) | – | 78 973,22 |

Summe Baden-Württemberg 1 807 639,44 · Sachsen 326 222,03 · Unbekannt 78 973,22.

### Nachweis: Warum SCD 2 die Zahlen verändert

Mit der **heutigen** Adresse statt der Adresse zum Bestellzeitpunkt würden **3 395,81 €** falsch von Baden-Württemberg
nach Sachsen wandern (Umsatz von Kunden, die erst nach ihren Bestellungen umgezogen sind, E-31):

| Bundesland | zum Bestellzeitpunkt (SCD 2, richtig) | mit heutiger Adresse | Differenz |
|---|---|---|---|
| Baden-Württemberg | 1 807 639,44 | 1 804 243,63 | −3 395,81 |
| Sachsen | 326 222,03 | 329 617,84 | +3 395,81 |
| Unbekannt | 78 973,22 | 78 973,22 | 0,00 |

Abfrage (nur lesen, keine View):
```sql
WITH x AS (
    SELECT k.bundesland AS bl_bestellung,      -- Version zum Bestelldatum (über f.kunde_sk)
           a.bundesland AS bl_heute,           -- aktuelle Version
           f.umsatz_netto
    FROM dwh.fact_verkauf f
    JOIN dwh.dim_status s USING (status_sk)
    JOIN dwh.dim_kunde  k ON k.kunde_sk  = f.kunde_sk
    JOIN dwh.dim_kunde  a ON a.kunden_nr = k.kunden_nr AND a.ist_aktuell
    WHERE s.lieferstatus <> 'storniert'
)
SELECT b.bundesland, b.zum_bestellzeitpunkt, h.mit_heutiger_adresse,
       h.mit_heutiger_adresse - b.zum_bestellzeitpunkt AS differenz
FROM (SELECT bl_bestellung AS bundesland, SUM(umsatz_netto) AS zum_bestellzeitpunkt FROM x GROUP BY 1) b
JOIN (SELECT bl_heute      AS bundesland, SUM(umsatz_netto) AS mit_heutiger_adresse FROM x GROUP BY 1) h USING (bundesland)
ORDER BY 1;
```

## F-05 · Stornierungen (Basis: 2081 geladene Positionen, 696 Bestellungen)

| Kennzahl | Anzahl | Anteil |
|---|---|---|
| Positionen storniert | 340 von 2081 | **16,3 %** |
| Positionen vollständig geliefert (E-13) | 1050 von 2081 | 50,5 % |
| Bestellungen vollständig storniert (O-03) | 34 von 696 | **4,9 %** |

## F-06 · Bestellungen und Umsatz je Zahlungsart

| Zahlungsart | Bestellungen | Umsatz |
|---|---|---|
| Rechnung | 248 | 879 308,63 |
| Lastschrift | 218 | 725 166,33 |
| Bar | 142 | 450 441,46 |
| Vorkasse | 54 | 157 918,27 |
| **Summe** | **662** | **2 212 834,69** |

Häufigste Zahlungsart: **Rechnung**. Eine Bestellung zählt, wenn sie mindestens eine nicht stornierte Position hat (E-37).

## F-07 · Wo wohnte der Kunde zum Zeitpunkt der Bestellung?

673 Bestellungen bekannter Kunden; **53** davon stammen von 14 Kunden, die später umgezogen sind.
Alle Bestellungen (2024–2025) liegen vor dem Stand des Updates (2026-01-10, E-31) und stehen deshalb an der alten Adresse.

| Kunde | Ort bei Bestellung | Ort heute | Bestellungen |
|---|---|---|---|
| K0009 | Gärtringen | Tübingen | 7 |
| K0014 | Esslingen am Neckar | Herrenberg | 4 |
| K0037 | Stuttgart | Herrenberg | 6 |
| K0042 | Dresden (Sachsen) | Stuttgart (BW) | 2 |
| K0043 | Esslingen am Neckar (BW) | Dresden (Sachsen) | 3 |
| K0050 | Stuttgart | Böblingen | 3 |
| K0056 | Ulm | Herrenberg | 2 |
| K0059 | Ulm | Esslingen am Neckar | 1 |
| K0060 | Herrenberg | Pforzheim | 4 |
| K0062 | Leipzig (Sachsen) | Pforzheim (BW) | 3 |
| K0065 | Ulm | Ludwigsburg | 8 |
| K0074 | Esslingen am Neckar | Herrenberg | 2 |
| K0105 | Sindelfingen | Esslingen am Neckar | 7 |
| K0139 | Esslingen am Neckar (BW) | Leipzig (Sachsen) | 1 |

Einschränkung (E-31): 2026-01-10 ist das Lieferdatum des Updates, das echte Umzugsdatum steht nicht in der Quelle.

## F-08 · Welche Kunden bestellen wiederholt? (Aggregation mit HAVING, E-40)

Wiederholungskunde = mindestens **2** Bestellungen mit einer nicht stornierten Position, je `kunden_nr`, ohne Kunde −1.

| Kennzahl | Wert |
|---|---|
| Kunden mit mindestens einer Bestellung | 149 |
| davon Wiederholungskunden | **136** (Gewerbe 100, Privat 36) |
| **Wiederkaufquote** | **91,3 %** |
| Umsatz der Wiederholungskunden | 2 074 632,55 € von 2 133 861,47 € bekannter Kunden (97,2 %) |

| Bestellungen je Wiederholungskunde | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Kunden | 25 | 18 | 28 | 24 | 20 | 9 | 8 | 1 | 1 | 1 | 1 |

13 Kunden haben genau eine Bestellung. Die Quote ist hoch und trennt wenig; eine strengere Schwelle wäre eine neue
Entscheidung (E-40, Folgen). Umsatz bekannter Kunden = Auftragsumsatz ohne Kunde −1 (2 212 834,69 − 78 973,22).
