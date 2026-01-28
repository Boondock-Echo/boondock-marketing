#!/usr/bin/env python3
"""
Fill missing addresses in fire_stations_with_rings.geojson using Nominatim reverse geocoding
Only processes rows with "No address tags"
"""

import os
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from tqdm import tqdm

# === CONFIG ===
REGION = os.environ.get("REGION", "default")
OUTPUT_ROOT = Path("outputs") / REGION
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

INPUT_FILE = OUTPUT_ROOT / "fire_stations_with_rings.geojson"      # or your CSV/GeoJSON
OUTPUT_FILE = OUTPUT_ROOT / "fire_stations_with_filled_addresses.geojson"
USER_AGENT = "FireStationFinder-Mark-LaHabra (your.email@example.com)"  # ← Change to your real email!

# === MAIN ===
print("Loading data...")
df = gpd.read_file(INPUT_FILE)

# Find missing addresses
missing = df[df['address'].str.contains("No address tags", na=False)].copy()
print(f"Found {len(missing)} stations with missing addresses.")

if len(missing) == 0:
    print("All addresses already present — nothing to do.")
    exit()

# Set up Nominatim with rate limiter (1 request per 1.2 seconds → safe)
geolocator = Nominatim(user_agent=USER_AGENT)
geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1.2)

# Function to get address from lat/lon
def get_address(row):
    try:
        location = geocode((row['lat'], row['lon']))
        if location and location.raw.get('address'):
            addr = location.raw['address']
            parts = []
            if 'house_number' in addr:
                parts.append(addr['house_number'])
            if 'road' in addr:
                parts.append(addr['road'])
            if 'city' in addr or 'town' in addr:
                parts.append(addr.get('city') or addr.get('town'))
            if 'postcode' in addr:
                parts.append(addr['postcode'])
            
            full_addr = ", ".join(filter(None, parts))
            return full_addr if full_addr else "Address found but incomplete"
        return "No address found via reverse geocoding"
    except Exception as e:
        print(f"Error for {row['name']}: {e}")
        return "Error during lookup"

# Apply reverse geocoding with progress bar
print("Performing reverse geocoding (this may take a few minutes)...")
tqdm.pandas(desc="Reverse geocoding")
missing['new_address'] = missing.progress_apply(get_address, axis=1)

# Update original dataframe
df.loc[missing.index, 'address'] = missing['new_address']

# Optional: keep lat/lon columns if not already present
if 'lat' not in df.columns:
    df['lat'] = df.geometry.y
if 'lon' not in df.columns:
    df['lon'] = df.geometry.x

# Save updated file
df.to_file(OUTPUT_FILE, driver="GeoJSON")
print(f"\nUpdated file saved to: {OUTPUT_FILE}")

# Summary
updated_count = len(missing[missing['new_address'].str.contains("No address") == False])
print(f"\nSuccessfully filled {updated_count} out of {len(missing)} missing addresses.")
print("Sample of updated addresses:")
print(missing[['name', 'new_address', 'distance_mi', 'ring']].head(8))
