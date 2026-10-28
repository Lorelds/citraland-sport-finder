# Citraland Sport Finder

GIS web app (Computer Graphics, Informatics, Universitas Ciputra) that finds the nearest sports venue in CitraLand Surabaya for a chosen sport and draws the road route from the user's address.

## Run

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # then fill GOOGLE_MAPS_API_KEY (optional)
.venv\Scripts\python data_fetch.py --refresh   # only with a key: fetch real venues
.venv\Scripts\flask --app app run              # open http://127.0.0.1:5000
```

Without an API key the app still runs: it uses `data/venues_sample.geojson` (8 **made-up sample venues**, names start with "Contoh") and places the user at Universitas Ciputra. The page shows a warning in both cases.

The first route request downloads the OSM road network (~1–2 minutes) and caches it to `data/graph.graphml`.

Google Cloud APIs needed: **Places API (New)** and **Geocoding API**.

## How it works

| Step | Function (`gis.py`) | What it does |
|---|---|---|
| Layer 1 | `load_venues` | Venue points from Google Places (cached in `data/venues.geojson`) |
| Layer 2 | `load_boundary` | CitraLand polygon: OSM pieces via `osmnx.geocode_to_gdf` + hand-drawn parts (see Data notes) |
| 1 | `spatial_join` | `sjoin(..., predicate="intersects")`: keep venues inside CitraLand |
| 2 | `filter_by_sport` | Dropdown filter on `Jenis_Olahraga` |
| 3 | `filter_open_now` | Places opening hours; unknown hours are kept and labelled |
| 4 | `rank_by_distance` | Straight-line distance in meters (EPSG:32749) |
| 5 | `route_to_nearest` | OSMnx `shortest_path` with nearest-node snapping, road distance in km |

All distances use EPSG:32749 (WGS 84 / UTM 49S). Data goes back to EPSG:4326 only for the Folium map.

**Straight-line vs. route:** the venue nearest in a straight line is not always nearest by road. The app routes to the 3 nearest straight-line candidates and picks the shortest road route, whose road distance is shown on the result card.

## Data notes

- `data/citraland_area.geojson`: **the boundary the app uses** (27 km²). It joins two OSM polygons ("Citraland, RW 07, Made" and "Citraland Utara") with a **hand-drawn approximation** for CitraLand Northwest, The GreenLake and the gaps between the pieces, since OSM has no polygon for those. The outline lives in `config.HAND_DRAWN_AREA`; rebuild with `python data_fetch.py --boundary`.
- `data/citraland_osm.geojson`: the original OSM polygon ("Citraland, RW 07, Made" only), kept for reference.
- `data/citraland_manual.geojson`: **approximate** fallback polygon (OSM boundary simplified to ~150 m), used only if the other boundary files are missing.
- Basemap is OpenStreetMap. Google tiles need a paid Map Tiles key; the line is left commented in `app.py`.

## Tests

```
.venv\Scripts\python -m pytest
```
