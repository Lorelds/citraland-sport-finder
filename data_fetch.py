"""Build the data files: boundary, venues (OSM + Places API), road graph.

    python data_fetch.py --boundary           Surabaya polygon from OSM
    python data_fetch.py --osm                venues from OpenStreetMap (free)
    python data_fetch.py --graph              road network for routing (several minutes)
    python data_fetch.py --refresh            venues from Google Places, resumable across days
"""

import argparse
import difflib
import json
import re
import sys
import time

import geopandas as gpd
import requests
from shapely.geometry import Point, box

import config

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_VIEWBOX = "112.59,-7.18,112.85,-7.36"  # prefer matches around Surabaya
PLACE_FIELDS = "places.id,places.displayName,places.location,places.primaryType,places.regularOpeningHours"
FIELD_MASK = f"{PLACE_FIELDS},nextPageToken"
USER_AGENT = "surabaya-sport-finder/1.0"  # required by Nominatim's and Overpass's usage policies
TIMEOUT_S = 15
OVERPASS_TIMEOUT_S = 180

# Name and geometry only, so a venue row never depends on which source found it.
VENUE_COLUMNS = ["Tempat_ID", "Nama", "Kategori", "Jenis_Olahraga", "opening_hours", "geometry"]
# Google files a shop selling rackets under the same search as the court.
NON_VENUE_PLACE_TYPES = {"store", "shopping_mall", "market"}
# What Google must call a place before a name that mentions no sport is believed:
# the old search also returned a car wash, a food court and a contractor.
SPORT_PLACE_TYPES = {
    "sports_activity_location", "sports_club", "sports_complex", "sports_coaching", "sports_school", "athletic_field", "gym",
    "fitness_center", "swimming_pool", "tennis_court", "stadium", "arena", "golf_course", "indoor_golf_course", "yoga_studio",
    "ice_skating_rink", "skateboard_park", "martial_arts_school",
}


# ---------------------------------------------------------- matching names


def has_word(lowered: str, words: list[str]) -> bool:
    """Whole words only: "lari" must not match "clarion" or "larissa"."""
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", lowered) for w in words)


def names_sport(lowered: str, sport_key: str) -> bool:
    sport = config.SPORTS[sport_key]
    if has_word(lowered, sport.get("not_words", [])):
        return False
    return has_word(lowered, sport["words"])


def names_other_sport(name: str, sport_key: str) -> bool:
    """True when the name clearly belongs to another sport and not this one.

    Text Search is loose: "lapangan futsal" also returns tennis courts.
    Names that mention no sport at all (e.g. "Square Park") are kept.
    """
    lowered = name.lower()
    if names_sport(lowered, sport_key):
        return False
    return any(names_sport(lowered, k) for k in config.SPORTS if k != sport_key)


def sports_in_text(text: str) -> list[str]:
    lowered = text.lower()
    return [k for k in config.SPORTS if names_sport(lowered, k)]


# ------------------------------------------------------------ OpenStreetMap


OSM_TAG_TO_SPORT = {tag: key for key, s in config.SPORTS.items() for tag in s["osm"]}
OSM_LEISURE_TO_SPORT = {tag: key for key, s in config.SPORTS.items() for tag in s.get("leisure", [])}


def osm_sports(tags: dict) -> list[str]:
    """Sport keys for one OSM feature. The sport tag wins; the name and leisure tag fill in.

    Tag values are not clean: "soccer;basketball", "TRX", "Lapangan Tenis".
    """
    name = tags.get("name", "")
    found = []
    for raw in tags.get("sport", "").split(";"):
        value = raw.strip().lower()
        if not value:
            continue
        mapped = OSM_TAG_TO_SPORT.get(value)
        found += [mapped] if mapped else sports_in_text(value) or sports_in_text(name) or ["lainnya"]
    if not found:
        found = sports_in_text(name) or [OSM_LEISURE_TO_SPORT.get(tags.get("leisure"), "serbaguna")]
    return list(dict.fromkeys(found))


def osm_rows(elements: list[dict]) -> tuple[list[dict], dict]:
    """Venue rows from Overpass elements, one per (feature, sport), and what was dropped."""
    rows = []
    dropped = {"tanpa_nama": 0, "private": 0, "toko": 0}
    for el in elements:
        tags = el.get("tags", {})
        if "shop" in tags:  # sport=* is also how OSM says what a sports shop sells
            dropped["toko"] += 1
            continue
        if tags.get("access") == "private":
            dropped["private"] += 1
            continue
        name = tags.get("name", "").strip()
        if not name:
            dropped["tanpa_nama"] += 1
            continue
        pos = el.get("center") or el  # nodes carry lat/lon themselves, ways and relations a center
        if "lat" not in pos:
            continue
        for sport_key in osm_sports(tags):
            rows.append(
                {
                    "Tempat_ID": f"osm:{el['type']}/{el['id']}",
                    "Nama": name,
                    "Kategori": tags.get("leisure", "sports_complex"),
                    "Jenis_Olahraga": sport_key,
                    # JSON text like Google's rows: a mix of JSON and plain text warns on every read.
                    "opening_hours": json.dumps(tags["opening_hours"]) if "opening_hours" in tags else None,
                    "geometry": Point(pos["lon"], pos["lat"]),
                }
            )
    return rows, dropped


def fetch_osm() -> gpd.GeoDataFrame:
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_S - 30}];
area({config.OVERPASS_AREA_ID})->.a;
(
  nwr["sport"](area.a);
  nwr["leisure"~"^(sports_centre|fitness_centre|pitch|swimming_pool|stadium|track|golf_course)$"](area.a);
);
out tags center;
"""
    resp = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=OVERPASS_TIMEOUT_S)
    resp.raise_for_status()
    elements = resp.json()["elements"]
    rows, dropped = osm_rows(elements)
    print(f"Overpass: {len(elements)} fitur, {len(rows)} baris; dibuang: {dropped}")
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=config.CRS_WGS84)
    return gdf.drop_duplicates(subset=["Tempat_ID", "Jenis_Olahraga"]).reset_index(drop=True)


# ------------------------------------------------------------ Google Places


def search_places(sport_key: str, rect: dict, api_key: str, page_token: str | None = None) -> tuple[list[dict], str | None]:
    """One page of Places Text Search inside a rectangle. Returns (rows, next page token)."""
    body = {
        "textQuery": config.SPORTS[sport_key]["query"],
        "languageCode": "id",
        "locationRestriction": {"rectangle": rect},
    }
    if page_token:
        body["pageToken"] = page_token
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}
    resp = requests.post(PLACES_URL, json=body, headers=headers, timeout=TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for place in data.get("places", []):
        loc = place.get("location", {})
        if "latitude" not in loc:
            continue
        hours = place.get("regularOpeningHours", {}).get("periods")
        rows.append(
            {
                "Tempat_ID": place["id"],
                "Nama": place.get("displayName", {}).get("text", "Tanpa nama"),
                "Kategori": place.get("primaryType", "sports_complex"),
                "Jenis_Olahraga": sport_key,
                # GeoJSON properties must be flat, so the periods list is stored as text.
                "opening_hours": json.dumps(hours) if hours else None,
                "geometry": Point(loc["longitude"], loc["latitude"]),
            }
        )
    return rows, data.get("nextPageToken")


def keep_place(row: dict) -> bool:
    """Drop what Text Search returns loosely: shops, other sports, unrelated businesses.

    A city-wide query covers a rare sport, so Google fills the page with whatever
    is closest ("Pasar Modern" under tenis meja); those rows must name the sport.
    """
    category = row["Kategori"]
    if category in NON_VENUE_PLACE_TYPES or category.endswith("_store"):
        return False
    key = row["Jenis_Olahraga"]
    sport = config.SPORTS[key]
    if names_sport(row["Nama"].lower(), key):
        return True
    if names_other_sport(row["Nama"], key):
        return False
    return (sport["grid"] or not sport["words"]) and category in SPORT_PLACE_TYPES


def _rect(minx: float, miny: float, maxx: float, maxy: float) -> dict:
    low = {"latitude": float(miny), "longitude": float(minx)}
    return {"low": low, "high": {"latitude": float(maxy), "longitude": float(maxx)}}


def grid_cells(boundary_utm: gpd.GeoDataFrame, size_m: float = config.PLACES_GRID_CELL_M) -> list[tuple[str, dict]]:
    """Square cells (cell id, lat/lon rectangle) that touch the polygon."""
    area = boundary_utm.geometry.union_all()
    minx, miny, maxx, maxy = area.bounds
    cells = []
    row = 0
    while miny + row * size_m < maxy:
        col = 0
        while minx + col * size_m < maxx:
            x, y = minx + col * size_m, miny + row * size_m
            cell = box(x, y, x + size_m, y + size_m)
            if cell.intersects(area):
                bounds = gpd.GeoSeries([cell], crs=config.CRS_UTM).to_crs(config.CRS_WGS84).total_bounds
                cells.append((f"r{row}c{col}", _rect(*bounds)))
            col += 1
        row += 1
    return cells


def places_tasks(boundary_utm: gpd.GeoDataFrame) -> list[tuple[str, str, dict]]:
    """Every (task id, sport, rectangle). City-wide sports first, then grid sports with the least OSM data."""
    city = _rect(*boundary_utm.to_crs(config.CRS_WGS84).total_bounds)
    tasks = [(f"{k}|kota", k, city) for k, s in config.SPORTS.items() if s["query"] and not s["grid"]]

    osm_counts = {}
    if config.VENUES_OSM.exists():
        osm_counts = gpd.read_file(config.VENUES_OSM)["Jenis_Olahraga"].value_counts().to_dict()
    grid_sports = sorted((k for k, s in config.SPORTS.items() if s["query"] and s["grid"]), key=lambda k: osm_counts.get(k, 0))
    cells = grid_cells(boundary_utm)
    tasks += [(f"{k}|{cell_id}", k, rect) for k in grid_sports for cell_id, rect in cells]
    return tasks


def load_progress() -> dict:
    if config.PLACES_PROGRESS.exists():
        return json.loads(config.PLACES_PROGRESS.read_text(encoding="utf-8"))
    return {"done": [], "requests": 0, "total_tasks": 0, "stopped": None}


def load_google_rows() -> dict:
    if not config.VENUES_GOOGLE.exists():
        return {}
    gdf = gpd.read_file(config.VENUES_GOOGLE)
    gdf = gdf.astype({"opening_hours": object}).where(gdf.notna(), None)
    return {(r["Tempat_ID"], r["Jenis_Olahraga"]): r for r in gdf[VENUE_COLUMNS].to_dict("records")}


def _save_places(rows: dict, progress: dict) -> None:
    if rows:
        gdf = gpd.GeoDataFrame(list(rows.values()), geometry="geometry", crs=config.CRS_WGS84)
        gdf.to_file(config.VENUES_GOOGLE, driver="GeoJSON")
    config.PLACES_PROGRESS.write_text(json.dumps(progress, indent=1), encoding="utf-8")


def fetch_places(api_key: str, budget: int, boundary_utm: gpd.GeoDataFrame) -> dict:
    """Run queries until the budget or the quota ends. Rerun later to continue.

    A query counts as done only after its last page, so one cut off halfway
    starts again from page one (page tokens do not survive until the next day).
    Everything is saved after each request, so a stop loses nothing.
    """
    tasks = places_tasks(boundary_utm)
    progress = load_progress()
    progress.update(total_tasks=len(tasks), stopped=None)
    rows = load_google_rows()
    done = set(progress["done"])
    used = 0

    for task_id, sport_key, rect in tasks:
        if task_id in done:
            continue
        token = None
        while True:
            if used >= budget:
                progress["stopped"] = f"budget {budget} habis"
                _save_places(rows, progress)
                return progress
            try:
                page, token = search_places(sport_key, rect, api_key, token)
            except requests.RequestException as exc:
                # Only the status: the exception text may carry request details.
                status = getattr(exc.response, "status_code", exc.__class__.__name__)
                progress["stopped"] = f"HTTP {status}"
                _save_places(rows, progress)
                return progress
            used += 1
            progress["requests"] += 1
            kept = [r for r in page if keep_place(r)]
            rows.update({(r["Tempat_ID"], r["Jenis_Olahraga"]): r for r in kept})
            _save_places(rows, progress)
            print(f"  {task_id}: {len(page)} hasil, {len(kept)} dipakai")
            if not token:
                break
        progress["done"].append(task_id)
        done.add(task_id)
        _save_places(rows, progress)
    return progress


# ------------------------------------------------------------------ merging


def same_place_name(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= config.DEDUPE_NAME_RATIO


def dedupe_venues(venues_utm: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per real place and sport. Google rows win over OSM rows.

    Works in meters, so the input must be in EPSG:32749.
    """
    if venues_utm.crs.to_string() != config.CRS_UTM:
        raise ValueError("dedupe_venues needs EPSG:32749")
    is_osm = venues_utm["Tempat_ID"].str.startswith("osm:")
    ordered = venues_utm.assign(_osm=is_osm).sort_values("_osm", kind="stable")
    kept_by_sport: dict[str, list] = {}
    keep = []
    for idx, row in ordered.iterrows():
        kept = kept_by_sport.setdefault(row["Jenis_Olahraga"], [])
        if any(row.geometry.distance(g) <= config.DEDUPE_DISTANCE_M and same_place_name(row["Nama"], n) for g, n in kept):
            continue
        kept.append((row.geometry, row["Nama"]))
        keep.append(idx)
    return ordered.loc[keep].drop(columns="_osm").reset_index(drop=True)


def merge_venues() -> gpd.GeoDataFrame:
    """Join both sources, keep what lies inside Surabaya, and write the file the app reads."""
    import gis

    parts = [gpd.read_file(p).to_crs(config.CRS_UTM) for p in (config.VENUES_GOOGLE, config.VENUES_OSM) if p.exists()]
    combined = gpd.GeoDataFrame(gpd.pd.concat(parts, ignore_index=True), crs=config.CRS_UTM)
    boundary, _ = gis.load_boundary()
    inside = gis.spatial_join(combined, boundary)
    merged = dedupe_venues(inside).to_crs(config.CRS_WGS84)
    merged[VENUE_COLUMNS].to_file(config.VENUES_CACHE, driver="GeoJSON")
    print(f"Gabungan: {len(combined)} baris masuk, {len(inside)} di dalam Surabaya, {len(merged)} setelah dedup")
    return merged


# ---------------------------------------------------------------- geocoding


def geocode(address: str, api_key: str) -> tuple[float, float] | None:
    """Return (lat, lon) for an address, or None when nothing matches.

    Google first. When Google itself fails (quota used up, billing off, no
    network), OpenStreetMap answers instead of the app guessing a location.
    """
    try:
        return geocode_google(address, api_key)
    except requests.RequestException:
        lowered = address.lower()
        for name, coords in config.KNOWN_PLACES.items():
            if name in lowered:
                return coords
        return geocode_nominatim(address)


def geocode_nominatim(address: str) -> tuple[float, float] | None:
    """Free OpenStreetMap geocoder. The viewbox is a preference, not a limit,
    so a far-away address stays far away and the distance check can reject it."""
    params = {"q": address, "format": "jsonv2", "limit": 1, "viewbox": NOMINATIM_VIEWBOX}
    resp = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def geocode_google(address: str, api_key: str) -> tuple[float, float] | None:
    """Tries the Geocoding API first. If that API is not enabled on the key
    (REQUEST_DENIED), falls back to Places Text Search, which also resolves
    addresses and place names such as "Universitas Ciputra".
    """
    params = {"address": address, "key": api_key, "region": "id", "language": "id"}
    resp = requests.get(GEOCODE_URL, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    if data.get("status") != "REQUEST_DENIED":
        return None

    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": "places.location"}
    # Bias, not ", Surabaya" in the text: that turned "Singapore" into a school in
    # Surabaya, so the distance limit measured the wrong place.
    center = {"latitude": config.MAP_CENTER[0], "longitude": config.MAP_CENTER[1]}
    body = {
        "textQuery": address,
        "languageCode": "id",
        "locationBias": {"circle": {"center": center, "radius": config.PLACES_BIAS_RADIUS_M}},
    }
    resp = requests.post(PLACES_URL, json=body, headers=headers, timeout=TIMEOUT_S)
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        return None
    loc = places[0]["location"]
    return loc["latitude"], loc["longitude"]


# ----------------------------------------------------------- boundary, graph


def build_boundary() -> float:
    """Write the Surabaya polygon and its simplified fallback. Returns the area in km2.

    Keeps the MultiPolygon as OSM has it. Refuses a shape of the wrong size
    rather than overwriting a good file.
    """
    import osmnx as ox

    gdf = ox.geocode_to_gdf(config.BOUNDARY_OSM_ID, by_osmid=True)[["display_name", "geometry"]]
    utm = gdf.to_crs(config.CRS_UTM)
    area_km2 = utm.geometry.iloc[0].area / 1e6
    low, high = config.BOUNDARY_AREA_RANGE_KM2
    if not low <= area_km2 <= high:
        raise ValueError(f"Luas {area_km2:.1f} km2 di luar {low}-{high} km2")
    gdf.to_file(config.BOUNDARY_AREA, driver="GeoJSON")
    simple = utm.assign(geometry=utm.simplify(config.BOUNDARY_SIMPLIFY_M))
    simple.to_crs(config.CRS_WGS84).to_file(config.BOUNDARY_MANUAL, driver="GeoJSON")
    return area_km2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--boundary", action="store_true", help="rebuild data/surabaya_area.geojson and surabaya_manual.geojson")
    parser.add_argument("--osm", action="store_true", help="refetch venues from OpenStreetMap")
    parser.add_argument("--graph", action="store_true", help="rebuild the road graph from OpenStreetMap")
    parser.add_argument("--refresh", action="store_true", help="continue fetching venues from Google Places API")
    parser.add_argument("--budget", type=int, default=config.PLACES_DAILY_BUDGET, help="max Places requests this run")
    args = parser.parse_args()
    if not (args.boundary or args.osm or args.graph or args.refresh):
        parser.print_help()
        return 0

    config.DATA_DIR.mkdir(exist_ok=True)
    if args.boundary:
        area_km2 = build_boundary()
        print(f"Tersimpan {config.BOUNDARY_AREA}: {area_km2:.1f} km2")
    if args.osm:
        gdf = fetch_osm()
        gdf.to_file(config.VENUES_OSM, driver="GeoJSON")
        print(f"Tersimpan {len(gdf)} baris ke {config.VENUES_OSM}")
    if args.graph:
        import gis

        started = time.perf_counter()
        boundary, _ = gis.load_boundary()
        graph = gis.build_graph(boundary)
        size_mb = config.GRAPH_CACHE.stat().st_size / 1e6
        print(f"Graph: {len(graph)} node, {graph.number_of_edges()} edge, {size_mb:.0f} MB, {time.perf_counter() - started:.0f} detik")
    if args.refresh:
        if not config.GOOGLE_MAPS_API_KEY:
            print("GOOGLE_MAPS_API_KEY belum diisi di .env", file=sys.stderr)
            return 1
        import gis

        boundary, _ = gis.load_boundary()
        progress = fetch_places(config.GOOGLE_MAPS_API_KEY, args.budget, boundary)
        left = progress["total_tasks"] - len(progress["done"])
        print(f"Places: {len(progress['done'])}/{progress['total_tasks']} query selesai, sisa {left}; berhenti: {progress['stopped']}")
    if args.osm or args.refresh:
        merge_venues()
    return 0


if __name__ == "__main__":
    sys.exit(main())
