-- ========================================================================
-- sql/02_create_dwh.sql
-- DWH-Tabellen (Star Schema) im Schema dwh
--
-- Projekt   : DWH Süd-Mineralöl · PostgreSQL 18 · Datenbank dwh_sued
-- Stand     : 11.10.2026
-- Design    : docs/star_schema.drawio (einzige Quelle des Designs)
-- Entscheid.: E-01 Grain · E-04 Zeile -1 · E-11 PostgreSQL · E-14 SCD 2
--             E-16 Star · E-18 dim_status · E-19 Messwerte
--             E-20 Schlüssel fact_verkauf · E-21 Schlüssel der Dimensionen
--
-- Regeln:
--   * Erst die Dimensionen, dann die Faktentabelle
--     (Fremdschlüssel brauchen die Eltern-Tabelle).
--   * KEIN DROP TABLE: Wenn eine Tabelle schon existiert, bricht das Skript
--     ab. So kann es nie geladene DWH-Daten still löschen.
--   * Alles in EINER Transaktion: entweder alle Tabellen oder keine.
--   * Jede Tabelle und jede Spalte hat einen COMMENT = Data Dictionary.
--   * Vorher sql/01b_typpruefung_staging.sql ausführen (Typen belegt?).
--
-- Ausführen: main.py führt Teil 1 nur auf einer leeren Datenbank aus (E-44).
--            Von Hand: pgAdmin -> dwh_sued -> Query Tool -> Datei öffnen
--            -> Teil 1 (BEGIN ... COMMIT) markieren -> F5
--            -> danach die Kontrollen einzeln markieren -> F5
--
-- Neu bauen (nur solange dwh noch leer ist!) – bewusst NICHT im Skript:
--   DROP TABLE dwh.fact_verkauf, dwh.dim_status, dwh.dim_zahlung,
--              dwh.dim_produkt, dwh.dim_kunde, dwh.dim_datum;
-- ========================================================================


-- ########################################################################
-- TEIL 1: Tabellen anlegen
-- ########################################################################

BEGIN;

CREATE SCHEMA IF NOT EXISTS dwh;


-- ------------------------------------------------------------------------
-- 1. dwh.dim_datum  (wird von etl/02_lade_dim_datum.py gefüllt)
--    Schlüssel = Datum als Zahl JJJJMMTT, kein Zähler (E-21)
-- ------------------------------------------------------------------------
CREATE TABLE dwh.dim_datum (
    datum_sk         INTEGER  NOT NULL,
    datum            DATE     NOT NULL,
    jahr             SMALLINT NOT NULL,
    quartal          SMALLINT NOT NULL,
    monat            SMALLINT NOT NULL,
    monat_name       TEXT     NOT NULL,
    kalenderwoche    SMALLINT NOT NULL,
    wochentag        SMALLINT NOT NULL,
    ist_wochenende   BOOLEAN  NOT NULL,
    ist_feiertag_bw  BOOLEAN  NOT NULL,

    CONSTRAINT pk_dim_datum       PRIMARY KEY (datum_sk),
    CONSTRAINT uq_dim_datum_datum UNIQUE (datum),

    -- Der Schlüssel muss zum Datum passen: 2025-03-17 -> 20250317
    CONSTRAINT ck_dim_datum_sk CHECK (
        datum_sk = EXTRACT(YEAR  FROM datum) * 10000
                 + EXTRACT(MONTH FROM datum) * 100
                 + EXTRACT(DAY   FROM datum)
    ),
    -- Die abgeleiteten Spalten müssen zum Datum passen.
    -- So prüft die Datenbank das Skript etl/02_lade_dim_datum.py mit.
    CONSTRAINT ck_dim_datum_teile CHECK (
            jahr          = EXTRACT(YEAR    FROM datum)
        AND quartal       = EXTRACT(QUARTER FROM datum)
        AND monat         = EXTRACT(MONTH   FROM datum)
        AND kalenderwoche = EXTRACT(WEEK    FROM datum)   -- ISO-Kalenderwoche
        AND wochentag     = EXTRACT(ISODOW  FROM datum)   -- 1 = Montag, 7 = Sonntag
    ),
    CONSTRAINT ck_dim_datum_wochenende CHECK (ist_wochenende = (wochentag >= 6))
);

COMMENT ON TABLE  dwh.dim_datum                 IS 'Datumsdimension (konform): 1 Zeile = 1 Kalendertag. Wird per Skript erzeugt, nicht aus den Quelldaten.';
COMMENT ON COLUMN dwh.dim_datum.datum_sk        IS 'PK: Datum als Zahl JJJJMMTT, z. B. 20250317 (kein Zähler, E-21)';
COMMENT ON COLUMN dwh.dim_datum.datum           IS 'Kalenderdatum';
COMMENT ON COLUMN dwh.dim_datum.jahr            IS 'Kalenderjahr, z. B. 2025';
COMMENT ON COLUMN dwh.dim_datum.quartal         IS 'Quartal 1 bis 4';
COMMENT ON COLUMN dwh.dim_datum.monat           IS 'Monat 1 bis 12';
COMMENT ON COLUMN dwh.dim_datum.monat_name      IS 'Deutscher Monatsname, z. B. März';
COMMENT ON COLUMN dwh.dim_datum.kalenderwoche   IS 'ISO-Kalenderwoche 1 bis 53';
COMMENT ON COLUMN dwh.dim_datum.wochentag       IS 'ISO-Wochentag: 1 = Montag ... 7 = Sonntag';
COMMENT ON COLUMN dwh.dim_datum.ist_wochenende  IS 'TRUE bei Samstag und Sonntag';
COMMENT ON COLUMN dwh.dim_datum.ist_feiertag_bw IS 'TRUE an gesetzlichen Feiertagen in Baden-Württemberg. Quelle: Python-Paket holidays (subdiv="BW")';


-- ------------------------------------------------------------------------
-- 2. dwh.dim_kunde  (SCD Typ 2, E-14)
--    Ohne Straße, Telefon, E-Mail (DSGVO, R-03)
-- ------------------------------------------------------------------------
CREATE TABLE dwh.dim_kunde (
    kunde_sk     INTEGER GENERATED ALWAYS AS IDENTITY,
    kunden_nr    TEXT    NOT NULL,
    kundentyp    TEXT    NOT NULL,
    firma        TEXT,
    vorname      TEXT,
    nachname     TEXT,
    plz          TEXT,
    ort          TEXT,
    bundesland   TEXT,
    erstellt_am  DATE,
    gueltig_von  DATE    NOT NULL,
    gueltig_bis  DATE    NOT NULL,
    ist_aktuell  BOOLEAN NOT NULL,

    CONSTRAINT pk_dim_kunde PRIMARY KEY (kunde_sk),
    -- Ein Kunde darf nicht zwei Versionen mit demselben Beginn haben
    CONSTRAINT uq_dim_kunde_version UNIQUE (kunden_nr, gueltig_von),
    -- Kundennummer schon vereinheitlicht (upper, Nr 34): 'K0040', nicht 'k0040'
    CONSTRAINT ck_dim_kunde_kunden_nr CHECK (kunden_nr ~ '^K[0-9]{4}$' OR kunden_nr = 'UNBEKANNT'),
    -- Mapping G/gewerbe -> Gewerbe, P/privat -> Privat (Nr 3)
    CONSTRAINT ck_dim_kunde_kundentyp CHECK (kundentyp IN ('Gewerbe', 'Privat', 'Unbekannt')),
    -- PLZ immer 5 Ziffern (zfill, ohne 'D-', ohne Leerzeichen; Nr 7-9). NULL erlaubt (Nr 6)
    CONSTRAINT ck_dim_kunde_plz CHECK (plz ~ '^[0-9]{5}$'),
    CONSTRAINT ck_dim_kunde_gueltigkeit CHECK (gueltig_von <= gueltig_bis),
    -- E-14: aktuelle Version gilt bis 9999-12-31, und nur dann ist_aktuell = TRUE
    CONSTRAINT ck_dim_kunde_aktuell CHECK (ist_aktuell = (gueltig_bis = DATE '9999-12-31'))
);

-- Pro Kundennummer genau EINE aktuelle Version
CREATE UNIQUE INDEX ux_dim_kunde_aktuell
    ON dwh.dim_kunde (kunden_nr)
    WHERE ist_aktuell;

COMMENT ON TABLE  dwh.dim_kunde             IS 'Kundendimension, SCD Typ 2: 1 Zeile = 1 Version eines Kunden. Ohne Straße, Telefon und E-Mail (DSGVO, R-03).';
COMMENT ON COLUMN dwh.dim_kunde.kunde_sk    IS 'PK: Surrogatschlüssel (IDENTITY). Zeile -1 = UNBEKANNT (E-04, E-21)';
COMMENT ON COLUMN dwh.dim_kunde.kunden_nr   IS 'Business Key aus kunden.csv, vereinheitlicht (upper, strip)';
COMMENT ON COLUMN dwh.dim_kunde.kundentyp   IS 'Gewerbe oder Privat (Mapping aus G/P/gewerbe/privat); Unbekannt nur für Zeile -1';
COMMENT ON COLUMN dwh.dim_kunde.firma       IS 'Firmenname, nur bei Gewerbekunden';
COMMENT ON COLUMN dwh.dim_kunde.vorname     IS 'Vorname (für F-02 Top-10); darf leer sein (Nr 16)';
COMMENT ON COLUMN dwh.dim_kunde.nachname    IS 'Nachname (für F-02 Top-10)';
COMMENT ON COLUMN dwh.dim_kunde.plz         IS 'Postleitzahl, 5 Ziffern als Text (führende Null bleibt). Historisiert';
COMMENT ON COLUMN dwh.dim_kunde.ort         IS 'Ort, offizielle Schreibweise nach Mapping (Nr 4, 5). Historisiert';
COMMENT ON COLUMN dwh.dim_kunde.bundesland  IS 'Bundesland, aus der PLZ abgeleitet (E-09). Historisiert';
COMMENT ON COLUMN dwh.dim_kunde.erstellt_am IS 'Anlagedatum des Kunden in der Quelle; normales Attribut, nicht der Versionsbeginn (E-14)';
COMMENT ON COLUMN dwh.dim_kunde.gueltig_von IS 'SCD 2: Beginn der Version. Erste Version ab 1900-01-01 (E-14)';
COMMENT ON COLUMN dwh.dim_kunde.gueltig_bis IS 'SCD 2: Ende der Version (inklusive). Aktuelle Version: 9999-12-31 (E-14)';
COMMENT ON COLUMN dwh.dim_kunde.ist_aktuell IS 'SCD 2: TRUE genau bei der aktuellen Version';

-- Zeile -1 'UNBEKANNT' (E-04). IDENTITY ist ALWAYS, deshalb ist der feste
-- Wert -1 nur mit OVERRIDING SYSTEM VALUE möglich (E-21). Der Zähler beginnt
-- bei 1, -1 kann also nie mit einem echten Kunden kollidieren.
INSERT INTO dwh.dim_kunde
       (kunde_sk, kunden_nr, kundentyp, ort, bundesland,
        gueltig_von, gueltig_bis, ist_aktuell)
OVERRIDING SYSTEM VALUE
VALUES (-1, 'UNBEKANNT', 'Unbekannt', 'Unbekannt', 'Unbekannt',
        DATE '1900-01-01', DATE '9999-12-31', TRUE);


-- ------------------------------------------------------------------------
-- 3. dwh.dim_produkt
--    Flache Hierarchie: kategorie und unterkategorie in derselben Tabelle (E-16)
-- ------------------------------------------------------------------------
CREATE TABLE dwh.dim_produkt (
    produkt_sk      INTEGER GENERATED ALWAYS AS IDENTITY,
    artikel_nr      TEXT          NOT NULL,
    bezeichnung     TEXT          NOT NULL,
    kategorie       TEXT          NOT NULL,
    unterkategorie  TEXT          NOT NULL,
    einheit         TEXT          NOT NULL,
    listenpreis     NUMERIC(12,2),
    lieferant       TEXT,
    lieferant_land  TEXT,
    aktiv           BOOLEAN       NOT NULL,

    CONSTRAINT pk_dim_produkt            PRIMARY KEY (produkt_sk),
    CONSTRAINT uq_dim_produkt_artikel_nr UNIQUE (artikel_nr),
    -- Artikelnummer vereinheitlicht: 'A-005' (Nr 19, 36)
    CONSTRAINT ck_dim_produkt_artikel_nr CHECK (artikel_nr ~ '^A-[0-9]{3}$'),
    CONSTRAINT ck_dim_produkt_listenpreis CHECK (listenpreis >= 0),
    -- Land als ISO-Code 'DE' statt Deutschland/Germany (Nr 27)
    CONSTRAINT ck_dim_produkt_land CHECK (lieferant_land ~ '^[A-Z]{2}$')
);

COMMENT ON TABLE  dwh.dim_produkt                IS 'Produktdimension: 1 Zeile = 1 Artikel. Kategorie und Lieferant flach in derselben Tabelle (Star, E-16).';
COMMENT ON COLUMN dwh.dim_produkt.produkt_sk     IS 'PK: Surrogatschlüssel (IDENTITY). Keine Zeile -1: Positionen mit unbekanntem Produkt gehen nach rejected (Nr 37)';
COMMENT ON COLUMN dwh.dim_produkt.artikel_nr     IS 'Business Key aus produkte.json, vereinheitlicht auf A-999';
COMMENT ON COLUMN dwh.dim_produkt.bezeichnung    IS 'Produktbezeichnung';
COMMENT ON COLUMN dwh.dim_produkt.kategorie      IS 'Hauptkategorie (Quelle: kategorie.haupt)';
COMMENT ON COLUMN dwh.dim_produkt.unterkategorie IS 'Unterkategorie (Quelle: kategorie.unter)';
COMMENT ON COLUMN dwh.dim_produkt.einheit        IS 'Verkaufseinheit nach Mapping (l/ltr/Liter -> L usw., Nr 23)';
COMMENT ON COLUMN dwh.dim_produkt.listenpreis    IS 'Empfohlener Preis aus dem Artikelstamm (Attribut, kein Fakt). NULL bei 4 Artikeln (E-07)';
COMMENT ON COLUMN dwh.dim_produkt.lieferant      IS 'Name des Lieferanten; NULL, wenn in der Quelle das Feld fehlt (Nr 26)';
COMMENT ON COLUMN dwh.dim_produkt.lieferant_land IS 'Land des Lieferanten als ISO-Code, z. B. DE';
COMMENT ON COLUMN dwh.dim_produkt.aktiv          IS 'Artikel aktiv (true/1/ja -> TRUE, Nr 24)';


-- ------------------------------------------------------------------------
-- 4. dwh.dim_zahlung  (statisch, 4 Werte nach F-06, feste Schlüssel E-21)
-- ------------------------------------------------------------------------
CREATE TABLE dwh.dim_zahlung (
    zahlung_sk   SMALLINT NOT NULL,
    zahlungsart  TEXT     NOT NULL,

    CONSTRAINT pk_dim_zahlung             PRIMARY KEY (zahlung_sk),
    CONSTRAINT uq_dim_zahlung_zahlungsart UNIQUE (zahlungsart),
    CONSTRAINT ck_dim_zahlung_zahlungsart CHECK (zahlungsart IN ('Rechnung', 'Lastschrift', 'Bar', 'Vorkasse'))
);

COMMENT ON TABLE  dwh.dim_zahlung             IS 'Zahlungsart: 1 Zeile = 1 Zahlungsart. Statisch, 4 Zeilen, hier fest eingefügt (E-21).';
COMMENT ON COLUMN dwh.dim_zahlung.zahlung_sk  IS 'PK: fester Schlüssel 1 bis 4 (kein IDENTITY, E-21)';
COMMENT ON COLUMN dwh.dim_zahlung.zahlungsart IS 'Rechnung, Lastschrift, Bar oder Vorkasse (9 Schreibweisen in der Quelle, Nr 44)';

INSERT INTO dwh.dim_zahlung (zahlung_sk, zahlungsart) VALUES
    (1, 'Rechnung'),
    (2, 'Lastschrift'),
    (3, 'Bar'),
    (4, 'Vorkasse');


-- ------------------------------------------------------------------------
-- 5. dwh.dim_status  (Junk Dimension, E-18; ersetzt E-12)
--    4 Lieferstatus x 2 Werte des Kennzeichens = 8 Zeilen, alle vorab
-- ------------------------------------------------------------------------
CREATE TABLE dwh.dim_status (
    status_sk              SMALLINT NOT NULL,
    lieferstatus           TEXT     NOT NULL,
    preis_aus_listenpreis  BOOLEAN  NOT NULL,

    CONSTRAINT pk_dim_status             PRIMARY KEY (status_sk),
    CONSTRAINT uq_dim_status_kombination UNIQUE (lieferstatus, preis_aus_listenpreis),
    CONSTRAINT ck_dim_status_lieferstatus CHECK (lieferstatus IN ('geliefert', 'teilgeliefert', 'offen', 'storniert'))
);

COMMENT ON TABLE  dwh.dim_status                       IS 'Junk Dimension: Status und Kennzeichen der Position, die zu keiner echten Dimension gehören (E-18). Alle 8 Kombinationen fest eingefügt.';
COMMENT ON COLUMN dwh.dim_status.status_sk             IS 'PK: fester Schlüssel 1 bis 8 (kein IDENTITY, E-21). Keine Zeile -1 (E-18)';
COMMENT ON COLUMN dwh.dim_status.lieferstatus          IS 'geliefert, teilgeliefert, offen oder storniert (6 Schreibweisen in der Quelle, lower(), Nr 45). Filter für E-13';
COMMENT ON COLUMN dwh.dim_status.preis_aus_listenpreis IS 'TRUE, wenn der Einzelpreis fehlte und aus dem Listenpreis übernommen wurde (E-07)';

INSERT INTO dwh.dim_status (status_sk, lieferstatus, preis_aus_listenpreis) VALUES
    (1, 'geliefert',     FALSE),
    (2, 'geliefert',     TRUE),
    (3, 'teilgeliefert', FALSE),
    (4, 'teilgeliefert', TRUE),
    (5, 'offen',         FALSE),
    (6, 'offen',         TRUE),
    (7, 'storniert',     FALSE),
    (8, 'storniert',     TRUE);


-- ------------------------------------------------------------------------
-- 6. dwh.fact_verkauf  (Grain E-01: 1 Zeile = 1 Bestellposition)
--    PK = Degenerate Dimensions (bestell_nr, position), E-20
--    umsatz_brutto / rabatt_betrag / umsatz_netto werden von der Datenbank
--    berechnet (GENERATED ... STORED, E-19). Das ETL schreibt sie NICHT.
--    Achtung PostgreSQL 18: Ohne STORED wäre die Spalte VIRTUAL (neuer
--    Standard in PG 18). STORED steht deshalb ausdrücklich da.
-- ------------------------------------------------------------------------
CREATE TABLE dwh.fact_verkauf (
    bestell_nr      INTEGER       NOT NULL,
    position        SMALLINT      NOT NULL,
    datum_sk        INTEGER       NOT NULL,
    kunde_sk        INTEGER       NOT NULL,
    produkt_sk      INTEGER       NOT NULL,
    zahlung_sk      SMALLINT      NOT NULL,
    status_sk       SMALLINT      NOT NULL,
    menge           INTEGER       NOT NULL,
    einzelpreis     NUMERIC(12,2) NOT NULL,
    rabatt_prozent  NUMERIC(5,2)  NOT NULL,
    umsatz_brutto   NUMERIC(14,2) GENERATED ALWAYS AS
                        (ROUND(menge * einzelpreis, 2)) STORED,
    rabatt_betrag   NUMERIC(14,2) GENERATED ALWAYS AS
                        (ROUND(menge * einzelpreis * rabatt_prozent / 100, 2)) STORED,
    umsatz_netto    NUMERIC(14,2) GENERATED ALWAYS AS
                        (ROUND(menge * einzelpreis, 2)
                         - ROUND(menge * einzelpreis * rabatt_prozent / 100, 2)) STORED,

    -- Der Grain wird von der Datenbank selbst geschützt (E-20)
    CONSTRAINT pk_fact_verkauf PRIMARY KEY (bestell_nr, position),

    CONSTRAINT fk_fact_verkauf_datum   FOREIGN KEY (datum_sk)   REFERENCES dwh.dim_datum   (datum_sk),
    CONSTRAINT fk_fact_verkauf_kunde   FOREIGN KEY (kunde_sk)   REFERENCES dwh.dim_kunde   (kunde_sk),
    CONSTRAINT fk_fact_verkauf_produkt FOREIGN KEY (produkt_sk) REFERENCES dwh.dim_produkt (produkt_sk),
    CONSTRAINT fk_fact_verkauf_zahlung FOREIGN KEY (zahlung_sk) REFERENCES dwh.dim_zahlung (zahlung_sk),
    CONSTRAINT fk_fact_verkauf_status  FOREIGN KEY (status_sk)  REFERENCES dwh.dim_status  (status_sk),

    CONSTRAINT ck_fact_verkauf_position    CHECK (position > 0),
    -- Menge <= 0 geht nach rejected (E-05), darf also nie ankommen
    CONSTRAINT ck_fact_verkauf_menge       CHECK (menge > 0),
    CONSTRAINT ck_fact_verkauf_einzelpreis CHECK (einzelpreis >= 0),
    CONSTRAINT ck_fact_verkauf_rabatt      CHECK (rabatt_prozent BETWEEN 0 AND 100)
);

-- PostgreSQL legt für Fremdschlüssel KEINEN Index automatisch an.
-- Indizes auf die großen Dimensionen beschleunigen die JOINs in F-01 bis F-07.
-- (dim_zahlung und dim_status haben nur 4 bzw. 8 Zeilen: kein Index nötig.)
CREATE INDEX ix_fact_verkauf_datum   ON dwh.fact_verkauf (datum_sk);
CREATE INDEX ix_fact_verkauf_kunde   ON dwh.fact_verkauf (kunde_sk);
CREATE INDEX ix_fact_verkauf_produkt ON dwh.fact_verkauf (produkt_sk);

COMMENT ON TABLE  dwh.fact_verkauf                IS 'Faktentabelle Verkauf. Geschäftsprozess: Verkauf (E-19). Grain: 1 Zeile = 1 Bestellposition (E-01). Nur Schlüssel und Messwerte.';
COMMENT ON COLUMN dwh.fact_verkauf.bestell_nr     IS 'PK-Teil, Degenerate Dimension: Bestellnummer aus der Quelle (Rückverfolgung)';
COMMENT ON COLUMN dwh.fact_verkauf.position       IS 'PK-Teil, Degenerate Dimension: Positionsnummer innerhalb der Bestellung';
COMMENT ON COLUMN dwh.fact_verkauf.datum_sk       IS 'FK -> dim_datum: Bestelldatum (Kopfdatum der Bestellung, E-03)';
COMMENT ON COLUMN dwh.fact_verkauf.kunde_sk       IS 'FK -> dim_kunde: Kundenversion zum Bestelldatum (SCD 2). -1 = UNBEKANNT (E-04)';
COMMENT ON COLUMN dwh.fact_verkauf.produkt_sk     IS 'FK -> dim_produkt';
COMMENT ON COLUMN dwh.fact_verkauf.zahlung_sk     IS 'FK -> dim_zahlung: Zahlungsart der Bestellung (E-03)';
COMMENT ON COLUMN dwh.fact_verkauf.status_sk      IS 'FK -> dim_status: Lieferstatus + Kennzeichen preis_aus_listenpreis (E-18)';
COMMENT ON COLUMN dwh.fact_verkauf.menge          IS 'Messwert, additiv: bestellte Menge (> 0, E-05)';
COMMENT ON COLUMN dwh.fact_verkauf.einzelpreis    IS 'Messwert, NICHT additiv: Verkaufspreis je Einheit zum Bestellzeitpunkt. Fehlend -> Listenpreis (E-07)';
COMMENT ON COLUMN dwh.fact_verkauf.rabatt_prozent IS 'Messwert, NICHT additiv: Rabatt in Prozent. Leer -> 0 (E-08). Durchschnitt = SUM(rabatt_betrag) / SUM(umsatz_brutto)';
COMMENT ON COLUMN dwh.fact_verkauf.umsatz_brutto  IS 'Messwert, additiv, berechnet: ROUND(menge * einzelpreis, 2) (E-19)';
COMMENT ON COLUMN dwh.fact_verkauf.rabatt_betrag  IS 'Messwert, additiv, berechnet: ROUND(menge * einzelpreis * rabatt_prozent / 100, 2) (E-19)';
COMMENT ON COLUMN dwh.fact_verkauf.umsatz_netto   IS 'Messwert, additiv, berechnet: umsatz_brutto - rabatt_betrag (E-19). Grundlage für F-01 bis F-04';

COMMIT;


-- ########################################################################
-- TEIL 2: Kontrollen (nach dem COMMIT, jede einzeln markieren -> F5)
-- ########################################################################

-- ------------------------------------------------------------------------
-- Kontrolle 1: Spaltenzahl Soll/Ist
-- Soll: 6 Zeilen, alle 'OK'
-- ------------------------------------------------------------------------
SELECT s.tabelle,
       s.soll_spalten,
       COUNT(c.column_name) AS ist_spalten,
       CASE WHEN COUNT(c.column_name) = s.soll_spalten THEN 'OK' ELSE 'FEHLER' END AS pruefung
FROM (VALUES
        ('dim_datum',    10),
        ('dim_kunde',    13),
        ('dim_produkt',  10),
        ('dim_zahlung',   2),
        ('dim_status',    3),
        ('fact_verkauf', 13)
     ) AS s(tabelle, soll_spalten)
LEFT JOIN information_schema.columns AS c
       ON c.table_schema = 'dwh'
      AND c.table_name   = s.tabelle
GROUP BY s.tabelle, s.soll_spalten
ORDER BY s.tabelle;


-- ------------------------------------------------------------------------
-- Kontrolle 2: Zeilenzahl Soll/Ist direkt nach dem Anlegen
-- Soll: dim_kunde 1 (nur -1), dim_zahlung 4, dim_status 8, Rest 0
-- ------------------------------------------------------------------------
SELECT t.tabelle, t.soll, t.ist,
       CASE WHEN t.soll = t.ist THEN 'OK' ELSE 'FEHLER' END AS pruefung
FROM (
    SELECT 'dim_datum'    AS tabelle, 0 AS soll, (SELECT COUNT(*) FROM dwh.dim_datum)    AS ist
    UNION ALL
    SELECT 'dim_kunde',    1, (SELECT COUNT(*) FROM dwh.dim_kunde)
    UNION ALL
    SELECT 'dim_produkt',  0, (SELECT COUNT(*) FROM dwh.dim_produkt)
    UNION ALL
    SELECT 'dim_zahlung',  4, (SELECT COUNT(*) FROM dwh.dim_zahlung)
    UNION ALL
    SELECT 'dim_status',   8, (SELECT COUNT(*) FROM dwh.dim_status)
    UNION ALL
    SELECT 'fact_verkauf', 0, (SELECT COUNT(*) FROM dwh.fact_verkauf)
) AS t
ORDER BY t.tabelle;


-- ------------------------------------------------------------------------
-- Kontrolle 3: Data Dictionary vollständig?
-- Soll: 0 Zeilen (jede Tabelle und jede Spalte hat einen Kommentar)
-- ------------------------------------------------------------------------
SELECT c.table_name, c.column_name, 'Spalte ohne Kommentar' AS problem
FROM information_schema.columns AS c
WHERE c.table_schema = 'dwh'
  AND col_description(format('%I.%I', c.table_schema, c.table_name)::regclass,
                      c.ordinal_position) IS NULL
UNION ALL
SELECT t.table_name, NULL, 'Tabelle ohne Kommentar'
FROM information_schema.tables AS t
WHERE t.table_schema = 'dwh'
  AND obj_description(format('%I.%I', t.table_schema, t.table_name)::regclass,
                      'pg_class') IS NULL;


-- ------------------------------------------------------------------------
-- Kontrolle 4: Fremdschlüssel der Faktentabelle
-- Soll: 5 Zeilen (datum, kunde, produkt, zahlung, status)
-- ------------------------------------------------------------------------
SELECT conname                    AS constraint_name,
       pg_get_constraintdef(oid)  AS definition
FROM pg_constraint
WHERE conrelid = 'dwh.fact_verkauf'::regclass
  AND contype  = 'f'
ORDER BY conname;


-- ------------------------------------------------------------------------
-- Kontrolle 5: Constraint-Test
-- Jeder Test versucht absichtlich, eine Regel zu brechen.
-- Erwartet: 7x '[OK]' im Reiter "Messages" von pgAdmin.
-- Es bleibt NICHTS in der Datenbank: Jeder Versuch läuft in einem eigenen
-- Unterblock und wird bei Fehler zurückgerollt. Kommt ein Insert unerwartet
-- durch, löst RAISE EXCEPTION ebenfalls den Rollback aus.
-- Tests 4 und 5 nutzen feste negative Schlüssel mit OVERRIDING SYSTEM VALUE,
-- damit der IDENTITY-Zähler nicht verbraucht wird.
-- ------------------------------------------------------------------------
DO $$
BEGIN
    -- Test 1: gleiche Kombination in der Junk Dimension
    BEGIN
        INSERT INTO dwh.dim_status VALUES (9, 'geliefert', FALSE);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN unique_violation THEN RAISE NOTICE '[OK]         Test 1: UNIQUE (lieferstatus, preis_aus_listenpreis) greift';
        WHEN raise_exception  THEN RAISE NOTICE '[UNERWARTET] Test 1: doppelte Kombination wurde angenommen';
    END;

    -- Test 2: unbekannter Lieferstatus
    BEGIN
        INSERT INTO dwh.dim_status VALUES (9, 'interessiert', FALSE);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN check_violation THEN RAISE NOTICE '[OK]         Test 2: CHECK lieferstatus greift';
        WHEN raise_exception THEN RAISE NOTICE '[UNERWARTET] Test 2: Status interessiert wurde angenommen';
    END;

    -- Test 3: eigener Wert in einer IDENTITY-ALWAYS-Spalte (ohne OVERRIDING)
    BEGIN
        INSERT INTO dwh.dim_kunde (kunde_sk, kunden_nr, kundentyp, gueltig_von, gueltig_bis, ist_aktuell)
        VALUES (5, 'K0005', 'Privat', DATE '1900-01-01', DATE '9999-12-31', TRUE);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN generated_always THEN RAISE NOTICE '[OK]         Test 3: GENERATED ALWAYS schützt kunde_sk';
        WHEN raise_exception  THEN RAISE NOTICE '[UNERWARTET] Test 3: eigener kunde_sk wurde angenommen';
    END;

    -- Test 4: Kundennummer nicht vereinheitlicht (Kleinbuchstabe, Nr 34)
    BEGIN
        INSERT INTO dwh.dim_kunde (kunde_sk, kunden_nr, kundentyp, gueltig_von, gueltig_bis, ist_aktuell)
        OVERRIDING SYSTEM VALUE
        VALUES (-2, 'k0040', 'Privat', DATE '1900-01-01', DATE '9999-12-31', TRUE);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN check_violation THEN RAISE NOTICE '[OK]         Test 4: CHECK kunden_nr (nur K + 4 Ziffern) greift';
        WHEN raise_exception THEN RAISE NOTICE '[UNERWARTET] Test 4: k0040 wurde angenommen';
    END;

    -- Test 5: SCD-2-Regel verletzt (aktuell, aber gueltig_bis nicht 9999-12-31)
    BEGIN
        INSERT INTO dwh.dim_kunde (kunde_sk, kunden_nr, kundentyp, gueltig_von, gueltig_bis, ist_aktuell)
        OVERRIDING SYSTEM VALUE
        VALUES (-3, 'K0040', 'Privat', DATE '1900-01-01', DATE '2025-12-31', TRUE);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN check_violation THEN RAISE NOTICE '[OK]         Test 5: CHECK ist_aktuell <-> 9999-12-31 greift';
        WHEN raise_exception THEN RAISE NOTICE '[UNERWARTET] Test 5: falsche SCD-2-Version wurde angenommen';
    END;

    -- Test 6: Menge 0 in der Faktentabelle (E-05)
    -- (CHECK wird vor den Fremdschlüsseln geprüft, deshalb check_violation)
    BEGIN
        INSERT INTO dwh.fact_verkauf
               (bestell_nr, position, datum_sk, kunde_sk, produkt_sk, zahlung_sk, status_sk,
                menge, einzelpreis, rabatt_prozent)
        VALUES (1, 1, 20250101, -1, 1, 1, 1, 0, 10.00, 0);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN check_violation THEN RAISE NOTICE '[OK]         Test 6: CHECK menge > 0 greift';
        WHEN raise_exception THEN RAISE NOTICE '[UNERWARTET] Test 6: Menge 0 wurde angenommen';
    END;

    -- Test 7: Fakt ohne Dimensionspartner (dim_datum und dim_produkt sind noch leer)
    BEGIN
        INSERT INTO dwh.fact_verkauf
               (bestell_nr, position, datum_sk, kunde_sk, produkt_sk, zahlung_sk, status_sk,
                menge, einzelpreis, rabatt_prozent)
        VALUES (1, 1, 20250101, -1, 1, 1, 1, 5, 10.00, 0);
        RAISE EXCEPTION 'durchgekommen';
    EXCEPTION
        WHEN foreign_key_violation THEN RAISE NOTICE '[OK]         Test 7: Fremdschlüssel greift (Partner fehlt)';
        WHEN raise_exception       THEN RAISE NOTICE '[UNERWARTET] Test 7: Fakt ohne Dimensionspartner wurde angenommen';
    END;
END
$$;


-- ------------------------------------------------------------------------
-- Kontrolle 6: Ist nach dem Test alles wie vorher?
-- Soll: wieder dim_kunde 1, dim_status 8, fact_verkauf 0
--       (Kontrolle 2 noch einmal ausführen)
-- ------------------------------------------------------------------------
