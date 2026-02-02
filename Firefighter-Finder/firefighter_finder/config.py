from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import json


@dataclass(frozen=True)
class RingDefinition:
    min_miles: float
    max_miles: float
    label: str
    color: str


DEFAULT_CENTER: Tuple[float, float] = (33.93, -117.95)
DEFAULT_RINGS = [
    RingDefinition(0, 25, "0-25 miles", "green"),
    RingDefinition(25, 50, "25-50 miles", "blue"),
    RingDefinition(50, 75, "50-75 miles", "orange"),
    RingDefinition(75, 100, "75-100 miles", "red"),
]

DEFAULT_REGION_NAME = "la-habra"


@dataclass(frozen=True)
class RegionConfig:
    name: str
    center_lat: float
    center_lon: float
    rings: tuple[RingDefinition, ...]
    pbf_url: str | None = None

    @property
    def center_latlon(self) -> tuple[float, float]:
        return (self.center_lat, self.center_lon)


def ring_definition_from_dict(data: dict) -> RingDefinition:
    return RingDefinition(
        min_miles=float(data["min_miles"]),
        max_miles=float(data["max_miles"]),
        label=str(data["label"]),
        color=str(data["color"]),
    )


def ring_definition_to_dict(ring: RingDefinition) -> dict:
    return {
        "min_miles": ring.min_miles,
        "max_miles": ring.max_miles,
        "label": ring.label,
        "color": ring.color,
    }


def region_config_from_dict(name: str, data: dict) -> RegionConfig:
    rings = tuple(ring_definition_from_dict(ring) for ring in data["rings"])
    return RegionConfig(
        name=name,
        center_lat=float(data["center_lat"]),
        center_lon=float(data["center_lon"]),
        rings=rings,
        pbf_url=data.get("pbf_url"),
    )


def region_config_to_dict(region: RegionConfig) -> dict:
    payload = {
        "center_lat": region.center_lat,
        "center_lon": region.center_lon,
        "rings": [ring_definition_to_dict(ring) for ring in region.rings],
    }
    if region.pbf_url:
        payload["pbf_url"] = region.pbf_url
    return payload


@dataclass(frozen=True)
class OutputPaths:
    output_root: Path
    input_file: Path
    output_geojson: Path
    map_file: Path
    rings_output_dir: Path


def get_region(default: str = DEFAULT_REGION_NAME) -> str:
    return os.environ.get("REGION", default)


def build_output_paths(
    region: str | RegionConfig, output_base: Path | str = "outputs"
) -> OutputPaths:
    region_name = region.name if isinstance(region, RegionConfig) else region
    output_root = Path(output_base) / region_name
    return OutputPaths(
        output_root=output_root,
        input_file=output_root / "fire_stations.geojson",
        output_geojson=output_root / "fire_stations_with_rings.geojson",
        map_file=output_root / "fire_stations_map.html",
        rings_output_dir=output_root / "rings_csv",
    )


def ensure_output_dirs(paths: OutputPaths) -> None:
    paths.output_root.mkdir(parents=True, exist_ok=True)
    paths.rings_output_dir.mkdir(parents=True, exist_ok=True)


def expected_outputs_exist(paths: OutputPaths) -> bool:
    return (
        paths.input_file.is_file()
        and paths.output_geojson.is_file()
        and paths.map_file.is_file()
        and paths.rings_output_dir.is_dir()
        and any(paths.rings_output_dir.glob("*.csv"))
    )


def outputs_complete(paths: OutputPaths) -> bool:
    return expected_outputs_exist(paths)


def rings_to_labels(rings: Iterable[RingDefinition]) -> list[str]:
    return [ring.label for ring in rings]


def _require_mapping(value: object, *, context: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object.")
    return value


def _require_sequence(value: object, *, context: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a JSON array.")
    return value


def _require_number(value: object, *, context: str) -> None:
    try:
        float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be a number.") from exc


def validate_regions_payload(payload: object) -> None:
    data = _require_mapping(payload, context="regions.json root")
    for region_name, region_data in data.items():
        if not isinstance(region_name, str):
            raise ValueError("Region names in regions.json must be strings.")
        region = _require_mapping(region_data, context=f"Region '{region_name}'")
        for key in ("center_lat", "center_lon", "rings"):
            if key not in region:
                raise ValueError(f"Region '{region_name}' missing required key '{key}'.")
        _require_number(region["center_lat"], context=f"Region '{region_name}' center_lat")
        _require_number(region["center_lon"], context=f"Region '{region_name}' center_lon")
        rings = _require_sequence(region["rings"], context=f"Region '{region_name}' rings")
        for index, ring_data in enumerate(rings):
            ring = _require_mapping(
                ring_data, context=f"Region '{region_name}' ring[{index}]"
            )
            for key in ("min_miles", "max_miles", "label", "color"):
                if key not in ring:
                    raise ValueError(
                        f"Region '{region_name}' ring[{index}] missing required key '{key}'."
                    )
            _require_number(
                ring["min_miles"],
                context=f"Region '{region_name}' ring[{index}] min_miles",
            )
            _require_number(
                ring["max_miles"],
                context=f"Region '{region_name}' ring[{index}] max_miles",
            )


def load_regions(path: Path | str = "regions.json") -> dict[str, RegionConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    validate_regions_payload(data)
    regions: dict[str, RegionConfig] = {}
    for name, config in data.items():
        regions[name] = region_config_from_dict(name, config)
    return regions


def save_regions(regions: dict[str, RegionConfig], path: Path | str = "regions.json") -> None:
    config_path = Path(path)
    payload = {
        name: region_config_to_dict(region) for name, region in sorted(regions.items())
    }
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
