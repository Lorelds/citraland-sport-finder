import json
import sys
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pytest
import requests
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import data_fetch  # noqa: E402
import gis  # noqa: E402

SIDOARJO = (-7.4478, 112.7183)  # Alun-alun Sidoarjo, about 11 km south of the city edge
GRESIK = (-7.1566, 112.6555)
TUNJUNGAN_PLAZA = (-7.2625, 112.7390)
ITS = (-7.2797, 112.7975)
GOR_UNESA = (-7.2988, 112.6687)
PURABAYA = (-7.3513, 112.7240)  # Terminal Purabaya, just over the southern edge


@pytest.fixture
def boundary():
    return gpd.read_file(config.BOUNDARY_MANUAL).to_crs(config.CRS_UTM)


@pytest.fixture
def venues():
    return gpd.read_file(config.VENUES_SAMPLE).to_crs(config.CRS_UTM)


def venue_rows(*rows):
    """GeoDataFrame in UTM from (id, name, sport, lat, lon) tuples."""
    data = [
        {"Tempat_ID": i, "Nama": n, "Kategori": "x", "Jenis_Olahraga": s, "opening_hours": None, "geometry": Point(lon, lat)}
        for i, n, s, lat, lon in rows
    ]
    return gpd.GeoDataFrame(data, geometry="geometry", crs=config.CRS_WGS84).to_crs(config.CRS_UTM)


def test_spatial_join_drops_point_outside(boundary, venues):
    outside = venue_rows(("luar", "Luar", "gym", *SIDOARJO))
    combined = gpd.GeoDataFrame(
        gpd.pd.concat([venues, outside], ignore_index=True), crs=config.CRS_UTM
    )
    joined = gis.spatial_join(combined, boundary)
    assert "luar" not in set(joined["Tempat_ID"])
    assert len(joined) == len(venues)


def test_distance_to_boundary_limit():
    boundary = gpd.read_file(config.BOUNDARY_AREA).to_crs(config.CRS_UTM)
    inside = gis.point_from_latlon(**{k: config.FALLBACK_ORIGIN[k] for k in ("lat", "lon")})
    assert gis.distance_to_boundary(inside, boundary) == 0
    near = gis.point_from_latlon(*PURABAYA)
    assert 0 < gis.distance_to_boundary(near, boundary) <= config.MAX_ORIGIN_DISTANCE_M
    far = gis.point_from_latlon(*SIDOARJO)
    assert gis.distance_to_boundary(far, boundary) > config.MAX_ORIGIN_DISTANCE_M


@pytest.mark.parametrize("found,expected", [
    ((3.1390, 101.6869), "berjarak"),  # Kuala Lumpur
    (SIDOARJO, "berjarak"),
    (None, "tidak ditemukan"),
])
def test_route_refuses_bad_origin(monkeypatch, found, expected):
    import app

    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "test")
    monkeypatch.setattr(data_fetch, "geocode", lambda address, key: found)
    html = app.app.test_client().get("/?action=route&address=Test").get_data(as_text=True)
    assert expected in html
    assert "Terdekat lewat jalan" not in html


def test_route_without_graph_warns_instead_of_downloading(monkeypatch):
    import app

    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "test")
    monkeypatch.setattr(data_fetch, "geocode", lambda address, key: TUNJUNGAN_PLAZA)
    monkeypatch.setattr(gis, "get_graph", lambda: None)
    monkeypatch.setattr(ox, "graph_from_polygon", lambda *a, **k: pytest.fail("downloaded during a request"))
    resp = app.app.test_client().get("/?action=route&address=Test")
    assert resp.status_code == 200
    assert "--graph" in resp.get_data(as_text=True)


@pytest.mark.parametrize("sport", ["semua", *config.SPORTS])
def test_filter_every_sport_responds(sport):
    import app

    assert app.app.test_client().get(f"/?action=filter&sport={sport}").status_code == 200


def test_every_sport_is_in_a_group_shown_in_the_dropdown():
    import app

    html = app.app.test_client().get("/").get_data(as_text=True)
    assert all(s["group"] in config.GROUPS for s in config.SPORTS.values())
    assert all(f'<optgroup label="{g["label"]}">' in html for g in config.GROUPS.values())
    assert all(f'value="{key}"' in html for key in config.SPORTS)


def test_filter_by_sport(venues):
    result = gis.filter_by_sport(venues, "badminton")
    assert len(result) == 2
    assert set(result["Jenis_Olahraga"]) == {"badminton"}
    assert len(gis.filter_by_sport(venues, "semua")) == len(venues)


def test_rank_by_distance_order(venues):
    user = gis.point_from_latlon(**{k: config.FALLBACK_ORIGIN[k] for k in ("lat", "lon")})
    ranked = gis.rank_by_distance(venues, user)
    assert list(ranked["Jarak_m"]) == sorted(ranked["Jarak_m"])
    # Meters, not degrees: every sample venue is a few hundred m to a few km away.
    assert 100 < ranked["Jarak_m"].iloc[0] < 10_000


def test_distances_use_utm(venues):
    user = gis.point_from_latlon(config.FALLBACK_ORIGIN["lat"], config.FALLBACK_ORIGIN["lon"])
    assert venues.crs.to_epsg() == 32749
    assert user.crs.to_epsg() == 32749
    with pytest.raises(ValueError):
        gis.rank_by_distance(venues.to_crs(config.CRS_WGS84), user)


def test_route_snaps_all_points_in_one_call(monkeypatch):
    """Three nodes on a line, 500 m apart. The nearer venue by road wins."""
    x0, y0 = 690000.0, 9195000.0
    graph = nx.MultiDiGraph(crs=config.CRS_UTM)
    for node, x in {1: x0, 2: x0 + 500, 3: x0 + 1000}.items():
        graph.add_node(node, x=x, y=y0)
    for u, v in [(1, 2), (2, 1), (2, 3), (3, 2)]:
        graph.add_edge(u, v, length=500.0)

    user = gpd.GeoSeries([Point(x0, y0)], crs=config.CRS_UTM)
    points = [Point(x0 + 1000, y0), Point(x0 + 500, y0)]
    ranked = gpd.GeoDataFrame({"Nama": ["jauh", "dekat"]}, geometry=points, crs=config.CRS_UTM)

    calls = []
    real = ox.distance.nearest_nodes
    monkeypatch.setattr(ox.distance, "nearest_nodes", lambda *a, **k: calls.append(1) or real(*a, **k))
    _, best = gis.route_to_nearest(ranked, user, graph)
    assert len(calls) == 1
    assert ranked.loc[best["index"], "Nama"] == "dekat"
    assert best["length_m"] == 500


def test_names_other_sport():
    assert data_fetch.names_other_sport("Tennis Court TPR Citraland", "futsal") is True
    assert data_fetch.names_other_sport("Kolam Renang dan Arena Tenis G-Walk", "tenis") is False
    assert data_fetch.names_other_sport("Citraland Square Park", "futsal") is False
    # Tenis and tenis meja are separate sports.
    assert data_fetch.names_other_sport("Tenis Meja Citraland", "tenis") is True
    assert data_fetch.names_other_sport("Tenis Meja Citraland", "tenis_meja") is False
    assert data_fetch.names_other_sport("Padel Club Surabaya", "tenis") is True
    # Mini soccer moved from futsal to sepak bola.
    assert data_fetch.names_other_sport("Mini Soccer X", "futsal") is True
    assert data_fetch.names_other_sport("Mini Soccer X", "sepak_bola") is False
    # A general venue name says nothing about the sport played there.
    assert data_fetch.names_other_sport("GOR Unesa", "futsal") is False


@pytest.mark.parametrize("name,sport,expected", [
    ("Clarion Hotel", "atletik", False),  # "lari" inside a word
    ("Larissa", "atletik", False),
    ("Lintasan Lari GBT", "atletik", True),
    ("Pandawa Basketball", "basket", True),  # written-out variant
    ("Swimming Pool Ubaya", "renang", True),
    ("Karate Dojo", "gym", False),
    ("Martial Arts Club", "bela_diri", True),
    ("Martial Arts Club", "gym", False),
])
def test_names_sport_matches_whole_words(name, sport, expected):
    assert data_fetch.names_sport(name.lower(), sport) is expected


@pytest.mark.parametrize("tags,expected", [
    ({"sport": "TRX"}, ["gym"]),  # uppercase value
    ({"sport": "Lapangan Tenis"}, ["tenis"]),  # free text
    ({"sport": "soccer;basketball"}, ["sepak_bola", "basket"]),  # several values
    ({"sport": "tennis", "name": "Lapangan Futsal"}, ["tenis"]),  # the tag beats the name
    ({"sport": "motor", "name": "Sirkuit"}, ["lainnya"]),  # known to nothing
    ({"sport": "multi"}, ["serbaguna"]),
    ({"leisure": "fitness_centre"}, ["gym"]),
    ({"leisure": "swimming_pool"}, ["renang"]),
    ({"leisure": "pitch", "name": "Lapangan Merah"}, ["serbaguna"]),
    ({"leisure": "sports_centre", "name": "GOR Bulu Tangkis"}, ["badminton"]),
])
def test_osm_sports(tags, expected):
    assert data_fetch.osm_sports(tags) == expected


def test_osm_rows_drop_unnamed_private_and_shops():
    elements = [
        {"type": "way", "id": 1, "center": {"lat": -7.26, "lon": 112.73}, "tags": {"sport": "tennis;soccer", "name": "Lapangan A"}},
        {"type": "node", "id": 2, "lat": -7.27, "lon": 112.74, "tags": {"sport": "tennis", "name": "Lapangan B", "opening_hours": "Mo-Fr 08:00"}},
        {"type": "way", "id": 3, "center": {"lat": -7.26, "lon": 112.73}, "tags": {"sport": "tennis"}},
        {"type": "way", "id": 4, "center": {"lat": -7.26, "lon": 112.73}, "tags": {"sport": "tennis", "name": "Rumah", "access": "private"}},
        {"type": "node", "id": 5, "lat": -7.26, "lon": 112.73, "tags": {"sport": "tennis", "name": "Toko", "shop": "sports"}},
    ]
    rows, dropped = data_fetch.osm_rows(elements)
    assert dropped == {"tanpa_nama": 1, "private": 1, "toko": 1}
    assert [(r["Tempat_ID"], r["Jenis_Olahraga"]) for r in rows] == [
        ("osm:way/1", "tenis"), ("osm:way/1", "sepak_bola"), ("osm:node/2", "tenis"),
    ]
    assert json.loads(rows[2]["opening_hours"]) == "Mo-Fr 08:00"


@pytest.mark.parametrize("name,category,sport,expected", [
    ("Toko Raket", "sporting_goods_store", "badminton", False),
    ("Pasar Modern", "market", "tenis_meja", False),
    ("Weston Sports", "sports_club", "tenis_meja", False),  # city-wide query: must name the sport
    ("PTM Surabaya", "sports_club", "tenis_meja", True),
    ("Cuci Mobil", "car_wash", "futsal", False),  # grid query: must at least be a sports place
    ("Arena Surabaya", "sports_club", "futsal", True),
    ("Tennis Court", "athletic_field", "futsal", False),
    ("GOR Pancasila", "sports_complex", "serbaguna", True),
    ("Warung Bu Ani", "restaurant", "serbaguna", False),
])
def test_keep_place(name, category, sport, expected):
    assert data_fetch.keep_place({"Nama": name, "Kategori": category, "Jenis_Olahraga": sport}) is expected


def test_dedupe_keeps_google_row_and_only_merges_the_same_place():
    a = (-7.2625, 112.7390)
    near = (-7.2626, 112.7391)  # about 15 m from a
    far = (-7.2700, 112.7390)  # about 830 m from a
    rows = venue_rows(
        ("osm:way/1", "GOR Kertajaya", "badminton", *near),
        ("google1", "GOR Kertajaya Surabaya", "badminton", *a),
        ("osm:way/2", "GOR Kertajaya", "futsal", *near),  # other sport
        ("osm:way/3", "GOR Kertajaya", "badminton", *far),  # same name elsewhere
        ("osm:way/4", "Lapangan Pemuda", "badminton", *near),  # other name, same spot
    )
    result = data_fetch.dedupe_venues(rows)
    assert set(result["Tempat_ID"]) == {"google1", "osm:way/2", "osm:way/3", "osm:way/4"}


def test_dedupe_needs_meters():
    rows = venue_rows(("a", "A", "gym", *TUNJUNGAN_PLAZA)).to_crs(config.CRS_WGS84)
    with pytest.raises(ValueError):
        data_fetch.dedupe_venues(rows)


def test_grid_cells_cover_the_city_without_empty_cells():
    area = gpd.read_file(config.BOUNDARY_AREA).to_crs(config.CRS_UTM)
    cells = data_fetch.grid_cells(area)
    assert len({cell_id for cell_id, _ in cells}) == len(cells)
    for lat, lon in (TUNJUNGAN_PLAZA, ITS, GOR_UNESA):
        assert any(
            r["low"]["latitude"] <= lat <= r["high"]["latitude"] and r["low"]["longitude"] <= lon <= r["high"]["longitude"]
            for _, r in cells
        )


def test_places_tasks_do_city_wide_first_then_grid_by_least_osm_data(tmp_path, monkeypatch):
    area = gpd.read_file(config.BOUNDARY_AREA).to_crs(config.CRS_UTM)
    tasks = data_fetch.places_tasks(area)
    city_count = sum(not s["grid"] and bool(s["query"]) for s in config.SPORTS.values())
    assert all(t[0].endswith("|kota") for t in tasks[:city_count])
    assert not any(t[0].endswith("|kota") for t in tasks[city_count:])
    assert "lainnya" not in {t[1] for t in tasks}  # has no search text


@pytest.fixture
def places_env(tmp_path, monkeypatch):
    """Two tasks and temporary output files; no network."""
    monkeypatch.setattr(config, "VENUES_GOOGLE", tmp_path / "google.geojson")
    monkeypatch.setattr(config, "PLACES_PROGRESS", tmp_path / "progress.json")
    monkeypatch.setattr(data_fetch, "places_tasks", lambda boundary: [("a|kota", "basket", {}), ("b|kota", "futsal", {})])


def fake_row(sport):
    return {"Tempat_ID": f"id-{sport}", "Nama": f"Lapangan {sport}", "Kategori": "sports_club", "Jenis_Olahraga": sport,
            "opening_hours": None, "geometry": Point(112.73, -7.26)}


def test_places_stop_at_budget_and_resume(places_env, monkeypatch):
    calls = []

    def search(sport, rect, key, token=None):
        calls.append((sport, token))
        # Basket has a second page; every page counts toward the budget.
        return [fake_row(sport)], "next" if sport == "basket" and token is None else None

    monkeypatch.setattr(data_fetch, "search_places", search)
    progress = data_fetch.fetch_places("key", 2, None)
    assert calls == [("basket", None), ("basket", "next")]
    assert progress["done"] == ["a|kota"]
    assert "budget" in progress["stopped"]
    assert json.loads(config.PLACES_PROGRESS.read_text())["done"] == ["a|kota"]

    calls.clear()
    progress = data_fetch.fetch_places("key", 2, None)
    assert calls == [("futsal", None)]  # basket is not asked again
    assert progress["done"] == ["a|kota", "b|kota"]
    assert progress["stopped"] is None
    assert progress["requests"] == 3
    assert set(gpd.read_file(config.VENUES_GOOGLE)["Jenis_Olahraga"]) == {"basket", "futsal"}


@pytest.mark.parametrize("status", [429, 403])
def test_places_stop_on_quota_error_without_retry(places_env, monkeypatch, status):
    calls = []

    def search(sport, rect, key, token=None):
        calls.append(sport)
        if sport == "futsal":
            response = requests.Response()
            response.status_code = status
            raise requests.HTTPError(response=response)
        return [fake_row(sport)], None

    monkeypatch.setattr(data_fetch, "search_places", search)
    progress = data_fetch.fetch_places("key", 80, None)
    assert calls == ["basket", "futsal"]
    assert progress["done"] == ["a|kota"]
    assert progress["stopped"] == f"HTTP {status}"
    assert config.VENUES_GOOGLE.exists()


INSIDE = {
    "Universitas Ciputra": (config.FALLBACK_ORIGIN["lat"], config.FALLBACK_ORIGIN["lon"]),
    "GOR UNESA": GOR_UNESA,
    "Tunjungan Plaza": TUNJUNGAN_PLAZA,
    "ITS": ITS,
}
OUTSIDE = {"Alun-alun Sidoarjo": SIDOARJO, "Gresik": GRESIK}


@pytest.mark.parametrize("name,latlon", list(INSIDE.items()))
def test_area_contains_surabaya_places(name, latlon):
    area = gpd.read_file(config.BOUNDARY_AREA).geometry.iloc[0]
    assert area.intersects(Point(latlon[1], latlon[0])), name


@pytest.mark.parametrize("name,latlon", list(OUTSIDE.items()))
def test_area_excludes_other_cities(name, latlon):
    area = gpd.read_file(config.BOUNDARY_AREA).geometry.iloc[0]
    assert not area.intersects(Point(latlon[1], latlon[0])), name


def test_area_size_matches_the_city():
    area = gpd.read_file(config.BOUNDARY_AREA).to_crs(config.CRS_UTM).geometry.iloc[0]
    low, high = config.BOUNDARY_AREA_RANGE_KM2
    assert low <= area.area / 1e6 <= high
    assert area.geom_type == "MultiPolygon"


def test_osm_alone_covers_the_city():
    osm = gpd.read_file(config.VENUES_OSM)
    assert len(osm) >= 200
    assert osm["Jenis_Olahraga"].nunique() >= 15
    assert set(osm["Jenis_Olahraga"]) <= set(config.SPORTS)


def test_merged_venues_are_inside_surabaya():
    merged = gpd.read_file(config.VENUES_CACHE).to_crs(config.CRS_UTM)
    area = gpd.read_file(config.BOUNDARY_AREA).to_crs(config.CRS_UTM).geometry.iloc[0]
    assert merged.geometry.intersects(area).all()
    assert not merged.duplicated(subset=["Tempat_ID", "Jenis_Olahraga"]).any()


def test_geocode_falls_back_when_google_fails(monkeypatch):
    def google_down(address, key):
        raise requests.HTTPError("429")

    monkeypatch.setattr(data_fetch, "geocode_google", google_down)
    monkeypatch.setattr(data_fetch, "geocode_nominatim", lambda address: (-7.25, 112.63))
    assert data_fetch.geocode("Bukit Palma", "key") == (-7.25, 112.63)
    assert data_fetch.geocode("Citraland Northwest, Surabaya", "key") == config.KNOWN_PLACES["northwest"]
