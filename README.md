# Systeme de Suivi IoT Temps Reel avec Apache Cassandra

| Champ | Valeur |
|---|---|
| **Etudiant** | `[NOM PRENOM — A REMPLACER]` |
| **Module** | NoSQL pour le Big Data |
| **Enseignant** | Dr. B. BENCHARIF |
| **Universite** | Universite Saad Dahlab — Blida 1 |
| **Filiere** | M1 DS&NLP |
| **Annee** | 2025/2026 |
| **Bareme** | 12 pts + 1 pt Bonus |

---

## Apercu du projet

Ce projet implemente un systeme de suivi logistique IoT simulant **10 camions** qui envoient des donnees GPS en temps reel vers **Apache Cassandra**. Le schema de donnees suit le paradigme **Query-Driven Modeling** : chaque table est concue pour repondre a une requete precise sans jamais utiliser `ALLOW FILTERING`. Un backend **FastAPI** expose les donnees via une API REST utilisant exclusivement des Prepared Statements, et un dashboard **Streamlit** permet la visualisation en temps reel des positions, temperatures et alertes sur une carte interactive centree sur l'Algerie.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  generator.py ──────► Cassandra 4.1 ◄──── FastAPI       │
│  (10 threads)         (port 9042)         (port 8000)   │
│                           ▲                   ▲         │
│                           │                   │         │
│                       schema.cql          Streamlit     │
│                       (3 tables)          (port 8501)   │
└─────────────────────────────────────────────────────────┘
```

**Flux de donnees :**
```
generator.py → [tracking_by_truck]  → FastAPI /trucks/{id}/positions → Streamlit
             → [alerts_by_day]      → FastAPI /alerts/{date}         → Streamlit
             → [truck_stats]        → FastAPI /trucks/{id}/stats      → Streamlit
```

---

## Prerequis

| Outil | Version minimale | Verification |
|---|---|---|
| Docker Desktop | 4.x | `docker --version` |
| Python | 3.10+ | `python --version` |
| Git | 2.x | `git --version` |

> **Important (Windows) :** Docker Desktop doit etre **demarre** (icone verte dans la barre des taches) avant toute commande `docker`.

---

## Demarrage rapide

### Etape 1 — Cloner le projet

```bash
git clone <URL_DU_DEPOT>
cd nosql_project
```

### Etape 2 — Demarrer l'infrastructure Docker

```bash
docker-compose up -d cassandra
```

> Cette commande demarre uniquement Cassandra. Les services `api` et `streamlit` seront demarres manuellement apres l'ingestion des donnees. Le flag `-d` execute les conteneurs en arriere-plan.

### Etape 3 — Verifier que Cassandra est prete

```bash
docker ps
```

Attendre que le statut affiche `(healthy)` — cela prend environ **2 minutes** :

```
CONTAINER ID   IMAGE          STATUS
xxxxxxxxxxxx   cassandra:4.1  Up 2 minutes (healthy)
```

Verification supplementaire :

```bash
docker exec -it cassandra_iot nodetool status
# Attendu : UN  172.x.x.x  datacenter1  rack1
```

### Etape 4 — Charger le schema CQL

```bash
docker exec -it cassandra_iot cqlsh -f /db/schema.cql
```

> Le dossier `db/` est monte en lecture seule dans le conteneur via le volume `./db:/db:ro` declare dans `docker-compose.yml`. Aucune sortie = aucune erreur = succes.

Verification des 3 tables creees :

```bash
docker exec -it cassandra_iot cqlsh -e "DESCRIBE KEYSPACE logistics_ks;"
```

### Etape 5 — Installer les dependances Python et lancer l'ingestion

```bash
# Installation des dependances (une seule fois)
pip install -r requirements.txt
pip install gevent

# Lancer le script d'ingestion dans un terminal dedie
python backend/generator.py
```

> Le script lance **10 threads** (un par camion). Laisser tourner **17 minutes minimum** pour atteindre 10 000 enregistrements. Appuyer sur `Ctrl+C` pour arreter proprement.

Verification en temps reel (dans un second terminal) :

```bash
docker exec -it cassandra_iot cqlsh -e "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

### Etape 6 — Verifier le COUNT >= 10 000

```bash
docker exec -it cassandra_iot cqlsh -e "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

Resultat attendu :

```
 count
-------
 10746
(1 rows)
```

> **Faire une capture d'ecran de cette commande — obligatoire dans le rapport.**

### Etape 7 — Demarrer le backend FastAPI

```bash
python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Verification :

```bash
curl.exe http://localhost:8000/health
# Attendu : {"status":"ok","cassandra":"connected","record_count":10746}
```

Documentation interactive : **http://localhost:8000/docs**

### Etape 8 — Demarrer le dashboard Streamlit

Dans un nouveau terminal :

```bash
python -m streamlit run streamlit_app.py
```

Dashboard : **http://localhost:8501**

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

Warnings :
Aggregation query used without partition key
```

> **Note :** Le warning `Aggregation query used without partition key` est attendu et normal pour un `COUNT(*)` global. Il n'est present que dans cette commande de verification — jamais dans le code applicatif.

> **Screenshot de cette commande obligatoire dans le rapport** (Section 5 — Journal d'ingestion).

---

## Structure du projet

```
nosql_project/
├── db/
│   └── schema.cql              # Schema CQL — 3 tables Query-Driven
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

## Decisions de conception cles

- **Query-Driven Modeling** : chaque table Cassandra (`tracking_by_truck`, `alerts_by_day`, `truck_stats`) est concue pour repondre a exactement une requete de l'interface, sans jamais utiliser `ALLOW FILTERING` — garantissant des acces O(1) via la Partition Key.

- **Partition Key `truck_id`** dans `tracking_by_truck` : toutes les positions d'un camion sont co-localisees sur le meme noeud Cassandra. La Clustering Column `event_time DESC` stocke physiquement les donnees du plus recent au plus ancien — `LIMIT 50` lit exactement 50 lignes sans tri supplementaire.

- **Prepared Statements obligatoires** : tous les `INSERT` et `SELECT` Python utilisent des Prepared Statements prepares une seule fois avant le lancement des threads. Cassandra parse et planifie la requete une seule fois, puis reutilise le plan d'execution en cache — gain de performance critique a 10 inserts/seconde.

- **Architecture decouplee** : le dashboard Streamlit ne se connecte jamais directement a Cassandra — il passe exclusivement par l'API FastAPI. Ce couplage faible permet de remplacer ou scaler independamment chaque composant.

- **Fix Python 3.12 + Windows** : le module `asyncore` ayant ete supprime en Python 3.12, le driver `cassandra-driver` utilise `GeventConnection` comme event loop de remplacement, installe via `pip install gevent`.

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

## Resultats obtenus

| Phase | Critere | Resultat | Points |
|---|---|---|---|
| Phase 1 | Infrastructure Docker | cassandra_iot healthy, version 4.1.11 | **1 pt Bonus** |
| Phase 2 | Modelisation CQL | 3 tables, zero ALLOW FILTERING | **3 pts** |
| Phase 3 | Ingestion | 10 746 enregistrements confirmes | **3 pts** |
| Phase 4 | Qualite du code | 5 Prepared Statements, FastAPI propre | **1 pt** |
| Phase 5 | Bonus UI | Dashboard Streamlit fonctionnel | **Bonus** |
| **Total** | | | **8 pts + Bonus** |

---

## References

- Documentation officielle Apache Cassandra : https://cassandra.apache.org/doc/latest/
- DataStax Python Driver : https://docs.datastax.com/en/developer/python-driver/3.29/
- FastAPI : https://fastapi.tiangolo.com
- Streamlit : https://docs.streamlit.io
- Pydeck : https://deckgl.readthedocs.io
- Docker Compose : https://docs.docker.com/compose/
