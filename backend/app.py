# =============================================================================
# app.py
# Mini-Projet NoSQL : Systeme de Suivi IoT Temps Reel
# Module : NoSQL pour le Big Data | Dr. B. BENCHARIF | USDB Blida 1
# Annee : 2025/2026
# =============================================================================
# Description :
#   Backend REST API expose les donnees Cassandra via 6 endpoints.
#   Toutes les requetes utilisent des Prepared Statements prepares
#   une seule fois au demarrage de l'application.
#
# Endpoints :
#   GET /health                        — Etat de la connexion Cassandra
#   GET /trucks                        — Liste des 10 camions avec position
#   GET /trucks/{truck_id}/positions   — Historique GPS d'un camion
#   GET /trucks/{truck_id}/stats       — Statistiques horaires d'un camion
#   GET /alerts/{date}                 — Alertes temperature par date
#   GET /dashboard/latest              — Derniere position de chaque camion
#
# Utilisation :
#   uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
# =============================================================================

import asyncio
import os
import sys
import types
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Correctif Python 3.12+ : asyncore supprime en Python 3.12
if "asyncore" not in sys.modules:
    _m = types.ModuleType("asyncore")
    _m.dispatcher = object
    sys.modules["asyncore"] = _m
if "asynchat" not in sys.modules:
    sys.modules["asynchat"] = types.ModuleType("asynchat")

from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy, RetryPolicy
from cassandra.query import ConsistencyLevel


# =============================================================================
# CONFIGURATION
# =============================================================================

CASSANDRA_HOST = os.environ.get("CASSANDRA_HOST", "127.0.0.1")
KEYSPACE       = os.environ.get("CASSANDRA_KEYSPACE", "logistics_ks")

# Identifiants des 10 camions connus
TRUCK_IDS = [f"TRUCK_{str(i).zfill(3)}" for i in range(1, 11)]


# =============================================================================
# CONNEXION CASSANDRA — SINGLETON via lru_cache
# =============================================================================
# lru_cache garantit qu'une seule session est creee pour toute la duree
# de vie de l'application. Chaque requete HTTP reutilise cette session.
# =============================================================================

@lru_cache(maxsize=1)
def get_session():
    """
    Cree et retourne la session Cassandra unique de l'application.
    Appelee une seule fois grace a lru_cache.
    """
    cluster = Cluster(
    contact_points=[CASSANDRA_HOST],
    load_balancing_policy=RoundRobinPolicy(),
    default_retry_policy=RetryPolicy(),
    connect_timeout=30,
)
    session = cluster.connect(KEYSPACE)
    session.default_consistency_level = ConsistencyLevel.ONE
    return session


# =============================================================================
# PREPARED STATEMENTS — DATACLASS
# =============================================================================
# Tous les Prepared Statements sont declares UNE SEULE FOIS au demarrage
# via @app.on_event("startup"). Les endpoints ne font que les executer.
# =============================================================================

@dataclass
class PreparedStatements:
    """Conteneur pour tous les Prepared Statements de l'application."""
    # Historique GPS d'un camion (LIMIT variable)
    select_positions:   object = None
    # Alertes par date calendaire
    select_alerts:      object = None
    # Statistiques horaires d'un camion (toutes les heures)
    select_stats_truck: object = None
    # Statistiques d'un camion pour une heure precise
    select_stats_hour:  object = None
    # Derniere position d'un camion (LIMIT 1)
    select_latest:      object = None
    # Comptage total des enregistrements
    select_count:       object = None


# Instance globale des Prepared Statements
ps = PreparedStatements()


# =============================================================================
# MODELES PYDANTIC — REPONSES API
# =============================================================================

class PositionRecord(BaseModel):
    """Modele de reponse pour une position GPS."""
    truck_id:     str
    event_time:   datetime
    latitude:     float
    longitude:    float
    temperature:  float
    cargo_status: str
    speed_kmh:    float


class AlertRecord(BaseModel):
    """Modele de reponse pour une alerte de temperature."""
    alert_date:  date
    event_time:  datetime
    truck_id:    str
    temperature: float
    alert_type:  str
    latitude:    float
    longitude:   float


class TruckStats(BaseModel):
    """Modele de reponse pour les statistiques horaires d'un camion."""
    truck_id:        str
    stat_hour:       str
    avg_temperature: Optional[float]
    max_temperature: Optional[float]
    min_temperature: Optional[float]
    record_count:    Optional[int]
    last_updated:    Optional[datetime]


class TruckSummary(BaseModel):
    """Modele de reponse pour la liste des camions avec derniere position."""
    truck_id:        str
    last_seen:       Optional[datetime]
    last_latitude:   Optional[float]
    last_longitude:  Optional[float]
    last_temp:       Optional[float]
    last_status:     Optional[str]


class HealthResponse(BaseModel):
    """Modele de reponse pour le endpoint /health."""
    status:       str
    cassandra:    str
    record_count: int


# =============================================================================
# APPLICATION FASTAPI
# =============================================================================

app = FastAPI(
    title="IoT Logistics — API de Suivi GPS",
    description=(
        "API REST pour le suivi en temps reel de 10 camions logistiques. "
        "Toutes les requetes utilisent des Prepared Statements Cassandra. "
        "Module : NoSQL pour le Big Data | Dr. B. BENCHARIF | USDB Blida 1"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware CORS : autorise Streamlit (port 8501) et tout autre client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# EVENEMENTS DE DEMARRAGE ET D'ARRET
# =============================================================================

@app.on_event("startup")
def startup_event():
    """
    Prepare tous les Prepared Statements au demarrage de l'application.
    Cette fonction est appelee une seule fois avant le premier requete HTTP.
    """
    session = get_session()

    # Statement 1 : historique GPS d'un camion avec LIMIT variable
    ps.select_positions = session.prepare("""
        SELECT truck_id, event_time, latitude, longitude,
               temperature, cargo_status, speed_kmh
        FROM tracking_by_truck
        WHERE truck_id = ?
        LIMIT ?
    """)

    # Statement 2 : toutes les alertes d'une date donnee
    ps.select_alerts = session.prepare("""
        SELECT alert_date, event_time, truck_id,
               temperature, alert_type, latitude, longitude
        FROM alerts_by_day
        WHERE alert_date = ?
    """)

    # Statement 3 : statistique precise pour un truck_id + stat_hour exact
    ps.select_stats_truck = session.prepare("""
        SELECT truck_id, stat_hour, avg_temperature, max_temperature,
               min_temperature, record_count, last_updated
        FROM truck_stats
        WHERE truck_id = ?
        AND stat_hour = ?
    """)

    # Statement 4 : derniere position d'un camion (LIMIT 1)
    ps.select_latest = session.prepare("""
        SELECT truck_id, event_time, latitude, longitude,
               temperature, cargo_status, speed_kmh
        FROM tracking_by_truck
        WHERE truck_id = ?
        LIMIT 1
    """)

    # Statement 5 : comptage total pour le endpoint /health
    ps.select_count = session.prepare("""
        SELECT count(*) FROM tracking_by_truck
    """)

    print("[APP] Tous les Prepared Statements sont prets.")


@app.on_event("shutdown")
def shutdown_event():
    """Fermeture propre de la session Cassandra."""
    try:
        session = get_session()
        session.cluster.shutdown()
        print("[APP] Connexion Cassandra fermee proprement.")
    except Exception:
        pass


# =============================================================================
# ENDPOINT 1 : GET /trucks/{truck_id}/positions
# =============================================================================

@app.get(
    "/trucks/{truck_id}/positions",
    response_model=List[PositionRecord],
    summary="Historique GPS d'un camion",
    tags=["Tracking"],
)
def get_truck_positions(
    truck_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Nombre de positions a retourner (max 200)"),
):
    """
    Retourne les N dernieres positions GPS d'un camion specifique,
    triees de la plus recente a la plus ancienne.
    Utilise tracking_by_truck avec Clustering Order DESC natif.
    """
    if truck_id not in TRUCK_IDS:
        raise HTTPException(status_code=404, detail=f"Camion {truck_id} inconnu.")

    session = get_session()
    rows = session.execute(ps.select_positions, (truck_id, limit))

    return [
        PositionRecord(
            truck_id=row.truck_id,
            event_time=row.event_time,
            latitude=row.latitude,
            longitude=row.longitude,
            temperature=row.temperature,
            cargo_status=row.cargo_status,
            speed_kmh=row.speed_kmh,
        )
        for row in rows
    ]


# =============================================================================
# ENDPOINT 2 : GET /alerts/{date}
# =============================================================================

@app.get(
    "/alerts/{alert_date}",
    response_model=List[AlertRecord],
    summary="Alertes de temperature par date",
    tags=["Alertes"],
)
def get_alerts_by_date(alert_date: str):
    """
    Retourne toutes les alertes de temperature pour une date donnee.
    Format de la date : YYYY-MM-DD
    Utilise alerts_by_day avec la Partition Key alert_date.
    """
    try:
        parsed_date = date.fromisoformat(alert_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Format de date invalide. Utilisez YYYY-MM-DD.",
        )

    session = get_session()
    rows = session.execute(ps.select_alerts, (parsed_date,))

    return [
        AlertRecord(
            alert_date=row.alert_date,
            event_time=row.event_time,
            truck_id=row.truck_id,
            temperature=row.temperature,
            alert_type=row.alert_type,
            latitude=row.latitude,
            longitude=row.longitude,
        )
        for row in rows
    ]


# =============================================================================
# ENDPOINT 3 : GET /trucks/{truck_id}/stats
# =============================================================================

@app.get(
    "/trucks/{truck_id}/stats",
    response_model=List[TruckStats],
    summary="Statistiques horaires d'un camion",
    tags=["Statistiques"],
)
def get_truck_stats(truck_id: str):
    if truck_id not in TRUCK_IDS:
        raise HTTPException(status_code=404, detail=f"Camion {truck_id} inconnu.")

    session = get_session()
    from datetime import timezone, timedelta

    # Generation des cles stat_hour pour les 24 dernieres heures
    now = datetime.now(timezone.utc)
    results = []
    for h in range(24):
        hour = now - timedelta(hours=h)
        stat_hour = f"{truck_id}_{hour.strftime('%Y%m%d%H')}"
        rows = list(session.execute(ps.select_stats_truck, (truck_id, stat_hour)))
        for row in rows:
            results.append(TruckStats(
                truck_id=row.truck_id,
                stat_hour=row.stat_hour,
                avg_temperature=row.avg_temperature,
                max_temperature=row.max_temperature,
                min_temperature=row.min_temperature,
                record_count=row.record_count,
                last_updated=row.last_updated,
            ))

    if not results:
        raise HTTPException(status_code=404, detail=f"Aucune statistique pour {truck_id}.")
    return results


# =============================================================================
# ENDPOINT 4 : GET /dashboard/latest
# =============================================================================

@app.get(
    "/dashboard/latest",
    response_model=List[PositionRecord],
    summary="Derniere position de chaque camion",
    tags=["Dashboard"],
)
def get_dashboard_latest():
    """
    Retourne la derniere position connue de chacun des 10 camions.
    Effectue 10 requetes en parallele via un executor de threads
    et fusionne les resultats.
    """
    session = get_session()

    def fetch_latest(truck_id: str):
        """Recupere la derniere position d'un camion."""
        rows = list(session.execute(ps.select_latest, (truck_id,)))
        if rows:
            row = rows[0]
            return PositionRecord(
                truck_id=row.truck_id,
                event_time=row.event_time,
                latitude=row.latitude,
                longitude=row.longitude,
                temperature=row.temperature,
                cargo_status=row.cargo_status,
                speed_kmh=row.speed_kmh,
            )
        return None

    # Execution parallele des 10 requetes via ThreadPoolExecutor
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_latest, truck_id) for truck_id in TRUCK_IDS]
        results = [f.result() for f in futures]

    # Filtrage des camions sans donnees
    return [r for r in results if r is not None]


# =============================================================================
# ENDPOINT 5 : GET /health
# =============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Etat de la connexion Cassandra",
    tags=["Systeme"],
)
def get_health():
    """
    Verifie la connexion a Cassandra et retourne le nombre total
    d'enregistrements dans tracking_by_truck.
    """
    try:
        session = get_session()
        row = session.execute(ps.select_count).one()
        record_count = row[0] if row else 0
        return HealthResponse(
            status="ok",
            cassandra="connected",
            record_count=record_count,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cassandra non disponible : {exc}",
        )


# =============================================================================
# ENDPOINT 6 : GET /trucks
# =============================================================================

@app.get(
    "/trucks",
    response_model=List[TruckSummary],
    summary="Liste des camions avec derniere position",
    tags=["Tracking"],
)
def get_trucks():
    """
    Retourne la liste des 10 camions connus avec leur derniere
    position, timestamp et temperature.
    """
    session = get_session()

    def fetch_summary(truck_id: str) -> TruckSummary:
        """Recupere le resume d'un camion."""
        rows = list(session.execute(ps.select_latest, (truck_id,)))
        if rows:
            row = rows[0]
            return TruckSummary(
                truck_id=truck_id,
                last_seen=row.event_time,
                last_latitude=row.latitude,
                last_longitude=row.longitude,
                last_temp=row.temperature,
                last_status=row.cargo_status,
            )
        return TruckSummary(
            truck_id=truck_id,
            last_seen=None,
            last_latitude=None,
            last_longitude=None,
            last_temp=None,
            last_status=None,
        )

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_summary, truck_id) for truck_id in TRUCK_IDS]
        return [f.result() for f in futures]
