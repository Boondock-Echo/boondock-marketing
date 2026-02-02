#!/usr/bin/env python3
"""
Assign fire stations to distance rings + export CSVs per ring + create interactive map
Input:  outputs/<region>/fire_stations.geojson
Output: outputs/<region>/fire_stations_with_rings.geojson + per-ring CSVs + interactive map.html
"""

import geopandas as gpd

from fire_station_tools.config import build_output_paths, get_region, load_regions
from fire_station_tools.export import create_interactive_map, export_geojson, export_ring_csvs
from fire_station_tools.rings import add_distance_and_rings


def main() -> None:
    region = get_region()
    regions = load_regions()
    if region not in regions:
        raise SystemExit(
            f"Error: Region '{region}' not found in regions.json. "
            "Run main.py to add it."
        )
    region_config = regions[region]
    paths = build_output_paths(region_config)
    paths.output_root.mkdir(parents=True, exist_ok=True)

    print("Loading fire stations...")
    stations = gpd.read_file(paths.input_file)

    if "geometry" not in stations.columns:
        raise SystemExit("Error: No 'geometry' column found. Check your GeoJSON.")

    print(f"Loaded {len(stations)} fire stations.")
    print("Calculating distances...")

    stations = add_distance_and_rings(
        stations, region_config.center_lat, region_config.center_lon, region_config.rings
    )
    stations_in_scope = stations[stations["ring"] != ">100 miles"].copy()

    export_geojson(stations, paths.output_geojson)
    print(f"\nSaved ring-assigned GeoJSON to: {paths.output_geojson}")

    print("\nExporting CSVs per ring...")
    export_ring_csvs(stations_in_scope, region_config.rings, paths.rings_output_dir)

    print("\nCreating interactive map...")
    create_interactive_map(
        stations_in_scope,
        region_config.center_lat,
        region_config.center_lon,
        region_config.rings,
        paths.map_file,
        center_label=region_config.name,
    )

    print(f"Interactive map saved to: {paths.map_file}")
    print("→ Open the file in your web browser to explore!")

    print("\nSummary of stations in each ring (0-100 miles):")
    summary = stations_in_scope["ring"].value_counts().sort_index()
    print(summary)
    print(f"\nTotal stations within 100 miles: {summary.sum()}")


if __name__ == "__main__":
    main()
