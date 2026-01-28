#!/usr/bin/env python3
"""
Assign fire stations to distance rings + export CSVs per ring + create interactive map
Input:  outputs/<region>/fire_stations.geojson
Output: outputs/<region>/fire_stations_with_rings.geojson + per-ring CSVs + interactive map.html
"""

import geopandas as gpd

from firefighter_finder.config import DEFAULT_CENTER, DEFAULT_RINGS, build_output_paths, get_region
from firefighter_finder.export import create_interactive_map, export_geojson, export_ring_csvs
from firefighter_finder.rings import add_distance_and_rings


def main() -> None:
    center_lat, center_lon = DEFAULT_CENTER
    region = get_region()
    paths = build_output_paths(region)
    paths.output_root.mkdir(parents=True, exist_ok=True)

    print("Loading fire stations...")
    stations = gpd.read_file(paths.input_file)

    if "geometry" not in stations.columns:
        raise SystemExit("Error: No 'geometry' column found. Check your GeoJSON.")

    print(f"Loaded {len(stations)} fire stations.")
    print("Calculating distances...")

    stations = add_distance_and_rings(stations, center_lat, center_lon, DEFAULT_RINGS)
    stations_in_scope = stations[stations["ring"] != ">100 miles"].copy()

    export_geojson(stations, paths.output_geojson)
    print(f"\nSaved ring-assigned GeoJSON to: {paths.output_geojson}")

    print("\nExporting CSVs per ring...")
    export_ring_csvs(stations_in_scope, DEFAULT_RINGS, paths.rings_output_dir)

    print("\nCreating interactive map...")
    create_interactive_map(
        stations_in_scope,
        center_lat,
        center_lon,
        DEFAULT_RINGS,
        paths.map_file,
        center_label="La Habra",
    )

    print(f"Interactive map saved to: {paths.map_file}")
    print("→ Open the file in your web browser to explore!")

    print("\nSummary of stations in each ring (0-100 miles):")
    summary = stations_in_scope["ring"].value_counts().sort_index()
    print(summary)
    print(f"\nTotal stations within 100 miles: {summary.sum()}")


if __name__ == "__main__":
    main()
