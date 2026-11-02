-- ========================================================================
-- sql/02d_setze_not_null_dim_produkt_lieferant.sql
-- Migration: NOT NULL für dim_produkt.lieferant und dim_produkt.lieferant_land
--
-- Zweck      : E-23 legt fest: Ein fehlender Lieferant steht als 'Unbekannt' in
--              dim_produkt, nie als NULL. Ein CHECK lässt NULL aber immer durch.
--              Ab jetzt prüft die Datenbank selbst, dass das ETL keine Lücke
--              vergisst (E-23, Folgen).
-- Eingabe    : dwh.dim_produkt, bereits geladen mit etl/04_lade_dimensionen.py
-- Ausgabe    : NOT NULL auf lieferant und lieferant_land. Keine Daten werden
--              geändert, gelöscht oder eingefügt.
-- Anforderung: B2/Q-03 Regeln stehen als Constraint in der Datenbank,
--              Q-05 mehrmals startbar mit gleichem Ergebnis
-- Bezug      : E-23 (Lieferant 'Unbekannt'), Nr 26, sql/02c_aendere_ck_dim_produkt_land.sql,
--              E-33 (Neuladen: TRUNCATE + INSERT, NOT NULL greift dann bei jedem Lauf)
-- Aufruf     : NACH etl/04_lade_dimensionen.py
--              pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/02d_setze_not_null_dim_produkt_lieferant.sql
--              Erwartet: Teil B 3x '[OK]' (Reiter Messages), Teil C 5 Zeilen, alle 'OK'.
-- ========================================================================


-- ------------------------------------------------------------------------
-- Teil A: NOT NULL setzen, in EINER Transaktion
-- ------------------------------------------------------------------------
BEGIN;

-- Vorbedingung: dim_produkt ist geladen. Auf einer leeren Tabelle würde
-- SET NOT NULL zwar funktionieren, aber nichts über die geladenen Daten
-- beweisen. Leer -> Abbruch mit Meldung, die Transaktion wird zurückgerollt.
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM dwh.dim_produkt) = 0 THEN
        RAISE EXCEPTION 'dwh.dim_produkt ist leer: zuerst etl/04_lade_dimensionen.py ausführen';
    END IF;
END $$;

-- SET NOT NULL prüft alle vorhandenen Zeilen. Steht irgendwo NULL, bricht der
-- Befehl ab und die ganze Transaktion wird zurückgerollt (nichts geändert).
-- Warum ohne IF NOT EXISTS: SET NOT NULL auf einer Spalte, die schon NOT NULL ist,
-- ist in PostgreSQL erlaubt und ändert nichts -> zweiter Lauf gleiches Ergebnis.
ALTER TABLE dwh.dim_produkt
    ALTER COLUMN lieferant      SET NOT NULL,
    ALTER COLUMN lieferant_land SET NOT NULL;

COMMIT;


-- ------------------------------------------------------------------------
-- Teil B: Constraint-Test (Soll 3x '[OK]' im Reiter Messages)
-- Es bleibt NICHTS in der Tabelle: jeder Versuch in einem eigenen Unterblock,
-- ein angenommener Wert wird mit RAISE EXCEPTION 'angenommen' sofort
-- zurückgerollt, und der ganze Test läuft in BEGIN ... ROLLBACK.
-- Warum OVERRIDING SYSTEM VALUE mit festem Schlüssel -2: Sonst verbraucht
-- jeder Versuch eine Nummer des IDENTITY-Zählers (wie in 02c).
-- Bei einem unerwarteten Ergebnis bricht der Block am Ende mit Fehler ab.
-- ------------------------------------------------------------------------
BEGIN;

DO $$
DECLARE
    fehler INTEGER := 0;
BEGIN
    -- Test 1: lieferant NULL -> Soll: abgewiesen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', NULL, 'DE', TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN not_null_violation THEN RAISE NOTICE '[OK]         Test 1: lieferant NULL wird abgewiesen';
        WHEN raise_exception    THEN RAISE NOTICE '[UNERWARTET] Test 1: lieferant NULL wurde angenommen'; fehler := fehler + 1;
    END;

    -- Test 2: lieferant_land NULL -> Soll: abgewiesen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', 'Test', NULL, TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN not_null_violation THEN RAISE NOTICE '[OK]         Test 2: lieferant_land NULL wird abgewiesen';
        WHEN raise_exception    THEN RAISE NOTICE '[UNERWARTET] Test 2: lieferant_land NULL wurde angenommen'; fehler := fehler + 1;
    END;

    -- Test 3: 'Unbekannt' / 'Unbekannt' (E-23) -> Soll: angenommen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', 'Unbekannt', 'Unbekannt', TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN raise_exception    THEN RAISE NOTICE '[OK]         Test 3: Unbekannt / Unbekannt wird angenommen';
        WHEN not_null_violation OR check_violation
                                THEN RAISE NOTICE '[UNERWARTET] Test 3: Unbekannt wurde abgewiesen'; fehler := fehler + 1;
    END;

    IF fehler > 0 THEN
        RAISE EXCEPTION 'Constraint-Test fehlgeschlagen: % unerwartete(s) Ergebnis(se)', fehler;
    END IF;
END $$;

ROLLBACK;


-- ------------------------------------------------------------------------
-- Teil C: Soll/Ist nach der Migration (nur lesen)
-- Erwartet: 5 Zeilen, alle 'OK'. Bei 'FEHLER': Meldungen von Teil A prüfen.
-- ------------------------------------------------------------------------
WITH pruefungen (nr, pruefung, soll, ist) AS (
    SELECT 'N1', 'lieferant NOT NULL', 1,
           (SELECT attnotnull::int FROM pg_attribute
            WHERE attrelid = 'dwh.dim_produkt'::regclass AND attname = 'lieferant')
    UNION ALL
    SELECT 'N2', 'lieferant_land NOT NULL', 1,
           (SELECT attnotnull::int FROM pg_attribute
            WHERE attrelid = 'dwh.dim_produkt'::regclass AND attname = 'lieferant_land')
    UNION ALL
    -- Die Tests haben nichts hinterlassen: weiter 24 Produkte (Stand nach etl/04)
    SELECT 'N3', 'Zeilen in dim_produkt', 24, (SELECT COUNT(*)::int FROM dwh.dim_produkt)
    UNION ALL
    SELECT 'N4', 'Lieferant Unbekannt (E-23)', 3,
           (SELECT COUNT(*)::int FROM dwh.dim_produkt WHERE lieferant = 'Unbekannt')
    UNION ALL
    -- Kein Test-Schlüssel -2 übrig
    SELECT 'N5', 'Zeilen mit produkt_sk < 1', 0,
           (SELECT COUNT(*)::int FROM dwh.dim_produkt WHERE produkt_sk < 1)
)
SELECT nr, pruefung, soll, ist,
       CASE WHEN soll = ist THEN 'OK' ELSE 'FEHLER' END AS ergebnis
FROM pruefungen
ORDER BY nr;
