"""Fetch venues (Places API) and geocode addresses (Geocoding API).

Run `python data_fetch.py --refresh` to rebuild data/venues.geojson.
"""

import argparse
import json
import sys

import geopandas as gpd
import requests
from shapely.geometry import Point

import config

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
FIELD_MASK = "places.id,places.displayName,places.location,places.primaryType,places.regularOpeningHours"
TIMEOUT_S = 15


def search_places(sport_key: str, api_key: str) -> list[dict]:
    """One Places Text Search per sport, biased to the CitraLand area."""
    sport = config.SPORTS[sport_key]
    body = {
        "textQuery": f"{sport['query']} CitraLand Surabaya",
        "languageCode": "id",
        "locationBias": {
            "circle": {
                "center": {"latitude": config.MAP_CENTER[0], "longitude": config.MAP_CENTER[1]},
                "radius": config.PLACES_BIAS_RADIUS_M,
            }
        },
    }
    headers = {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": FIELD_MASK}
    resp = requests.post(PLACES_URL, json=body, headers=headers, timeout=TIMEOUT_S)
    resp.raise_for_status()

    rows = []
    for place in resp.json().get("places", []):
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
    return rows


def names_other_sport(name: str, sport_key: str) -> bool:
    """True when the name clearly belongs to another sport and not this one.

    Text Search is loose: "lapangan futsal" also returns tennis courts.
    Names that mention no sport at all (e.g. "Citraland Square Park") are kept.
    """
    lowered = name.lower()
    if any(w in lowered for w in config.SPORTS[sport_key]["words"]):
        return False
    return any(w in lowered for k, s in config.SPORTS.items() if k != sport_key for w in s["words"])


def fetch_all_venues(api_key: str) -> gpd.GeoDataFrame:
    rows = []
    for sport_key in config.SPORTS:
        found = [r for r in search_places(sport_key, api_key) if not names_other_sport(r["Nama"], sport_key)]
        print(f"  {sport_key}: {len(found)} tempat")
        rows.extend(found)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=config.CRS_WGS84)
    # A sports centre can show up under several keywords; keep one row per (place, sport).
    return gdf.drop_duplicates(subset=["Tempat_ID", "Jenis_Olahraga"]).reset_index(drop=True)


def geocode(address: str, api_key: str) -> tuple[float, float] | None:
    """Return (lat, lon) for an address, or None when Google finds nothing.

    Tries the Geocoding API first. If that API is not enabled on the key
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
    body = {"textQuery": f"{address}, Surabaya", "languageCode": "id"}
    resp = requests.post(PLACES_URL, json=body, headers=headers, timeout=TIMEOUT_S)
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        return None
    loc = places[0]["location"]
    return loc["latitude"], loc["longitude"]


def build_area() -> gpd.GeoDataFrame:
    """Full CitraLand polygon: two OSM pieces plus the hand-drawn outline.

    OSM only maps "Citraland, RW 07, Made" and "Citraland Utara"; Northwest
    and the GreenLake have no polygon, so HAND_DRAWN_AREA fills them in.
    """
    import osmnx as ox
    from shapely.geometry import Polygon

    main_osm = ox.geocode_to_gdf(config.BOUNDARY_QUERY).geometry.iloc[0]
    utara_osm = ox.geocode_to_gdf(config.BOUNDARY_QUERY_UTARA).geometry.iloc[0]
    pieces = gpd.GeoSeries([main_osm, utara_osm, Polygon(config.HAND_DRAWN_AREA)], crs=config.CRS_WGS84)
    # Close the thin gaps where the pieces almost touch, then drop interior holes.
    merged = pieces.to_crs(config.CRS_UTM).union_all().buffer(50).buffer(-50)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)
    merged = Polygon(merged.exterior)
    return gpd.GeoDataFrame(
        {
            "name": ["CitraLand Surabaya"],
            "source": ["OSM: Citraland (RW 07 Made) + Citraland Utara; hand-drawn approximation: Northwest, GreenLake, gaps"],
        },
        geometry=[merged],
        crs=config.CRS_UTM,
    ).to_crs(config.CRS_WGS84)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refetch venues from Google Places API")
    parser.add_argument("--boundary", action="store_true", help="rebuild data/citraland_area.geojson")
    args = parser.parse_args()
    if args.boundary:
        area = build_area()
        area.to_file(config.BOUNDARY_AREA, driver="GeoJSON")
        utm = area.to_crs(config.CRS_UTM).geometry.iloc[0]
        c = area.geometry.iloc[0].centroid
        print(f"Tersimpan {config.BOUNDARY_AREA}: {utm.area / 1e6:.2f} km2, pusat ({c.y:.4f}, {c.x:.4f})")
    if not args.refresh:
        if not args.boundary:
            parser.print_help()
        return 0
    if not config.GOOGLE_MAPS_API_KEY:
        print("GOOGLE_MAPS_API_KEY belum diisi di .env", file=sys.stderr)
        return 1
    print("Mengambil data tempat olahraga dari Google Places API...")
    gdf = fetch_all_venues(config.GOOGLE_MAPS_API_KEY)
    config.DATA_DIR.mkdir(exist_ok=True)
    gdf.to_file(config.VENUES_CACHE, driver="GeoJSON")
    print(f"Tersimpan {len(gdf)} baris ke {config.VENUES_CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
