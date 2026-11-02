-- ========================================================================
-- sql/06b_create_mart_dq.sql
-- Migration: mart-View für die Datenqualität, abgewiesene Zeilen je Grund
--
-- Zweck      : Zählt je Ablehnungsgrund, wie viele abgewiesene Zeilen ihn haben.
--              Datenquelle für Diagramm D3 (etl/06_erstelle_diagramme.py, E-41, E-42).
-- Eingabe    : protokoll.abgewiesene_position (aus sql/06_create_protokoll_abgewiesen.sql)
-- Ausgabe    : View mart.v_dq_abgewiesene_zeilen_grund mit COMMENT
-- Anforderung: Kontrollzahl je Prüfung, Diagramm D3
-- Bezug      : E-27, E-41, E-42
-- Aufruf     : pgAdmin -> dwh_sued -> Query Tool -> ganze Datei -> F5
--              oder: psql -d dwh_sued -f sql/06b_create_mart_dq.sql
--              Voraussetzung: sql/05_create_mart.sql (Schema mart) und sql/06_create_protokoll_abgewiesen.sql.
--              Erwartet: BEGIN, CREATE VIEW, COMMENT, COMMIT. Mehrmals startbar.
--              Kontrolle: sql/05b_kontrolle_mart.sql (M14, M15, S14).
--
-- WICHTIG (E-27): Eine Zeile kann mehrere Gründe haben (" | " getrennt). Sie zählt dann bei
-- JEDEM ihrer Gründe. Die Summe über alle Gründe ist deshalb die Zahl der GRÜNDE, nicht der
-- Zeilen, und kann größer sein als die Zahl der abgewiesenen Zeilen.
-- Keine ORDER BY in der View: Die Reihenfolge legt die Abfrage fest, die die View liest.
-- ========================================================================

BEGIN;

CREATE OR REPLACE VIEW mart.v_dq_abgewiesene_zeilen_grund AS
WITH einzelgrund AS (
    -- WAS: eine Zeile je (abgewiesene Position, Grund).
    -- WARUM unnest(string_to_array(...)): zerlegt "Grund A | Grund B" in zwei Zeilen (E-27).
    -- btrim: Leerzeichen am Rand gehören nicht zum Grund.
    SELECT btrim(g.grund) AS grund
    FROM protokoll.abgewiesene_position a
    CROSS JOIN LATERAL unnest(string_to_array(a.grund, ' | ')) AS g(grund)
)
SELECT grund,
       -- Jede Zeile von einzelgrund ist ein (Position, Grund)-Paar: COUNT(*) = Zeilen mit diesem Grund.
       -- etl/03 hängt jeden Grund je Zeile nur einmal an (E-27), Doppelzählung ist nicht möglich.
       COUNT(*) AS zeilen
FROM einzelgrund
GROUP BY grund;

COMMENT ON VIEW mart.v_dq_abgewiesene_zeilen_grund IS
  'Datenqualität: Anzahl abgewiesener Zeilen je Ablehnungsgrund (protokoll.abgewiesene_position). Mehrere Gründe je Zeile (E-27): Zeile zählt bei jedem Grund, Summe = Anzahl Gründe, nicht Zeilen (E-42).';

COMMIT;
