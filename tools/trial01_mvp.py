import osmnx as ox

place = "La Habra, California, USA"
tags = {'amenity': 'fire_station'}  # or 'police'

try:
    gdf = ox.features_from_place(place, tags)
    print(gdf[['name', 'geometry']])  # GeoDataFrame with names + lat/lon points
    # gdf.plot()  # visualize if you have matplotlib
except Exception as e:
    print("osmnx error:", e)
