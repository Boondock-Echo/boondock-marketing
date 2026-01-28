from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import Iterable

import geopandas as gpd
import pandas as pd
import pyproj
from shapely.geometry import Point

from .config import RingDefinition


def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return earth_radius * c


def assign_ring(distance_miles: float, rings: Iterable[RingDefinition]) -> tuple[str, str]:
    for ring in rings:
        if ring.min_miles <= distance_miles < ring.max_miles:
            return ring.label, ring.color
    return ">100 miles", "gray"


def add_distance_and_rings(
    stations: gpd.GeoDataFrame,
    center_lat: float,
    center_lon: float,
    rings: Iterable[RingDefinition],
) -> gpd.GeoDataFrame:
    if "geometry" not in stations.columns:
        raise ValueError("GeoDataFrame is missing geometry column.")

    stations = stations[stations.geometry.type == "Point"].copy()
    stations["lon"] = stations.geometry.x
    stations["lat"] = stations.geometry.y
    stations["distance_mi"] = stations.apply(
        lambda row: haversine_distance_miles(center_lat, center_lon, row["lat"], row["lon"]),
        axis=1,
    )
    stations[["ring", "color"]] = stations["distance_mi"].apply(
        lambda dist: pd.Series(assign_ring(dist, rings))
    )
    return stations


def build_ring_buffers(
    center_latlon: tuple[float, float],
    rings_miles: list[float],
    utm_crs: str = "EPSG:32611",
    wgs84: str = "EPSG:4326",
) -> list[tuple[float, float, object]]:
    proj_to_utm = pyproj.Transformer.from_crs(wgs84, utm_crs, always_xy=True)
    center_utm = proj_to_utm.transform(center_latlon[1], center_latlon[0])
    buffers = []

    for i in range(1, len(rings_miles)):
        inner_miles = rings_miles[i - 1]
        outer_miles = rings_miles[i]
        outer_buffer_utm = Point(center_utm).buffer(outer_miles * 1609.34)
        proj_to_wgs = pyproj.Transformer.from_crs(utm_crs, wgs84, always_xy=True)
        outer_buffer_wgs = gpd.GeoSeries([outer_buffer_utm], crs=utm_crs).to_crs(wgs84).iloc[0]
        buffers.append((inner_miles, outer_miles, outer_buffer_wgs))
    return buffers


def assign_rings_by_buffers(
    stations: gpd.GeoDataFrame,
    center_latlon: tuple[float, float],
    rings_miles: list[float],
    utm_crs: str = "EPSG:32611",
    wgs84: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    buffers = build_ring_buffers(center_latlon, rings_miles, utm_crs=utm_crs, wgs84=wgs84)
    results = []

    for inner_miles, outer_miles, outer_buffer_wgs in buffers:
        if inner_miles > 0:
            inner_buffer_utm = Point(
                pyproj.Transformer.from_crs(wgs84, utm_crs, always_xy=True).transform(
                    center_latlon[1], center_latlon[0]
                )
            ).buffer(inner_miles * 1609.34)
            inner_buffer_wgs = (
                gpd.GeoSeries([inner_buffer_utm], crs=utm_crs).to_crs(wgs84).iloc[0]
            )
            ring_stations = gpd.overlay(
                stations[stations.intersects(outer_buffer_wgs)],
                stations[stations.intersects(inner_buffer_wgs)],
                how="difference",
            )
        else:
            ring_stations = stations[stations.intersects(outer_buffer_wgs)]

        ring_stations = ring_stations.copy()
        ring_stations["ring_label"] = f"{inner_miles}-{outer_miles} miles"
        results.append(ring_stations)

    if not results:
        return stations.iloc[0:0]

    return gpd.pd.concat(results, ignore_index=True)
