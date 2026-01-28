#!/usr/bin/env python3
"""
Low-memory extraction of fire stations (amenity=fire_station) from OSM .osm.pbf file
Uses pyosmium for streaming parsing → very low RAM usage (~1-4 GB peak for large files)

Usage:
    python find_fire_stations_lowmem.py socal-260118.osm.pbf

Output: outputs/<region>/fire_stations.geojson (GeoJSON FeatureCollection)
"""

import os
import sys
from datetime import datetime
from pathlib import Path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python find_fire_stations_lowmem.py <path_to_california-latest.osm.pbf>")
        sys.exit(1)

    pbf_path = sys.argv[1]
    region = os.environ.get("REGION", "default")
    output_dir = Path("outputs") / region
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "fire_stations.geojson"

    if not os.path.exists(pbf_path):
        print(f"File not found: {pbf_path}")
        sys.exit(1)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting extraction from: {pbf_path}")
    print("This is a streaming process — memory usage should stay low.")
    print("Progress will update every 50 stations found.\n")

    try:
        from firefighter_finder.osm import extract_fire_stations_lowmem

        extract_fire_stations_lowmem(Path(pbf_path), output_file)
    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)
