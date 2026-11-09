"""Shared constants for Surabaya Sport Finder."""

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

VENUES_CACHE = DATA_DIR / "venues_surabaya.geojson"  # merged file the app reads
VENUES_OSM = DATA_DIR / "venues_osm.geojson"
VENUES_GOOGLE = DATA_DIR / "venues_google.geojson"
PLACES_PROGRESS = DATA_DIR / "places_progress.json"
VENUES_SAMPLE = DATA_DIR / "venues_sample.geojson"
BOUNDARY_AREA = DATA_DIR / "surabaya_area.geojson"  # built by data_fetch.py --boundary
BOUNDARY_MANUAL = DATA_DIR / "surabaya_manual.geojson"  # same outline simplified, offline fallback
GRAPH_CACHE = DATA_DIR / "graph_surabaya.graphml"  # built by data_fetch.py --graph

BOUNDARY_OSM_ID = "R8225862"  # OSM relation for Kota Surabaya
OVERPASS_AREA_ID = 3608225862  # Overpass area id: 3600000000 + relation id
BOUNDARY_AREA_RANGE_KM2 = (300, 400)  # anything else means OSM returned the wrong shape
BOUNDARY_SIMPLIFY_M = 150

# Farthest a starting address may be from the Surabaya boundary (straight line).
# Anything farther is rejected, so the app only serves Surabaya and its surroundings.
MAX_ORIGIN_DISTANCE_M = 2500
# The road graph extends past the boundary so users starting just outside the city
# can still be routed in. It covers exactly the allowed origin distance, so every
# accepted address has roads around it.
GRAPH_BUFFER_M = MAX_ORIGIN_DISTANCE_M

ROUTE_CANDIDATES = 3
PLACES_BIAS_RADIUS_M = 20000.0
PLACES_GRID_CELL_M = 5000
PLACES_DAILY_BUDGET = 80  # of the key's 100 requests/day; the rest stays free for geocoding

# Two rows are one place when the sport matches, they are this close, and the names agree.
DEDUPE_DISTANCE_M = 75
DEDUPE_NAME_RATIO = 0.6

# Areas OpenStreetMap has no name for, used when Google is unavailable: (lat, lon).
KNOWN_PLACES = {"northwest": (-7.2503184, 112.6187887)}

# Universitas Ciputra, used when geocoding is unavailable.
FALLBACK_ORIGIN = {"name": "Universitas Ciputra, Surabaya", "lat": -7.2861, "lon": 112.6319}
MAP_CENTER = (-7.2737, 112.7241)  # centroid of surabaya_area.geojson

# Markers are colored by group: about 30 sports cannot have colors that tell apart.
GROUPS = {
    "raket": {"label": "Raket", "color": "#e6194b"},
    "bola": {"label": "Bola", "color": "#3cb44b"},
    "kebugaran": {"label": "Kebugaran", "color": "#4363d8"},
    "air": {"label": "Air", "color": "#42d4f4"},
    "bela_diri": {"label": "Bela Diri", "color": "#911eb4"},
    "luar_ruang": {"label": "Luar Ruang", "color": "#f58231"},
    "dalam_ruang": {"label": "Dalam Ruang", "color": "#9a6324"},
    "lainnya": {"label": "Lainnya", "color": "#64748b"},
}

# key: dropdown value, label: Indonesian label, group: key in GROUPS, query: Places search text,
# grid: True when one query per grid cell is needed (too many venues for one city-wide query),
# osm: values of OSM's sport=* tag, leisure: OSM leisure=* values that imply the sport,
# words: whole words in a name that identify the sport,
# not_words: whole words that rule the sport out even when a word matches (tenis vs tenis meja)
SPORTS = {
    # Raket
    "badminton": {"label": "Badminton", "group": "raket", "query": "lapangan badminton", "grid": True, "osm": ["badminton"],
                  "words": ["badminton", "bulu tangkis", "bulutangkis", "smash"]},
    "tenis": {"label": "Tenis", "group": "raket", "query": "lapangan tenis", "grid": True, "osm": ["tennis"],
              "words": ["tenis", "tennis"], "not_words": ["tenis meja", "table tennis"]},
    "tenis_meja": {"label": "Tenis Meja", "group": "raket", "query": "tenis meja", "osm": ["table_tennis"],
                   "words": ["tenis meja", "table tennis", "pingpong", "ping pong", "ptm"]},
    "padel": {"label": "Padel", "group": "raket", "query": "lapangan padel", "osm": ["padel"], "words": ["padel"]},
    "squash": {"label": "Squash", "group": "raket", "query": "lapangan squash", "osm": ["squash"], "words": ["squash"]},
    "pickleball": {"label": "Pickleball", "group": "raket", "query": "lapangan pickleball", "osm": ["pickleball"],
                   "words": ["pickleball"]},
    # Bola
    "futsal": {"label": "Futsal", "group": "bola", "query": "lapangan futsal", "grid": True, "osm": ["futsal"], "words": ["futsal"]},
    "sepak_bola": {"label": "Sepak Bola", "group": "bola", "query": "lapangan sepak bola mini soccer", "osm": ["soccer", "football"],
                   "words": ["soccer", "mini soccer", "sepak bola", "sepakbola", "football"]},
    "basket": {"label": "Basket", "group": "bola", "query": "lapangan basket", "grid": True, "osm": ["basketball"],
               "words": ["basket", "basketball"]},
    "voli": {"label": "Voli", "group": "bola", "query": "lapangan voli", "osm": ["volleyball", "beachvolleyball"],
             "words": ["voli", "volley", "volleyball"]},
    "baseball_softball": {"label": "Baseball & Softball", "group": "bola", "query": "lapangan baseball softball",
                          "osm": ["baseball", "softball"], "words": ["baseball", "softball"]},
    # Kebugaran
    "gym": {"label": "Gym", "group": "kebugaran", "query": "gym fitness", "grid": True, "osm": ["fitness", "crossfit", "trx"],
            "leisure": ["fitness_centre"], "words": ["gym", "fitness", "fitnessworks", "training", "bodywork", "bodyworks", "crossfit", "trx"]},
    "yoga_pilates": {"label": "Yoga & Pilates", "group": "kebugaran", "query": "studio yoga pilates", "grid": True,
                     "osm": ["yoga", "pilates"], "words": ["yoga", "pilates"]},
    "senam": {"label": "Senam", "group": "kebugaran", "query": "sanggar senam aerobik zumba", "osm": ["aerobics", "zumba"],
              "words": ["senam", "aerobik", "aerobics", "zumba"]},
    # Air
    "renang": {"label": "Renang", "group": "air", "query": "kolam renang", "grid": True, "osm": ["swimming"],
               "leisure": ["swimming_pool"], "words": ["renang", "swim", "swimming", "waterpark", "water park", "waterboom"]},
    # Bela diri
    "bela_diri": {"label": "Bela Diri", "group": "bela_diri", "query": "tempat latihan bela diri", "grid": True,
                  "osm": ["martial_arts", "karate", "taekwondo", "judo", "boxing", "muay_thai", "wushu", "kickboxing"],
                  "words": ["bela diri", "beladiri", "martial", "martial arts", "karate", "taekwondo", "judo", "tinju", "boxing",
                            "muay thai", "muaythai", "wushu", "kickboxing", "silat"]},
    # Luar ruang
    "atletik": {"label": "Atletik & Lari", "group": "luar_ruang", "query": "lintasan lari atletik", "osm": ["athletics", "running"],
                "leisure": ["track"], "words": ["atletik", "athletics", "lari", "jogging", "running"]},
    "golf": {"label": "Golf", "group": "luar_ruang", "query": "lapangan golf driving range", "osm": ["golf"],
             "leisure": ["golf_course"], "words": ["golf"]},
    "panjat_tebing": {"label": "Panjat Tebing", "group": "luar_ruang", "query": "panjat tebing climbing", "osm": ["climbing"],
                      "words": ["panjat tebing", "climbing", "bouldering"]},
    "skate": {"label": "Skate & Sepatu Roda", "group": "luar_ruang", "query": "skate park sepatu roda", "osm": ["skateboard", "roller_skating"],
              "words": ["skate", "skatepark", "skateboard", "sepatu roda"]},
    "sepeda": {"label": "Sepeda", "group": "luar_ruang", "query": "lintasan sepeda BMX velodrome", "osm": ["cycling", "bmx"],
               "words": ["velodrome", "velodrom", "bmx", "pump track", "pumptrack", "cycling"]},
    "berkuda": {"label": "Berkuda", "group": "luar_ruang", "query": "tempat berkuda equestrian", "osm": ["equestrian"],
                "words": ["berkuda", "equestrian", "pacuan kuda", "horse riding"]},
    "panahan": {"label": "Panahan", "group": "luar_ruang", "query": "lapangan panahan", "osm": ["archery"], "words": ["panahan", "archery"]},
    "menembak": {"label": "Menembak", "group": "luar_ruang", "query": "lapangan tembak perbakin", "osm": ["shooting"],
                 "words": ["menembak", "lapangan tembak", "shooting range", "perbakin"]},
    # Dalam ruang
    "biliar": {"label": "Biliar", "group": "dalam_ruang", "query": "tempat biliar", "osm": ["billiards"],
               "words": ["biliar", "billiard", "billiards", "bilyar", "bilyard"]},
    "bowling": {"label": "Bowling", "group": "dalam_ruang", "query": "tempat bowling", "osm": ["10pin", "9pin"], "words": ["bowling"]},
    "ice_skating": {"label": "Ice Skating", "group": "dalam_ruang", "query": "ice skating", "osm": ["ice_skating"],
                    "words": ["ice skating", "ice skate", "ice rink"]},
    # Lainnya: no words, a name like "GOR Unesa" does not say which sport is played there.
    "serbaguna": {"label": "Serbaguna", "group": "lainnya", "query": "gelanggang olahraga GOR", "osm": ["multi"],
                  "leisure": ["sports_centre", "stadium"], "words": []},
    "lainnya": {"label": "Lainnya", "group": "lainnya", "query": None, "osm": [], "words": []},
}
for _sport in SPORTS.values():
    _sport["color"] = GROUPS[_sport["group"]]["color"]
    _sport.setdefault("grid", False)

ACCENT_COLOR = "#0f172a"  # button and route line; dark so it reads against every sport color
