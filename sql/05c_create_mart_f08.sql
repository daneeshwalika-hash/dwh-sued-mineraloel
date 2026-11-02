-- ========================================================================
-- sql/05c_create_mart_f08.sql
-- Migration: neue mart-View für F-08 Wiederholungskunden (Aggregation mit HAVING)
--
-- Zweck      : Beantwortet F-08: Welche Kunden haben mehr als einmal bestellt, und wie hoch
--              ist die Wiederkaufquote? Ergänzt das Schema mart um eine Auswertung mit
--              Aggregation und Filter auf das Aggregat (HAVING).
--              Neue Datei statt Änderung an sql/05_create_mart.sql: Schema-Änderungen nur als
--              Migration (wie sql/02c, sql/02d).
-- Eingabe    : dwh.fact_verkauf, dwh.dim_kunde, dwh.dim_status
-- Ausgabe    : View mart.v_f08_wiederholungskunden mit COMMENT (Data Dictionary)
-- Anforderung: F-08 (docs/anforderungen.md), Aggregation mit Filter (HAVING)
-- Bezug      : E-04, E-13, E-32, E-37, E-38, E-40
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/05c_create_mart_f08.sql
--              Voraussetzung: sql/05_create_mart.sql (Schema mart) ist ausgeführt.
--              Erwartet: BEGIN, CREATE VIEW, COMMENT, COMMIT. Mehrmals startbar.
--              Danach die Kontrolle: sql/05b_kontrolle_mart.sql (M11-M13, S11-S13).
--              Fehlt diese View, bricht sql/05b mit "relation ... does not exist" ab
--              -> der Gesamtlauf stoppt in Schritt 7.
--
-- Lesart (E-40):
--   Kunde           = kunden_nr (nicht SCD-Version), ohne Kunde -1 (E-04, wie F-02).
--   Bestellung zählt, wenn sie mindestens eine nicht stornierte Position hat (E-13, wie F-06).
--   Wiederholungskunde = mindestens 2 solche Bestellungen. Die Schwelle 2 folgt aus der
--                    Definition "mehr als einmal bestellt", sie ist kein geschätzter Wert.
--   Wiederkaufquote = Wiederholungskunden / Kunden mit mindestens einer Bestellung (in %).
-- Keine Namen in der View, nur kunden_nr und kundentyp (R-03, E-38).
-- Keine ORDER BY in der View: Die Reihenfolge legt die Abfrage fest, die die View liest.
-- ========================================================================

-- Alles in EINER Transaktion: entweder die View samt Kommentar oder nichts.
BEGIN;

-- ------------------------------------------------------------------------
-- F-08: Wiederholungskunden und Wiederkaufquote
-- ------------------------------------------------------------------------
-- CREATE OR REPLACE VIEW: mehrmals startbar ohne Fehler und ohne DROP.
CREATE OR REPLACE VIEW mart.v_f08_wiederholungskunden AS
WITH basis AS (
    -- WAS: Nenner der Wiederkaufquote = Kunden mit mindestens einer Bestellung.
    -- WARUM eigene CTE: Die Hauptabfrage sieht nach HAVING nur noch die Wiederholungskunden.
    SELECT COUNT(DISTINCT k.kunden_nr) AS kunden_mit_bestellung
    FROM dwh.fact_verkauf f
    JOIN dwh.dim_kunde  k ON k.kunde_sk  = f.kunde_sk
    JOIN dwh.dim_status s ON s.status_sk = f.status_sk
    WHERE s.lieferstatus <> 'storniert'          -- Auftragsumsatz (E-13)
      AND f.kunde_sk <> -1                       -- Unbekannt-Kunde zählt nicht (E-04)
)
-- WAS: Bestellungen und Auftragsumsatz je kunden_nr, nur Kunden mit mindestens 2 Bestellungen.
-- WARUM je kunden_nr: Ein umgezogener Kunde (zwei SCD-2-Versionen) ist EIN Kunde (E-37, wie F-02).
SELECT k.kunden_nr,
       a.kundentyp,                              -- aus der aktuellen Version (SCD 1, E-32)
       COUNT(DISTINCT f.bestell_nr) AS bestellungen,
       COUNT(*)                     AS positionen,
       SUM(f.umsatz_netto)          AS umsatz_netto,
       MIN(d.datum)                 AS erste_bestellung,
       MAX(d.datum)                 AS letzte_bestellung,
       -- Wiederkaufquote in jeder Zeile gleich, damit die View allein die Antwort trägt.
       -- Fensterfunktionen laufen NACH HAVING: COUNT(*) OVER () = Anzahl Wiederholungskunden.
       COUNT(*) OVER ()             AS wiederholungskunden,
       b.kunden_mit_bestellung,
       -- NULLIF: kein Fehler "Division durch 0", falls fact_verkauf leer wäre.
       ROUND(100.0 * COUNT(*) OVER () / NULLIF(b.kunden_mit_bestellung, 0), 1) AS wiederkaufquote_prozent
FROM dwh.fact_verkauf f
JOIN dwh.dim_kunde  k ON k.kunde_sk  = f.kunde_sk
JOIN dwh.dim_status s ON s.status_sk = f.status_sk
JOIN dwh.dim_datum  d ON d.datum_sk  = f.datum_sk
-- Genau eine aktuelle Version je kunden_nr (ux_dim_kunde_aktuell): kein Mehrfachzählen.
JOIN dwh.dim_kunde  a ON a.kunden_nr = k.kunden_nr AND a.ist_aktuell
CROSS JOIN basis b
WHERE s.lieferstatus <> 'storniert'
  AND f.kunde_sk <> -1
GROUP BY k.kunden_nr, a.kundentyp, b.kunden_mit_bestellung
-- WARUM HAVING und nicht WHERE: Die Bedingung gilt für das Aggregat COUNT(...), das erst
-- nach GROUP BY existiert. WHERE filtert einzelne Positionen VOR der Gruppierung.
-- Schwelle 2 = Definition "mehr als einmal bestellt", kein geschätzter Wert (E-40).
HAVING COUNT(DISTINCT f.bestell_nr) >= 2;

COMMENT ON VIEW mart.v_f08_wiederholungskunden IS
  'F-08: Kunden (kunden_nr, ohne -1) mit mindestens 2 Bestellungen mit nicht stornierter Position (HAVING, E-40). Wiederkaufquote = Wiederholungskunden / Kunden mit mindestens einer Bestellung. Ohne Namen (E-38).';

COMMIT;
