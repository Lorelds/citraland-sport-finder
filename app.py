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

# Styles injected into the map iframe; the page stylesheet does not reach inside it.
MAP_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
.legend{position:absolute;bottom:16px;left:16px;z-index:999;background:#fff;padding:12px 14px;
  border-radius:12px;box-shadow:0 4px 20px rgba(15,23,42,.15);font:12px Inter,system-ui,sans-serif;color:#0f172a}
.legend b{display:block;margin-bottom:6px;font-weight:600}
.legend div{display:flex;align-items:center;gap:8px;line-height:20px}
.legend span{width:10px;height:10px;border-radius:50%}
.leaflet-tooltip{font-family:Inter,system-ui,sans-serif}
@media (max-width:640px){.legend{top:12px;bottom:auto;left:12px;padding:8px 10px}}
</style>
"""


def km_text(meters: float) -> str:
    return f"{meters / 1000:.2f}".replace(".", ",") + " km"


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
    m = folium.Map(location=config.MAP_CENTER, tiles="OpenStreetMap", zoom_control=False)
    # Google tiles need a paid Map Tiles API key and agreement to Google's terms:
    # folium.TileLayer("https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", attr="Google").add_to(m)

    boundary = BOUNDARY.to_crs(config.CRS_WGS84)
    folium.GeoJson(
        boundary.geometry,
        name="Batas CitraLand",
        style_function=lambda _: {"color": "#334155", "weight": 2, "dashArray": "6 4", "fillColor": "#334155", "fillOpacity": 0.04},
    ).add_to(m)

    for _, v in venues.to_crs(config.CRS_WGS84).iterrows():
        sport = config.SPORTS.get(v["Jenis_Olahraga"], {"label": v["Jenis_Olahraga"], "color": "#888"})
        folium.CircleMarker(
            location=(v.geometry.y, v.geometry.x),
            radius=7,
            color="#fff",
            weight=2,
            fill=True,
            fill_color=sport["color"],
            fill_opacity=1,
            tooltip=f"{v['Nama']} ({sport['label']})",
        ).add_to(m)

    if user:
        folium.Marker((user["lat"], user["lon"]), tooltip=f"Alamat awal: {user['name']}",
                      icon=folium.Icon(color="black", icon="home")).add_to(m)

    if route:
        line = route["line_wgs84"]
        coords = [(y, x) for x, y in line.coords]
        # White casing under the route keeps it readable over roads and markers.
        folium.PolyLine(coords, color="#fff", weight=9, opacity=0.9).add_to(m)
        folium.PolyLine(coords, color=config.ACCENT_COLOR, weight=5, tooltip=km_text(route["length_m"])).add_to(m)
        b = line.bounds
    else:
        b = boundary.total_bounds
    m.location = [(b[1] + b[3]) / 2, (b[0] + b[2]) / 2]
    m.options["zoom"] = 14
    # Fit in the browser so the padding can follow the screen: the panel sits on
    # the left on desktop (~376 px) and as a bottom sheet on phones.
    fit_js = (
        f"var bounds = [[{b[1]}, {b[0]}], [{b[3]}, {b[2]}]];"
        "var narrow = window.innerWidth <= 640;"
        f"{m.get_name()}.fitBounds(bounds, narrow"
        " ? {paddingTopLeft: [24, 150], paddingBottomRight: [24, Math.round(window.innerHeight * 0.55)]}"
        " : {paddingTopLeft: [400, 40], paddingBottomRight: [60, 40]});"
    )

    legend = "".join(
        f'<div><span style="background:{s["color"]}"></span>{s["label"]}</div>' for s in config.SPORTS.values()
    )
    m.get_root().header.add_child(Element(MAP_CSS))
    m.get_root().html.add_child(Element(f'<div class="legend"><b>Olahraga</b>{legend}</div>'))
    # Figure scripts render before the map's own script, so wait until the map exists.
    m.get_root().script.add_child(Element(
        f"window.addEventListener('load', function () {{ L.control.zoom({{position: 'topright'}}).addTo({m.get_name()}); {fit_js} }});"
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

    page = {"sports": config.SPORTS, "sport": sport, "address": address, "open_now": open_only,
            "warnings": warnings, "result": None, "notice": None}

    venues = gis.spatial_join(VENUES_ALL, BOUNDARY)
    if not action:
        # First load: every venue, no filter, no route.
        return render_template("index.html", map_html=build_map(venues), **page)

    venues = gis.filter_by_sport(venues, sport)
    venues = gis.filter_open_now(venues, enabled=open_only)
    user, best = None, None

    if action == "route":
        lat, lon, name = resolve_origin(address or config.FALLBACK_ORIGIN["name"], warnings)
        user = {"lat": lat, "lon": lon, "name": name}
        ranked = gis.rank_by_distance(venues, gis.point_from_latlon(lat, lon))
        if ranked.empty:
            page["notice"] = "Tidak ada tempat yang cocok dengan filter ini."
        else:
            try:
                ranked, best = gis.route_to_nearest(ranked, gis.point_from_latlon(lat, lon), gis.get_graph(BOUNDARY))
            except Exception as exc:
                warnings.append(f"Rute tidak bisa dihitung ({exc.__class__.__name__}). Butuh internet untuk jaringan jalan OSM pertama kali.")
            if best:
                target = ranked.loc[best["index"]]
                sport_info = config.SPORTS.get(target["Jenis_Olahraga"], {"label": target["Jenis_Olahraga"], "color": "#888"})
                page["result"] = {"name": target["Nama"], "sport": sport_info["label"],
                                  "color": sport_info["color"], "distance": km_text(best["length_m"])}
            venues = ranked

    return render_template("index.html", map_html=build_map(venues, user, best), **page)


if __name__ == "__main__":
    app.run(debug=True)
