# =============================================================================
# generator.py
# Mini-Projet NoSQL : Systeme de Suivi IoT Temps Reel
# Module : NoSQL pour le Big Data | Dr. B. BENCHARIF | USDB Blida 1
# Annee : 2025/2026
# =============================================================================
# Description :
#   Script de simulation et d'ingestion de donnees GPS pour 10 camions.
#   Chaque camion est simule dans un thread independant et insere ses
#   positions dans Apache Cassandra via des Prepared Statements.
#
# Architecture :
#   - 10 threads (un par camion TRUCK_001 a TRUCK_010)
#   - 3 Prepared Statements declares une seule fois avant le lancement
#   - Arret propre sur Ctrl+C via threading.Event
#   - Compteurs thread-safe via threading.Lock
#
# Utilisation :
#   python backend/generator.py
#   CASSANDRA_HOST=192.168.1.10 python backend/generator.py
# =============================================================================

import os
import random
import threading
import time
from datetime import datetime, timezone

# Correctif Windows + Python 3.12 : utilisation de gevent comme event loop
# gevent remplace asyncore qui a ete supprime en Python 3.12
from gevent import monkey
monkey.patch_all()

from cassandra.io.geventreactor import GeventConnection
from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy, RetryPolicy
from cassandra.query import ConsistencyLevel


# =============================================================================
# CONFIGURATION GLOBALE
# =============================================================================

# Adresse du noeud Cassandra — lit la variable d'environnement si presente
# Valeur par defaut : 127.0.0.1 (execution locale)
# En Docker : CASSANDRA_HOST=cassandra (nom du service docker-compose)
CASSANDRA_HOST = os.environ.get("CASSANDRA_HOST", "127.0.0.1")

# Keyspace cible (cree par schema.cql)
KEYSPACE = "logistics_ks"

# Identifiants des 10 camions simules
TRUCK_IDS = [f"TRUCK_{str(i).zfill(3)}" for i in range(1, 11)]

# Intervalle d'insertion en secondes (aleatoire par iteration)
INTERVAL_MIN = 0.5
INTERVAL_MAX = 1.5

# Seuil de temperature declenchant une alerte
ALERT_THRESHOLD = 35.0

# Frequence d'affichage des logs (toutes les N insertions)
LOG_EVERY = 100


# =============================================================================
# DEFINITION DES ROUTES GPS ALGERIENNES
# =============================================================================
# Chaque route est definie par un tuple (lat_min, lat_max, lon_min, lon_max).
# Les camions se deplacent de facon realiste le long de leur route assignee.
# =============================================================================

ROUTES = {
    # Route A : Alger -> Blida (axe nord-sud)
    "A": {"lat_min": 36.4, "lat_max": 36.7, "lon_min": 2.8, "lon_max": 3.1},
    # Route B : Blida -> Medea (axe est-ouest en altitude)
    "B": {"lat_min": 36.2, "lat_max": 36.4, "lon_min": 2.8, "lon_max": 2.9},
    # Route C : Alger -> Boumerdes (axe nord-est cotier)
    "C": {"lat_min": 36.7, "lat_max": 36.8, "lon_min": 3.1, "lon_max": 3.6},
}

# Attribution fixe d'une route par camion pour simuler des trajets realistes
TRUCK_ROUTES = {
    "TRUCK_001": "A", "TRUCK_002": "A", "TRUCK_003": "A", "TRUCK_004": "A",
    "TRUCK_005": "B", "TRUCK_006": "B", "TRUCK_007": "B",
    "TRUCK_008": "C", "TRUCK_009": "C", "TRUCK_010": "C",
}

# Statuts de cargaison avec probabilites ponderees
CARGO_STATUSES = ["EN_ROUTE", "EN_LIVRAISON", "A_LARRET", "RETARD"]
CARGO_WEIGHTS  = [0.55,       0.25,           0.10,       0.10]

# Vitesses correlees au statut de cargaison (min_kmh, max_kmh)
SPEED_RANGES = {
    "EN_ROUTE"     : (60.0, 120.0),
    "EN_LIVRAISON" : (10.0,  60.0),
    "A_LARRET"     : ( 0.0,   5.0),
    "RETARD"       : ( 5.0,  40.0),
}


# =============================================================================
# VARIABLES PARTAGEES ENTRE LES THREADS
# =============================================================================

# Evenement d'arret : mis a True par Ctrl+C, tous les threads s'arretent
stop_event = threading.Event()

# Compteurs d'insertions par camion (acces thread-safe via lock)
counters = {truck_id: 0 for truck_id in TRUCK_IDS}
counters_lock = threading.Lock()


# =============================================================================
# CONNEXION A CASSANDRA
# =============================================================================

def create_session():
    cluster = Cluster(
        contact_points=[CASSANDRA_HOST],
        load_balancing_policy=RoundRobinPolicy(),
        default_retry_policy=RetryPolicy(),
        connection_class=GeventConnection,
        connect_timeout=30,
    )
    session = cluster.connect(KEYSPACE)
    session.default_consistency_level = ConsistencyLevel.ONE
    return session

# =============================================================================
# DECLARATION DES PREPARED STATEMENTS
# =============================================================================
# Les Prepared Statements sont prepares UNE SEULE FOIS avant le lancement
# des threads. Cassandra parse et planifie la requete une seule fois, puis
# reutilise le plan d'execution en cache pour toutes les insertions suivantes.
# =============================================================================

def prepare_statements(session):
    """
    Prepare et retourne les 3 statements d'insertion.
    Cette fonction est appelee une seule fois dans le thread principal.
    """

    # Statement 1 : insertion d'une position GPS dans tracking_by_truck
    stmt_tracking = session.prepare("""
        INSERT INTO tracking_by_truck
            (truck_id, event_time, latitude, longitude,
             temperature, cargo_status, speed_kmh)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """)

    # Statement 2 : insertion d'une alerte dans alerts_by_day
    stmt_alert = session.prepare("""
        INSERT INTO alerts_by_day
            (alert_date, event_time, truck_id,
             temperature, alert_type, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """)

    # Statement 3 : mise a jour des statistiques horaires dans truck_stats
    # INSERT ... IF NOT EXISTS n'est pas utilise pour conserver la performance.
    # L'upsert natif de Cassandra (derniere ecriture gagne) est suffisant ici.
    stmt_stats = session.prepare("""
        INSERT INTO truck_stats
            (truck_id, stat_hour, avg_temperature, max_temperature,
             min_temperature, record_count, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """)

    return stmt_tracking, stmt_alert, stmt_stats


# =============================================================================
# LOGIQUE DE SIMULATION PAR CAMION
# =============================================================================

def simulate_truck(truck_id, session, stmt_tracking, stmt_alert, stmt_stats):
    """
    Fonction executee dans un thread dedie a chaque camion.
    Simule le deplacement GPS, la temperature et le statut de cargaison,
    puis insere les donnees dans Cassandra via les Prepared Statements.

    Parametres :
        truck_id       : identifiant du camion (ex: 'TRUCK_001')
        session        : session Cassandra partagee entre les threads
        stmt_tracking  : Prepared Statement pour tracking_by_truck
        stmt_alert     : Prepared Statement pour alerts_by_day
        stmt_stats     : Prepared Statement pour truck_stats
    """

    # Recuperation de la route assignee au camion
    route_key = TRUCK_ROUTES[truck_id]
    route = ROUTES[route_key]

    # Initialisation de la position GPS au debut de la route
    lat = random.uniform(route["lat_min"], route["lat_max"])
    lon = random.uniform(route["lon_min"], route["lon_max"])

    # Initialisation de la temperature avec derive lente (realisme)
    temperature = random.uniform(20.0, 30.0)

    # Statistiques locales pour la fenetre horaire courante
    # Ces valeurs sont re-initialisees a chaque nouvelle heure
    hour_stats = {
        "avg_temp"     : temperature,
        "max_temp"     : temperature,
        "min_temp"     : temperature,
        "count"        : 0,
        "sum_temp"     : 0.0,
        "current_hour" : datetime.now(timezone.utc).strftime("%Y%m%d%H"),
    }

    print(f"[{truck_id}] Thread demarre — Route {route_key} "
          f"| lat={lat:.4f} lon={lon:.4f}")

    # -------------------------------------------------------------------------
    # BOUCLE PRINCIPALE D'INSERTION
    # Chaque iteration = 1 enregistrement GPS insere dans Cassandra
    # -------------------------------------------------------------------------
    while not stop_event.is_set():

        # --- Horodatage de l'evenement ---
        now_utc = datetime.now(timezone.utc)
        event_time = now_utc

        # --- Simulation du mouvement GPS (derive progressive sur la route) ---
        lat_delta = random.uniform(-0.005, 0.005)
        lon_delta = random.uniform(-0.005, 0.005)
        lat = max(route["lat_min"], min(route["lat_max"], lat + lat_delta))
        lon = max(route["lon_min"], min(route["lon_max"], lon + lon_delta))

        # --- Simulation de la temperature avec derive lente (±0.5 par pas) ---
        temp_delta = random.uniform(-0.5, 0.5)
        temperature = max(15.0, min(45.0, temperature + temp_delta))

        # --- Statut de cargaison et vitesse correlee ---
        cargo_status = random.choices(CARGO_STATUSES, weights=CARGO_WEIGHTS, k=1)[0]
        speed_min, speed_max = SPEED_RANGES[cargo_status]
        speed_kmh = random.uniform(speed_min, speed_max)

        # --- Insertion dans tracking_by_truck via Prepared Statement ---
        try:
            session.execute(
                stmt_tracking,
                (truck_id, event_time, lat, lon,
                 float(temperature), cargo_status, float(speed_kmh))
            )
        except Exception as exc:
            print(f"[{truck_id}] ERREUR tracking_by_truck : {exc}")
            time.sleep(2)
            continue

        # --- Mise a jour du compteur thread-safe ---
        with counters_lock:
            counters[truck_id] += 1
            local_count = counters[truck_id]

        # --- Mise a jour des statistiques horaires locales ---
        current_hour_str = now_utc.strftime("%Y%m%d%H")

        if current_hour_str != hour_stats["current_hour"]:
            # Changement d'heure : reinitialisation des statistiques
            hour_stats["current_hour"] = current_hour_str
            hour_stats["sum_temp"]     = temperature
            hour_stats["count"]        = 1
            hour_stats["max_temp"]     = temperature
            hour_stats["min_temp"]     = temperature
            hour_stats["avg_temp"]     = temperature
        else:
            hour_stats["sum_temp"] += temperature
            hour_stats["count"]    += 1
            hour_stats["max_temp"] = max(hour_stats["max_temp"], temperature)
            hour_stats["min_temp"] = min(hour_stats["min_temp"], temperature)
            hour_stats["avg_temp"] = hour_stats["sum_temp"] / hour_stats["count"]

        # --- Alerte temperature : insertion dans alerts_by_day et truck_stats ---
        if temperature > ALERT_THRESHOLD:

            # Cle de partition pour alerts_by_day : date calendaire seule
            alert_date = now_utc.date()

            # Type d'alerte selon le niveau de temperature
            if temperature >= 42.0:
                alert_type = "CRITIQUE"
            elif temperature >= 38.0:
                alert_type = "ELEVE"
            else:
                alert_type = "ATTENTION"

            # Insertion de l'alerte dans alerts_by_day
            try:
                session.execute(
                    stmt_alert,
                    (alert_date, event_time, truck_id,
                     float(temperature), alert_type,
                     lat, lon)
                )
            except Exception as exc:
                print(f"[{truck_id}] ERREUR alerts_by_day : {exc}")

            # Upsert des statistiques horaires dans truck_stats
            # Format de stat_hour : 'TRUCK_001_2026040109'
            stat_hour = f"{truck_id}_{current_hour_str}"
            try:
                session.execute(
                    stmt_stats,
                    (truck_id, stat_hour,
                     float(hour_stats["avg_temp"]),
                     float(hour_stats["max_temp"]),
                     float(hour_stats["min_temp"]),
                     hour_stats["count"],
                     now_utc)
                )
            except Exception as exc:
                print(f"[{truck_id}] ERREUR truck_stats : {exc}")

        # --- Log de progression tous les LOG_EVERY insertions ---
        if local_count % LOG_EVERY == 0:
            print(
                f"[{truck_id}] {local_count:>6} enregistrements "
                f"| temp={temperature:.1f}C "
                f"| lat={lat:.4f} lon={lon:.4f} "
                f"| statut={cargo_status}"
            )

        # --- Pause inter-insertion (simule la frequence IoT reelle) ---
        time.sleep(random.uniform(INTERVAL_MIN, INTERVAL_MAX))

    print(f"[{truck_id}] Thread arrete proprement.")


# =============================================================================
# AFFICHAGE DU TABLEAU RECAPITULATIF FINAL
# =============================================================================

def print_summary():
    """
    Affiche le tableau final des insertions par camion apres Ctrl+C.
    """
    print("\n" + "=" * 65)
    print("  RESUME FINAL — INSERTIONS PAR CAMION")
    print("=" * 65)
    print(f"  {'Camion':<15} {'Enregistrements':>18} {'Route':>8}")
    print("-" * 65)
    total = 0
    for truck_id in TRUCK_IDS:
        count = counters[truck_id]
        route = TRUCK_ROUTES[truck_id]
        total += count
        print(f"  {truck_id:<15} {count:>18}      {route:>5}")
    print("-" * 65)
    print(f"  {'TOTAL':<15} {total:>18}")
    print("=" * 65)
    print(f"\n  Commande de verification dans cqlsh :")
    print(f"  SELECT count(*) FROM logistics_ks.tracking_by_truck;")
    print()


# =============================================================================
# POINT D'ENTREE PRINCIPAL
# =============================================================================

def main():
    """
    Point d'entree du script de simulation.
    1. Connexion a Cassandra
    2. Declaration des Prepared Statements (une seule fois)
    3. Lancement de 10 threads (un par camion)
    4. Attente du signal Ctrl+C
    5. Arret propre et affichage du resume
    """

    print("=" * 65)
    print("  SIMULATEUR IoT — SUIVI GPS TEMPS REEL")
    print(f"  Connexion a Cassandra : {CASSANDRA_HOST}:9042")
    print(f"  Keyspace              : {KEYSPACE}")
    print(f"  Camions               : {len(TRUCK_IDS)}")
    print(f"  Interval d'insertion  : {INTERVAL_MIN}s - {INTERVAL_MAX}s par camion")
    print(f"  Seuil alerte temp.    : {ALERT_THRESHOLD} degres C")
    print("=" * 65)

    # --- Connexion et preparation des statements ---
    print("\n[INIT] Connexion a Cassandra en cours...")
    try:
        session = create_session()
        print(f"[INIT] Connexion etablie sur {CASSANDRA_HOST}:9042")
    except Exception as exc:
        print(f"[ERREUR] Impossible de se connecter a Cassandra : {exc}")
        print(f"         Verifiez que le conteneur cassandra_iot est en cours d'execution.")
        return

    print("[INIT] Preparation des Prepared Statements...")
    stmt_tracking, stmt_alert, stmt_stats = prepare_statements(session)
    print("[INIT] 3 Prepared Statements prepares avec succes.")

    # --- Lancement des threads ---
    print(f"\n[INIT] Lancement de {len(TRUCK_IDS)} threads de simulation...\n")
    threads = []
    for truck_id in TRUCK_IDS:
        t = threading.Thread(
            target=simulate_truck,
            args=(truck_id, session, stmt_tracking, stmt_alert, stmt_stats),
            name=f"thread-{truck_id}",
            daemon=True,
        )
        threads.append(t)
        t.start()

    print(f"\n[INFO] Simulation en cours. Appuyez sur Ctrl+C pour arreter.\n")

    # --- Attente du signal d'arret (Ctrl+C) ---
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[INFO] Signal d'arret recu (Ctrl+C). Arret en cours...")
        stop_event.set()

    # --- Attente de la fin de tous les threads ---
    print("[INFO] Attente de la fin des threads...")
    for t in threads:
        t.join(timeout=5)

    # --- Affichage du resume final ---
    print_summary()


if __name__ == "__main__":
    main()