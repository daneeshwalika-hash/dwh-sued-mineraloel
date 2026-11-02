-- ========================================================================
-- sql/02b_pruefung_staging_dwh.sql
-- Abschlussprüfung nach dem Anlegen der DWH-Tabellen: alle Prüfungen in EINER Ergebnistabelle
--
-- Projekt : DWH Süd-Mineralöl · PostgreSQL 18 · Datenbank dwh_sued
-- Stand   : 11.10.2026
-- Enthält : P1-P9 aus sql/01b_typpruefung_staging.sql (Staging-Typen)
--           K1-K4 aus sql/02_create_dwh.sql (DWH-Tabellen)
-- Liest nur (nur SELECT), ändert nichts.
-- Hinweis : K2 prüft den Stand DIREKT nach sql/02_create_dwh.sql (dim_datum, dim_produkt
--           und fact_verkauf leer). Nach einem Lauf von main.py zeigt K2 deshalb ABWEICHUNG.
--
-- Ausführen: pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
-- Soll     : jede Zeile in der Spalte "ergebnis" = OK
-- ========================================================================

WITH
-- Positionen ohne die 25 exakten Dubletten (gleiche Basis wie E-12)
b AS (
    SELECT DISTINCT bestell_nr, position, artikel_nr, menge, einzelpreis,
                    rabatt_prozent, zahlungsart, lieferstatus
    FROM stg.bestellungen
),
-- Artikelstamm mit vereinheitlichter Artikelnummer (wie P9)
p AS (
    SELECT upper(trim(artikel_nr))                          AS artikel_nr,
           bool_or(preis IS NOT NULL AND trim(preis) <> '') AS hat_listenpreis
    FROM stg.produkte
    GROUP BY upper(trim(artikel_nr))
),
-- Positionen ohne Einzelpreis (P9)
ohne_preis AS (
    SELECT p.artikel_nr IS NULL AS produkt_unbekannt,
           coalesce(p.hat_listenpreis, FALSE) AS hat_listenpreis
    FROM b
    LEFT JOIN p
           ON p.artikel_nr = regexp_replace(upper(replace(b.artikel_nr, ' ', '')),
                                            '^A-?([0-9]{3})$', 'A-\1')
    WHERE trim(b.einzelpreis) = ''
),
-- Alle Prüfungen: nr, Text, Soll (als Text), Ist (als Zahl), OK?
pruefungen (nr, pruefung, soll, ist, ok) AS (
    -- ---------------- Staging-Typen ----------------
    SELECT 'P1', 'bestell_nr nicht numerisch', '0',
           COUNT(*)::numeric, COUNT(*) = 0
    FROM stg.bestellungen WHERE trim(bestell_nr) !~ '^[0-9]+$'
    UNION ALL
    SELECT 'P2a', 'position nicht numerisch', '0',
           COUNT(*)::numeric, COUNT(*) = 0
    FROM stg.bestellungen WHERE trim(position) !~ '^[0-9]+$'
    UNION ALL
    SELECT 'P2b', 'position Maximum (SMALLINT)', '< 32767',
           MAX(trim(position)::integer)::numeric, MAX(trim(position)::integer) < 32767
    FROM stg.bestellungen WHERE trim(position) ~ '^[0-9]+$'
    UNION ALL
    SELECT 'P3', 'menge nicht ganzzahlig', '0',
           COUNT(*)::numeric, COUNT(*) = 0
    FROM stg.bestellungen WHERE trim(menge) !~ '^-?[0-9]+$'
    UNION ALL
    SELECT 'P4', 'einzelpreis max. Nachkommastellen', '<= 2',
           MAX(length(split_part(replace(trim(einzelpreis), ',', '.'), '.', 2)))::numeric,
           MAX(length(split_part(replace(trim(einzelpreis), ',', '.'), '.', 2))) <= 2
    FROM stg.bestellungen WHERE trim(einzelpreis) <> ''
    UNION ALL
    SELECT 'P5', 'listenpreis max. Nachkommastellen', '<= 2',
           MAX(length(split_part(replace(regexp_replace(trim(preis), '[^0-9,.]', '', 'g'), ',', '.'), '.', 2)))::numeric,
           MAX(length(split_part(replace(regexp_replace(trim(preis), '[^0-9,.]', '', 'g'), ',', '.'), '.', 2))) <= 2
    FROM stg.produkte WHERE preis IS NOT NULL AND trim(preis) <> ''
    UNION ALL
    SELECT 'P6a', 'rabatt_prozent Minimum', '>= 0',
           MIN(replace(trim(rabatt_prozent), ',', '.')::numeric),
           MIN(replace(trim(rabatt_prozent), ',', '.')::numeric) >= 0
    FROM stg.bestellungen WHERE trim(rabatt_prozent) <> ''
    UNION ALL
    SELECT 'P6b', 'rabatt_prozent Maximum', '<= 100',
           MAX(replace(trim(rabatt_prozent), ',', '.')::numeric),
           MAX(replace(trim(rabatt_prozent), ',', '.')::numeric) <= 100
    FROM stg.bestellungen WHERE trim(rabatt_prozent) <> ''
    UNION ALL
    SELECT 'P7a', 'Lieferstatus geliefert', '1083',
           COUNT(*)::numeric, COUNT(*) = 1083
    FROM b WHERE lower(trim(lieferstatus)) = 'geliefert'
    UNION ALL
    SELECT 'P7b', 'Lieferstatus offen', '369',
           COUNT(*)::numeric, COUNT(*) = 369
    FROM b WHERE lower(trim(lieferstatus)) = 'offen'
    UNION ALL
    SELECT 'P7c', 'Lieferstatus storniert', '353',
           COUNT(*)::numeric, COUNT(*) = 353
    FROM b WHERE lower(trim(lieferstatus)) = 'storniert'
    UNION ALL
    SELECT 'P7d', 'Lieferstatus teilgeliefert', '351',
           COUNT(*)::numeric, COUNT(*) = 351
    FROM b WHERE lower(trim(lieferstatus)) = 'teilgeliefert'
    UNION ALL
    SELECT 'P7e', 'Lieferstatus: Anzahl verschiedener Werte', '4',
           COUNT(DISTINCT lower(trim(lieferstatus)))::numeric,
           COUNT(DISTINCT lower(trim(lieferstatus))) = 4
    FROM b
    UNION ALL
    SELECT 'P7f', 'Positionen ohne Dubletten (Summe)', '2156',
           COUNT(*)::numeric, COUNT(*) = 2156
    FROM b
    UNION ALL
    SELECT 'P8', 'zahlungsart: Schreibweisen', '9',
           COUNT(DISTINCT zahlungsart)::numeric, COUNT(DISTINCT zahlungsart) = 9
    FROM b
    UNION ALL
    SELECT 'P9a', 'ohne Preis -> preis_aus_listenpreis = TRUE', '49',
           COUNT(*) FILTER (WHERE NOT produkt_unbekannt AND hat_listenpreis)::numeric,
           COUNT(*) FILTER (WHERE NOT produkt_unbekannt AND hat_listenpreis) = 49
    FROM ohne_preis
    UNION ALL
    SELECT 'P9b', 'ohne Preis und ohne Listenpreis -> rejected', '7',
           COUNT(*) FILTER (WHERE NOT produkt_unbekannt AND NOT hat_listenpreis)::numeric,
           COUNT(*) FILTER (WHERE NOT produkt_unbekannt AND NOT hat_listenpreis) = 7
    FROM ohne_preis
    UNION ALL
    SELECT 'P9c', 'ohne Preis gesamt (Nr 40)', '56',
           COUNT(*)::numeric, COUNT(*) = 56
    FROM ohne_preis
    -- ---------------- DWH-Tabellen ----------------
    UNION ALL
    SELECT 'K1a', 'Tabellen in dwh', '6',
           COUNT(*)::numeric, COUNT(*) = 6
    FROM information_schema.tables
    WHERE table_schema = 'dwh' AND table_type = 'BASE TABLE'
    UNION ALL
    SELECT 'K1b', 'Spalten in dwh (10+13+10+2+3+13)', '51',
           COUNT(*)::numeric, COUNT(*) = 51
    FROM information_schema.columns WHERE table_schema = 'dwh'
    UNION ALL
    SELECT 'K2a', 'Zeilen dim_kunde (nur -1)', '1',
           COUNT(*)::numeric, COUNT(*) = 1 FROM dwh.dim_kunde
    UNION ALL
    SELECT 'K2b', 'Zeilen dim_zahlung', '4',
           COUNT(*)::numeric, COUNT(*) = 4 FROM dwh.dim_zahlung
    UNION ALL
    SELECT 'K2c', 'Zeilen dim_status', '8',
           COUNT(*)::numeric, COUNT(*) = 8 FROM dwh.dim_status
    UNION ALL
    SELECT 'K2d', 'Zeilen dim_datum + dim_produkt + fact_verkauf', '0',
           ((SELECT COUNT(*) FROM dwh.dim_datum)
          + (SELECT COUNT(*) FROM dwh.dim_produkt)
          + (SELECT COUNT(*) FROM dwh.fact_verkauf))::numeric,
           ((SELECT COUNT(*) FROM dwh.dim_datum)
          + (SELECT COUNT(*) FROM dwh.dim_produkt)
          + (SELECT COUNT(*) FROM dwh.fact_verkauf)) = 0
    UNION ALL
    SELECT 'K3a', 'Spalten ohne Kommentar', '0',
           COUNT(*)::numeric, COUNT(*) = 0
    FROM information_schema.columns AS c
    WHERE c.table_schema = 'dwh'
      AND col_description(format('%I.%I', c.table_schema, c.table_name)::regclass,
                          c.ordinal_position) IS NULL
    UNION ALL
    SELECT 'K3b', 'Tabellen ohne Kommentar', '0',
           COUNT(*)::numeric, COUNT(*) = 0
    FROM information_schema.tables AS t
    WHERE t.table_schema = 'dwh'
      AND obj_description(format('%I.%I', t.table_schema, t.table_name)::regclass,
                          'pg_class') IS NULL
    UNION ALL
    SELECT 'K4', 'Fremdschlüssel in fact_verkauf', '5',
           COUNT(*)::numeric, COUNT(*) = 5
    FROM pg_constraint
    WHERE conrelid = 'dwh.fact_verkauf'::regclass AND contype = 'f'
)
SELECT nr,
       pruefung,
       soll,
       ist,
       CASE WHEN ok THEN 'OK' ELSE 'ABWEICHUNG' END AS ergebnis
FROM pruefungen
ORDER BY nr;
