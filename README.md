# Systeme de Suivi IoT Temps Reel avec Apache Cassandra

| Champ | Valeur |
|---|---|
| **Etudiant** | Abdelaziz Merzoug |
| **Module** | NoSQL pour le Big Data |
| **Enseignant** | Dr. B. BENCHARIF |
| **Universite** | Universite Saad Dahlab — Blida 1 |
| **Filiere** | M1 DS&NLP |
| **Annee** | 2025/2026 |
---

## Apercu du projet

Ce projet implemente un systeme de suivi logistique IoT simulant **10 camions** qui envoient des donnees GPS en temps reel vers **Apache Cassandra**. Le schema de donnees suit le paradigme **Query-Driven Modeling** : chaque table est concue pour repondre a une requete precise sans jamais utiliser `ALLOW FILTERING`. Un backend **FastAPI** expose les donnees via une API REST utilisant exclusivement des Prepared Statements, et un dashboard **Streamlit** permet la visualisation en temps reel des positions, temperatures et alertes sur une carte interactive centree sur l'Algerie.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Compose                          │
│                                                             │
│  generator.py ──────► Cassandra 4.1 ◄──── FastAPI (app.py) │
│  (10 threads)         (port 9042)         (port 8000)       │
│                            ▲                   ▲            │
│                            │                   │            │
│                        schema.cql          Streamlit        │
│                        (3 tables)          (port 8501)      │
└─────────────────────────────────────────────────────────────┘
```

**Flux de donnees :**
```
generator.py → [tracking_by_truck]  → FastAPI /trucks/{id}/positions → Streamlit
             → [alerts_by_day]      → FastAPI /alerts/{date}         → Streamlit
             → [truck_stats]        → FastAPI /trucks/{id}/stats      → Streamlit
```

**Stack technique :**

| Composant | Technologie | Version |
|---|---|---|
| Base de donnees | Apache Cassandra | 4.1.11 |
| Driver Python | cassandra-driver | 3.29.1 |
| Event loop (Python 3.12) | gevent | 23.9.1 |
| Backend API | FastAPI + Uvicorn | 0.111.0 |
| Dashboard | Streamlit | 1.35.0 |
| Cartographie | Folium + Pydeck | 0.16.0 / 0.9.1 |
| Orchestration | Docker Compose | 3.8 |

---

## Prerequis

| Outil | Version minimale | Verification |
|---|---|---|
| Docker Desktop | 4.x | `docker --version` |
| Python | 3.10+ | `python --version` |
| Git | 2.x | `git --version` |

> **Important (Windows) :** Docker Desktop doit etre **demarre** (icone verte dans la barre des taches) avant toute commande `docker`.

> **Important (Python 3.12) :** Le module `asyncore` a ete supprime en Python 3.12. Ce projet utilise `gevent` comme event loop de remplacement. Voir Etape 5.

---

## Structure du projet

```
nosql_project/
├── db/
│   └── schema.cql              # Schema CQL — 3 tables Query-Driven Modeling
├── backend/
│   ├── generator.py            # Simulation GPS — 10 camions / 10 threads
│   └── app.py                  # API REST FastAPI — 6 endpoints
├── streamlit_app.py            # Dashboard monitoring temps reel
├── docker-compose.yml          # Orchestration : cassandra + api + streamlit
├── Dockerfile.api              # Image Docker pour FastAPI (Python 3.10)
├── Dockerfile.streamlit        # Image Docker pour Streamlit (Python 3.10)
├── requirements.txt            # Dependances Python epinglees
└── README.md                   # Ce fichier
```

---

## Demarrage rapide (pas a pas)

### Etape 1 — Cloner le projet

```bash
git clone <URL_DU_DEPOT>
cd nosql_project
```

---

### Etape 2 — Demarrer Cassandra

```bash
docker-compose up -d cassandra
```

> Cette commande demarre uniquement le service `cassandra`. Les services `api` et `streamlit` sont demarres manuellement dans les etapes suivantes. Le flag `-d` execute le conteneur en arriere-plan.

**Ce que fait Docker en coulisses :**
- Telecharge l'image `cassandra:4.1` si absente
- Cree le conteneur `cassandra_iot`
- Alloue 512 Mo de heap JVM (adapte aux machines de dev)
- Monte le dossier `./db` en lecture seule sur `/db` dans le conteneur
- Configure un healthcheck qui verifie la disponibilite CQL toutes les 30 secondes

---

### Etape 3 — Attendre que Cassandra soit prete (2 minutes)

```bash
docker ps
```

Attendre que le statut passe de `(health: starting)` a `(healthy)` :

```
CONTAINER ID   IMAGE           STATUS
xxxxxxxxxxxx   cassandra:4.1   Up 2 minutes (healthy)
```

**Verification supplementaire :**

```bash
# Verifier que le noeud est Up/Normal
docker exec -it cassandra_iot nodetool status
```

Sortie attendue :
```
Datacenter: datacenter1
=======================
UN  172.18.0.2  ... rack1
```

`UN` signifie Up/Normal — le noeud est operationnel.

```bash
# Verifier la version Cassandra
docker exec -it cassandra_iot cqlsh -e "SELECT release_version FROM system.local;"
```

Sortie attendue :
```
 release_version
-----------------
          4.1.11
```

---

### Etape 4 — Charger le schema CQL

```bash
docker exec -it cassandra_iot cqlsh -f /db/schema.cql
```

> Le dossier `db/` est monte dans le conteneur via le volume `./db:/db:ro` declare dans `docker-compose.yml`. Le fichier `schema.cql` est donc accessible a `/db/schema.cql` depuis l'interieur du conteneur.

**Aucune sortie = aucune erreur = succes.**

**Verification des 3 tables creees :**

```bash
docker exec -it cassandra_iot cqlsh -e "DESCRIBE KEYSPACE logistics_ks;"
```

Vous devez voir les 3 tables : `tracking_by_truck`, `alerts_by_day`, `truck_stats`.

**Test des requetes cibles (sans ALLOW FILTERING) :**

```bash
# Table 1 — Historique GPS d'un camion
docker exec -it cassandra_iot cqlsh -e "SELECT * FROM logistics_ks.tracking_by_truck WHERE truck_id = 'TRUCK_001' LIMIT 50;"

# Table 2 — Alertes par date
docker exec -it cassandra_iot cqlsh -e "SELECT * FROM logistics_ks.alerts_by_day WHERE alert_date = '2026-04-01';"

# Table 3 — Statistiques horaires
docker exec -it cassandra_iot cqlsh -e "SELECT * FROM logistics_ks.truck_stats WHERE truck_id = 'TRUCK_001' AND stat_hour = 'TRUCK_001_2026040109';"
```

> Resultats vides = normal a ce stade. L'important est qu'aucune erreur ne s'affiche.

---

### Etape 5 — Installer les dependances Python

```bash
# Installer toutes les dependances epinglees
pip install -r requirements.txt

# Installer gevent (fix Python 3.12 — asyncore supprime)
pip install gevent
```

> **Pourquoi gevent ?** Le module `asyncore` utilise par defaut par `cassandra-driver` a ete retire de Python 3.12. `gevent` fournit un event loop de remplacement compatible.

---

### Etape 6 — Lancer l'ingestion des donnees

**Ouvrir un terminal dedie (ne pas fermer pendant la simulation) :**

```bash
python backend/generator.py
```

**Sortie attendue au demarrage :**
```
=================================================================
  SIMULATEUR IoT — SUIVI GPS TEMPS REEL
  Connexion a Cassandra : 127.0.0.1:9042
  Keyspace              : logistics_ks
  Camions               : 10
  Interval d'insertion  : 0.5s - 1.5s par camion
  Seuil alerte temp.    : 35.0 degres C
=================================================================
[INIT] Connexion a Cassandra en cours...
[INIT] Connexion etablie sur 127.0.0.1:9042
[INIT] Preparation des Prepared Statements...
[INIT] 3 Prepared Statements prepares avec succes.
[INIT] Lancement de 10 threads de simulation...

[TRUCK_001] Thread demarre — Route A | lat=36.6733 lon=2.9709
[TRUCK_002] Thread demarre — Route A | lat=36.4358 lon=2.8051
[TRUCK_003] Thread demarre — Route A | lat=36.5298 lon=3.0578
[TRUCK_004] Thread demarre — Route A | lat=36.6429 lon=3.0861
[TRUCK_005] Thread demarre — Route B | lat=36.3010 lon=2.8562
[TRUCK_006] Thread demarre — Route B | lat=36.2152 lon=2.8166
[TRUCK_007] Thread demarre — Route B | lat=36.3600 lon=2.8763
[TRUCK_008] Thread demarre — Route C | lat=36.7676 lon=3.2508
[TRUCK_009] Thread demarre — Route C | lat=36.7001 lon=3.3681
[TRUCK_010] Thread demarre — Route C | lat=36.7053 lon=3.5768

[INFO] Simulation en cours. Appuyez sur Ctrl+C pour arreter.
```

**Logs de progression (toutes les 100 insertions par camion) :**
```
[TRUCK_001]    100 enregistrements | temp=32.4C | lat=36.5821 lon=2.9134 | statut=EN_ROUTE
[TRUCK_006]    100 enregistrements | temp=37.1C | lat=36.2891 lon=2.8445 | statut=EN_LIVRAISON
```

**Calcul du temps d'ingestion :**
```
Intervalle moyen  = (0.5 + 1.5) / 2 = 1.0 seconde par camion
Debit total       = 10 camions x 1 insert/sec = 10 inserts/sec
Temps pour 10 000 = 10 000 / 10 = 1 000 secondes ≈ 17 minutes
Recommandation    : laisser tourner 17-20 minutes
```

---

### Etape 7 — Verifier le COUNT >= 10 000

**Dans un second terminal (pendant que generator.py tourne) :**

```bash
docker exec -it cassandra_iot cqlsh -e "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

**Resultat attendu apres ~17 minutes :**

```
 count
-------
 10746
(1 rows)

Warnings :
Aggregation query used without partition key
```

> **Note :** Le warning est normal pour un `COUNT(*)` global — jamais present dans le code applicatif.

**Arreter le script proprement :**
```
Ctrl+C
```

---

### Etape 8 — Demarrer le backend FastAPI

**Nouveau terminal :**

```bash
python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**Sortie attendue :**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
[APP] Tous les Prepared Statements sont prets.
INFO:     Application startup complete.
```

**Verification :**
```bash
curl.exe http://localhost:8000/health
# {"status":"ok","cassandra":"connected","record_count":10746}
```

**Swagger UI :** http://localhost:8000/docs

---

### Etape 9 — Demarrer le dashboard Streamlit

**Troisieme terminal :**

```bash
python -m streamlit run streamlit_app.py
```

**Dashboard :** http://localhost:8501

---

## Preuve des 10 000 enregistrements

```bash
docker exec -it cassandra_iot cqlsh -e "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

**Sortie obtenue :**
```
 count
-------
 10746
(1 rows)
```

> **Screenshot de cette commande obligatoire dans le rapport** (Section 5 — Journal d'ingestion).

---

## API — Endpoints disponibles

| Methode | Endpoint | Description |
|---|---|---|
| GET | `/health` | Statut Cassandra + record count |
| GET | `/trucks` | Liste des 10 camions avec derniere position |
| GET | `/trucks/{truck_id}/positions` | Historique GPS (param: `limit`) |
| GET | `/trucks/{truck_id}/stats` | Statistiques horaires pre-agreges |
| GET | `/alerts/{date}` | Alertes temperature par date (YYYY-MM-DD) |
| GET | `/dashboard/latest` | Derniere position de chaque camion |
| GET | `/docs` | Documentation Swagger interactive |

---

## Schema CQL — Decisions de modelisation

### Table 1 — tracking_by_truck
```sql
PRIMARY KEY (truck_id, event_time)
CLUSTERING ORDER BY (event_time DESC)
-- Requete : SELECT * WHERE truck_id = ? LIMIT 50
-- truck_id → co-localisation sur un noeud, O(1)
-- event_time DESC → 50 derniers physiquement en tete de partition
```

### Table 2 — alerts_by_day
```sql
PRIMARY KEY (alert_date, event_time, truck_id)
CLUSTERING ORDER BY (event_time DESC, truck_id ASC)
-- Requete : SELECT * WHERE alert_date = ?
-- alert_date → toutes les alertes d'une journee sur un noeud
```

### Table 3 — truck_stats
```sql
PRIMARY KEY ((truck_id, stat_hour))   -- cle composite anti-hotspot
-- Requete : SELECT * WHERE truck_id = ? AND stat_hour = ?
-- Une partition = un camion + une heure = une seule ligne d'agregat
```

---

## Decisions de conception cles

- **Query-Driven Modeling** : chaque table repond a exactement une requete de l'interface, sans jamais utiliser `ALLOW FILTERING`.
- **Prepared Statements** : 3 dans `generator.py`, 5 dans `app.py`, tous declares une seule fois. Cassandra parse la requete une fois, reutilise le plan en cache pour toutes les insertions suivantes.
- **Architecture multi-thread** : 10 threads (un par camion), arret propre via `threading.Event`, compteurs thread-safe via `threading.Lock`.
- **Architecture decouplee** : Streamlit ne se connecte jamais directement a Cassandra — uniquement via l'API FastAPI.
- **Fix Python 3.12** : `asyncore` supprime → remplace par `GeventConnection` via `gevent`.

---

## Troubleshooting

| Probleme | Cause | Solution |
|---|---|---|
| `npipe error` | Docker Desktop ferme | Ouvrir Docker Desktop, attendre icone verte |
| `ConnectionRefusedError` | Cassandra pas prete | Attendre `(healthy)` et retester avec `cqlsh` |
| `DependencyException` | Python 3.12 sans gevent | `pip install gevent` |
| `OperationTimedOut` | Cassandra demarre recemment | Attendre 2 min, tester `cqlsh` avant relance |
| Warning `version` obsolete | Docker Compose recente | Inoffensif, ignorer |
| `DeprecationWarning` uvicorn | Driver 3.x cosmétique | Aucun impact fonctionnel |

---

## References

- Documentation officielle Apache Cassandra : https://cassandra.apache.org/doc/latest/
- DataStax Python Driver : https://docs.datastax.com/en/developer/python-driver/3.29/
- FastAPI : https://fastapi.tiangolo.com
- Streamlit : https://docs.streamlit.io
- Gevent : https://www.gevent.org/
- Docker Compose : https://docs.docker.com/compose/