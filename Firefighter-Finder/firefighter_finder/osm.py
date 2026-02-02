from __future__ import annotations

import json
import os
import time
import urllib.request
from urllib.error import HTTPError, URLError
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import osmium


@dataclass
class OverpassRingResult:
    ring_label: str
    geodataframe: "gpd.GeoDataFrame"


class FireStationHandler(osmium.SimpleHandler):
    def __init__(self, output_file: Path, progress_every: int = 50):
        super().__init__()
        self.output_file = output_file
        self.progress_every = progress_every
        self.count = 0
        self.start_time = time.time()
        self._first_feature = True
        self._stream = self.output_file.open("w", encoding="utf-8")
        self._stream.write('{"type": "FeatureCollection", "features": [\n')

    def node(self, n):
        if n.tags.get("amenity") != "fire_station":
            return

        lat = n.location.lat
        lon = n.location.lon
        tags = dict(n.tags)
        name = tags.get("name", "Unnamed Fire Station")

        housenumber = tags.get("addr:housenumber", "")
        street = tags.get("addr:street", "")
        city = tags.get("addr:city", "")
        postcode = tags.get("addr:postcode", "")

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
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": name,
                "address": full_address,
                "osm_id": n.id,
                "tags": tags,
            },
        }

        if not self._first_feature:
            self._stream.write(",\n")
        json.dump(feature, self._stream, ensure_ascii=False)
        self._first_feature = False
        self.count += 1

        if self.progress_every and self.count % self.progress_every == 0:
            elapsed = time.time() - self.start_time
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Found {self.count} fire stations so far "
                f"({elapsed:.1f}s elapsed)"
            )

    def finalize(self) -> int:
        elapsed = time.time() - self.start_time
        print("\nExtraction complete!")
        print(f"Total fire stations found: {self.count}")
        print(f"Time taken: {elapsed:.1f} seconds")

        self._stream.write("\n]}\n")
        self._stream.close()

        print(f"Saved to: {self.output_file}")
        return self.count


def _is_retryable_http_error(error: HTTPError) -> bool:
    return error.code in {408, 429} or 500 <= error.code <= 599


def _iter_download_chunks(response, chunk_size: int = 1024 * 1024):
    while True:
        chunk = response.read(chunk_size)
        if not chunk:
            break
        yield chunk


def download_pbf(
    url: str,
    destination: Path,
    overwrite: bool = False,
    timeout: int = 60,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        return destination

    attempts = 0
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    while True:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response, temp_path.open("wb") as f:
                for chunk in _iter_download_chunks(response):
                    f.write(chunk)
            os.replace(temp_path, destination)
            break
        except HTTPError as exc:
            attempts += 1
            if attempts > max_retries or not _is_retryable_http_error(exc):
                if temp_path.exists():
                    temp_path.unlink()
                raise
        except (URLError, TimeoutError) as exc:
            attempts += 1
            if attempts > max_retries:
                if temp_path.exists():
                    temp_path.unlink()
                raise
        sleep_for = backoff_seconds * (2 ** (attempts - 1))
        time.sleep(sleep_for)

    return destination


def extract_fire_stations_lowmem(pbf_path: Path, output_file: Path, progress_every: int = 50) -> int:
    handler = FireStationHandler(output_file, progress_every=progress_every)
    handler.apply_file(str(pbf_path), locations=True)
    return handler.finalize()


def load_fire_stations_pyrosm(
    pbf_path: Path,
    custom_filter: Optional[dict] = None,
    extra_attributes: Optional[Iterable[str]] = None,
):
    from pyrosm import OSM

    osm = OSM(str(pbf_path))
    filter_value = custom_filter or {"amenity": ["fire_station"]}
    return osm.get_pois(custom_filter=filter_value, extra_attributes=extra_attributes)


def query_overpass_rings(
    center_point: tuple[float, float],
    tags: dict,
    rings_miles: list[float],
    output_root: Path,
    overpass_settings: Optional[str] = None,
    overpass_url: Optional[str] = None,
    overpass_timeout: Optional[int] = 180,
    overpass_max_retries: int = 3,
    overpass_backoff_seconds: float = 2.0,
) -> "gpd.GeoDataFrame":
    import geopandas as gpd
    import osmnx as ox
    import requests

    if overpass_settings:
        ox.settings.overpass_settings = overpass_settings
    if overpass_url:
        ox.settings.overpass_url = overpass_url
    if overpass_timeout is not None:
        ox.settings.timeout = overpass_timeout
    ox.settings.use_cache = True

    meters_per_mile = 1609.34
    rings_meters = [d * meters_per_mile for d in rings_miles]
    results = []

    def _features_from_point_with_retries(dist: float):
        attempts = 0
        while True:
            try:
                return ox.features_from_point(center_point, tags, dist=dist)
            except requests.exceptions.RequestException:
                attempts += 1
                if attempts > overpass_max_retries:
                    raise
                sleep_for = overpass_backoff_seconds * (2 ** (attempts - 1))
                time.sleep(sleep_for)

    for i in range(1, len(rings_meters)):
        inner_dist = rings_meters[i - 1]
        outer_dist = rings_meters[i]
        ring_label = f"{rings_miles[i - 1]}-{rings_miles[i]} miles"

        outer_gdf = _features_from_point_with_retries(outer_dist)
        if inner_dist > 0:
            inner_gdf = _features_from_point_with_retries(inner_dist)
            ring_gdf = gpd.overlay(outer_gdf, inner_gdf, how="difference")
        else:
            ring_gdf = outer_gdf

        ring_gdf["ring_label"] = ring_label
        results.append(ring_gdf)

        ring_output = output_root / f"fire_stations_{ring_label.replace(' ', '_')}.geojson"
        ring_gdf.to_file(ring_output, driver="GeoJSON")

    if not results:
        return gpd.GeoDataFrame()

    return gpd.pd.concat(results, ignore_index=True)
