from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple


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

REGION_CENTERS = {
    "la-habra": DEFAULT_CENTER,
}


@dataclass(frozen=True)
class OutputPaths:
    output_root: Path
    input_file: Path
    output_geojson: Path
    map_file: Path
    rings_output_dir: Path


def get_region(default: str = "default") -> str:
    return os.environ.get("REGION", default)


def build_output_paths(region: str, output_base: Path | str = "outputs") -> OutputPaths:
    output_root = Path(output_base) / region
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


def rings_to_labels(rings: Iterable[RingDefinition]) -> list[str]:
    return [ring.label for ring in rings]
