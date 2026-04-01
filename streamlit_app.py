# =============================================================================
# streamlit_app.py
# Mini-Projet NoSQL : Systeme de Suivi IoT Temps Reel
# Module : NoSQL pour le Big Data | Dr. B. BENCHARIF | USDB Blida 1
# Annee : 2025/2026
# =============================================================================
# Description :
#   Dashboard de monitoring IoT en temps reel.
#   Se connecte UNIQUEMENT via l'API FastAPI — aucune connexion directe
#   a Cassandra depuis ce fichier.
#
# Utilisation :
#   streamlit run streamlit_app.py
# =============================================================================

import os
from datetime import date, datetime, timezone, timedelta

import httpx
import pandas as pd
import pydeck as pdk
import streamlit as st
import folium
from streamlit_folium import st_folium

# =============================================================================
# CONFIGURATION DE LA PAGE
# =============================================================================

st.set_page_config(
    layout="wide",
    page_title="IoT Logistics Monitor",
    page_icon="🚛",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CONFIGURATION DE L'API
# =============================================================================

BASE_URL = os.getenv("API_URL", "http://localhost:8000")

# Identifiants des 10 camions
TRUCK_IDS = [f"TRUCK_{str(i).zfill(3)}" for i in range(1, 11)]


# =============================================================================
# STYLES CSS PERSONNALISES
# =============================================================================

st.markdown("""
<style>
    /* Arriere-plan general */
    .main { background-color: #0f1117; }

    /* Cartes KPI personnalisees */
    .kpi-card {
        background: linear-gradient(135deg, #1e2130, #252a3d);
        border: 1px solid #3d4466;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        margin: 4px;
    }
    .kpi-value {
        font-size: 2.2rem;
        font-weight: 700;
        color: #4fc3f7;
        line-height: 1.2;
    }
    .kpi-label {
        font-size: 0.85rem;
        color: #9aa0b4;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-top: 4px;
    }
    .kpi-delta-ok  { color: #4caf50; font-size: 0.8rem; }
    .kpi-delta-warn{ color: #ff9800; font-size: 0.8rem; }

    /* Badge de statut */
    .badge-actif   { background:#1b5e20; color:#a5d6a7;
                     padding:2px 10px; border-radius:12px;
                     font-size:0.78rem; font-weight:600; }
    .badge-inactif { background:#4a1010; color:#ef9a9a;
                     padding:2px 10px; border-radius:12px;
                     font-size:0.78rem; font-weight:600; }

    /* Titres de section */
    .section-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #e0e6f0;
        border-left: 4px solid #4fc3f7;
        padding-left: 12px;
        margin: 24px 0 16px 0;
    }

    /* Sidebar */
    .sidebar-logo {
        font-size: 1.4rem;
        font-weight: 800;
        color: #4fc3f7;
        text-align: center;
        padding: 10px 0 20px 0;
        border-bottom: 1px solid #3d4466;
        margin-bottom: 20px;
    }

    /* Masquer le menu hamburger Streamlit */
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# FONCTIONS D'APPEL API
# =============================================================================

@st.cache_data(ttl=5)
def api_health():
    """Appel GET /health — statut et record count."""
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


@st.cache_data(ttl=5)
def api_dashboard_latest():
    """Appel GET /dashboard/latest — derniere position de chaque camion."""
    try:
        r = httpx.get(f"{BASE_URL}/dashboard/latest", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


@st.cache_data(ttl=5)
def api_truck_positions(truck_id: str, limit: int):
    """Appel GET /trucks/{truck_id}/positions."""
    try:
        r = httpx.get(
            f"{BASE_URL}/trucks/{truck_id}/positions",
            params={"limit": limit},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


@st.cache_data(ttl=5)
def api_alerts(alert_date: str):
    """Appel GET /alerts/{date}."""
    try:
        r = httpx.get(f"{BASE_URL}/alerts/{alert_date}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


@st.cache_data(ttl=5)
def api_trucks():
    """Appel GET /trucks — liste des camions avec derniere position."""
    try:
        r = httpx.get(f"{BASE_URL}/trucks", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    st.markdown('<div class="sidebar-logo">IoT Logistics</div>',
                unsafe_allow_html=True)

    st.markdown("**Configuration**")
    refresh_rate = st.slider(
        "Rafraichissement (sec)",
        min_value=5,
        max_value=30,
        value=10,
        step=5,
    )

    st.markdown("---")
    now_local = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    st.markdown(f"Derniere mise a jour : `{now_local}`")

    st.markdown("---")

    # Statut de l'API
    health = api_health()
    if health:
        st.success("API connectee")
        st.metric("Total Records", f"{health.get('record_count', 0):,}")
    else:
        st.error("API non disponible")
        st.info(f"Verifiez que l'API tourne sur {BASE_URL}")

    st.markdown("---")
    st.markdown("**Module :** NoSQL pour le Big Data")
    st.markdown("**Dr. B. BENCHARIF | USDB Blida 1**")

# Auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=refresh_rate * 1000, key="auto_refresh")
except ImportError:
    pass


# =============================================================================
# SECTION 1 — TABLEAU DE BORD EN TEMPS REEL
# =============================================================================

st.markdown('<div class="section-title">Tableau de Bord — Suivi en Temps Reel</div>',
            unsafe_allow_html=True)

# --- Chargement des donnees ---
latest_positions = api_dashboard_latest()
health_data      = api_health()

# --- Calcul des KPI ---
total_records  = health_data.get("record_count", 0) if health_data else 0
active_trucks  = len(latest_positions)

temps = [p["temperature"] for p in latest_positions if p.get("temperature")]
avg_temp = round(sum(temps) / len(temps), 1) if temps else 0.0

today_str    = date.today().isoformat()
alerts_today = api_alerts(today_str)
alert_count  = len(alerts_today)

# --- Ligne KPI ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-value">{total_records:,}</div>
        <div class="kpi-label">Total Enregistrements</div>
    </div>""", unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-value">{active_trucks}</div>
        <div class="kpi-label">Camions Actifs</div>
    </div>""", unsafe_allow_html=True)

with col3:
    delta_class = "kpi-delta-warn" if alert_count > 0 else "kpi-delta-ok"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-value">{alert_count}</div>
        <div class="kpi-label">Alertes Aujourd'hui</div>
        <div class="{delta_class}">{"seuil > 35 degC" if alert_count > 0 else "aucune alerte"}</div>
    </div>""", unsafe_allow_html=True)

with col4:
    temp_class = "kpi-delta-warn" if avg_temp > 35 else "kpi-delta-ok"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-value">{avg_temp} C</div>
        <div class="kpi-label">Temp. Moyenne</div>
        <div class="{temp_class}">{"ALERTE" if avg_temp > 35 else "NORMAL"}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Carte pydeck ---
if latest_positions:
    map_data = []
    for p in latest_positions:
        temp = p.get("temperature", 20)
        # Rouge si temperature > 35, Vert sinon
        if temp > 35:
            color = [220, 50, 50, 200]
        else:
            color = [50, 200, 100, 200]
        map_data.append({
            "truck_id"   : p["truck_id"],
            "latitude"   : p["latitude"],
            "longitude"  : p["longitude"],
            "temperature": round(temp, 1),
            "color"      : color,
        })

    df_map = pd.DataFrame(map_data)

    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["longitude", "latitude"],
        get_color="color",
        get_radius=3000,
        pickable=True,
        auto_highlight=True,
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=df_map,
        get_position=["longitude", "latitude"],
        get_text="truck_id",
        get_size=14,
        get_color=[255, 255, 255],
        get_alignment_baseline="'bottom'",
    )

    view_state = pdk.ViewState(
        latitude=36.5,
        longitude=3.0,
        zoom=8,
        pitch=0,
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[scatter_layer, text_layer],
            initial_view_state=view_state,
            tooltip={"text": "{truck_id}\nTemp: {temperature} C"},
            map_style="mapbox://styles/mapbox/dark-v10",
        ),
        use_container_width=True,
    )
else:
    st.warning("Aucune donnee disponible — verifiez que l'API est demarree.")


# =============================================================================
# SECTION 2 — RECHERCHE PAR CAMION
# =============================================================================

st.markdown("---")
st.markdown('<div class="section-title">Recherche par Camion</div>',
            unsafe_allow_html=True)

col_sel, col_lim = st.columns([1, 2])

with col_sel:
    selected_truck = st.selectbox(
        "Selectionner un camion",
        options=TRUCK_IDS,
        index=0,
    )

with col_lim:
    position_limit = st.slider(
        "Nombre de positions",
        min_value=10,
        max_value=200,
        value=50,
        step=10,
    )

positions = api_truck_positions(selected_truck, position_limit)

if positions:
    df_pos = pd.DataFrame(positions)
    df_pos["event_time"] = pd.to_datetime(df_pos["event_time"])
    df_pos = df_pos.sort_values("event_time")

    col_map, col_stats = st.columns([3, 2])

    with col_map:
        # Carte Folium avec polyligne du trajet
        center_lat = df_pos["latitude"].mean()
        center_lon = df_pos["longitude"].mean()
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=10,
            tiles="CartoDB dark_matter",
        )

        # Polyligne du trajet (ordre chronologique)
        coords = list(zip(df_pos["latitude"], df_pos["longitude"]))
        if len(coords) > 1:
            folium.PolyLine(
                coords,
                color="#4fc3f7",
                weight=2.5,
                opacity=0.8,
            ).add_to(m)

        # Marqueur de depart
        folium.Marker(
            location=coords[0],
            popup="Debut du trajet",
            icon=folium.Icon(color="green", icon="play"),
        ).add_to(m)

        # Marqueur de la derniere position
        folium.Marker(
            location=coords[-1],
            popup=f"Derniere position\nTemp: {df_pos.iloc[-1]['temperature']:.1f} C",
            icon=folium.Icon(color="red", icon="stop"),
        ).add_to(m)

        st_folium(m, width=None, height=400, returned_objects=[])

    with col_stats:
        # Statistiques du trajet
        max_temp = df_pos["temperature"].max()
        min_temp = df_pos["temperature"].min()
        total_pts = len(df_pos)

        st.markdown("**Statistiques du trajet**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Temp. Max", f"{max_temp:.1f} C",
                  delta="ALERTE" if max_temp > 35 else None,
                  delta_color="inverse")
        c2.metric("Temp. Min", f"{min_temp:.1f} C")
        c3.metric("Points GPS", total_pts)

        # Tableau des positions
        st.markdown("**Historique des positions**")
        df_display = df_pos[["event_time", "latitude", "longitude",
                              "temperature", "cargo_status", "speed_kmh"]].copy()
        df_display.columns = ["Horodatage", "Latitude", "Longitude",
                               "Temp (C)", "Statut", "Vitesse (km/h)"]
        df_display["Horodatage"] = df_display["Horodatage"].dt.strftime("%H:%M:%S")
        df_display = df_display.sort_values("Horodatage", ascending=False)
        st.dataframe(df_display, use_container_width=True, height=300)
else:
    st.info(f"Aucune position disponible pour {selected_truck}.")


# =============================================================================
# SECTION 3 — ALERTES DE TEMPERATURE
# =============================================================================

st.markdown("---")
st.markdown('<div class="section-title">Alertes de Temperature</div>',
            unsafe_allow_html=True)

selected_date = st.date_input(
    "Selectionner une date",
    value=date.today(),
    max_value=date.today(),
)

alerts = api_alerts(selected_date.isoformat())

if alerts:
    st.markdown(f"**{len(alerts)} alerte(s) le {selected_date.strftime('%d/%m/%Y')}**")

    df_alerts = pd.DataFrame(alerts)
    df_alerts["event_time"] = pd.to_datetime(df_alerts["event_time"]).dt.strftime("%H:%M:%S")
    df_alerts["alert_date"] = df_alerts["alert_date"].astype(str)

    # Formatage conditionnel de la temperature
    def color_temp(val):
        try:
            v = float(val)
            if v >= 40:
                return "background-color: #7f0000; color: white; font-weight: bold"
            elif v > 35:
                return "background-color: #e65100; color: white"
            return ""
        except Exception:
            return ""

    df_display = df_alerts[["event_time", "truck_id", "temperature",
                             "alert_type", "latitude", "longitude"]].copy()
    df_display.columns = ["Heure", "Camion", "Temp (C)", "Type", "Latitude", "Longitude"]

    st.dataframe(
        df_display.style.applymap(color_temp, subset=["Temp (C)"]),
        use_container_width=True,
        height=300,
    )
else:
    st.info(f"Aucune alerte le {selected_date.strftime('%d/%m/%Y')}.")


# =============================================================================
# SECTION 4 — MONITEUR D'INGESTION
# =============================================================================

st.markdown("---")
st.markdown('<div class="section-title">Moniteur d\'Ingestion en Temps Reel</div>',
            unsafe_allow_html=True)

trucks_data = api_dashboard_latest()

if trucks_data:
    rows = []
    now_utc = datetime.now(timezone.utc)

    for truck in trucks_data:
        truck_id   = truck.get("truck_id", "—")
        last_temp  = truck.get("temperature")
        last_lat   = truck.get("latitude")
        last_lon   = truck.get("longitude")
        last_cargo = truck.get("cargo_status", "—")

        # Calcul du delai depuis la derniere vue
        last_seen_str = truck.get("event_time")
        if last_seen_str:
            try:
                last_seen_dt = datetime.fromisoformat(
                    last_seen_str.replace("Z", "+00:00")
                )
                if last_seen_dt.tzinfo is None:
                    last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
                delta_sec = (now_utc - last_seen_dt).total_seconds()
                last_seen_disp = f"{int(delta_sec)}s"
                status_html = (
                    '<span class="badge-actif">ACTIF</span>'
                    if delta_sec < 30
                    else '<span class="badge-inactif">INACTIF</span>'
                )
            except Exception:
                last_seen_disp = "—"
                status_html = '<span class="badge-inactif">INACTIF</span>'
        else:
            last_seen_disp = "—"
            status_html = '<span class="badge-inactif">INACTIF</span>'

        rows.append({
            "Camion"    : truck_id,
            "Temp (C)"  : f"{last_temp:.1f}" if last_temp else "—",
            "Position"  : f"{last_lat:.4f}, {last_lon:.4f}" if last_lat else "—",
            "Statut Cargo": last_cargo,
            "Vu il y a" : last_seen_disp,
            "Etat"      : status_html,
        })

    df_monitor = pd.DataFrame(rows)

    # Affichage avec HTML pour les badges de statut
    st.markdown(
        df_monitor.to_html(escape=False, index=False),
        unsafe_allow_html=True,
    )
else:
    st.warning("Aucune donnee de monitoring — demarrez generator.py pour ingerer des donnees.")

# Pied de page
st.markdown("---")
st.markdown(
    "<center style='color:#555; font-size:0.8rem;'>"
    "Mini-Projet NoSQL — Suivi IoT Temps Reel avec Apache Cassandra | "
    "Module : NoSQL pour le Big Data | Dr. B. BENCHARIF | USDB Blida 1 | 2025/2026"
    "</center>",
    unsafe_allow_html=True,
)
