"""Flask web GUI for Citraland Sport Finder."""

import folium
from branca.element import Element
from flask import Flask, render_template, request

import config
import data_fetch
import gis

app = Flask(__name__)

BOUNDARY, BOUNDARY_SOURCE = gis.load_boundary()
VENUES_ALL, VENUES_SOURCE = gis.load_venues()


def resolve_origin(address: str, warnings: list[str]) -> tuple[float, float, str]:
    """Geocode the address, or fall back to the Universitas Ciputra coordinate."""
    fb = config.FALLBACK_ORIGIN
    if not config.GOOGLE_MAPS_API_KEY:
        warnings.append(f"API key belum diisi: alamat awal memakai koordinat {fb['name']}.")
        return fb["lat"], fb["lon"], fb["name"]
    try:
        found = data_fetch.geocode(address, config.GOOGLE_MAPS_API_KEY)
    except Exception as exc:
        warnings.append(f"Geocoding gagal ({exc.__class__.__name__}): memakai {fb['name']}.")
        return fb["lat"], fb["lon"], fb["name"]
    if found is None:
        warnings.append(f"Alamat tidak ditemukan: memakai {fb['name']}.")
        return fb["lat"], fb["lon"], fb["name"]
    return found[0], found[1], address


def build_map(venues, user=None, route=None):
    m = folium.Map(location=config.MAP_CENTER, zoom_start=14, tiles="OpenStreetMap")
    # Google tiles need a paid Map Tiles API key and agreement to Google's terms:
    # folium.TileLayer("https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", attr="Google").add_to(m)

    folium.GeoJson(
        BOUNDARY.to_crs(config.CRS_WGS84).geometry,
        name="Batas CitraLand",
        style_function=lambda _: {"color": "#555", "weight": 2, "fillOpacity": 0.05},
    ).add_to(m)

    for _, v in venues.to_crs(config.CRS_WGS84).iterrows():
        sport = config.SPORTS.get(v["Jenis_Olahraga"], {"label": v["Jenis_Olahraga"], "color": "#888"})
        folium.CircleMarker(
            location=(v.geometry.y, v.geometry.x),
            radius=8,
            color=sport["color"],
            fill=True,
            fill_opacity=0.9,
            tooltip=f"{v['Nama']} ({sport['label']})",
        ).add_to(m)

    if user:
        folium.Marker((user["lat"], user["lon"]), tooltip=f"Alamat awal: {user['name']}",
                      icon=folium.Icon(color="black", icon="home")).add_to(m)
    if route:
        line = route["line_wgs84"]
        folium.PolyLine([(y, x) for x, y in line.coords], color=config.ROUTE_COLOR, weight=5,
                        tooltip=f"{route['length_m'] / 1000:.2f} km, ±{route['minutes']:.0f} menit").add_to(m)
        m.fit_bounds([[line.bounds[1], line.bounds[0]], [line.bounds[3], line.bounds[2]]])

    legend = "".join(
        f'<div><span style="background:{s["color"]}"></span>{s["label"]}</div>' for s in config.SPORTS.values()
    )
    m.get_root().html.add_child(Element(f'<div class="legend"><b>Olahraga</b>{legend}</div>'))
    m.get_root().header.add_child(Element(
        "<style>.legend{position:absolute;bottom:20px;left:10px;z-index:9999;background:#fff;"
        "padding:8px 10px;border-radius:6px;font:12px sans-serif;box-shadow:0 1px 4px #0004}"
        ".legend span{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}</style>"
    ))
    return m._repr_html_()


@app.route("/")
def index():
    action = request.args.get("action", "")
    sport = request.args.get("sport", "semua")
    address = request.args.get("address", "").strip()
    # Checkbox defaults to on for the first page load.
    open_only = request.args.get("open_now") == "on" if action else True

    warnings: list[str] = []
    if VENUES_SOURCE == "data contoh":
        warnings.append("Memakai data contoh (bukan data asli). Jalankan `python data_fetch.py --refresh` dengan API key.")
    if BOUNDARY_SOURCE.startswith("manual"):
        warnings.append("Batas CitraLand memakai polygon manual (perkiraan).")

    venues = gis.spatial_join(VENUES_ALL, BOUNDARY)
    if not action:
        # First load: every venue, no filter, no route.
        venues = gis.filter_open_now(venues, enabled=False)
        return render_template("index.html", sports=config.SPORTS, sport=sport, address=address,
                               open_now=open_only, map_html=build_map(venues),
                               warnings=warnings, summary=None)

    venues = gis.filter_by_sport(venues, sport)
    venues = gis.filter_open_now(venues, enabled=open_only)
    user, best, summary = None, None, None

    if action == "route":
        lat, lon, name = resolve_origin(address or config.FALLBACK_ORIGIN["name"], warnings)
        user = {"lat": lat, "lon": lon, "name": name}
        ranked = gis.rank_by_distance(venues, gis.point_from_latlon(lat, lon))
        if ranked.empty:
            summary = "Tidak ada tempat yang cocok dengan filter ini."
        else:
            try:
                ranked, best = gis.route_to_nearest(ranked, gis.point_from_latlon(lat, lon), gis.get_graph(BOUNDARY))
            except Exception as exc:
                warnings.append(f"Rute tidak bisa dihitung ({exc.__class__.__name__}). Butuh internet untuk jaringan jalan OSM pertama kali.")
            if best:
                target = ranked.loc[best["index"]]
                km = f"{best['length_m'] / 1000:.2f}".replace(".", ",")
                summary = (f"Terdekat lewat jalan: {target['Nama']}, {km} km, "
                           f"±{best['minutes']:.0f} menit (asumsi {config.AVG_SPEED_KMH} km/jam).")
        venues = ranked if not ranked.empty else venues

    return render_template("index.html", sports=config.SPORTS, sport=sport, address=address,
                           open_now=open_only, map_html=build_map(venues, user, best),
                           warnings=warnings, summary=summary)


if __name__ == "__main__":
    app.run(debug=True)
