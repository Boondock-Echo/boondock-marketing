import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
from tqdm import tqdm
import time
from datetime import datetime

# === CONFIG ===
center_point = (33.93, -117.95)          # La Habra lat, lon
tags = {'amenity': 'fire_station'}       # change to 'police' etc.
rings_miles = [0, 25, 50, 75, 100]       # your annuli
meters_per_mile = 1609.34

# Tune for large queries
ox.settings.overpass_settings = '[out:json][timeout:1800][maxsize:1073741824]'
ox.settings.overpass_url = "https://overpass.kumi.systems/api/interpreter"  # faster mirror
ox.settings.use_cache = True             # reuse previous downloads if possible

# === MAIN LOOP ===
results = []
rings_meters = [d * meters_per_mile for d in rings_miles]

for i in tqdm(range(1, len(rings_meters)), desc="Processing rings"):
    inner_dist = rings_meters[i-1]
    outer_dist = rings_meters[i]
    ring_label = f"{rings_miles[i-1]}-{rings_miles[i]} miles"
    
    start_time = time.time()
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting {ring_label} (outer dist: {outer_dist/1000:.0f} km)")
    
    try:
        # Outer circle
        print("  → Querying outer area...")
        outer_gdf = ox.features_from_point(center_point, tags, dist=outer_dist)
        outer_count = len(outer_gdf)
        print(f"  → Found {outer_count} features in outer circle")
        
        if inner_dist > 0:
            print("  → Querying inner area for subtraction...")
            inner_gdf = ox.features_from_point(center_point, tags, dist=inner_dist)
            inner_count = len(inner_gdf)
            print(f"  → Found {inner_count} features in inner circle")
            
            print("  → Computing ring (difference)...")
            ring_gdf = gpd.overlay(outer_gdf, inner_gdf, how='difference')
        else:
            ring_gdf = outer_gdf
        
        ring_gdf['ring_label'] = ring_label
        results.append(ring_gdf)
        
        elapsed = time.time() - start_time
        print(f"  → Finished {ring_label} in {elapsed:.1f} seconds ({len(ring_gdf)} features after diff)")
        
        # Optional: save each ring immediately (good for resuming)
        ring_gdf.to_file(f"fire_stations_{ring_label.replace(' ', '_')}.geojson", driver="GeoJSON")
        print(f"  → Saved to fire_stations_{ring_label.replace(' ', '_')}.geojson")
    
    except Exception as e:
        print(f"  → ERROR on {ring_label}: {str(e)}")
        print("     → Tip: Try increasing timeout, using a different overpass_url, or smaller dist")

# === FINAL COMBINE & SAVE ===
if results:
    all_rings = gpd.pd.concat(results, ignore_index=True)
    all_rings.to_file("fire_stations_all_rings.geojson", driver="GeoJSON")
    print(f"\nAll done! Total features: {len(all_rings)}")
    print("Saved combined file: fire_stations_all_rings.geojson")
    
    # Nice summary table (with basic address if available)
    summary = all_rings[['name', 'addr:housenumber', 'addr:street', 'ring_label']].copy()
    summary['address'] = (summary['addr:housenumber'].fillna('') + ' ' + 
                          summary['addr:street'].fillna('')).str.strip()
    print("\nSummary (first few per ring):")
    print(summary.groupby('ring_label').head(3))
else:
    print("No successful rings.")
