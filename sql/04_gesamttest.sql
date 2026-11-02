-- ========================================================================
-- sql/04_gesamttest.sql
-- Gesamttest des DWH in SQL, unabhängig vom Python-Ladeskript (E-35)
--
-- Zweck      : Zweite, unabhängige Prüfung nach dem Laden. Liest nur (eine einzige
--              SELECT-Abfrage), ändert nichts und kann jederzeit laufen.
-- Eingabe    : stg.bestellungen, dwh.fact_verkauf, dwh.dim_datum, dwh.dim_kunde,
--              dwh.dim_status, dwh.dim_zahlung, protokoll.abgewiesene_position (E-42)
-- Ausgabe    : eine Tabelle: nr, art, pruefung, soll, ist, ergebnis, reaktion, rolle
-- Anforderung: Q-01 (roh = Fakten + rejected + Dubletten), Q-03 Referenzen,
--              E-19 berechnete Spalten, E-14/E-31 SCD 2, F-01 Zeitraum
-- Bezug      : E-35 (Gesamttest mit Reaktion), E-36 (Gesamtlauf), E-42, etl/05_lade_fakten.py
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/04_gesamttest.sql
--              oder: als letzter Schritt von etl/00_starte_gesamtlauf.py
--              Erwartet: jede Zeile ergebnis = 'OK'.
--
-- Zwei Arten von Zeilen:
--   R = Regel, gilt bei ALLEN Daten. 'FEHLER' -> reaktion 'Abbruch':
--       Der Gesamtlauf bricht ab, das Daten-Team muss den Fehler finden.
--   S = dokumentierter Stand vom 14.10.2026 (nach Bereinigung und Laden).
--       Ändern sich die Rohdaten, ändern sich diese Zahlen. 'FEHLER' -> 'Warnung':
--       Die Rolle prüft den Inhalt, es ist kein Ladefehler.
-- Q-01 genau (mit der echten rejected-Datei) prüft etl/05_lade_fakten.py (C1).
-- Hier wird rejected aus stg und dwh abgeleitet: roh - Dubletten - Fakten.
-- ========================================================================
WITH
roh AS (
    SELECT COUNT(*) AS n FROM stg.bestellungen
),
-- Dubletten wie in explore/01_explore.py: exakt gleiche Zeilen (alle Fachspalten).
-- Warum ohne _source_file/_loaded_at: Diese technischen Spalten sind bei Kopien gleich,
-- würden aber eine neue Spalte im Staging still mitzählen.
ohne_dubletten AS (
    SELECT COUNT(*) AS n FROM (
        SELECT DISTINCT bestell_nr, position, bestelldatum, kunden_nr, artikel_nr, menge,
                        einzelpreis, rabatt_prozent, zahlungsart, lieferstatus
        FROM stg.bestellungen) x
),
f AS (
    SELECT f.*, d.datum, s.lieferstatus, s.preis_aus_listenpreis, z.zahlungsart
    FROM dwh.fact_verkauf f
    JOIN dwh.dim_datum   d ON d.datum_sk   = f.datum_sk
    JOIN dwh.dim_status  s ON s.status_sk  = f.status_sk
    JOIN dwh.dim_zahlung z ON z.zahlung_sk = f.zahlung_sk
),
pruefungen (nr, art, pruefung, soll, ist, rolle) AS (
    -- ---------- R: Regeln -------------------------------------------------
    SELECT 'R1', 'R', 'Menge <= 0 (E-05)', 0::numeric, (SELECT COUNT(*) FROM f WHERE menge <= 0)::numeric, 'Daten-Team'
    UNION ALL
    SELECT 'R2', 'R', 'Rabatt außerhalb 0-100 (E-29)', 0, (SELECT COUNT(*) FROM f WHERE rabatt_prozent NOT BETWEEN 0 AND 100), 'Daten-Team'
    UNION ALL
    SELECT 'R3', 'R', 'Einzelpreis < 0 (E-29)', 0, (SELECT COUNT(*) FROM f WHERE einzelpreis < 0), 'Daten-Team'
    UNION ALL
    SELECT 'R4', 'R', 'Datum nach Export 2026-01-05 (Nr 31)', 0, (SELECT COUNT(*) FROM f WHERE datum > DATE '2026-01-05'), 'Daten-Team'
    UNION ALL
    -- Netto = Brutto - Rabatt pro Zeile (E-19). Die DB rechnet es selbst; die Prüfung zeigt, dass niemand
    -- die Formel geändert hat.
    SELECT 'R5', 'R', 'umsatz_netto <> brutto - rabatt_betrag', 0,
           (SELECT COUNT(*) FROM f WHERE umsatz_netto <> umsatz_brutto - rabatt_betrag), 'Controlling'
    UNION ALL
    -- SCD 2 (E-14, E-31): Das Bestelldatum liegt in der Gültigkeit der zugeordneten Kundenversion
    SELECT 'R6', 'R', 'Kundenversion passt nicht zum Bestelldatum', 0,
           (SELECT COUNT(*) FROM f JOIN dwh.dim_kunde k ON k.kunde_sk = f.kunde_sk
            WHERE f.datum NOT BETWEEN k.gueltig_von AND k.gueltig_bis), 'Daten-Team'
    UNION ALL
    SELECT 'R7', 'R', 'Kunden ohne genau 1 aktuelle Version', 0,
           (SELECT COUNT(*) FROM (SELECT kunden_nr FROM dwh.dim_kunde GROUP BY kunden_nr
                                  HAVING COUNT(*) FILTER (WHERE ist_aktuell) <> 1) x), 'Daten-Team'
    UNION ALL
    -- Q-01 als Gleichung mit abgeleitetem rejected: muss >= 0 sein, sonst gäbe es mehr Fakten als Zeilen
    SELECT 'R8', 'R', 'abgeleitete rejected < 0 (mehr Fakten als Rohzeilen)', 0,
           (SELECT CASE WHEN (SELECT n FROM ohne_dubletten) - (SELECT COUNT(*) FROM f) < 0 THEN 1 ELSE 0 END), 'Daten-Team'
    UNION ALL
    -- Q-01 von der Datenbank-Seite (E-42): Die Protokolltabelle enthält genau die Zeilen, die nach
    -- dem Entfernen der Dubletten NICHT in fact_verkauf stehen. Erwartet gleich, sonst Abbruch.
    SELECT 'R9', 'R', 'Protokolltabelle = roh - Dubletten - Fakten',
           (SELECT n FROM ohne_dubletten) - (SELECT COUNT(*) FROM f),
           (SELECT COUNT(*) FROM protokoll.abgewiesene_position), 'Daten-Team'

    -- ---------- S: Stand 14.10.2026 ---------------------------------------
    UNION ALL SELECT 'S1',  'S', 'stg.bestellungen roh',                2181,       (SELECT n FROM roh), 'Daten-Team'
    UNION ALL SELECT 'S2',  'S', 'exakte Dubletten (O-05)',             25,         (SELECT n FROM roh) - (SELECT n FROM ohne_dubletten), 'Daten-Team'
    UNION ALL SELECT 'S3',  'S', 'Zeilen fact_verkauf',                 2081,       (SELECT COUNT(*) FROM f), 'Daten-Team'
    UNION ALL SELECT 'S4',  'S', 'rejected abgeleitet (roh - Dubletten - Fakten)', 75,
                                 (SELECT n FROM ohne_dubletten) - (SELECT COUNT(*) FROM f), 'Daten-Team'
    UNION ALL SELECT 'S5',  'S', 'Bestellungen',                        696,        (SELECT COUNT(DISTINCT bestell_nr) FROM f), 'Daten-Team'
    UNION ALL SELECT 'S6',  'S', 'SUM(menge)',                          1272280,    (SELECT SUM(menge) FROM f), 'Controlling'
    UNION ALL SELECT 'S7',  'S', 'SUM(umsatz_brutto)',                  2643822.71, (SELECT SUM(umsatz_brutto) FROM f), 'Controlling'
    UNION ALL SELECT 'S8',  'S', 'SUM(rabatt_betrag)',                  61058.56,   (SELECT SUM(rabatt_betrag) FROM f), 'Controlling'
    UNION ALL SELECT 'S9',  'S', 'SUM(umsatz_netto)',                   2582764.15, (SELECT SUM(umsatz_netto) FROM f), 'Controlling'
    UNION ALL SELECT 'S10', 'S', 'Positionen auf Kunde -1',             71,         (SELECT COUNT(*) FROM f WHERE kunde_sk = -1), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S11', 'S', 'preis_aus_listenpreis = TRUE',        49,         (SELECT COUNT(*) FROM f WHERE preis_aus_listenpreis), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S12', 'S', 'Lieferstatus geliefert',              1050,       (SELECT COUNT(*) FROM f WHERE lieferstatus = 'geliefert'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S13', 'S', 'Lieferstatus offen',                  355,        (SELECT COUNT(*) FROM f WHERE lieferstatus = 'offen'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S14', 'S', 'Lieferstatus storniert',              340,        (SELECT COUNT(*) FROM f WHERE lieferstatus = 'storniert'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S15', 'S', 'Lieferstatus teilgeliefert',          336,        (SELECT COUNT(*) FROM f WHERE lieferstatus = 'teilgeliefert'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S16', 'S', 'Zahlungsart Rechnung',                778,        (SELECT COUNT(*) FROM f WHERE zahlungsart = 'Rechnung'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S17', 'S', 'Zahlungsart Lastschrift',             695,        (SELECT COUNT(*) FROM f WHERE zahlungsart = 'Lastschrift'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S18', 'S', 'Zahlungsart Bar',                     433,        (SELECT COUNT(*) FROM f WHERE zahlungsart = 'Bar'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S19', 'S', 'Zahlungsart Vorkasse',                175,        (SELECT COUNT(*) FROM f WHERE zahlungsart = 'Vorkasse'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S20', 'S', 'Positionen außerhalb F-01 (2024-2025)', 0,
                                 (SELECT COUNT(*) FROM f WHERE datum NOT BETWEEN DATE '2024-01-01' AND DATE '2025-12-31'), 'Fachbereich Vertrieb'
)
SELECT nr, art, pruefung, soll, ist,
       CASE WHEN soll = ist THEN 'OK' ELSE 'FEHLER' END            AS ergebnis,
       CASE WHEN art = 'R' THEN 'Abbruch' ELSE 'Warnung' END        AS reaktion,
       rolle
FROM pruefungen
ORDER BY art, length(nr), nr;
