-- ========================================================================
-- sql/01b_typpruefung_staging.sql
-- Vorab-Prüfung der Datentypen in stg.*, BEVOR sql/02_create_dwh.sql läuft
--
-- Projekt : DWH Süd-Mineralöl · PostgreSQL 18 · Datenbank dwh_sued
-- Stand   : 11.10.2026
--
-- Warum?  Die Typen in dwh.* (INTEGER, NUMERIC(12,2) ...) werden aus den
--         echten Daten abgeleitet, nicht aus einer Vermutung.
--         Weicht ein Ergebnis vom Soll ab: STOPP, erst den Typ in
--         sql/02_create_dwh.sql anpassen und die Änderung dokumentieren.
--
-- Wichtig: Dieses Skript LIEST nur (nur SELECT). Es ändert nichts.
-- Ausführen: pgAdmin -> dwh_sued -> Query Tool -> jede Abfrage einzeln
--            markieren und mit F5 ausführen (sonst erscheint nur das
--            Ergebnis der letzten Abfrage).
--            Alle Prüfungen in einer Ergebnistabelle: sql/02b_pruefung_staging_dwh.sql.
-- ========================================================================


-- ------------------------------------------------------------------------
-- P1: Ist bestell_nr immer eine Zahl?  (fact_verkauf.bestell_nr INTEGER, E-20)
-- Soll: nicht_numerisch = 0
-- ------------------------------------------------------------------------
SELECT COUNT(*) AS nicht_numerisch
FROM stg.bestellungen
WHERE trim(bestell_nr) !~ '^[0-9]+$';


-- ------------------------------------------------------------------------
-- P2: Ist position immer eine kleine Zahl?  (fact_verkauf.position SMALLINT)
-- Soll: nicht_numerisch = 0, max_position < 32767
-- ------------------------------------------------------------------------
SELECT COUNT(*) FILTER (WHERE trim(position) !~ '^[0-9]+$')           AS nicht_numerisch,
       MAX(CASE WHEN trim(position) ~ '^[0-9]+$'
                THEN CAST(trim(position) AS INTEGER) END)              AS max_position
FROM stg.bestellungen;


-- ------------------------------------------------------------------------
-- P3: Ist menge immer ganzzahlig?  (fact_verkauf.menge INTEGER)
-- Soll: nicht_ganzzahlig = 0
-- Falls > 0: menge in 02_create_dwh.sql auf NUMERIC(12,3) ändern.
-- (Negative Mengen und 0 zählen hier NICHT als Fehler, sie gehen in
--  der Bereinigung nach rejected, E-05.)
-- ------------------------------------------------------------------------
SELECT COUNT(*) AS nicht_ganzzahlig
FROM stg.bestellungen
WHERE trim(menge) !~ '^-?[0-9]+$';


-- ------------------------------------------------------------------------
-- P4: Wie viele Nachkommastellen hat einzelpreis?  (NUMERIC(12,2))
-- Soll: max_nachkommastellen <= 2
-- Falls 3 oder mehr: einzelpreis auf NUMERIC(12,3) ändern.
-- ------------------------------------------------------------------------
SELECT MAX(length(split_part(replace(trim(einzelpreis), ',', '.'), '.', 2))) AS max_nachkommastellen
FROM stg.bestellungen
WHERE trim(einzelpreis) <> '';


-- ------------------------------------------------------------------------
-- P5: Wie viele Nachkommastellen hat der Listenpreis?  (dim_produkt.listenpreis)
-- Beispiele aus data_quality_issues Nr 22: '1.62', '1,74 €'
-- Soll: max_nachkommastellen <= 2
-- ------------------------------------------------------------------------
SELECT MAX(length(split_part(
           replace(regexp_replace(trim(preis), '[^0-9,.]', '', 'g'), ',', '.'),
           '.', 2))) AS max_nachkommastellen
FROM stg.produkte
WHERE preis IS NOT NULL
  AND trim(preis) <> '';


-- ------------------------------------------------------------------------
-- P6: Liegt der Rabatt zwischen 0 und 100?  (rabatt_prozent NUMERIC(5,2))
-- Soll: min >= 0, max <= 100
-- ------------------------------------------------------------------------
SELECT MIN(CAST(replace(trim(rabatt_prozent), ',', '.') AS NUMERIC)) AS min_rabatt,
       MAX(CAST(replace(trim(rabatt_prozent), ',', '.') AS NUMERIC)) AS max_rabatt
FROM stg.bestellungen
WHERE trim(rabatt_prozent) <> '';


-- ------------------------------------------------------------------------
-- P7: Welche Lieferstatus gibt es?  (dim_status, E-18)
-- Basis: OHNE die 25 exakten Dubletten (gleiche Basis wie E-12!).
-- Soll: genau 4 Zeilen
--       geliefert 1083 · offen 369 · storniert 353 · teilgeliefert 351
--       Summe 2156
-- ------------------------------------------------------------------------
SELECT lower(trim(b.lieferstatus)) AS lieferstatus,
       COUNT(*)                    AS positionen
FROM (SELECT DISTINCT bestell_nr, position, lieferstatus
      FROM stg.bestellungen) AS b
GROUP BY lower(trim(b.lieferstatus))
ORDER BY 1;


-- ------------------------------------------------------------------------
-- P8: Welche Schreibweisen hat zahlungsart?  (dim_zahlung, 4 Werte nach F-06)
-- Soll: 9 Schreibweisen (data_quality_issues Nr 44), jede lässt sich
--       eindeutig einem der 4 Werte zuordnen:
--       Rechnung · Lastschrift · Bar · Vorkasse
-- Das Ergebnis ist die Grundlage der Mapping-Tabelle ZAHLUNGSART in etl/abbildungsregeln.py.
-- ------------------------------------------------------------------------
SELECT b.zahlungsart,
       COUNT(*) AS positionen
FROM (SELECT DISTINCT bestell_nr, position, zahlungsart
      FROM stg.bestellungen) AS b
GROUP BY b.zahlungsart
ORDER BY 1;


-- ------------------------------------------------------------------------
-- P9: Wie oft wird preis_aus_listenpreis = TRUE?  (E-07, E-18)
-- Positionen ohne Einzelpreis, aufgeteilt nach dem, was im ETL passiert.
-- Die Artikelnummer wird wie in der Bereinigung (etl/03) vereinheitlicht
-- ('a-020', 'A019', ' A-005' -> 'A-020', 'A-019', 'A-005'; Nr 36).
-- Soll: Summe aller Zeilen = 56 (data_quality_issues Nr 40)
-- Hinweis: Einige dieser Positionen können zusätzlich aus einem
--          anderen Grund rejected werden (z. B. Menge <= 0, E-05).
-- ------------------------------------------------------------------------
WITH b AS (
    SELECT DISTINCT bestell_nr, position, artikel_nr, einzelpreis
    FROM stg.bestellungen
),
p AS (
    SELECT upper(trim(artikel_nr))                               AS artikel_nr,
           bool_or(preis IS NOT NULL AND trim(preis) <> '')      AS hat_listenpreis
    FROM stg.produkte
    GROUP BY upper(trim(artikel_nr))
)
SELECT CASE
           WHEN p.artikel_nr IS NULL THEN 'Produkt unbekannt -> rejected (Nr 37)'
           WHEN p.hat_listenpreis    THEN 'Listenpreis vorhanden -> preis_aus_listenpreis = TRUE'
           ELSE                           'kein Listenpreis -> rejected (E-07)'
       END      AS fall,
       COUNT(*) AS positionen
FROM b
LEFT JOIN p
       ON p.artikel_nr = regexp_replace(upper(replace(b.artikel_nr, ' ', '')),
                                        '^A-?([0-9]{3})$', 'A-\1')
WHERE trim(b.einzelpreis) = ''
GROUP BY 1
ORDER BY 1;
