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
                "radius": 4000.0,
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


def fetch_all_venues(api_key: str) -> gpd.GeoDataFrame:
    rows = []
    for sport_key in config.SPORTS:
        found = search_places(sport_key, api_key)
        print(f"  {sport_key}: {len(found)} tempat")
        rows.extend(found)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=config.CRS_WGS84)
    # A sports centre can show up under several keywords; keep one row per (place, sport).
    return gdf.drop_duplicates(subset=["Tempat_ID", "Jenis_Olahraga"]).reset_index(drop=True)


def geocode(address: str, api_key: str) -> tuple[float, float] | None:
    """Return (lat, lon) for an address, or None when Google finds nothing."""
    params = {"address": address, "key": api_key, "region": "id", "language": "id"}
    resp = requests.get(GEOCODE_URL, params=params, timeout=TIMEOUT_S)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    loc = results[0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="refetch venues from Google Places API")
    args = parser.parse_args()
    if not args.refresh:
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
