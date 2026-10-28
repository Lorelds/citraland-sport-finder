import json
import sys
from datetime import datetime
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


def test_open_now():
    hours = json.dumps([{"open": {"day": d, "hour": 7, "minute": 0}, "close": {"day": d, "hour": 22, "minute": 0}} for d in range(7)])
    assert gis.is_open(hours, datetime(2026, 10, 28, 10, 0)) is True
    assert gis.is_open(hours, datetime(2026, 10, 28, 23, 0)) is False
    assert gis.is_open(None, datetime(2026, 10, 28, 10, 0)) is None
    assert gis.is_open(json.dumps([{"open": {"day": 0, "hour": 0, "minute": 0}}]), datetime(2026, 10, 28, 3, 0)) is True


def test_open_now_on_sample_file(venues):
    # The GeoJSON reader returns opening_hours as parsed lists; this must not crash.
    result = gis.filter_open_now(venues, enabled=True, now=datetime(2026, 10, 28, 23, 30))
    assert "Status_Buka" in result.columns
    assert "Contoh Lapangan Basket" in set(result["Nama"])  # unknown hours are kept


def test_names_other_sport():
    import data_fetch

    assert data_fetch.names_other_sport("Tennis Court TPR Citraland", "futsal") is True
    assert data_fetch.names_other_sport("Kolam Renang dan Arena Tenis G-Walk", "tenis") is False
    assert data_fetch.names_other_sport("Citraland Square Park", "futsal") is False
