from pyrosm import OSM
import geopandas as gpd
from shapely.geometry import Point
import pyproj
import time
from datetime import datetime
from tqdm import tqdm  # optional for progress

# === CONFIG ===
pbf_path = "socal-260118.osm.pbf"  # Update to your actual file path
center_latlon = (33.93, -117.95)        # La Habra
rings_miles = [0, 25, 50, 75, 100]
meters_per_mile = 1609.34

# UTM Zone 11N for Southern California (accurate distance calculations)
utm_crs = "EPSG:32611"
wgs84 = "EPSG:4326"

# Project center point to UTM for buffering
proj_to_utm = pyproj.Transformer.from_crs(wgs84, utm_crs, always_xy=True)
center_utm = proj_to_utm.transform(center_latlon[1], center_latlon[0])  # Note: lon, lat order!

# Load the OSM file ONCE (outside the loop — this is key for speed!)
print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading California PBF (this may take 30-90s first time)...")
osm = OSM(pbf_path)  # Optionally add bounding_box if you want to pre-clip to a huge SoCal area

# Get ALL fire stations once (fastest approach — then filter in memory)
print("Extracting all fire stations from PBF...")
custom_filter = {'amenity': ['fire_station']}
fire_stations = osm.get_pois(custom_filter=custom_filter)

if fire_stations is None or len(fire_stations) == 0:
    print("No fire stations found! Check your filter or PBF file.")
    exit()

print(f"Found {len(fire_stations)} fire stations statewide.")

# Optional: add extra columns if you want more tags
# fire_stations = osm.get_pois(custom_filter=custom_filter, extra_attributes=['name', 'addr:housenumber', 'addr:street'])

# Make sure geometry is set
fire_stations = fire_stations.set_geometry('geometry')

results = []

for i in tqdm(range(1, len(rings_miles)), desc="Processing rings"):
    inner_miles = rings_miles[i-1]
    outer_miles = rings_miles[i]
    ring_label = f"{inner_miles}-{outer_miles} miles"
    
    start_time = time.time()
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processing {ring_label}")
    
    try:
        # Create outer buffer in UTM (meters)
        outer_buffer_utm = Point(center_utm).buffer(outer_miles * meters_per_mile)
        
        # Transform back to lat/lon
        proj_to_wgs = pyproj.Transformer.from_crs(utm_crs, wgs84, always_xy=True)
        outer_buffer_wgs = gpd.GeoSeries([outer_buffer_utm], crs=utm_crs).to_crs(wgs84).iloc[0]
        
        # Filter stations inside outer
        in_outer = fire_stations[fire_stations.intersects(outer_buffer_wgs)]
        
        if inner_miles > 0:
            inner_buffer_utm = Point(center_utm).buffer(inner_miles * meters_per_mile)
            inner_buffer_wgs = gpd.GeoSeries([inner_buffer_utm], crs=utm_crs).to_crs(wgs84).iloc[0]
            in_inner = fire_stations[fire_stations.intersects(inner_buffer_wgs)]
            ring_stations = gpd.overlay(in_outer, in_inner, how='difference')
        else:
            ring_stations = in_outer
        
        ring_stations['ring_label'] = ring_label
        results.append(ring_stations)
        
        elapsed = time.time() - start_time
        print(f"  → Found {len(ring_stations)} stations in {ring_label} ({elapsed:.1f}s)")
        
        # Save each ring
        ring_stations.to_file(f"fire_stations_{ring_label.replace(' ', '_')}.geojson", driver="GeoJSON")
    
    except Exception as e:
        print(f"ERROR on {ring_label}: {str(e)}")

# Combine & save all
if results:
    all_rings = gpd.pd.concat(results, ignore_index=True)
    all_rings.to_file("fire_stations_all_rings.geojson", driver="GeoJSON")
    print(f"\nDone! Total stations across all rings: {len(all_rings)}")
    
    # Quick summary with address
    summary = all_rings[['name', 'addr:housenumber', 'addr:street', 'ring_label']].copy()
    summary['address'] = (summary['addr:housenumber'].fillna('') + ' ' + 
                          summary['addr:street'].fillna('')).str.strip()
    print("\nSample (first 5 per ring):")
    print(summary.groupby('ring_label').head(5))
