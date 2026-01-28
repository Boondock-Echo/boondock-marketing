#!/usr/bin/env python3
"""
Low-memory extraction of fire stations (amenity=fire_station) from OSM .osm.pbf file
Uses pyosmium for streaming parsing → very low RAM usage (~1-4 GB peak for large files)

Usage:
    python find_fire_stations_lowmem.py socal-260118.osm.pbf

Output: fire_stations.geojson (GeoJSON FeatureCollection)
"""

import osmium
import json
import sys
import time
import os
from datetime import datetime
from tqdm import tqdm  # optional progress bar

class FireStationHandler(osmium.SimpleHandler):
    def __init__(self, output_file="fire_stations.geojson"):
        super().__init__()
        self.output_file = output_file
        self.features = []
        self.count = 0
        self.start_time = time.time()

    def node(self, n):
        if 'amenity' in n.tags and n.tags['amenity'] == 'fire_station':
            lat = n.location.lat
            lon = n.location.lon

            tags = dict(n.tags)
            name = tags.get('name', 'Unnamed Fire Station')

            # Build address if available
            housenumber = tags.get('addr:housenumber', '')
            street = tags.get('addr:street', '')
            city = tags.get('addr:city', '')
            postcode = tags.get('addr:postcode', '')

            address_parts = []
            if housenumber and street:
                address_parts.append(f"{housenumber} {street}")
            elif street:
                address_parts.append(street)
            if city:
                address_parts.append(city)
            if postcode:
                address_parts.append(postcode)

            full_address = ", ".join(address_parts) if address_parts else "No address tags"

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                },
                "properties": {
                    "name": name,
                    "address": full_address,
                    "osm_id": n.id,
                    "tags": tags  # all original tags for reference
                }
            }

            self.features.append(feature)
            self.count += 1

            # Progress feedback every 50 stations
            if self.count % 50 == 0:
                elapsed = time.time() - self.start_time
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {self.count} fire stations so far "
                      f"({elapsed:.1f}s elapsed)")

    # Optional: You can add way() and relation() if you want polygons/centroids
    # Most fire stations are nodes, so this is usually sufficient

    def finalize(self):
        elapsed = time.time() - self.start_time
        print(f"\nExtraction complete!")
        print(f"Total fire stations found: {self.count}")
        print(f"Time taken: {elapsed:.1f} seconds")

        # Write to GeoJSON
        geojson = {
            "type": "FeatureCollection",
            "features": self.features
        }

        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2, ensure_ascii=False)

        print(f"Saved to: {self.output_file}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_fire_stations_lowmem.py <path_to_california-latest.osm.pbf>")
        sys.exit(1)

    pbf_path = sys.argv[1]

    if not os.path.exists(pbf_path):
        print(f"File not found: {pbf_path}")
        sys.exit(1)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting extraction from: {pbf_path}")
    print("This is a streaming process — memory usage should stay low.")
    print("Progress will update every 50 stations found.\n")

    handler = FireStationHandler()
    try:
        # locations=True enables lat/lon access on nodes
        handler.apply_file(pbf_path, locations=True)
        handler.finalize()
    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)
