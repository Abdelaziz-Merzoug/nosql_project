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
| Base de donnees | Apache Cassandra | 4.1 |
| Driver Python | cassandra-driver | 3.29.1 |
| Event loop (Python 3.12) | gevent | 23.9.1 |
| Backend API | FastAPI + Uvicorn | 0.111.0 |
| Dashboard | Streamlit | 1.35.0 |
| Cartographie | Folium + Pydeck | 0.16.0 / 0.9.1 |
| Orchestration | Docker Compose | 3.8 |

---

## Prerequis

Verifier que les outils suivants sont installes avant de commencer :

| Outil | Version minimale | Commande de verification |
|---|---|---|
| Docker Desktop | 4.x | `docker --version` |
| Python | 3.10+ | `python --version` |
| Git | 2.x | `git --version` |

> **Important (Windows) :** Docker Desktop doit etre **demarre** (icone verte dans la barre des taches) avant toute commande `docker`. Si vous voyez une erreur `npipe`, c'est que Docker n'est pas demarre.

> **Important (Python 3.12) :** Le module `asyncore` a ete supprime en Python 3.12. Ce projet utilise `gevent` comme event loop de remplacement — il est inclus dans `requirements.txt` et s'installe automatiquement.

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

> Ce guide utilise le **mode developpement local** : Cassandra tourne dans Docker,
> le generateur, l'API et le dashboard tournent en Python local.
> Un mode Docker complet (tout en conteneurs) est documente en fin de README.

---

### Etape 1 — Recuperer le projet

**Option A — Via Git :**
```bash
git clone https://github.com/Abdelaziz-Merzoug/nosql_project.git
cd nosql_project
```

**Option B — Via ZIP (si pas de Git) :**
Telecharger le ZIP depuis la plateforme du cours, extraire le dossier, puis ouvrir un terminal dans ce dossier.

---

### Etape 2 — Creer un environnement virtuel Python

> Cette etape isole les dependances du projet de votre installation Python globale.
> Elle est fortement recommandee pour eviter les conflits de versions.

**Windows (PowerShell) :**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS :**
```bash
python3 -m venv venv
source venv/bin/activate
```

Votre terminal doit afficher `(venv)` au debut de la ligne — signe que l'environnement est actif.

---

### Etape 3 — Installer les dependances Python

```bash
pip install -r requirements.txt
```

Cette commande installe toutes les dependances epinglees, dont `gevent` (fix Python 3.12), `cassandra-driver`, `fastapi`, `streamlit`, et les bibliotheques cartographiques.

**Verification :**
```bash
pip show cassandra-driver
# Version: 3.29.1
```

---

### Etape 4 — Demarrer Cassandra via Docker

```bash
docker-compose up -d cassandra
```

> Le flag `-d` demarre le conteneur en arriere-plan (detached mode).
> Seul le service `cassandra` est demarre ici — l'API et le dashboard
> seront lances manuellement en Python dans les etapes suivantes.

**Ce que fait Docker en coulisses :**
- Telecharge l'image `cassandra:4.1` depuis Docker Hub (une seule fois, ~400 Mo)
- Cree le conteneur nomme `cassandra_iot`
- Alloue 512 Mo de heap JVM (adapte aux machines de developpement)
- Monte le dossier `./db` en lecture seule sur `/db` dans le conteneur
- Configure un healthcheck CQL toutes les 30 secondes

---

### Etape 5 — Attendre que Cassandra soit prete (~2 minutes)

Cassandra prend 60 a 90 secondes pour demarrer sa JVM. Verifier le statut avec :

```bash
docker ps
```

Attendre que le statut passe de `(health: starting)` a `(healthy)` :

```
CONTAINER ID   IMAGE           STATUS
xxxxxxxxxxxx   cassandra:4.1   Up 2 minutes (healthy)
```

> **Ne pas passer a l'etape suivante tant que le statut n'est pas `(healthy)`.**
> Une connexion trop precoce provoquera une erreur `ConnectionRefusedError` ou `OperationTimedOut`.

**Verification supplementaire :**

```bash
# Verifier que le noeud Cassandra est operationnel (UN = Up/Normal)
docker exec -it cassandra_iot nodetool status
```

Sortie attendue :
```
Datacenter: datacenter1
=======================
UN  172.18.0.2  ...
```

```bash
# Verifier la version Cassandra
docker exec -it cassandra_iot cqlsh -e "SELECT release_version FROM system.local;"
```

Sortie attendue :
```
 release_version
-----------------
          4.1.x
```

---

### Etape 6 — Charger le schema CQL

```bash
docker exec -it cassandra_iot cqlsh -f /db/schema.cql
```

> Le dossier `db/` est monte automatiquement dans le conteneur via le volume
> `./db:/db:ro` declare dans `docker-compose.yml`.

**Aucune sortie = aucune erreur = succes.**

**Verification — les 3 tables doivent etre visibles :**

```bash
docker exec -it cassandra_iot cqlsh -e "DESCRIBE KEYSPACE logistics_ks;"
```

Vous devez voir les 3 tables : `tracking_by_truck`, `alerts_by_day`, `truck_stats`.

**Test rapide des 3 requetes cibles (sans ALLOW FILTERING) :**

```bash
# Table 1 — Historique GPS d'un camion
docker exec -it cassandra_iot cqlsh -e \
  "SELECT * FROM logistics_ks.tracking_by_truck WHERE truck_id = 'TRUCK_001' LIMIT 5;"

# Table 2 — Alertes par date (remplacer la date par aujourd'hui)
docker exec -it cassandra_iot cqlsh -e \
  "SELECT * FROM logistics_ks.alerts_by_day WHERE alert_date = '2026-04-02';"

# Table 3 — Statistiques horaires
docker exec -it cassandra_iot cqlsh -e \
  "SELECT * FROM logistics_ks.truck_stats WHERE truck_id = 'TRUCK_001' AND stat_hour = 'TRUCK_001_2026040209';"
```

> Resultats vides = normal a ce stade (aucune donnee encore ingeree).
> L'important est qu'**aucune erreur** ne s'affiche.

---

### Etape 7 — Lancer l'ingestion des donnees

> Ouvrir un **terminal dedie** pour cette etape — ne pas le fermer pendant la simulation.
> L'environnement virtuel `(venv)` doit etre actif dans ce terminal.

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
...
[INFO] Simulation en cours. Appuyez sur Ctrl+C pour arreter.
```

**Progression (log toutes les 100 insertions par camion) :**
```
[TRUCK_001]    100 enregistrements | temp=32.4C | lat=36.5821 | statut=EN_ROUTE
[TRUCK_006]    100 enregistrements | temp=37.1C | lat=36.2891 | statut=EN_LIVRAISON
```

**Duree estimee pour atteindre 10 000 enregistrements :**
```
Intervalle moyen = (0.5 + 1.5) / 2 = 1.0 seconde par camion
Debit total      = 10 camions x 1 insert/sec = 10 inserts/sec
Temps cible      = 10 000 / 10 = 1 000 sec ≈ 17 minutes
Recommandation   : laisser tourner 17 a 20 minutes
```

**Suivi de progression (dans un 2eme terminal) :**
```bash
docker exec -it cassandra_iot cqlsh -e \
  "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

Relancer cette commande toutes les 5 minutes pour voir le compteur augmenter.

---

### Etape 8 — Verifier le COUNT >= 10 000

Une fois les 17-20 minutes ecoulees, verifier le total dans un second terminal :

```bash
docker exec -it cassandra_iot cqlsh -e \
  "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

**Resultat attendu :**
```
 count
-------
 10746
(1 rows)

Warnings :
Aggregation query used without partition key
```

> **Note :** Le warning `Aggregation query used without partition key` est attendu
> et normal pour un `COUNT(*)` global. Il indique que Cassandra a scanne toutes
> les partitions pour compter. Cette commande est uniquement pour verification —
> elle n'apparait jamais dans le code applicatif.

**Arreter le simulateur proprement :**
```
Ctrl+C
```

Le script affiche un tableau recapitulatif par camion avant de quitter.

---

### Etape 9 — Demarrer le backend FastAPI

> Ouvrir un **nouveau terminal** avec `(venv)` actif.

```bash
python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

**Sortie attendue :**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
[APP] Tous les Prepared Statements sont prets.
INFO:     Application startup complete.
```

**Verification de l'API :**

Windows PowerShell :
```powershell
curl.exe http://localhost:8000/health
```

Linux / macOS :
```bash
curl http://localhost:8000/health
```

Reponse attendue :
```json
{"status":"ok","cassandra":"connected","record_count":10746}
```

**Documentation interactive Swagger :** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Etape 10 — Demarrer le dashboard Streamlit

> Ouvrir un **troisieme terminal** avec `(venv)` actif.

```bash
python -m streamlit run streamlit_app.py
```

**Dashboard :** [http://localhost:8501](http://localhost:8501)

Le dashboard affiche :
- Carte interactive avec les 10 camions (vert = normal, rouge = alerte temperature)
- KPI : total enregistrements, camions actifs, alertes du jour, temperature moyenne
- Historique GPS par camion avec tracé de route
- Tableau des alertes de temperature par date

---

## Mode Docker Complet (tout en conteneurs)

> Cette methode demarre les 3 services (cassandra + api + streamlit) via Docker
> sans aucune installation Python locale. Utile pour une demonstration rapide.

```bash
# Demarrer tous les services (cassandra d'abord, puis api et streamlit automatiquement)
docker-compose up -d

# Suivre les logs en temps reel
docker-compose logs -f

# Verifier que les 3 services sont actifs
docker-compose ps
```

Ensuite, charger le schema et lancer le generateur en local (Etapes 6 et 7 ci-dessus).

**Arreter tous les services :**
```bash
docker-compose down
```

**Arreter et supprimer les donnees (reset complet) :**
```bash
docker-compose down -v
```

---

## Preuve des 10 000 enregistrements

```bash
docker exec -it cassandra_iot cqlsh -e \
  "SELECT count(*) FROM logistics_ks.tracking_by_truck;"
```

**Sortie obtenue :**
```
 count
-------
 10746
(1 rows)
```

---

## API — Endpoints disponibles

| Methode | Endpoint | Description |
|---|---|---|
| GET | `/health` | Statut Cassandra + nombre total d'enregistrements |
| GET | `/trucks` | Liste des 10 camions avec derniere position connue |
| GET | `/trucks/{truck_id}/positions` | Historique GPS d'un camion (param: `limit`, defaut 50) |
| GET | `/trucks/{truck_id}/stats` | Statistiques horaires pre-aggregees (24 dernieres heures) |
| GET | `/alerts/{date}` | Alertes temperature par date au format `YYYY-MM-DD` |
| GET | `/dashboard/latest` | Derniere position de chacun des 10 camions |
| GET | `/docs` | Documentation Swagger interactive |

---

## Schema CQL — Decisions de modelisation

### Table 1 — tracking_by_truck
```sql
PRIMARY KEY (truck_id, event_time)
CLUSTERING ORDER BY (event_time DESC)
-- Requete ciblee : SELECT * WHERE truck_id = ? LIMIT 50
-- truck_id  → co-localisation sur un noeud Cassandra, acces O(1)
-- event_time DESC → les 50 enregistrements les plus recents
--                   sont physiquement en tete de partition
```

### Table 2 — alerts_by_day
```sql
PRIMARY KEY (alert_date, event_time, truck_id)
CLUSTERING ORDER BY (event_time DESC, truck_id ASC)
-- Requete ciblee : SELECT * WHERE alert_date = ?
-- alert_date → toutes les alertes d'une journee sur le meme noeud
-- event_time DESC → alertes les plus recentes en premier
-- truck_id ASC → ordre deterministe si deux alertes a la meme milliseconde
```

### Table 3 — truck_stats
```sql
PRIMARY KEY ((truck_id, stat_hour))   -- cle de partition COMPOSITE
-- Requete ciblee : SELECT * WHERE truck_id = ? AND stat_hour = ?
-- Composite anti-hotspot : une partition = un camion + une fenetre horaire
-- Format stat_hour : 'TRUCK_001_2026040209' (truck_id + YYYYMMDDH)
```

---

## Decisions de conception cles

- **Query-Driven Modeling** : chaque table repond a exactement une requete de l'interface, sans jamais utiliser `ALLOW FILTERING`.
- **Prepared Statements** : 3 dans `generator.py`, 5 dans `app.py`, tous declares une seule fois au demarrage. Cassandra parse la requete une fois et reutilise le plan en cache.
- **Architecture multi-thread** : 10 threads (un par camion), arret propre via `threading.Event`, compteurs thread-safe via `threading.Lock`.
- **Architecture decouplee** : Streamlit ne se connecte jamais directement a Cassandra — uniquement via l'API FastAPI.
- **Singleton session** : `@lru_cache(maxsize=1)` sur `get_session()` garantit une seule connexion Cassandra pour toute la duree de vie de l'API.
- **Fix Python 3.12** : `asyncore` supprime en 3.12 → remplace par `GeventConnection` via `gevent`.

---

## Troubleshooting

| Probleme | Cause probable | Solution |
|---|---|---|
| `npipe error` ou `Cannot connect to Docker` | Docker Desktop ferme | Ouvrir Docker Desktop, attendre l'icone verte |
| `ConnectionRefusedError: [Errno 111]` | Cassandra pas encore prete | Attendre `(healthy)` dans `docker ps`, puis retenter |
| `OperationTimedOut` | Cassandra vient de demarrer | Attendre 2 min supplementaires, verifier avec `nodetool status` |
| `ModuleNotFoundError: gevent` | requirements.txt non installe | Relancer `pip install -r requirements.txt` dans `(venv)` |
| `ModuleNotFoundError: cassandra` | Venv non active | Activer le venv : `venv\Scripts\activate` (Windows) |
| `Address already in use :8000` | Un autre processus utilise le port | `taskkill /f /im python.exe` (Windows) ou `kill $(lsof -t -i:8000)` (Linux) |
| Warning `version` obsolete dans docker-compose | Version de Docker Compose recente | Inoffensif, ignorer |
| Warning `DeprecationWarning` dans uvicorn | Driver cassandra 3.x cosmétique | Aucun impact fonctionnel |
| Carte Streamlit vide ou noire | Aucune donnee dans Cassandra | Verifier que generator.py a insere des donnees (Etape 7) |

---

## References

- Documentation officielle Apache Cassandra 4.1 : https://cassandra.apache.org/doc/latest/
- DataStax Python Driver 3.29 : https://docs.datastax.com/en/developer/python-driver/3.29/
- O'Neil, P. et al. (1996). The Log-Structured Merge-Tree. Acta Informatica, 33(4).
- Gilbert, S. & Lynch, N. (2002). Brewer's conjecture. ACM SIGACT News, 33(2).
- FastAPI : https://fastapi.tiangolo.com
- Streamlit : https://docs.streamlit.io
- Gevent : https://www.gevent.org/
- Docker Compose : https://docs.docker.com/compose/
