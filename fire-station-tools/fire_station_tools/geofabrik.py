from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
DEFAULT_GEOFABRIK_CACHE = (
    Path(__file__).resolve().parents[1] / "data" / "geofabrik_index.json"
)


def _iter_coords(coordinates: Iterable) -> Iterable[tuple[float, float]]:
    for item in coordinates:
        if isinstance(item, (list, tuple)) and len(item) == 2 and all(
            isinstance(value, (int, float)) for value in item
        ):
            yield float(item[0]), float(item[1])
        else:
            yield from _iter_coords(item)


def _bbox_from_geometry(geometry: dict) -> Optional[tuple[float, float, float, float]]:
    coords = geometry.get("coordinates")
    if coords is None:
        return None
    flattened = list(_iter_coords(coords))
    if not flattened:
        return None
    lons, lats = zip(*flattened)
    return min(lons), min(lats), max(lons), max(lats)


def _extract_bbox(feature: dict) -> Optional[tuple[float, float, float, float]]:
    bbox = feature.get("bbox")
    if bbox and len(bbox) == 4:
        return tuple(float(value) for value in bbox)
    props = feature.get("properties", {})
    bbox = props.get("bbox")
    if bbox and len(bbox) == 4:
        return tuple(float(value) for value in bbox)
    geometry = feature.get("geometry")
    if isinstance(geometry, dict):
        return _bbox_from_geometry(geometry)
    return None


def load_geofabrik_index(
    cache_path: Optional[Path] = None,
    index_url: str = GEOFABRIK_INDEX_URL,
) -> dict:
    if cache_path and cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    with urllib.request.urlopen(index_url) as response:
        data = json.load(response)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle)
    return data


def find_geofabrik_pbf(
    lat: float,
    lon: float,
    cache_path: Optional[Path] = None,
    index_url: str = GEOFABRIK_INDEX_URL,
) -> Optional[str]:
    if cache_path is None:
        cache_path = DEFAULT_GEOFABRIK_CACHE
    try:
        data = load_geofabrik_index(cache_path=cache_path, index_url=index_url)
    except Exception:
        return None

    best_url = None
    best_area = None
    for feature in data.get("features", []):
        bbox = _extract_bbox(feature)
        if not bbox:
            continue
        min_lon, min_lat, max_lon, max_lat = bbox
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            continue
        urls = feature.get("properties", {}).get("urls", {})
        pbf_url = urls.get("pbf")
        if not pbf_url:
            continue
        area = abs((max_lat - min_lat) * (max_lon - min_lon))
        if best_area is None or area < best_area:
            best_area = area
            best_url = pbf_url
    return best_url
