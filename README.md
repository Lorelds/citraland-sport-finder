# Surabaya Sport Finder

GIS web app (Computer Graphics, Informatics, Universitas Ciputra) that finds the nearest sports venue anywhere in Kota Surabaya for a chosen sport and draws the road route from the user's address.

## Run

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env                       # then fill GOOGLE_MAPS_API_KEY (optional)
.venv\Scripts\python data_fetch.py --graph   # once: downloads the road network, needed for routes
.venv\Scripts\flask --app app run            # open http://127.0.0.1:5000
```

The boundary and venue files are in the repo, so the app runs without a key. Without `--graph`, the map and filters work but routes show a warning: the road network is never downloaded during a request.

Without an API key the address falls back to Universitas Ciputra. If `data/venues_surabaya.geojson` is missing, the app uses `data/venues_sample.geojson` (8 **made-up sample venues**, names start with "Contoh"). The page shows a warning in both cases.

Google Cloud APIs needed: **Places API (New)** and **Geocoding API**.

## Data commands

| Command | Writes | Notes |
|---|---|---|
| `data_fetch.py --boundary` | `data/surabaya_area.geojson`, `data/surabaya_manual.geojson` | OSM relation 8225862; refuses a shape outside 300–400 km² |
| `data_fetch.py --osm` | `data/venues_osm.geojson` | Overpass, free; drops unnamed and `access=private` features and shops |
| `data_fetch.py --refresh [--budget N]` | `data/venues_google.geojson`, `data/places_progress.json` | Google Places; default 80 requests, **rerun daily until done** |
| `data_fetch.py --graph` | `data/graph_surabaya.graphml` | Not in git |

`--osm` and `--refresh` also rebuild `data/venues_surabaya.geojson`, the file the app reads.

**Places across several days.** The key allows about 100 requests per day, and the city needs about 200 queries: one for each rare sport, one per 5 km grid cell for common sports (`grid: True` in `config.SPORTS`). Progress is saved after every request, and a 429 or 403 stops the run without retrying, so `--refresh` simply continues where it stopped. The default budget leaves 20 requests for address lookups.

## How it works

| Step | Function (`gis.py`) | What it does |
|---|---|---|
| Layer 1 | `load_venues` | Venue points merged from OSM and Google Places |
| Layer 2 | `load_boundary` | Surabaya MultiPolygon from OSM |
| 1 | `spatial_join` | `sjoin(..., predicate="intersects")`: keep venues inside Surabaya |
| 2 | `filter_by_sport` | Dropdown filter on `Jenis_Olahraga` |
| 3 | `rank_by_distance` | Straight-line distance in meters (EPSG:32749) |
| 4 | `route_to_nearest` | OSMnx `shortest_path` with nearest-node snapping, road distance in km |

All distances use EPSG:32749 (WGS 84 / UTM 49S). Data goes back to EPSG:4326 only for the Folium map.

**Straight-line vs. route:** the venue nearest in a straight line is not always nearest by road. The app routes to the 3 nearest straight-line candidates and picks the shortest road route, whose road distance is shown on the result card.

**Sports:** `config.SPORTS` lists about 30 sports in 8 groups. Marker colors follow the group, since 30 colors cannot be told apart; the tooltip names the sport.

**Merging sources:** two rows are one place when the sport matches, they are at most 75 m apart, and the names are similar (`difflib` ratio ≥ 0.6, or one contains the other). The Google row wins.

## Data notes

- Basemap is OpenStreetMap. Google tiles need a paid Map Tiles key; the line is left commented in `app.py`.
- `data/surabaya_manual.geojson` is the OSM outline simplified to about 150 m, used only if the main boundary file is missing and OSM cannot be reached.
- `data/citraland_*.geojson`, `data/venues.geojson`, and `data/graph.graphml` belong to the earlier CitraLand-only version. The app no longer reads them.

## Tests

```
.venv\Scripts\python -m pytest
```

## Study guide

`docs/Panduan-Belajar-Citraland-Sport-Finder.pdf` and `docs/Catatan-Penjelasan-File.md` (Bahasa Indonesia) still describe the CitraLand-only version, so their code references and line numbers match the `main` branch rather than this one.
