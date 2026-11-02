-- ========================================================================
-- sql/03_kontrolle_dim_datum.sql
-- Kontrolle von dwh.dim_datum (unabhängig von etl/02_lade_dim_datum.py)
--
-- Projekt : DWH Süd-Mineralöl · PostgreSQL 18 · Datenbank dwh_sued
-- Stand   : 11.10.2026
-- Liest nur (nur SELECT), ändert nichts.
--
-- Warum eine zweite Prüfung? Das Python-Skript prüft sich selbst.
-- Hier rechnet die DATENBANK nach, mit eigenen Funktionen
-- (generate_series, EXTRACT) – also eine unabhängige Kontrolle.
--
-- Ausführen: pgAdmin -> dwh_sued -> Query Tool
--   Teil A markieren -> F5   (Soll: jede Zeile OK)
--   Teil B markieren -> F5   (Feiertagsliste zum Vergleich mit amtlicher Quelle)
-- ========================================================================


-- ------------------------------------------------------------------------
-- Teil A: Soll/Ist in einer Tabelle
-- ------------------------------------------------------------------------
WITH
-- Soll-Kalender: von PostgreSQL selbst erzeugt
kalender AS (
    SELECT tag::date AS datum
    FROM generate_series(DATE '2021-01-01', DATE '2027-12-31', INTERVAL '1 day') AS tag
),
pruefungen (nr, pruefung, soll, ist) AS (
    SELECT 'D1', 'Tage gesamt in dim_datum',
           (SELECT COUNT(*) FROM kalender),
           (SELECT COUNT(*) FROM dwh.dim_datum)
    UNION ALL
    -- Tage im Kalender, die in dim_datum fehlen (Lücken)
    SELECT 'D2', 'fehlende Tage (Lücken)', 0,
           (SELECT COUNT(*) FROM kalender k
            LEFT JOIN dwh.dim_datum d ON d.datum = k.datum
            WHERE d.datum IS NULL)
    UNION ALL
    -- Tage in dim_datum, die nicht im Zeitraum liegen
    SELECT 'D3', 'Tage außerhalb 2021-2027', 0,
           (SELECT COUNT(*) FROM dwh.dim_datum
            WHERE datum NOT BETWEEN DATE '2021-01-01' AND DATE '2027-12-31')
    UNION ALL
    -- Wochenende: Soll aus dem Kalender (ISODOW 6 = Samstag, 7 = Sonntag)
    SELECT 'D4', 'Wochenendtage',
           (SELECT COUNT(*) FROM kalender WHERE EXTRACT(ISODOW FROM datum) >= 6),
           (SELECT COUNT(*) FROM dwh.dim_datum WHERE ist_wochenende)
    UNION ALL
    -- Tage pro Jahr: 365, Schaltjahr 2024: 366
    SELECT 'D5', 'Tage im Schaltjahr 2024', 366,
           (SELECT COUNT(*) FROM dwh.dim_datum WHERE jahr = 2024)
    UNION ALL
    SELECT 'D6', 'Feiertage BW gesamt (7 Jahre x 12, Paket holidays 0.106)', 84,
           (SELECT COUNT(*) FROM dwh.dim_datum WHERE ist_feiertag_bw)
    UNION ALL
    -- Jedes Jahr gleich viele Feiertage? (Anzahl Jahre mit genau 12)
    SELECT 'D7', 'Jahre mit genau 12 Feiertagen', 7,
           (SELECT COUNT(*) FROM (
                SELECT jahr FROM dwh.dim_datum WHERE ist_feiertag_bw
                GROUP BY jahr HAVING COUNT(*) = 12) AS j)
    UNION ALL
    -- Feste Feiertage: am richtigen Tag? (7 Jahre x 7 feste Daten = 49)
    -- Neujahr 01-01, Hl. Drei Könige 01-06, 1. Mai, Tag der Dt. Einheit 10-03,
    -- Allerheiligen 11-01, 1. und 2. Weihnachtstag 12-25/12-26
    SELECT 'D8', 'feste Feiertage markiert (7 x 7)', 49,
           (SELECT COUNT(*) FROM dwh.dim_datum
            WHERE ist_feiertag_bw
              AND to_char(datum, 'MM-DD') IN ('01-01', '01-06', '05-01', '10-03',
                                               '11-01', '12-25', '12-26'))
    UNION ALL
    -- Bewegliche Feiertage hängen an Ostern: Karfreitag, Ostermontag,
    -- Himmelfahrt, Pfingstmontag, Fronleichnam = 5 pro Jahr
    SELECT 'D9', 'bewegliche Feiertage (7 x 5)', 35,
           (SELECT COUNT(*) FROM dwh.dim_datum
            WHERE ist_feiertag_bw
              AND to_char(datum, 'MM-DD') NOT IN ('01-01', '01-06', '05-01', '10-03',
                                                   '11-01', '12-25', '12-26'))
    UNION ALL
    -- Ein Feiertag kann auf ein Wochenende fallen. Er bleibt Feiertag.
    -- Hier nur zur Information (Soll = Ist aus der Tabelle selbst).
    SELECT 'D10', 'Feiertage am Wochenende (Info)',
           (SELECT COUNT(*) FROM dwh.dim_datum WHERE ist_feiertag_bw AND ist_wochenende),
           (SELECT COUNT(*) FROM dwh.dim_datum WHERE ist_feiertag_bw AND ist_wochenende)
)
SELECT nr, pruefung, soll, ist,
       CASE WHEN soll = ist THEN 'OK' ELSE 'ABWEICHUNG' END AS ergebnis
FROM pruefungen
ORDER BY length(nr), nr;


-- ------------------------------------------------------------------------
-- Teil B: Feiertagsliste (zum Vergleich mit einer amtlichen Quelle,
--         z. B. Feiertagsgesetz Baden-Württemberg)
-- Ein Jahr reicht für den Sichtvergleich. Für andere Jahre die Zahl ändern.
-- ------------------------------------------------------------------------
SELECT datum,
       CASE wochentag
            WHEN 1 THEN 'Montag'     WHEN 2 THEN 'Dienstag' WHEN 3 THEN 'Mittwoch'
            WHEN 4 THEN 'Donnerstag' WHEN 5 THEN 'Freitag'  WHEN 6 THEN 'Samstag'
            ELSE 'Sonntag'
       END AS wochentag,
       ist_wochenende
FROM dwh.dim_datum
WHERE ist_feiertag_bw
  AND jahr = 2025
ORDER BY datum;
