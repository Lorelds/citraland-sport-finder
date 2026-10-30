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
BOUNDARY_AREA = DATA_DIR / "citraland_area.geojson"  # full township, built by data_fetch.py --boundary
BOUNDARY_CACHE = DATA_DIR / "citraland_osm.geojson"  # OSM "Citraland, RW 07, Made" only
BOUNDARY_MANUAL = DATA_DIR / "citraland_manual.geojson"
GRAPH_CACHE = DATA_DIR / "graph.graphml"

BOUNDARY_QUERY = "CitraLand, Surabaya"
BOUNDARY_QUERY_UTARA = "Citraland Utara, Surabaya"

# Hand-drawn (lon, lat) outline for the parts of CitraLand that OSM has no
# polygon for: CitraLand Northwest, the gap between Utara and the main estate,
# and The GreenLake in the south. Traced from known venues, so it is approximate.
HAND_DRAWN_AREA = [
    (112.6120, -7.2455), (112.6330, -7.2465), (112.6420, -7.2580), (112.6420, -7.2700),
    (112.6520, -7.2715), (112.6600, -7.2790), (112.6630, -7.2950), (112.6630, -7.3040),
    (112.6600, -7.3130), (112.6480, -7.3140), (112.6380, -7.3065), (112.6260, -7.3020),
    (112.6200, -7.2900), (112.6175, -7.2780), (112.6120, -7.2650),
]
# The road graph extends past the boundary so users starting from outside
# (a kos in Lontar or Sambikerep) can still be routed in.
GRAPH_BUFFER_M = 2500

ROUTE_CANDIDATES = 3
PLACES_BIAS_RADIUS_M = 6000.0

# Universitas Ciputra, used when geocoding is unavailable.
FALLBACK_ORIGIN = {"name": "Universitas Ciputra, Surabaya", "lat": -7.2861, "lon": 112.6319}
MAP_CENTER = (-7.2804, 112.6369)  # centroid of citraland_area.geojson

# key: dropdown value, label: Indonesian label, query: Places search text, color: marker color,
# words: name words that identify the sport (used to drop results Google files under the wrong sport)
# not_words: name words that rule the sport out even when a word matches (tenis vs tenis meja)
SPORTS = {
    "badminton": {"label": "Badminton", "query": "lapangan badminton", "color": "#e6194b", "words": ["badminton", "bulu tangkis", "smash"]},
    "futsal": {"label": "Futsal", "query": "lapangan futsal", "color": "#3cb44b", "words": ["futsal", "soccer", "sepak bola", "mini soccer"]},
    "basket": {"label": "Basket", "query": "lapangan basket", "color": "#f58231", "words": ["basket"]},
    "tenis": {"label": "Tenis", "query": "lapangan tenis", "color": "#911eb4", "words": ["tenis", "tennis"],
              "not_words": ["tenis meja", "table tennis"]},
    "tenis_meja": {"label": "Tenis Meja", "query": "tenis meja", "color": "#9a6324", "words": ["tenis meja", "table tennis", "pingpong", "ping pong", "ptm"]},
    "padel": {"label": "Padel", "query": "lapangan padel", "color": "#469990", "words": ["padel"]},
    "gym": {"label": "Gym", "query": "gym fitness", "color": "#4363d8", "words": ["gym", "fitness", "training", "bodywork", "martial"]},
    "renang": {"label": "Renang", "query": "kolam renang", "color": "#42d4f4", "words": ["renang", "swim", "kolam", "waterpark"]},
}
ACCENT_COLOR = "#0f172a"  # button and route line; dark so it reads against every sport color
