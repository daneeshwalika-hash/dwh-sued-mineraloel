-- ========================================================================
-- sql/06_create_protokoll_abgewiesen.sql
-- Migration: Schema protokoll und Tabelle protokoll.abgewiesene_position
--
-- Zweck      : Die abgewiesenen Bestellpositionen liegen zusätzlich zur CSV
--              (data/rejected/bestellungen_rejected.csv) als Protokolltabelle in der Datenbank.
--              So sind sie per SQL auswertbar (mart.v_dq_abgewiesene_zeilen_grund, Diagramm D3)
--              und werden in derselben Transaktion wie dwh.fact_verkauf geladen (E-42).
-- Eingabe    : keine (legt nur Objekte an). Befüllt von etl/05_lade_fakten.py.
-- Ausgabe    : Schema protokoll, Tabelle protokoll.abgewiesene_position mit COMMENT
-- Anforderung: abgelehnte Zeilen mit Grund in einer Protokolltabelle, Q-02 Grund nie leer,
--              Q-05 zweiter Lauf = gleiche Tabelle
-- Bezug      : E-05, E-07, E-10, E-27, E-34, E-42; Nr 37
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/06_create_protokoll_abgewiesen.sql
--              Erwartet: BEGIN, CREATE SCHEMA, CREATE TABLE, COMMENT ..., COMMIT.
--              Mehrmals startbar: IF NOT EXISTS legt nur an, was fehlt. Kein DROP, keine Daten weg.
--              Danach: etl/00_starte_gesamtlauf.py (Schritt 5 befüllt die Tabelle).
--
-- Aufbau (E-42):
--   - Fachspalten als TEXT mit den Originalwerten, wie stg (E-10): Die Tabelle muss JEDE schlechte
--     Zeile aufnehmen können, auch "abc" als Menge oder ein leeres Datum.
--   - KEIN Primärschlüssel auf Rohwerten (bestell_nr, position): Eine künftige Zeile ohne
--     bestell_nr oder mit doppeltem Schlüssel würde sonst den ganzen Lauf abbrechen.
--   - Technischer Schlüssel (_source_file, lfd_nr): lfd_nr = 1..N in der festen Sortierung über
--     alle Spalten (wie etl/03 lese_staging). stg hat keine Zeilennummer der Rohdatei (E-42, Ausblick).
--   - Keine Spalte _loaded_at: Ein Zeitstempel änderte bei jedem Lauf den Inhalt (Q-05).
--     Der Ladezeitpunkt steht in logs/ladeprotokoll_dwh.csv.
-- ========================================================================

-- Alles in EINER Transaktion: Schema und Tabelle ganz oder gar nicht.
BEGIN;

-- Eigenes Schema: Protokolle sind kein Teil des Star Schemas, dwh bleibt Dimensionen + Fakten (E-16, E-42).
CREATE SCHEMA IF NOT EXISTS protokoll;
COMMENT ON SCHEMA protokoll IS 'Protokolltabellen der Ladestrecke (keine Dimensionen, keine Fakten), E-42';

CREATE TABLE IF NOT EXISTS protokoll.abgewiesene_position (
    _source_file    TEXT    NOT NULL,
    lfd_nr          INTEGER NOT NULL,
    bestell_nr      TEXT,
    position        TEXT,
    bestelldatum    TEXT,
    kunden_nr       TEXT,
    artikel_nr      TEXT,
    menge           TEXT,
    einzelpreis     TEXT,
    rabatt_prozent  TEXT,
    zahlungsart     TEXT,
    lieferstatus    TEXT,
    grund           TEXT    NOT NULL,
    CONSTRAINT pk_abgewiesene_position PRIMARY KEY (_source_file, lfd_nr),
    -- lfd_nr beginnt bei 1 (Zählung in etl/05).
    CONSTRAINT ck_abgewiesene_position_lfd_nr CHECK (lfd_nr >= 1),
    -- Q-02: Grund nie leer. Leerzeichen allein zählen als leer. Verstoß -> Fehler -> ROLLBACK in etl/05.
    CONSTRAINT ck_abgewiesene_position_grund CHECK (btrim(grund) <> '')
);

COMMENT ON TABLE protokoll.abgewiesene_position IS
  'Abgewiesene Bestellpositionen mit Originalwerten (TEXT) und Grund. Bei jedem Lauf neu geladen, in derselben Transaktion wie dwh.fact_verkauf (E-42). Gleicher Inhalt wie data/rejected/bestellungen_rejected.csv.';
COMMENT ON COLUMN protokoll.abgewiesene_position._source_file IS 'Technisch: Name der Quelldatei, Teil des Schlüssels';
COMMENT ON COLUMN protokoll.abgewiesene_position.lfd_nr IS
  'Technisch: laufende Nummer 1..N in fester Sortierung über alle Spalten. Keine Zeilennummer der Rohdatei (E-42).';
COMMENT ON COLUMN protokoll.abgewiesene_position.grund IS
  'Alle Ablehnungsgründe der Zeile, getrennt durch " | " (E-27). Nie leer (Q-02).';

COMMIT;
