-- ========================================================================
-- sql/07_create_stg_kunden_update.sql
-- Migration: eine Staging-Tabelle für ALLE Kunden-Update-Dateien
--
-- Zweck      : Datennachschub: Statt einer festen Tabelle für kunden_update_2026-01.csv
--              nimmt stg.kunden_update alle Dateien kunden_update_*.csv auf. Die Spalte
--              _source_file sagt, aus welcher Datei eine Zeile stammt; aus dem Dateinamen
--              folgt das Gültigkeitsdatum (etl/kunden_updates.py, E-43).
-- Eingabe    : keine (legt nur an). Befüllt von etl/01_lade_staging.py.
-- Ausgabe    : Tabelle stg.kunden_update mit COMMENT;
--              COMMENT an stg.kunden_update_2026_01: abgelöst, wird nicht mehr geladen.
-- Anforderung: erneuter Lauf nach Datennachschub aktualisiert; Laden 1:1 mit Soll/Ist wie in etl/01
-- Bezug      : E-10, E-17, E-31, E-43
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/07_create_stg_kunden_update.sql
--              Erwartet: BEGIN, CREATE TABLE, COMMENT ..., COMMIT. Mehrmals startbar (IF NOT EXISTS).
--
-- Fachspalten wie stg.kunden_update_2026_01 in sql/01_create_staging.sql (alle TEXT, E-10).
-- Unterschied: _source_file ohne DEFAULT und NOT NULL. Bei mehreren Dateien muss etl/01 den
-- Dateinamen je Zeile setzen; ein fester DEFAULT würde eine falsche Herkunft still eintragen.
-- Die alte Tabelle stg.kunden_update_2026_01 wird NICHT gelöscht (kein stilles Löschen);
-- sie behält ihren letzten Inhalt und bekommt einen Hinweis im COMMENT.
-- Später entfernt sql/08 die alte Tabelle nach einer Inhaltsprüfung (E-50).
-- ========================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS stg.kunden_update (
    kunden_nr     TEXT,
    kundentyp     TEXT,
    firma         TEXT,
    vorname       TEXT,
    nachname      TEXT,
    strasse       TEXT,
    plz           TEXT,
    ort           TEXT,
    bundesland    TEXT,
    telefon       TEXT,
    email         TEXT,
    erstellt_am   TEXT,
    _source_file  TEXT NOT NULL,
    _loaded_at    TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE stg.kunden_update IS
  'Rohdaten aller Dateien kunden_update_*.csv (E-43), alle Fachspalten TEXT. Herkunft je Zeile in _source_file, gueltig_von aus dem Dateinamen (etl/kunden_updates.py).';
COMMENT ON COLUMN stg.kunden_update._source_file IS 'Technisch: Name der Quelldatei, von etl/01 je Zeile gesetzt (kein DEFAULT)';
COMMENT ON COLUMN stg.kunden_update._loaded_at IS 'Technisch: Zeitpunkt des Ladens';

COMMENT ON TABLE stg.kunden_update_2026_01 IS
  'Abgelöst durch stg.kunden_update (E-43, 19.10.2026): wird nicht mehr geladen, Inhalt = letzter Stand vor der Umstellung. Rohdaten aus kunden_update_2026-01.csv, 20 Datenzeilen bei Generierung; alle Fachspalten TEXT';

COMMIT;
