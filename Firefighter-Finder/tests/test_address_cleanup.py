from pathlib import Path

import pandas as pd
import pytest

from address_cleanup import (
    address_is_complete,
    ensure_lat_lon,
    process_dataframe,
)


class DummyLocation:
    def __init__(self, address):
        self.raw = {"address": address}


def fixture_path(filename: str) -> Path:
    return Path(__file__).parent / "fixtures" / filename


def test_address_is_complete_variants():
    assert address_is_complete("123 Main St, Springfield, CA 90210")
    assert address_is_complete("123 Main St, Springfield, CA, 90210")
    assert not address_is_complete("Main St, Springfield, CA 90210")
    assert not address_is_complete("123 Main St, Springfield, CA")
    assert not address_is_complete("")
    assert not address_is_complete(None)


def test_process_dataframe_repairs_incomplete_addresses():
    df = pd.read_csv(fixture_path("sample_addresses.csv"))

    def geocode(coords, exactly_one=True, addressdetails=True):
        lat, lon = coords
        if (lat, lon) == (34.1, -118.1):
            return DummyLocation(
                {
                    "house_number": "456",
                    "road": "Oak Ave",
                    "city": "Springfield",
                    "state": "CA",
                    "postcode": "90211",
                }
            )
        return DummyLocation(
            {
                "house_number": "789",
                "road": "Pine Rd",
                "city": "Springfield",
                "state": "CA",
                "postcode": "90212",
            }
        )

    cache = {}
    updated, invalid_count, corrected_count = process_dataframe(
        df,
        geocode,
        cache,
        address_column="address",
        lat_column="lat",
        lon_column="lon",
    )

    assert invalid_count == 2
    assert corrected_count == 2
    assert address_is_complete(updated.loc[1, "address"])
    assert address_is_complete(updated.loc[2, "address"])


def test_ensure_lat_lon_from_geojson_fixture():
    gpd = pytest.importorskip("geopandas")
    df = gpd.read_file(fixture_path("sample_stations.geojson"))
    df = df.drop(columns=["lat", "lon"], errors="ignore")

    updated = ensure_lat_lon(df, "lat", "lon")

    assert "lat" in updated.columns
    assert "lon" in updated.columns
    assert updated.loc[0, "lat"] == 34.0
    assert updated.loc[0, "lon"] == -118.0
