"""Flask web GUI for Surabaya Sport Finder."""

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
@media (max-width:640px){.legend{top:12px;bottom:auto;left:12px;padding:8px 10px}
.legend .rows{display:grid;grid-template-columns:auto auto;gap:0 12px}}
</style>
"""


def km_text(meters: float) -> str:
    return f"{meters / 1000:.2f}".replace(".", ",") + " km"


def resolve_origin(address: str, warnings: list[str]) -> tuple[float, float, str] | None:
    """Geocode the address. None when it does not exist.

    Falls back to the Universitas Ciputra coordinate only when geocoding itself
    is unavailable (no API key or a failed request).
    """
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
        return None
    return found[0], found[1], address


def build_map(venues, user=None, route=None):
    # Canvas: one element per marker would slow the browser down at city scale.
    # Half zoom steps: on a phone a whole step leaves the city far smaller than the space it has.
    m = folium.Map(location=config.MAP_CENTER, tiles="OpenStreetMap", zoom_control=False, prefer_canvas=True, zoom_snap=0.5)
    # Google tiles need a paid Map Tiles API key and agreement to Google's terms:
    # folium.TileLayer("https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", attr="Google").add_to(m)

    boundary = BOUNDARY.to_crs(config.CRS_WGS84)
    folium.GeoJson(
        boundary.geometry,
        name="Batas Kota Surabaya",
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
    m.options["zoom"] = 12
    # Fit in the browser so the padding can follow the screen: the panel sits on
    # the left on desktop (~376 px) and as a bottom sheet on phones. The sheet's
    # height changes with the result card and warnings, so it is measured.
    fit_js = (
        f"var bounds = [[{b[1]}, {b[0]}], [{b[3]}, {b[2]}]];"
        "var narrow = window.innerWidth <= 640;"
        "var sheet = narrow && window.parent.document.getElementById('panel');"
        "var below = sheet ? Math.round(window.innerHeight - sheet.getBoundingClientRect().top) + 12 : Math.round(window.innerHeight * 0.55);"
        f"{m.get_name()}.fitBounds(bounds, narrow"
        " ? {paddingTopLeft: [24, 130], paddingBottomRight: [24, below]}"
        " : {paddingTopLeft: [400, 40], paddingBottomRight: [60, 40]});"
    )

    legend = "".join(
        f'<div><span style="background:{g["color"]}"></span>{g["label"]}</div>' for g in config.GROUPS.values()
    )
    m.get_root().header.add_child(Element(MAP_CSS))
    m.get_root().html.add_child(Element(f'<div class="legend"><b>Olahraga</b><div class="rows">{legend}</div></div>'))
    # Figure scripts render before the map's own script, so wait until the map exists.
    m.get_root().script.add_child(Element(
        "window.addEventListener('load', function () {"
        f" L.control.zoom({{position: 'topright'}}).addTo({m.get_name()});"
        f" {m.get_name()}.attributionControl.addAttribution('Data tempat: OpenStreetMap, Google');"
        f" {fit_js} }});"
    ))
    return m._repr_html_()


@app.route("/")
def index():
    action = request.args.get("action", "")
    sport = request.args.get("sport", "semua")
    address = request.args.get("address", "").strip()

    warnings: list[str] = []
    if VENUES_SOURCE == "data contoh":
        warnings.append("Memakai data contoh (bukan data asli). Jalankan `python data_fetch.py --refresh` dengan API key.")
    if BOUNDARY_SOURCE.startswith("manual"):
        warnings.append("Batas Kota Surabaya memakai polygon manual (perkiraan).")

    page = {"sports": config.SPORTS, "groups": config.GROUPS, "sport": sport, "address": address,
            "warnings": warnings, "result": None, "notice": None}

    venues = gis.spatial_join(VENUES_ALL, BOUNDARY)
    if not action:
        # First load: every venue, no filter, no route.
        return render_template("index.html", map_html=build_map(venues), **page)

    venues = gis.filter_by_sport(venues, sport)
    user, best = None, None

    if action == "route":
        query = address or config.FALLBACK_ORIGIN["name"]
        resolved = resolve_origin(query, warnings)
        if resolved is None:
            page["notice"] = f"Alamat \"{query}\" tidak ditemukan."
            return render_template("index.html", map_html=build_map(venues), **page)
        lat, lon, name = resolved
        origin = gis.point_from_latlon(lat, lon)
        away_m = gis.distance_to_boundary(origin, BOUNDARY)
        if away_m > config.MAX_ORIGIN_DISTANCE_M:
            # Too far out: no marker and no route, the map stays on Surabaya.
            page["notice"] = (f"Alamat \"{name}\" berjarak {km_text(away_m)} dari batas Kota Surabaya. "
                              f"Maksimal {km_text(config.MAX_ORIGIN_DISTANCE_M)}.")
            return render_template("index.html", map_html=build_map(venues), **page)
        user = {"lat": lat, "lon": lon, "name": name}
        ranked = gis.rank_by_distance(venues, origin)
        graph = gis.get_graph()
        if ranked.empty:
            page["notice"] = "Tidak ada tempat yang cocok dengan filter ini."
        elif graph is None:
            warnings.append("Data jalan belum dibangun. Jalankan `python data_fetch.py --graph`.")
        else:
            try:
                ranked, best = gis.route_to_nearest(ranked, origin, graph)
            except Exception as exc:
                warnings.append(f"Rute tidak bisa dihitung ({exc.__class__.__name__}).")
            if best:
                target = ranked.loc[best["index"]]
                sport_info = config.SPORTS.get(target["Jenis_Olahraga"], {"label": target["Jenis_Olahraga"], "color": "#888"})
                page["result"] = {"name": target["Nama"], "sport": sport_info["label"],
                                "color": sport_info["color"], "distance": km_text(best["length_m"])}
            venues = ranked

    return render_template("index.html", map_html=build_map(venues, user, best), **page)


if __name__ == "__main__":
    app.run(debug=True)
