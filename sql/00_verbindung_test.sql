/* ============================================================================
   sql/00_verbindung_test.sql
   Zweck   : PostgreSQL prüfen und die leere Datenbank dwh_sued mit den Schemas
             stg und dwh anlegen (einmalig, vor dem ersten Lauf von main.py).
   Werkzeug: pgAdmin 4 (Query Tool) oder DBeaver
   Erwartet: Teil 2 liefert zwei Zeilen (dwh, stg) für die Datenbank dwh_sued.

   In PostgreSQL gibt es kein "USE <db>": Jede Verbindung gehört zu genau
   EINER Datenbank. Deshalb zwei Teile mit zwei verschiedenen Verbindungen.

   Namen immer klein schreiben (dwh_sued, nicht DWH_Sued), sonst müssen sie
   überall in "Anführungszeichen" stehen.
   ============================================================================ */


/* ---- TEIL 1 · verbunden mit der Standard-Datenbank "postgres" ------------- */

SELECT version();

-- Nur beim ersten Mal ausführen (CREATE DATABASE kennt kein IF NOT EXISTS)
CREATE DATABASE dwh_sued;


/* ---- TEIL 2 · verbunden mit der neuen Datenbank "dwh_sued" ----------------
   pgAdmin: im Baum links "dwh_sued" markieren -> Tools -> Query Tool         */

-- Zwei Schemas: stg = Rohdaten (nur Text), dwh = Star Schema
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dwh;

SELECT current_database() AS datenbank, schema_name
FROM information_schema.schemata
WHERE schema_name IN ('stg', 'dwh')
ORDER BY schema_name;
