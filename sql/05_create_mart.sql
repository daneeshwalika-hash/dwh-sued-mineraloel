-- ========================================================================
-- sql/05_create_mart.sql
-- Schema mart: eine View pro Business Question F-01 bis F-07
--
-- Zweck      : Die Antworten auf F-01 bis F-07 als Views über dem Star Schema.
--              Views speichern keine Daten: Nach jedem Neuladen von dwh zeigen sie
--              sofort den neuen Stand.
-- Eingabe    : dwh.fact_verkauf, dim_datum, dim_kunde, dim_produkt, dim_zahlung, dim_status
-- Ausgabe    : Schema mart, Views mart.v_f01_ ... mart.v_f07_ mit COMMENT (Data Dictionary)
-- Anforderung: F-01 bis F-07 (docs/anforderungen.md), B3 alles beschrieben
-- Bezug      : E-04, E-13, E-16, E-19, E-21, E-31, E-32, E-37
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/05_create_mart.sql
--              Erwartet: BEGIN, CREATE VIEW x7, COMMENT, COMMIT. Mehrmals startbar.
--              Danach die Kontrolle: sql/05b_kontrolle_mart.sql (auch Schritt 7 im Gesamtlauf).
--
-- Umsatz in allen Views = SUM(umsatz_netto) OHNE lieferstatus 'storniert'
-- (Auftragsumsatz, E-13; für F-06 E-37). Gefiltert wird über dim_status (E-18).
-- Keine ORDER BY in den Views: Die Reihenfolge legt die Abfrage fest, die die View liest.
-- ========================================================================

-- Alles in EINER Transaktion: entweder alle Views neu oder keine.
BEGIN;

-- IF NOT EXISTS + CREATE OR REPLACE VIEW: mehrmals startbar ohne Fehler und ohne DROP.
CREATE SCHEMA IF NOT EXISTS mart;
COMMENT ON SCHEMA mart IS 'Auswertungsschicht: eine View pro Business Question F-01 bis F-08 und DQ-View (E-37)';


-- ------------------------------------------------------------------------
-- F-01: Umsatz pro Monat 2024 und 2025
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f01_umsatz_monat AS
SELECT d.jahr,
       d.monat,
       d.monat_name,
       COUNT(*)               AS positionen,
       SUM(f.umsatz_brutto)   AS umsatz_brutto,
       SUM(f.rabatt_betrag)   AS rabatt_betrag,
       SUM(f.umsatz_netto)    AS umsatz_netto,
       -- Rabatt ist nicht additiv (E-19): Quote = Summe / Summe, nie AVG(rabatt_prozent).
       -- NULLIF: kein Fehler "Division durch 0", falls ein Monat nur Preise 0 hätte.
       ROUND(100 * SUM(f.rabatt_betrag) / NULLIF(SUM(f.umsatz_brutto), 0), 2) AS rabatt_quote_prozent
FROM dwh.fact_verkauf f
JOIN dwh.dim_datum  d ON d.datum_sk  = f.datum_sk
JOIN dwh.dim_status s ON s.status_sk = f.status_sk
WHERE s.lieferstatus <> 'storniert'
  AND d.datum BETWEEN DATE '2024-01-01' AND DATE '2025-12-31'
GROUP BY d.jahr, d.monat, d.monat_name;

COMMENT ON VIEW mart.v_f01_umsatz_monat IS
  'F-01: Auftragsumsatz (umsatz_netto ohne storniert, E-13) je Kalendermonat 2024-01 bis 2025-12. Rabattquote = SUM/SUM (E-19).';


-- ------------------------------------------------------------------------
-- F-02: Top-10-Kunden nach Umsatz (ohne -1)
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f02_top10_kunden AS
WITH umsatz AS (
    -- Je kunden_nr, nicht je SCD-Version: Ein umgezogener Kunde ist EIN Kunde.
    SELECT k.kunden_nr,
           COUNT(DISTINCT f.bestell_nr) AS bestellungen,
           SUM(f.umsatz_netto)          AS umsatz_netto
    FROM dwh.fact_verkauf f
    JOIN dwh.dim_kunde  k ON k.kunde_sk  = f.kunde_sk
    JOIN dwh.dim_status s ON s.status_sk = f.status_sk
    WHERE s.lieferstatus <> 'storniert'
      AND f.kunde_sk <> -1                       -- F-02: Unbekannt-Kunde zählt nicht (E-04)
    GROUP BY k.kunden_nr
),
rangliste AS (
    -- RANK statt ROW_NUMBER: Bei Gleichstand bekommen beide denselben Rang und beide
    -- erscheinen. Es gibt keine versteckte, zufällige Grenze bei 10 (E-37).
    SELECT u.*, RANK() OVER (ORDER BY u.umsatz_netto DESC) AS rang
    FROM umsatz u
)
SELECT r.rang,
       r.kunden_nr,
       a.kundentyp,
       a.firma,
       a.vorname,
       a.nachname,
       r.bestellungen,
       r.umsatz_netto
FROM rangliste r
-- Namen und Kundentyp aus der aktuellen Version (SCD 1 für diese Attribute, E-32)
JOIN dwh.dim_kunde a ON a.kunden_nr = r.kunden_nr AND a.ist_aktuell
WHERE r.rang <= 10;

COMMENT ON VIEW mart.v_f02_top10_kunden IS
  'F-02: Top-10-Kunden je kunden_nr nach Auftragsumsatz, ohne Kunde -1. RANK(): Gleichstände werden mitgezeigt (E-37). Namen nur intern (E-38, R-03).';


-- ------------------------------------------------------------------------
-- F-03: Umsatz nach Produktkategorie (Haupt- und Unterkategorie)
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f03_umsatz_kategorie AS
SELECT p.kategorie,
       p.unterkategorie,
       COUNT(*)            AS positionen,
       SUM(f.menge)        AS menge,
       SUM(f.umsatz_netto) AS umsatz_netto
FROM dwh.fact_verkauf f
JOIN dwh.dim_produkt p ON p.produkt_sk = f.produkt_sk
JOIN dwh.dim_status  s ON s.status_sk  = f.status_sk
WHERE s.lieferstatus <> 'storniert'
-- Kein ROLLUP: Zwischensummen würden in der Kontrollsumme doppelt zählen (E-37).
-- Summe je Hauptkategorie: SUM(umsatz_netto) ... GROUP BY kategorie auf diese View.
GROUP BY p.kategorie, p.unterkategorie;

COMMENT ON VIEW mart.v_f03_umsatz_kategorie IS
  'F-03: Auftragsumsatz je Unterkategorie mit Spalte Hauptkategorie (flache Hierarchie, E-16). Summe je Hauptkategorie per GROUP BY auf die View.';


-- ------------------------------------------------------------------------
-- F-04: Umsatz nach Ort und Bundesland zum Zeitpunkt der Bestellung
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f04_umsatz_ort AS
SELECT k.bundesland,
       k.ort,
       COUNT(DISTINCT k.kunden_nr) AS kunden,
       COUNT(*)                    AS positionen,
       SUM(f.umsatz_netto)         AS umsatz_netto
FROM dwh.fact_verkauf f
-- f.kunde_sk zeigt auf die Kundenversion zum Bestelldatum (SCD 2, E-31):
-- Ort und Bundesland sind also die Adresse zum Zeitpunkt der Bestellung.
JOIN dwh.dim_kunde  k ON k.kunde_sk  = f.kunde_sk
JOIN dwh.dim_status s ON s.status_sk = f.status_sk
WHERE s.lieferstatus <> 'storniert'
GROUP BY k.bundesland, k.ort;

COMMENT ON VIEW mart.v_f04_umsatz_ort IS
  'F-04: Auftragsumsatz je Ort mit Spalte Bundesland, Adresse zum Bestellzeitpunkt (SCD 2). Kunde -1 erscheint als Ort/Bundesland Unbekannt (E-21).';


-- ------------------------------------------------------------------------
-- F-05: Anteil stornierter Positionen und vollständig stornierter Bestellungen
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f05_stornoquote AS
WITH pos AS (
    SELECT f.bestell_nr, s.lieferstatus
    FROM dwh.fact_verkauf f
    JOIN dwh.dim_status s ON s.status_sk = f.status_sk
),
bestellung AS (
    -- bool_and: TRUE nur, wenn ALLE geladenen Positionen der Bestellung storniert sind (O-03)
    SELECT bestell_nr, bool_and(lieferstatus = 'storniert') AS voll_storniert
    FROM pos
    GROUP BY bestell_nr
)
SELECT (SELECT COUNT(*) FROM pos)                                         AS positionen,
       (SELECT COUNT(*) FROM pos WHERE lieferstatus = 'storniert')       AS positionen_storniert,
       ROUND(100.0 * (SELECT COUNT(*) FROM pos WHERE lieferstatus = 'storniert')
                   / (SELECT COUNT(*) FROM pos), 1)                      AS anteil_positionen_storniert_prozent,
       (SELECT COUNT(*) FROM pos WHERE lieferstatus = 'geliefert')       AS positionen_geliefert,
       ROUND(100.0 * (SELECT COUNT(*) FROM pos WHERE lieferstatus = 'geliefert')
                   / (SELECT COUNT(*) FROM pos), 1)                      AS anteil_vollstaendig_geliefert_prozent,
       (SELECT COUNT(*) FROM bestellung)                                 AS bestellungen,
       (SELECT COUNT(*) FROM bestellung WHERE voll_storniert)            AS bestellungen_voll_storniert,
       ROUND(100.0 * (SELECT COUNT(*) FROM bestellung WHERE voll_storniert)
                   / (SELECT COUNT(*) FROM bestellung), 1)               AS anteil_bestellungen_voll_storniert_prozent;

COMMENT ON VIEW mart.v_f05_stornoquote IS
  'F-05: Anteil stornierter Positionen und vollständig stornierter Bestellungen (O-03), dazu Anteil vollständig geliefert (E-13). Basis: geladene Positionen, rejected zählen nicht.';


-- ------------------------------------------------------------------------
-- F-06: Bestellungen und Umsatz je Zahlungsart
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f06_zahlungsart AS
SELECT z.zahlungsart,
       -- Eine Bestellung zählt, wenn sie mindestens eine nicht stornierte Position hat (E-37).
       -- Die Zahlungsart ist Attribut der Bestellung (E-03): keine Doppelzählung über Zahlungsarten.
       COUNT(DISTINCT f.bestell_nr) AS bestellungen,
       COUNT(*)                     AS positionen,
       SUM(f.umsatz_netto)          AS umsatz_netto
FROM dwh.fact_verkauf f
JOIN dwh.dim_zahlung z ON z.zahlung_sk = f.zahlung_sk
JOIN dwh.dim_status  s ON s.status_sk  = f.status_sk
WHERE s.lieferstatus <> 'storniert'
GROUP BY z.zahlungsart;

COMMENT ON VIEW mart.v_f06_zahlungsart IS
  'F-06: Anzahl Bestellungen (mit mindestens einer nicht stornierten Position) und Auftragsumsatz je Zahlungsart (E-37).';


-- ------------------------------------------------------------------------
-- F-07: Wo wohnte der Kunde zum Zeitpunkt der Bestellung?
-- ------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_f07_wohnort_bestellung AS
SELECT f.bestell_nr,
       d.datum         AS bestelldatum,
       k.kunden_nr,
       k.plz           AS plz_bei_bestellung,
       k.ort           AS ort_bei_bestellung,
       k.bundesland    AS bundesland_bei_bestellung,
       a.ort           AS ort_aktuell,
       a.bundesland    AS bundesland_aktuell,
       -- Umgezogen = Adresse zum Bestellzeitpunkt ist nicht die heutige.
       -- IS DISTINCT FROM: vergleicht auch NULL richtig (PLZ kann NULL sein, E-26).
       (k.plz, k.ort, k.bundesland) IS DISTINCT FROM (a.plz, a.ort, a.bundesland) AS umgezogen
FROM dwh.fact_verkauf f
JOIN dwh.dim_datum d ON d.datum_sk = f.datum_sk
JOIN dwh.dim_kunde k ON k.kunde_sk = f.kunde_sk                       -- Version zum Bestelldatum
JOIN dwh.dim_kunde a ON a.kunden_nr = k.kunden_nr AND a.ist_aktuell   -- Version heute
WHERE f.kunde_sk <> -1                                                -- ohne Adresse (E-04)
-- Eine Zeile pro Bestellung: Kunde und Datum sind Attribute der Bestellung (E-03)
GROUP BY f.bestell_nr, d.datum, k.kunden_nr, k.plz, k.ort, k.bundesland, a.plz, a.ort, a.bundesland;

COMMENT ON VIEW mart.v_f07_wohnort_bestellung IS
  'F-07: je Bestellung Wohnort zum Bestellzeitpunkt (SCD 2) und heute, Kennzeichen umgezogen. Ohne Kunde -1. Alle Bestellungen 2024-2025 liegen vor den Änderungen ab 2026-01-10 (E-31).';

COMMIT;
