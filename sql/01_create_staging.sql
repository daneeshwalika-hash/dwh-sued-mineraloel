-- ========================================================================
-- Staging-Tabellen (automatisch erzeugt)
--
-- Generator : Staging-DDL-Generator 1.0.0
-- Erzeugt am: 2026-10-06 12:26
-- Dialekt   : PostgreSQL
-- Schema    : stg
-- Quellen   : 4 Datei(en): bestellungen.csv, kunden.csv, kunden_update_2026-01.csv, produkte.json
--
-- Regeln:
--   * Eine Datei = eine Tabelle, Spalten in der Reihenfolge der Quelle.
--   * Alle Fachspalten TEXT: Rohdaten unverändert, keine Typumwandlung.
--   * Keine Primär-/Fremdschlüssel, kein NOT NULL: Rohdaten dürfen Fehler enthalten.
--   * Bereinigung und Typen folgen erst im ETL (Staging -> DWH).
--
-- Diese Datei ist generiert. Änderungen bitte im Generator vornehmen.
--
-- Ausführung: main.py führt die Datei nur auf einer leeren Datenbank aus (E-44),
--   weil sie DROP TABLE enthält.
-- Hinweis: stg.kunden_update_2026_01 entfernt sql/08 wieder (E-50); die Kunden-Updates
--   liegen in stg.kunden_update (sql/07, E-43).
-- ========================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS stg;

-- ------------------------------------------------------------------------
-- stg.bestellungen  <-  bestellungen.csv
-- Typ: CSV · Trennzeichen: ";" · Encoding: utf-8-sig · Datenzeilen: 2181
-- ------------------------------------------------------------------------
DROP TABLE IF EXISTS stg.bestellungen;

CREATE TABLE stg.bestellungen (
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
    _source_file    TEXT DEFAULT 'bestellungen.csv',
    _loaded_at      TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE stg.bestellungen IS 'Rohdaten aus bestellungen.csv, 2181 Datenzeilen bei Generierung; alle Fachspalten TEXT';
COMMENT ON COLUMN stg.bestellungen._source_file IS 'Technisch: Name der Quelldatei';
COMMENT ON COLUMN stg.bestellungen._loaded_at IS 'Technisch: Zeitpunkt des Ladens';

-- ------------------------------------------------------------------------
-- stg.kunden  <-  kunden.csv
-- Typ: CSV · Trennzeichen: ";" · Encoding: utf-8-sig · Datenzeilen: 157
-- ------------------------------------------------------------------------
DROP TABLE IF EXISTS stg.kunden;

CREATE TABLE stg.kunden (
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
    _source_file  TEXT DEFAULT 'kunden.csv',
    _loaded_at    TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE stg.kunden IS 'Rohdaten aus kunden.csv, 157 Datenzeilen bei Generierung; alle Fachspalten TEXT';
COMMENT ON COLUMN stg.kunden._source_file IS 'Technisch: Name der Quelldatei';
COMMENT ON COLUMN stg.kunden._loaded_at IS 'Technisch: Zeitpunkt des Ladens';

-- ------------------------------------------------------------------------
-- stg.kunden_update_2026_01  <-  kunden_update_2026-01.csv
-- Typ: CSV · Trennzeichen: ";" · Encoding: utf-8-sig · Datenzeilen: 20
-- ------------------------------------------------------------------------
DROP TABLE IF EXISTS stg.kunden_update_2026_01;

CREATE TABLE stg.kunden_update_2026_01 (
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
    _source_file  TEXT DEFAULT 'kunden_update_2026-01.csv',
    _loaded_at    TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE stg.kunden_update_2026_01 IS 'Rohdaten aus kunden_update_2026-01.csv, 20 Datenzeilen bei Generierung; alle Fachspalten TEXT';
COMMENT ON COLUMN stg.kunden_update_2026_01._source_file IS 'Technisch: Name der Quelldatei';
COMMENT ON COLUMN stg.kunden_update_2026_01._loaded_at IS 'Technisch: Zeitpunkt des Ladens';

-- ------------------------------------------------------------------------
-- stg.produkte  <-  produkte.json
-- Typ: JSON · Datensätze: $.artikel · Encoding: utf-8-sig · Datensätze (Anzahl): 25
-- ------------------------------------------------------------------------
DROP TABLE IF EXISTS stg.produkte;

CREATE TABLE stg.produkte (
    artikel_nr       TEXT,
    bezeichnung      TEXT,
    kategorie_haupt  TEXT,
    kategorie_unter  TEXT,
    einheit          TEXT,
    preis            TEXT,
    aktiv            TEXT,
    lieferant_name   TEXT,
    lieferant_land   TEXT,
    _source_file     TEXT DEFAULT 'produkte.json',
    _loaded_at       TIMESTAMPTZ DEFAULT now()
);

COMMENT ON TABLE stg.produkte IS 'Rohdaten aus produkte.json, 25 Datenzeilen bei Generierung; alle Fachspalten TEXT';
COMMENT ON COLUMN stg.produkte.kategorie_haupt IS 'Quelle: kategorie.haupt';
COMMENT ON COLUMN stg.produkte.kategorie_unter IS 'Quelle: kategorie.unter';
COMMENT ON COLUMN stg.produkte.lieferant_name IS 'Quelle: lieferant.name';
COMMENT ON COLUMN stg.produkte.lieferant_land IS 'Quelle: lieferant.land';
COMMENT ON COLUMN stg.produkte._source_file IS 'Technisch: Name der Quelldatei';
COMMENT ON COLUMN stg.produkte._loaded_at IS 'Technisch: Zeitpunkt des Ladens';

COMMIT;

-- ========================================================================
-- Kontrolle 1: Spaltenzahl Soll/Ist (kann sofort laufen)
-- ========================================================================
SELECT s.tabelle,
       s.soll_spalten,
       COUNT(c.column_name) AS ist_spalten,
       CASE WHEN COUNT(c.column_name) = s.soll_spalten THEN 'OK' ELSE 'FEHLER' END AS pruefung
FROM (VALUES
        ('bestellungen', 12),
        ('kunden', 14),
        ('kunden_update_2026_01', 14),
        ('produkte', 11)
     ) AS s(tabelle, soll_spalten)
LEFT JOIN information_schema.columns AS c
       ON c.table_schema = 'stg'
      AND c.table_name   = s.tabelle
GROUP BY s.tabelle, s.soll_spalten
ORDER BY s.tabelle;

-- ========================================================================
-- Kontrolle 2: Zeilenzahl Soll/Ist nach dem Laden
-- ========================================================================
-- Prüft etl/01_lade_staging.py bei jedem Lauf (Soll aus der Datei, Ist aus der Datenbank,
-- Abbruch bei Abweichung); Nachweis in logs/ladeprotokoll_staging.csv.
