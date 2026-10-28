"""Shared constants for Citraland Sport Finder."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

load_dotenv(BASE_DIR / ".env")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

# Lat/long from GPS and Google are in degrees; distances need meters.
CRS_WGS84 = "EPSG:4326"
CRS_UTM = "EPSG:32749"  # WGS 84 / UTM zone 49S, covers Surabaya

VENUES_CACHE = DATA_DIR / "venues.geojson"
VENUES_SAMPLE = DATA_DIR / "venues_sample.geojson"
BOUNDARY_CACHE = DATA_DIR / "citraland_osm.geojson"
BOUNDARY_MANUAL = DATA_DIR / "citraland_manual.geojson"
GRAPH_CACHE = DATA_DIR / "graph.graphml"

BOUNDARY_QUERY = "CitraLand, Surabaya"
# The road graph extends past the boundary so users starting from outside
# (a kos in Lontar or Sambikerep) can still be routed in.
GRAPH_BUFFER_M = 2500

AVG_SPEED_KMH = 30
ROUTE_CANDIDATES = 3

# Universitas Ciputra, used when geocoding is unavailable.
FALLBACK_ORIGIN = {"name": "Universitas Ciputra, Surabaya", "lat": -7.2861, "lon": 112.6319}
MAP_CENTER = (-7.2875, 112.6420)

# key: dropdown value, label: Indonesian label, query: Places search text, color: marker color
SPORTS = {
    "badminton": {"label": "Badminton", "query": "lapangan badminton", "color": "#e6194b"},
    "futsal": {"label": "Futsal", "query": "lapangan futsal", "color": "#3cb44b"},
    "basket": {"label": "Basket", "query": "lapangan basket", "color": "#f58231"},
    "tenis": {"label": "Tenis", "query": "lapangan tenis", "color": "#911eb4"},
    "gym": {"label": "Gym", "query": "gym fitness", "color": "#4363d8"},
    "renang": {"label": "Renang", "query": "kolam renang", "color": "#42d4f4"},
}
ROUTE_COLOR = "#111111"
TIMEZONE = "Asia/Jakarta"
