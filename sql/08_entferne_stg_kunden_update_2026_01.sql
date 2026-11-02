-- ========================================================================
-- sql/08_entferne_stg_kunden_update_2026_01.sql
-- Migration: alte Staging-Tabelle stg.kunden_update_2026_01 entfernen (E-50)
--
-- Zweck      : Seit E-43 lädt etl/01 alle Update-Dateien nach stg.kunden_update. Die alte Tabelle
--              wird nicht mehr ersetzt und widerspricht der Löschfrist für stg.* (E-46).
--              Sie wird entfernt, aber NUR, wenn ihr Inhalt vollständig in stg.kunden_update steht.
-- Eingabe    : stg.kunden_update_2026_01, stg.kunden_update (aus sql/07)
-- Ausgabe    : stg.kunden_update_2026_01 entfernt; Meldung (NOTICE) mit der Zeilenzahl
-- Anforderung: E-46 Löschfrist stg.*, kein stilles Löschen (Anzahl und Grund gemeldet)
-- Bezug      : E-17, E-43, E-46, E-50
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/08_entferne_stg_kunden_update_2026_01.sql
--              oder: automatisch in main.py (Schritt 1, nach sql/07)
--              Erwartet beim ersten Lauf: NOTICE "... entfernt: N Zeilen ...", COMMIT.
--              Erwartet bei jedem weiteren Lauf: NOTICE "... nicht vorhanden, nichts zu tun". Mehrmals startbar.
--
-- Prüfung vor dem Entfernen (sonst Abbruch, Tabelle bleibt):
--   1. Zeilen der alten Tabelle = Zeilen in stg.kunden_update aus derselben Datei (kunden_update_2026-01.csv).
--   2. Inhalt gleich: jede Zeile (alle Fachspalten) steht in beiden Tabellen (EXCEPT in beide Richtungen = 0).
--   Auf einer neuen Datenbank sind beide leer (0 = 0): Dann wird die leere Tabelle entfernt.
-- ========================================================================

BEGIN;

DO $$
DECLARE
    alt        BIGINT;
    neu        BIGINT;
    nur_alt    BIGINT;
    nur_neu    BIGINT;
BEGIN
    IF to_regclass('stg.kunden_update_2026_01') IS NULL THEN
        RAISE NOTICE 'stg.kunden_update_2026_01 nicht vorhanden, nichts zu tun (E-50)';
        RETURN;
    END IF;
    IF to_regclass('stg.kunden_update') IS NULL THEN
        RAISE EXCEPTION 'stg.kunden_update fehlt: zuerst sql/07_create_stg_kunden_update.sql ausführen';
    END IF;

    SELECT COUNT(*) INTO alt FROM stg.kunden_update_2026_01;
    SELECT COUNT(*) INTO neu FROM stg.kunden_update WHERE _source_file = 'kunden_update_2026-01.csv';

    -- Fachspalten wie in sql/01_create_staging.sql; technische Spalten (_source_file, _loaded_at) zählen nicht.
    SELECT COUNT(*) INTO nur_alt FROM (
        SELECT kunden_nr, kundentyp, firma, vorname, nachname, strasse, plz, ort, bundesland, telefon, email, erstellt_am
        FROM stg.kunden_update_2026_01
        EXCEPT ALL
        SELECT kunden_nr, kundentyp, firma, vorname, nachname, strasse, plz, ort, bundesland, telefon, email, erstellt_am
        FROM stg.kunden_update WHERE _source_file = 'kunden_update_2026-01.csv') x;
    SELECT COUNT(*) INTO nur_neu FROM (
        SELECT kunden_nr, kundentyp, firma, vorname, nachname, strasse, plz, ort, bundesland, telefon, email, erstellt_am
        FROM stg.kunden_update WHERE _source_file = 'kunden_update_2026-01.csv'
        EXCEPT ALL
        SELECT kunden_nr, kundentyp, firma, vorname, nachname, strasse, plz, ort, bundesland, telefon, email, erstellt_am
        FROM stg.kunden_update_2026_01) x;

    IF alt <> neu OR nur_alt <> 0 OR nur_neu <> 0 THEN
        RAISE EXCEPTION 'Abbruch, Tabelle bleibt: alt % Zeilen, neu % Zeilen, nur alt %, nur neu % (E-50)',
                        alt, neu, nur_alt, nur_neu;
    END IF;

    DROP TABLE stg.kunden_update_2026_01;
    RAISE NOTICE 'stg.kunden_update_2026_01 entfernt: % Zeilen, Inhalt vollständig in stg.kunden_update (% Zeilen aus kunden_update_2026-01.csv, Unterschiede 0) (E-50)',
                 alt, neu;
END $$;

COMMIT;
