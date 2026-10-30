"""Spatial layers and GIS operations.

All distance work happens in EPSG:32749 (meters). Results are converted
back to EPSG:4326 only when they are drawn on the Folium map.
"""

import geopandas as gpd
import osmnx as ox
from shapely.geometry import LineString, Point

import config

_graph_cache = None


# ---------------------------------------------------------------- layers


def load_boundary() -> tuple[gpd.GeoDataFrame, str]:
    """Layer 2: CitraLand polygon. Returns (gdf in UTM, source label)."""
    if config.BOUNDARY_AREA.exists():
        return gpd.read_file(config.BOUNDARY_AREA).to_crs(config.CRS_UTM), "OSM + manual"
    if config.BOUNDARY_CACHE.exists():
        return gpd.read_file(config.BOUNDARY_CACHE).to_crs(config.CRS_UTM), "OSM (cache)"
    try:
        gdf = ox.geocode_to_gdf(config.BOUNDARY_QUERY)
        if gdf.geometry.iloc[0].geom_type in ("Polygon", "MultiPolygon"):
            gdf = gdf[["display_name", "geometry"]]
            gdf.to_file(config.BOUNDARY_CACHE, driver="GeoJSON")
            return gdf.to_crs(config.CRS_UTM), "OSM"
    except Exception:  # no network or no OSM match: fall through to the manual polygon
        pass
    return gpd.read_file(config.BOUNDARY_MANUAL).to_crs(config.CRS_UTM), "manual (perkiraan)"


def load_venues() -> tuple[gpd.GeoDataFrame, str]:
    """Layer 1: sports venues. Real cache first, otherwise the sample file."""
    if config.VENUES_CACHE.exists():
        path, source = config.VENUES_CACHE, "Google Places (cache)"
    else:
        path, source = config.VENUES_SAMPLE, "data contoh"
    return gpd.read_file(path).to_crs(config.CRS_UTM), source


def point_from_latlon(lat: float, lon: float) -> gpd.GeoSeries:
    """User point, projected to UTM."""
    return gpd.GeoSeries([Point(lon, lat)], crs=config.CRS_WGS84).to_crs(config.CRS_UTM)


# ------------------------------------------------------------ operations


def spatial_join(venues: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep venues inside the CitraLand polygon or on its edge."""
    joined = gpd.sjoin(venues, boundary[["geometry"]], how="inner", predicate="intersects")
    return joined.drop(columns="index_right").drop_duplicates(subset=["Tempat_ID", "Jenis_Olahraga"])


def filter_by_sport(venues: gpd.GeoDataFrame, sport: str) -> gpd.GeoDataFrame:
    if not sport or sport == "semua":
        return venues
    return venues[venues["Jenis_Olahraga"] == sport]


def rank_by_distance(venues: gpd.GeoDataFrame, user_point: gpd.GeoSeries) -> gpd.GeoDataFrame:
    """Straight-line distance in meters, nearest first."""
    if venues.crs.to_string() != config.CRS_UTM or user_point.crs.to_string() != config.CRS_UTM:
        raise ValueError("rank_by_distance needs both layers in EPSG:32749")
    venues = venues.copy()
    venues["Jarak_m"] = venues.geometry.distance(user_point.iloc[0])
    return venues.sort_values("Jarak_m").reset_index(drop=True)


def get_graph(boundary: gpd.GeoDataFrame):
    """Drive network around CitraLand, projected to UTM. Cached on disk and in memory."""
    global _graph_cache
    if _graph_cache is not None:
        return _graph_cache
    if config.GRAPH_CACHE.exists():
        graph = ox.load_graphml(config.GRAPH_CACHE)
    else:
        area = boundary.buffer(config.GRAPH_BUFFER_M).to_crs(config.CRS_WGS84).union_all()
        graph = ox.graph_from_polygon(area, network_type="drive")
        ox.save_graphml(graph, config.GRAPH_CACHE)
    _graph_cache = ox.project_graph(graph, to_crs=config.CRS_UTM)
    return _graph_cache


def _route(graph, origin: Point, dest: Point) -> dict | None:
    # Snap both ends to the nearest road node: a new venue from Google may sit
    # on a driveway that OSM has not mapped yet.
    o_node = ox.distance.nearest_nodes(graph, X=origin.x, Y=origin.y)
    d_node = ox.distance.nearest_nodes(graph, X=dest.x, Y=dest.y)
    nodes = ox.routing.shortest_path(graph, o_node, d_node, weight="length")
    if not nodes:
        return None
    length_m = 0.0 if len(nodes) < 2 else ox.routing.route_to_gdf(graph, nodes)["length"].sum()
    coords = [(graph.nodes[n]["x"], graph.nodes[n]["y"]) for n in nodes]
    line = LineString([(origin.x, origin.y), *coords, (dest.x, dest.y)])
    return {"length_m": float(length_m), "line": line}


def route_to_nearest(ranked: gpd.GeoDataFrame, user_point: gpd.GeoSeries, graph) -> tuple[gpd.GeoDataFrame, dict | None]:
    """Route to the top straight-line candidates and pick the shortest by road.

    The straight-line nearest venue is not always nearest by road, so the
    top ROUTE_CANDIDATES are compared on route length.
    """
    ranked = ranked.copy()
    ranked["Jarak_Rute_m"] = None
    best = None
    origin = user_point.iloc[0]
    for idx in ranked.index[: config.ROUTE_CANDIDATES]:
        result = _route(graph, origin, ranked.at[idx, "geometry"])
        if result is None:
            continue
        ranked.at[idx, "Jarak_Rute_m"] = result["length_m"]
        if best is None or result["length_m"] < best["length_m"]:
            best = {**result, "index": idx}
    if best is None:
        return ranked, None
    best["line_wgs84"] = gpd.GeoSeries([best["line"]], crs=config.CRS_UTM).to_crs(config.CRS_WGS84).iloc[0]
    return ranked, best
