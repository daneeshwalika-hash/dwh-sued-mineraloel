-- ========================================================================
-- sql/05b_kontrolle_mart.sql
-- Kontrolle der mart-Views F-01 bis F-08 und Datenqualität (nur lesen)
--
-- Zweck      : Beweist, dass die Antworten auf F-01 bis F-08 zur Faktentabelle passen:
--              jede View läuft, Summenprobe, Plausibilität. Ändert nichts.
-- Eingabe    : mart.v_f01_ ... mart.v_f07_ (aus sql/05_create_mart.sql),
--              mart.v_f08_wiederholungskunden (aus sql/05c_create_mart_f08.sql),
--              mart.v_dq_abgewiesene_zeilen_grund (aus sql/06b_create_mart_dq.sql),
--              protokoll.abgewiesene_position, dwh.fact_verkauf,
--              dwh.dim_status, dwh.dim_kunde
-- Ausgabe    : eine Tabelle: nr, art, pruefung, soll, ist, ergebnis, reaktion, rolle
-- Anforderung: F-01 bis F-08, Q-04 nachvollziehbar, Aggregation mit Filter (HAVING, F-08)
-- Bezug      : E-13, E-19, E-27, E-35 (Prüfung mit Reaktion), E-37, E-39, E-40, E-42
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/05b_kontrolle_mart.sql
--              oder: Schritt 7 von etl/00_starte_gesamtlauf.py
--              Erwartet: jede Zeile ergebnis = 'OK'.
--              Fehlt eine View (05_create_mart.sql nicht ausgeführt), bricht die Abfrage
--              mit "relation ... does not exist" ab -> der Gesamtlauf stoppt in Schritt 7.
--
-- Wie in sql/04_gesamttest.sql:
--   R = Regel, gilt bei ALLEN Daten. Das Soll wird hier direkt aus dwh.fact_verkauf
--       berechnet (zweiter Weg). 'FEHLER' -> 'Abbruch', das Daten-Team prüft die View.
--   S = dokumentierter Stand vom 14.10.2026 (S1-S10) und vom 19.10.2026 (S11-S14;
--       Ergebnisse in docs/ergebnisse/ergebnisse.md und docs/protokoll.md).
--       'FEHLER' -> 'Warnung': Der Inhalt hat sich geändert, die Rolle prüft ihn.
-- ========================================================================
WITH
-- Zweiter Weg: Auftragsumsatz direkt aus der Faktentabelle, ohne View (E-13)
auftrag AS (
    SELECT SUM(f.umsatz_netto)          AS umsatz,
           COUNT(DISTINCT f.bestell_nr) AS bestellungen
    FROM dwh.fact_verkauf f
    JOIN dwh.dim_status s ON s.status_sk = f.status_sk
    WHERE s.lieferstatus <> 'storniert'
),
f05 AS (SELECT * FROM mart.v_f05_stornoquote),
pruefungen (nr, art, pruefung, soll, ist, rolle) AS (
    -- ---------- R: Summenprobe und Regeln ---------------------------------
    SELECT 'M1', 'R', 'Summenprobe F-01 = Auftragsumsatz', (SELECT umsatz FROM auftrag),
           (SELECT SUM(umsatz_netto) FROM mart.v_f01_umsatz_monat), 'Controlling'
    UNION ALL
    SELECT 'M2', 'R', 'Summenprobe F-03 = Auftragsumsatz', (SELECT umsatz FROM auftrag),
           (SELECT SUM(umsatz_netto) FROM mart.v_f03_umsatz_kategorie), 'Controlling'
    UNION ALL
    SELECT 'M3', 'R', 'Summenprobe F-04 = Auftragsumsatz', (SELECT umsatz FROM auftrag),
           (SELECT SUM(umsatz_netto) FROM mart.v_f04_umsatz_ort), 'Controlling'
    UNION ALL
    SELECT 'M4', 'R', 'Summenprobe F-06 = Auftragsumsatz', (SELECT umsatz FROM auftrag),
           (SELECT SUM(umsatz_netto) FROM mart.v_f06_zahlungsart), 'Controlling'
    UNION ALL
    -- Zahlungsart ist Attribut der Bestellung (E-03): Summe der Bestellungen über alle
    -- Zahlungsarten = Bestellungen insgesamt. Sonst wäre eine Bestellung doppelt gezählt.
    SELECT 'M5', 'R', 'F-06 Summe Bestellungen = Bestellungen ohne Storno', (SELECT bestellungen FROM auftrag),
           (SELECT SUM(bestellungen) FROM mart.v_f06_zahlungsart), 'Daten-Team'
    UNION ALL
    SELECT 'M6', 'R', 'F-02 enthält Kunde -1 / UNBEKANNT', 0,
           (SELECT COUNT(*) FROM mart.v_f02_top10_kunden WHERE kunden_nr = 'UNBEKANNT'), 'Daten-Team'
    UNION ALL
    -- Mit RANK() sind bei Gleichstand mehr als 10 Zeilen erlaubt, weniger als 10 nicht
    -- (es gibt mehr als 10 Kunden mit Umsatz).
    SELECT 'M7', 'R', 'F-02 weniger als 10 Zeilen', 0,
           (SELECT CASE WHEN COUNT(*) < 10 THEN 1 ELSE 0 END FROM mart.v_f02_top10_kunden), 'Daten-Team'
    UNION ALL
    SELECT 'M8', 'R', 'F-05 Anteile außerhalb 0-100', 0,
           (SELECT (anteil_positionen_storniert_prozent NOT BETWEEN 0 AND 100)::int
                 + (anteil_vollstaendig_geliefert_prozent NOT BETWEEN 0 AND 100)::int
                 + (anteil_bestellungen_voll_storniert_prozent NOT BETWEEN 0 AND 100)::int FROM f05), 'Daten-Team'
    UNION ALL
    -- F-07: eine Zeile pro Bestellung eines bekannten Kunden (zweiter Weg aus fact_verkauf)
    SELECT 'M9', 'R', 'F-07 Zeilen = Bestellungen ohne Kunde -1',
           (SELECT COUNT(DISTINCT bestell_nr) FROM dwh.fact_verkauf WHERE kunde_sk <> -1),
           (SELECT COUNT(*) FROM mart.v_f07_wohnort_bestellung), 'Daten-Team'
    UNION ALL
    -- F-07: "umgezogen" passt zu SCD 2: Umgezogen heißt, der Kunde hat mehr als eine Version
    SELECT 'M10', 'R', 'F-07 umgezogen ohne zweite Kundenversion', 0,
           (SELECT COUNT(*) FROM mart.v_f07_wohnort_bestellung v
            WHERE v.umgezogen
              AND (SELECT COUNT(*) FROM dwh.dim_kunde k WHERE k.kunden_nr = v.kunden_nr) < 2), 'Daten-Team'
    UNION ALL
    -- F-08 (E-40): Der HAVING-Filter wirkt. Erwartet 0 Kunden mit weniger als 2 Bestellungen.
    SELECT 'M11', 'R', 'F-08 Kunden mit weniger als 2 Bestellungen', 0,
           (SELECT COUNT(*) FROM mart.v_f08_wiederholungskunden WHERE bestellungen < 2), 'Daten-Team'
    UNION ALL
    -- F-08: zweiter Weg OHNE HAVING: Ein Kunde hat mindestens 2 Bestellungen genau dann,
    -- wenn seine kleinste und größte bestell_nr verschieden sind. Erwartet: gleiche Anzahl.
    SELECT 'M12', 'R', 'F-08 Zeilen = Kunden mit 2+ Bestellungen (zweiter Weg)',
           (SELECT COUNT(*)
            FROM (SELECT k.kunden_nr, MIN(f.bestell_nr) AS erste, MAX(f.bestell_nr) AS letzte
                  FROM dwh.fact_verkauf f
                  JOIN dwh.dim_kunde  k ON k.kunde_sk  = f.kunde_sk
                  JOIN dwh.dim_status s ON s.status_sk = f.status_sk
                  WHERE s.lieferstatus <> 'storniert' AND f.kunde_sk <> -1
                  GROUP BY k.kunden_nr) x
            WHERE x.erste <> x.letzte),
           (SELECT COUNT(*) FROM mart.v_f08_wiederholungskunden), 'Daten-Team'
    UNION ALL
    -- F-08: Spalte wiederholungskunden = Zeilen der View, Quote = Zeilen / Nenner.
    -- Erwartet 0 abweichende Zeilen. Fängt Mehrfachzählung durch den Join auf die aktuelle Version.
    SELECT 'M13', 'R', 'F-08 Quote passt nicht zu den Zeilen', 0,
           (SELECT COUNT(*) FROM mart.v_f08_wiederholungskunden v
            WHERE v.wiederholungskunden <> (SELECT COUNT(*) FROM mart.v_f08_wiederholungskunden)
               OR v.wiederkaufquote_prozent <> ROUND(100.0 * v.wiederholungskunden / v.kunden_mit_bestellung, 1)
               OR v.wiederkaufquote_prozent NOT BETWEEN 0 AND 100), 'Daten-Team'
    UNION ALL
    -- Datenqualität (E-42, E-27): Eine Zeile kann mehrere Gründe haben (" | "). Die Summe der View
    -- ist deshalb die Zahl der GRÜNDE, nicht der Zeilen. Zweiter Weg direkt aus der Tabelle:
    -- je Zeile die Anzahl ihrer Gründe, aufsummiert. Erwartet gleich, sonst Abbruch.
    SELECT 'M14', 'R', 'DQ Summe je Grund = Anzahl Gründe in der Tabelle',
           (SELECT COALESCE(SUM(array_length(string_to_array(grund, ' | '), 1)), 0)
            FROM protokoll.abgewiesene_position),
           (SELECT COALESCE(SUM(zeilen), 0) FROM mart.v_dq_abgewiesene_zeilen_grund), 'Daten-Team'
    UNION ALL
    -- Jede Zeile hat mindestens einen Grund (Q-02): Summe der Gründe >= Zeilen. Erwartet 0 Verstöße.
    -- Gleichheit ist NICHT gefordert: bei mehreren Gründen je Zeile ist die Summe größer.
    SELECT 'M15', 'R', 'DQ weniger Gründe als Zeilen oder leerer Grund', 0,
           (SELECT CASE WHEN (SELECT COALESCE(SUM(zeilen), 0) FROM mart.v_dq_abgewiesene_zeilen_grund)
                             < (SELECT COUNT(*) FROM protokoll.abgewiesene_position) THEN 1 ELSE 0 END)
         + (SELECT COUNT(*) FROM mart.v_dq_abgewiesene_zeilen_grund WHERE grund = ''), 'Daten-Team'

    -- ---------- S: Stand 14.10.2026 ---------------------------------------
    UNION ALL SELECT 'S1', 'S', 'Auftragsumsatz (Kontrollsumme)',           2212834.69, (SELECT umsatz FROM auftrag), 'Controlling'
    UNION ALL SELECT 'S2', 'S', 'F-01 Monate',                              24,  (SELECT COUNT(*) FROM mart.v_f01_umsatz_monat), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S3', 'S', 'F-02 Rang 1 Umsatz',                       54631.71,
                                (SELECT umsatz_netto FROM mart.v_f02_top10_kunden WHERE rang = 1), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S4', 'S', 'F-02 Zeilen (keine Gleichstände)',         10,  (SELECT COUNT(*) FROM mart.v_f02_top10_kunden), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S5', 'S', 'F-04 Umsatz Unbekannt (Kunde -1)',         78973.22,
                                (SELECT SUM(umsatz_netto) FROM mart.v_f04_umsatz_ort WHERE ort = 'Unbekannt'), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S6', 'S', 'F-05 Anteil Positionen storniert %',       16.3, (SELECT anteil_positionen_storniert_prozent FROM f05), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S7', 'S', 'F-05 Anteil vollständig geliefert %',      50.5, (SELECT anteil_vollstaendig_geliefert_prozent FROM f05), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S8', 'S', 'F-05 Anteil Bestellungen voll storniert %', 4.9, (SELECT anteil_bestellungen_voll_storniert_prozent FROM f05), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S9', 'S', 'F-06 Bestellungen ohne Storno',            662, (SELECT SUM(bestellungen) FROM mart.v_f06_zahlungsart), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S10', 'S', 'F-07 umgezogene Kunden mit Bestellungen', 14,
                                (SELECT COUNT(DISTINCT kunden_nr) FROM mart.v_f07_wohnort_bestellung WHERE umgezogen), 'Fachbereich Vertrieb'
    -- Stand 19.10.2026 (E-40): Verteilung der Bestellungen je Kunde (docs/ergebnisse/ergebnisse.md, F-08)
    UNION ALL SELECT 'S11', 'S', 'F-08 Wiederholungskunden',                136,
                                (SELECT COUNT(*) FROM mart.v_f08_wiederholungskunden), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S12', 'S', 'F-08 Kunden mit mindestens einer Bestellung', 149,
                                (SELECT MAX(kunden_mit_bestellung) FROM mart.v_f08_wiederholungskunden), 'Fachbereich Vertrieb'
    UNION ALL SELECT 'S13', 'S', 'F-08 Wiederkaufquote %',                  91.3,
                                (SELECT MAX(wiederkaufquote_prozent) FROM mart.v_f08_wiederholungskunden), 'Fachbereich Vertrieb'
    -- Stand 19.10.2026 (E-42): 75 abgewiesene Zeilen, je ein Grund (docs/protokoll.md)
    UNION ALL SELECT 'S14', 'S', 'DQ abgewiesene Zeilen (Protokolltabelle)', 75,
                                (SELECT COUNT(*) FROM protokoll.abgewiesene_position), 'Daten-Team'
)
SELECT nr, art, pruefung, soll, ist,
       CASE WHEN soll = ist THEN 'OK' ELSE 'FEHLER' END       AS ergebnis,
       CASE WHEN art = 'R' THEN 'Abbruch' ELSE 'Warnung' END   AS reaktion,
       rolle
FROM pruefungen
ORDER BY art, length(nr), nr;
