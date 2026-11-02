-- ========================================================================
-- sql/02c_aendere_ck_dim_produkt_land.sql
-- Migration: CHECK-Constraint ck_dim_produkt_land um 'Unbekannt' erweitern
--
-- Zweck      : E-23 legt fest: Fehlt der Lieferant in der Quelle (Nr 26),
--              steht in dim_produkt lieferant = 'Unbekannt' und
--              lieferant_land = 'Unbekannt'. Der bisherige CHECK erlaubt nur
--              einen ISO-Code aus 2 Großbuchstaben (Nr 27) und würde
--              'Unbekannt' abweisen. Dieses Skript erweitert den CHECK und
--              passt die Spaltenkommentare (Data Dictionary) an.
-- Eingabe    : bestehende Tabelle dwh.dim_produkt (aus sql/02_create_dwh.sql)
-- Ausgabe    : geänderter Constraint ck_dim_produkt_land, neue COMMENTs für
--              dwh.dim_produkt.lieferant und dwh.dim_produkt.lieferant_land.
--              Keine Daten werden geändert, gelöscht oder eingefügt.
-- Anforderung: B2 Regeln stehen als Constraint in der Datenbank (Q-03)
--              B3 jede Spalte ist beschrieben (Data Dictionary)
--              B4 nichts wird still gelöscht (hier: nur Constraint ersetzt)
--              Q-05 mehrmals startbar mit gleichem Ergebnis
-- Bezug      : E-23 (Lieferant 'Unbekannt'), E-21 (gleiche Regel wie Zeile -1),
--              Nr 26 (Lieferant fehlt), Nr 27 (Land als ISO-Code)
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/02c_aendere_ck_dim_produkt_land.sql
--              Erwartet: Teil B 4x '[OK]' (Reiter Messages),
--                        Teil C 5 Zeilen, alle 'OK'.
--
-- Warum eine eigene Datei und nicht sql/02_create_dwh.sql ändern?
--   02_create_dwh.sql bricht ab, wenn die Tabellen schon existieren (B4).
--   Eine Änderung dort würde auf der bestehenden Datenbank nie ausgeführt.
--   Die Migration ist ein eigener, nachvollziehbarer Schritt.
-- ========================================================================


-- ------------------------------------------------------------------------
-- Teil A: Constraint ersetzen und Kommentare anpassen
-- Alles in EINER Transaktion: Entweder ist der neue CHECK da, oder der alte
-- bleibt unverändert. Es gibt keinen Zustand ganz ohne CHECK.
-- ------------------------------------------------------------------------
BEGIN;

-- Warum DROP ... IF EXISTS + ADD statt nur ADD: So kann man die Datei
-- mehrmals starten (Q-05). Beim zweiten Lauf wird der schon erweiterte
-- CHECK durch denselben CHECK ersetzt, das Ergebnis ist gleich.
ALTER TABLE dwh.dim_produkt
    DROP CONSTRAINT IF EXISTS ck_dim_produkt_land;

-- Neue Regel: ISO-Code aus 2 Großbuchstaben (wie bisher, Nr 27)
-- ODER genau der Text 'Unbekannt' (E-23). Alle anderen Werte wie
-- 'Deutschland' oder 'de' werden weiter abgewiesen.
-- ADD CONSTRAINT prüft dabei alle vorhandenen Zeilen. Verletzt eine Zeile
-- die Regel, bricht der Befehl ab und die ganze Transaktion wird
-- zurückgerollt (der alte CHECK bleibt dann bestehen).
-- Hinweis: NULL besteht jeden CHECK. NOT NULL ist hier bewusst noch nicht
-- gesetzt (siehe E-23, Folgen).
ALTER TABLE dwh.dim_produkt
    ADD CONSTRAINT ck_dim_produkt_land
    CHECK (lieferant_land ~ '^[A-Z]{2}$' OR lieferant_land = 'Unbekannt');

-- Data Dictionary (B3): Der alte Kommentar zu lieferant sagte "NULL, wenn das
-- Feld fehlt". Das widerspricht E-23 und wird deshalb ersetzt.
COMMENT ON COLUMN dwh.dim_produkt.lieferant      IS 'Name des Lieferanten; ''Unbekannt'', wenn in der Quelle das Feld fehlt (Nr 26, E-23). Kein NULL';
COMMENT ON COLUMN dwh.dim_produkt.lieferant_land IS 'Land des Lieferanten als ISO-Code, z. B. DE (Nr 27); ''Unbekannt'', wenn in der Quelle das Feld fehlt (Nr 26, E-23). Kein NULL';

COMMIT;


-- ------------------------------------------------------------------------
-- Teil B: Constraint-Test (vier Werte, Soll 4x '[OK]' im Reiter Messages)
-- Es bleibt NICHTS in der Tabelle:
--   * Jeder Versuch läuft in einem eigenen Unterblock. Ein Fehler darin
--     rollt nur diesen Unterblock zurück.
--   * Auch ein angenommener Wert wird sofort wieder entfernt: RAISE EXCEPTION
--     'angenommen' löst den Rollback des Unterblocks aus.
--   * Zusätzlich läuft der ganze Test in BEGIN ... ROLLBACK.
-- Warum OVERRIDING SYSTEM VALUE mit festem Schlüssel -2: Sonst würde jeder
-- Versuch eine Nummer des IDENTITY-Zählers verbrauchen, und das erste echte
-- Produkt bekäme nicht produkt_sk = 1 (gleiches Vorgehen wie Kontrolle 5 in
-- sql/02_create_dwh.sql).
-- Bei einem unerwarteten Ergebnis bricht der Block am Ende mit Fehler ab
-- (Meldung "Constraint-Test fehlgeschlagen"). Dann gilt die Migration als
-- nicht geprüft und darf nicht für das Laden verwendet werden.
-- ------------------------------------------------------------------------
BEGIN;

DO $$
DECLARE
    fehler INTEGER := 0;   -- Anzahl unerwarteter Ergebnisse
BEGIN
    -- Test 1: ISO-Code 'DE' -> Soll: angenommen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', 'Test', 'DE', TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN raise_exception THEN RAISE NOTICE '[OK]         Test 1: DE wird angenommen';
        WHEN check_violation THEN RAISE NOTICE '[UNERWARTET] Test 1: DE wurde abgewiesen'; fehler := fehler + 1;
    END;

    -- Test 2: 'Unbekannt' (E-23) -> Soll: angenommen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', 'Unbekannt', 'Unbekannt', TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN raise_exception THEN RAISE NOTICE '[OK]         Test 2: Unbekannt wird angenommen';
        WHEN check_violation THEN RAISE NOTICE '[UNERWARTET] Test 2: Unbekannt wurde abgewiesen'; fehler := fehler + 1;
    END;

    -- Test 3: Ländername statt ISO-Code (Nr 27) -> Soll: abgewiesen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', 'Test', 'Deutschland', TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN check_violation THEN RAISE NOTICE '[OK]         Test 3: Deutschland wird abgewiesen';
        WHEN raise_exception THEN RAISE NOTICE '[UNERWARTET] Test 3: Deutschland wurde angenommen'; fehler := fehler + 1;
    END;

    -- Test 4: Kleinbuchstaben (nicht vereinheitlicht) -> Soll: abgewiesen
    BEGIN
        INSERT INTO dwh.dim_produkt (produkt_sk, artikel_nr, bezeichnung, kategorie, unterkategorie,
                                     einheit, lieferant, lieferant_land, aktiv)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'A-990', 'Test', 'Test', 'Test', 'L', 'Test', 'de', TRUE);
        RAISE EXCEPTION 'angenommen';
    EXCEPTION
        WHEN check_violation THEN RAISE NOTICE '[OK]         Test 4: de wird abgewiesen';
        WHEN raise_exception THEN RAISE NOTICE '[UNERWARTET] Test 4: de wurde angenommen'; fehler := fehler + 1;
    END;

    -- Abbruch, wenn ein Test nicht wie erwartet ausging (siehe Kopf von Teil B)
    IF fehler > 0 THEN
        RAISE EXCEPTION 'Constraint-Test fehlgeschlagen: % unerwartete(s) Ergebnis(se)', fehler;
    END IF;
END $$;

ROLLBACK;


-- ------------------------------------------------------------------------
-- Teil C: Soll/Ist nach der Migration (nur lesen)
-- Erwartet: 5 Zeilen, alle 'OK'. Bei 'FEHLER' ist die Migration nicht
-- (vollständig) angekommen: Teil A erneut ausführen und Meldungen prüfen.
-- ------------------------------------------------------------------------
WITH pruefungen (nr, pruefung, soll, ist) AS (
    -- Genau ein Constraint mit diesem Namen (kein Duplikat nach zweitem Lauf)
    SELECT 'M1', 'Anzahl ck_dim_produkt_land', 1,
           (SELECT COUNT(*)::int FROM pg_constraint
            WHERE conrelid = 'dwh.dim_produkt'::regclass AND conname = 'ck_dim_produkt_land')
    UNION ALL
    -- Der Constraint enthält die neue Regel 'Unbekannt'
    SELECT 'M2', 'CHECK erlaubt Unbekannt', 1,
           (SELECT COUNT(*)::int FROM pg_constraint
            WHERE conrelid = 'dwh.dim_produkt'::regclass AND conname = 'ck_dim_produkt_land'
              AND pg_get_constraintdef(oid) LIKE '%Unbekannt%')
    UNION ALL
    -- Neue Kommentare verweisen auf E-23 (Data Dictionary aktuell)
    SELECT 'M3', 'Kommentar lieferant nennt E-23', 1,
           CASE WHEN col_description('dwh.dim_produkt'::regclass,
                     (SELECT attnum FROM pg_attribute WHERE attrelid = 'dwh.dim_produkt'::regclass
                      AND attname = 'lieferant')) LIKE '%E-23%' THEN 1 ELSE 0 END
    UNION ALL
    SELECT 'M4', 'Kommentar lieferant_land nennt E-23', 1,
           CASE WHEN col_description('dwh.dim_produkt'::regclass,
                     (SELECT attnum FROM pg_attribute WHERE attrelid = 'dwh.dim_produkt'::regclass
                      AND attname = 'lieferant_land')) LIKE '%E-23%' THEN 1 ELSE 0 END
    UNION ALL
    -- Der Test hat nichts in der Tabelle hinterlassen (dim_produkt ist vor dem ersten Laden leer)
    SELECT 'M5', 'Zeilen in dim_produkt', 0,
           (SELECT COUNT(*)::int FROM dwh.dim_produkt)
)
SELECT nr, pruefung, soll, ist,
       CASE WHEN soll = ist THEN 'OK' ELSE 'FEHLER' END AS ergebnis
FROM pruefungen
ORDER BY nr;
