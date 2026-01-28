#!/usr/bin/env python3
"""
Assign fire stations to distance rings + export CSVs per ring + create interactive map
Input:  outputs/<region>/fire_stations.geojson
Output: outputs/<region>/fire_stations_with_rings.geojson + per-ring CSVs + interactive map.html
"""

import os
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# === CONFIG ===
CENTER_LAT = 33.93
CENTER_LON = -117.95
CENTER = Point(CENTER_LON, CENTER_LAT)  # shapely Point (lon, lat)

RINGS = [
    (0, 25, "0-25 miles", "green"),
    (25, 50, "25-50 miles", "blue"),
    (50, 75, "50-75 miles", "orange"),
    (75, 100, "75-100 miles", "red")
]

REGION = os.environ.get("REGION", "default")
OUTPUT_ROOT = Path("outputs") / REGION
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

INPUT_FILE = OUTPUT_ROOT / "fire_stations.geojson"
OUTPUT_GEOJSON = OUTPUT_ROOT / "fire_stations_with_rings.geojson"
MAP_FILE = OUTPUT_ROOT / "fire_stations_map.html"
RINGS_OUTPUT_DIR = OUTPUT_ROOT / "rings_csv"

# Haversine function (straight-line distance in miles)
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

# === MAIN ===
print("Loading fire stations...")
stations = gpd.read_file(INPUT_FILE)

if 'geometry' not in stations.columns:
    print("Error: No 'geometry' column found. Check your GeoJSON.")
    exit(1)

print(f"Loaded {len(stations)} fire stations.")

# Ensure geometry is points and extract lat/lon if needed
stations = stations[stations.geometry.type == "Point"].copy()
stations['lon'] = stations.geometry.x
stations['lat'] = stations.geometry.y

# Calculate distance in miles using haversine (no projection needed)
print("Calculating distances...")
stations['distance_mi'] = stations.apply(
    lambda row: haversine(CENTER_LAT, CENTER_LON, row['lat'], row['lon']),
    axis=1
)

# Assign ring label and color
def assign_ring_and_color(dist):
    for min_d, max_d, label, color in RINGS:
        if min_d <= dist < max_d:
            return label, color
    return ">100 miles", "gray"

stations[['ring', 'color']] = stations['distance_mi'].apply(
    lambda d: pd.Series(assign_ring_and_color(d))
)

# Filter only stations within 100 miles (optional: comment out if you want all)
stations_in_scope = stations[stations['ring'] != ">100 miles"].copy()

# Save full GeoJSON with rings
stations.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
print(f"\nSaved ring-assigned GeoJSON to: {OUTPUT_GEOJSON}")

# === Export per-ring CSVs ===
print("\nExporting CSVs per ring...")
RINGS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for min_d, max_d, label, _ in RINGS:
    ring_df = stations_in_scope[stations_in_scope['ring'] == label]
    if not ring_df.empty:
        csv_path = RINGS_OUTPUT_DIR / f"fire_stations_{label.replace(' ', '_')}.csv"
        ring_df[['name', 'address', 'distance_mi', 'lat', 'lon', 'osm_id', 'ring']].to_csv(
            csv_path, index=False
        )
        print(f"  → {len(ring_df)} stations → {csv_path}")
    else:
        print(f"  → No stations in {label}")

# === Create Interactive Map ===
print("\nCreating interactive map...")
m = folium.Map(location=[CENTER_LAT, CENTER_LON], zoom_start=9, tiles="CartoDB positron")

# Add center marker
folium.Marker(
    [CENTER_LAT, CENTER_LON],
    popup="Center: La Habra",
    icon=folium.Icon(color="black", icon="home")
).add_to(m)

# Add stations colored by ring
for _, row in stations_in_scope.iterrows():
    if pd.notna(row['lat']) and pd.notna(row['lon']):
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6,
            color=row['color'],
            fill=True,
            fill_color=row['color'],
            fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>{row.get('name', 'Unnamed')}</b><br>"
                f"{row.get('address', 'No address')}<br>"
                f"Distance: {row['distance_mi']:.1f} miles<br>"
                f"Ring: {row['ring']}",
                max_width=300
            )
        ).add_to(m)

# Add legend (simple HTML)
legend_html = '''
<div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 140px; 
            border:2px solid grey; z-index:9999; font-size:14px; background-color:white;
            padding: 10px;">
&nbsp; <b>Ring Legend</b> <br>
&nbsp; 0-25 mi &nbsp; <i style="background:green"></i><br>
&nbsp; 25-50 mi &nbsp; <i style="background:blue"></i><br>
&nbsp; 50-75 mi &nbsp; <i style="background:orange"></i><br>
&nbsp; 75-100 mi &nbsp; <i style="background:red"></i>
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html))

# Save and open map
m.save(MAP_FILE)
print(f"Interactive map saved to: {MAP_FILE}")
print("→ Open the file in your web browser to explore!")

# Final summary
print("\nSummary of stations in each ring (0-100 miles):")
summary = stations_in_scope['ring'].value_counts().sort_index()
print(summary)
print(f"\nTotal stations within 100 miles: {summary.sum()}")
