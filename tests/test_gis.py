import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import gis  # noqa: E402


@pytest.fixture
def boundary():
    return gpd.read_file(config.BOUNDARY_MANUAL).to_crs(config.CRS_UTM)


@pytest.fixture
def venues():
    return gpd.read_file(config.VENUES_SAMPLE).to_crs(config.CRS_UTM)


def test_spatial_join_drops_point_outside(boundary, venues):
    # Tunjungan Plaza, central Surabaya: well outside CitraLand.
    outside = gpd.GeoDataFrame(
        {"Tempat_ID": ["luar"], "Nama": ["Luar"], "Kategori": ["x"], "Jenis_Olahraga": ["gym"], "opening_hours": [None]},
        geometry=[Point(112.7390, -7.2625)], crs=config.CRS_WGS84,
    ).to_crs(config.CRS_UTM)
    combined = gpd.GeoDataFrame(
        gpd.pd.concat([venues, outside], ignore_index=True), crs=config.CRS_UTM
    )
    joined = gis.spatial_join(combined, boundary)
    assert "luar" not in set(joined["Tempat_ID"])
    assert len(joined) == len(venues)


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


def test_names_other_sport():
    import data_fetch

    assert data_fetch.names_other_sport("Tennis Court TPR Citraland", "futsal") is True
    assert data_fetch.names_other_sport("Kolam Renang dan Arena Tenis G-Walk", "tenis") is False
    assert data_fetch.names_other_sport("Citraland Square Park", "futsal") is False
    # Tenis and tenis meja are separate sports.
    assert data_fetch.names_other_sport("Tenis Meja Citraland", "tenis") is True
    assert data_fetch.names_other_sport("Tenis Meja Citraland", "tenis_meja") is False
    assert data_fetch.names_other_sport("Padel Club Surabaya", "tenis") is True


# Private Fitness is labelled "Ngagel" but its coordinate is inside OSM's own
# "Citraland Utara" polygon, so it counts as CitraLand.
INSIDE = {
    "KYZN / Ciputra Arena (Northwest)": (-7.2519, 112.6159),
    "Clubhouse Citraland Utara": (-7.2601, 112.6339),
    "Ola Fit Club The GreenLake": (-7.3096, 112.6564),
    "Nisrina Futsal Center": (-7.2783, 112.6320),
    "Private Fitness": (-7.2550, 112.6246),
}
OUTSIDE = {
    "GOR UNESA": (-7.2988, 112.6687),
    "55th Graha Sport Center": (-7.2925, 112.6771),
    "MAXICOURT Royal Surabaya": (-7.3181, 112.6776),
}


@pytest.mark.parametrize("name,latlon", list(INSIDE.items()))
def test_area_contains_citraland_venues(name, latlon):
    area = gpd.read_file(config.BOUNDARY_AREA).geometry.iloc[0]
    assert area.intersects(Point(latlon[1], latlon[0])), name


@pytest.mark.parametrize("name,latlon", list(OUTSIDE.items()))
def test_area_excludes_other_venues(name, latlon):
    area = gpd.read_file(config.BOUNDARY_AREA).geometry.iloc[0]
    assert not area.intersects(Point(latlon[1], latlon[0])), name


def test_area_is_single_polygon_without_holes():
    area = gpd.read_file(config.BOUNDARY_AREA).geometry.iloc[0]
    assert area.geom_type == "Polygon" and len(area.interiors) == 0
