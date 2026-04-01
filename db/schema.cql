-- ============================================================
-- schema.cql
-- Mini-Projet NoSQL : Systeme de Suivi IoT Temps Reel
-- Module : NoSQL pour le Big Data | Dr. B. BENCHARIF | USDB Blida 1
-- Annee : 2025/2026
-- ============================================================
-- Principe de conception : Query-Driven Modeling
-- Chaque table est concue pour repondre a UNE requete precise
-- sans jamais recourir a ALLOW FILTERING.
-- ============================================================


-- ============================================================
-- KEYSPACE : logistics_ks
-- Strategie : SimpleStrategy (environnement de developpement
--             mono-noeud — a remplacer par NetworkTopologyStrategy
--             en production multi-datacenter)
-- Replication Factor : 1 (pas de redondance en dev local)
-- ============================================================

CREATE KEYSPACE IF NOT EXISTS logistics_ks
    WITH REPLICATION = {
        'class'              : 'SimpleStrategy',
        'replication_factor' : 1
    }
    AND DURABLE_WRITES = true;

-- Activation du keyspace pour les instructions suivantes
USE logistics_ks;


-- ============================================================
-- TABLE 1 : tracking_by_truck
-- ============================================================
-- Objectif : Recuperer les N dernieres positions GPS
--            d'un camion specifique, triees du plus recent
--            au plus ancien.
--
-- Requete ciblee (sans ALLOW FILTERING) :
--   SELECT * FROM logistics_ks.tracking_by_truck
--   WHERE truck_id = 'TRUCK_001'
--   LIMIT 50;
--
-- Justification des cles :
--   - Partition Key  : truck_id
--       Toutes les positions d'un meme camion sont stockees
--       sur le meme noeud Cassandra. La requete WHERE truck_id = ?
--       n'interroge qu'un seul noeud => O(1) en temps de lookup.
--   - Clustering Key : event_time DESC
--       Les enregistrements sont physiquement tries par ordre
--       decroissant dans la SSTable sur disque. LIMIT 50 lit
--       exactement les 50 premieres lignes de la partition
--       sans aucun tri applicatif supplementaire.
-- ============================================================

CREATE TABLE IF NOT EXISTS logistics_ks.tracking_by_truck (
    truck_id        TEXT,
    event_time      TIMESTAMP,
    latitude        DOUBLE,
    longitude       DOUBLE,
    temperature     FLOAT,
    cargo_status    TEXT,
    speed_kmh       FLOAT,
    PRIMARY KEY (truck_id, event_time)
) WITH CLUSTERING ORDER BY (event_time DESC)
  AND comment = 'Historique GPS des camions — tri decroissant natif sur event_time';


-- ============================================================
-- TABLE 2 : alerts_by_day
-- ============================================================
-- Objectif : Afficher toutes les alertes de temperature
--            enregistrees pour une date calendaire donnee.
--
-- Requete ciblee (sans ALLOW FILTERING) :
--   SELECT * FROM logistics_ks.alerts_by_day
--   WHERE alert_date = '2026-03-18';
--
-- Justification des cles :
--   - Partition Key     : alert_date (DATE)
--       Toutes les alertes d'une journee sont co-localisees
--       sur le meme noeud. La requete WHERE alert_date = ?
--       est un acces direct a une seule partition.
--   - Clustering Key 1  : event_time DESC
--       Les alertes les plus recentes apparaissent en premier
--       dans le resultat — comportement attendu pour un
--       tableau de bord de monitoring en temps reel.
--   - Clustering Key 2  : truck_id ASC
--       Permet de departager deux alertes survenues a la
--       meme seconde et garantit un ordre deterministe
--       et stable dans la SSTable.
-- ============================================================

CREATE TABLE IF NOT EXISTS logistics_ks.alerts_by_day (
    alert_date      DATE,
    event_time      TIMESTAMP,
    truck_id        TEXT,
    temperature     FLOAT,
    alert_type      TEXT,
    latitude        DOUBLE,
    longitude       DOUBLE,
    PRIMARY KEY (alert_date, event_time, truck_id)
) WITH CLUSTERING ORDER BY (event_time DESC, truck_id ASC)
  AND comment = 'Alertes de temperature groupees par jour — acces O(1) par date';


-- ============================================================
-- TABLE 3 : truck_stats
-- ============================================================
-- Objectif : Retourner les statistiques de temperature
--            pre-aggregees pour un camion sur une fenetre
--            horaire precise, sans scan complet de la base.
--
-- Requete ciblee (sans ALLOW FILTERING) :
--   SELECT * FROM logistics_ks.truck_stats
--   WHERE truck_id = 'TRUCK_001'
--   AND   stat_hour = 'TRUCK_001_2026031814';
--
-- Justification des cles :
--   - Partition Key composite : (truck_id, stat_hour)
--       La combinaison truck_id + stat_hour identifie
--       de maniere unique une fenetre horaire pour un camion.
--       Cela evite les partitions "hotspot" qu'un seul
--       truck_id provoquerait si tous les enregistrements
--       de tous les camions etaient dans la meme partition.
--       Format de stat_hour : 'TRUCK_001_2026031814'
--       (truck_id + YYYYMMDDMM pour un lookup exact).
--   - Pas de Clustering Column : une seule ligne par partition
--       (un agregat par camion par heure). La cle composite
--       suffit a identifier la ligne de facon unique.
-- ============================================================

CREATE TABLE IF NOT EXISTS logistics_ks.truck_stats (
    truck_id            TEXT,
    stat_hour           TEXT,
    avg_temperature     FLOAT,
    max_temperature     FLOAT,
    min_temperature     FLOAT,
    record_count        INT,
    last_updated        TIMESTAMP,
    PRIMARY KEY ((truck_id, stat_hour))
) WITH comment = 'Statistiques horaires pre-aggregees par camion — partition composite anti-hotspot';


-- ============================================================
-- VERIFICATION POST-CREATION
-- Executer ces commandes dans cqlsh pour valider le schema :
--
--   DESCRIBE KEYSPACE logistics_ks;
--
--   SELECT * FROM logistics_ks.tracking_by_truck
--   WHERE truck_id = 'TRUCK_001' LIMIT 50;
--
--   SELECT * FROM logistics_ks.alerts_by_day
--   WHERE alert_date = '2026-03-18';
--
--   SELECT * FROM logistics_ks.truck_stats
--   WHERE truck_id = 'TRUCK_001'
--   AND stat_hour = 'TRUCK_001_2026031814';
-- ============================================================
