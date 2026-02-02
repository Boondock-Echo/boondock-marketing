import pandas as pd
import geopandas as gpd

from fire_station_tools.config import RingDefinition
from fire_station_tools.export import export_ring_csvs


def test_export_ring_csvs_missing_ring_column(tmp_path, capsys):
    stations = gpd.GeoDataFrame({"name": ["Station 1"], "address": ["123 Main St"]})
    rings = (RingDefinition(0, 10, "0-10 miles", "green"),)

    export_ring_csvs(stations, rings, tmp_path)

    output = capsys.readouterr().out
    assert "Missing required column 'ring'" in output
    assert list(tmp_path.glob("*.csv")) == []


def test_export_ring_csvs_fills_missing_columns(tmp_path, capsys):
    stations = gpd.GeoDataFrame({"name": ["Station 1"], "ring": ["0-10 miles"]})
    rings = (RingDefinition(0, 10, "0-10 miles", "green"),)

    export_ring_csvs(stations, rings, tmp_path)

    output = capsys.readouterr().out
    assert "missing columns for CSV export" in output

    csv_path = tmp_path / "fire_stations_0-10_miles.csv"
    assert csv_path.exists()

    data = pd.read_csv(csv_path)
    assert list(data.columns) == [
        "name",
        "address",
        "distance_mi",
        "lat",
        "lon",
        "osm_id",
        "ring",
    ]
    assert data.loc[0, "name"] == "Station 1"
    assert pd.isna(data.loc[0, "address"])
    assert data.loc[0, "ring"] == "0-10 miles"
