#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
import re
from pathlib import Path

import geopandas as gpd

from firefighter_finder.config import DEFAULT_RINGS, RegionConfig, RingDefinition, build_output_paths
from firefighter_finder.config import load_regions, save_regions
from firefighter_finder.export import create_interactive_map, export_geojson, export_ring_csvs
from firefighter_finder.osm import download_pbf, extract_fire_stations_lowmem
from firefighter_finder.rings import add_distance_and_rings

BASE_DIR = Path(__file__).resolve().parent
REGIONS_PATH = BASE_DIR / "regions.json"
PBF_CACHE_DIR = BASE_DIR / "data" / "pbf"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "region"


def pbf_cache_path(region_name: str) -> Path:
    return PBF_CACHE_DIR / f"{slugify(region_name)}.osm.pbf"


def prompt_input(prompt: str) -> str:
    return input(prompt).strip()


def prompt_float(prompt: str, min_value: float, max_value: float) -> float:
    while True:
        value = prompt_input(prompt)
        try:
            number = float(value)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if not (min_value <= number <= max_value):
            print(f"Value must be between {min_value} and {max_value}.")
            continue
        return number


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        response = prompt_input(f"{prompt}{suffix}").lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please enter yes or no.")


def validate_rings(rings: list[RingDefinition]) -> None:
    if not rings:
        raise ValueError("At least one ring is required.")
    sorted_rings = sorted(rings, key=lambda ring: ring.min_miles)
    for previous, current in zip(sorted_rings, sorted_rings[1:]):
        if previous.max_miles > current.min_miles:
            raise ValueError("Ring ranges must be non-overlapping and increasing.")
    for ring in sorted_rings:
        if ring.min_miles < 0 or ring.max_miles <= ring.min_miles:
            raise ValueError("Each ring must have min_miles >= 0 and max_miles > min_miles.")


def prompt_rings() -> tuple[RingDefinition, ...]:
    if prompt_yes_no("Use the default ring set?", default=True):
        return tuple(DEFAULT_RINGS)

    rings: list[RingDefinition] = []
    count = int(prompt_float("How many rings? ", min_value=1, max_value=20))
    for idx in range(count):
        print(f"Ring {idx + 1}:")
        min_miles = prompt_float("  Min miles: ", min_value=0, max_value=10000)
        max_miles = prompt_float("  Max miles: ", min_value=0, max_value=10000)
        if max_miles <= min_miles:
            print("  Max miles must be greater than min miles.")
            return prompt_rings()
        label = prompt_input("  Label: ")
        color = prompt_input("  Color (CSS name or hex): ")
        rings.append(RingDefinition(min_miles, max_miles, label, color))
    validate_rings(rings)
    return tuple(sorted(rings, key=lambda ring: ring.min_miles))


def prompt_new_region(regions: dict[str, RegionConfig]) -> RegionConfig:
    while True:
        name = prompt_input("Region name: ")
        if not name:
            print("Region name cannot be empty.")
            continue
        if name in regions and not prompt_yes_no("Region exists. Overwrite?", default=False):
            continue
        center_lat = prompt_float("Center latitude (-90 to 90): ", -90, 90)
        center_lon = prompt_float("Center longitude (-180 to 180): ", -180, 180)
        rings = prompt_rings()
        pbf_url = prompt_input("PBF URL (optional, press Enter to skip): ") or None
        return RegionConfig(
            name=name,
            center_lat=center_lat,
            center_lon=center_lon,
            rings=rings,
            pbf_url=pbf_url,
        )


def choose_region(regions: dict[str, RegionConfig]) -> RegionConfig:
    if regions:
        print("Available regions:")
        for name, region in regions.items():
            cached = "cached" if pbf_cache_path(region.name).exists() else "missing"
            print(f"  - {name} ({cached} PBF)")
    else:
        print("No regions configured yet.")

    choice = prompt_input("Enter a region name or type 'new': ").lower()
    if choice == "new":
        return prompt_new_region(regions)
    if not choice:
        if regions:
            name = next(iter(regions))
            print(f"Using default region: {name}")
            return regions[name]
        return prompt_new_region(regions)
    if choice in regions:
        return regions[choice]
    print(f"Region '{choice}' not found.")
    return prompt_new_region(regions)


def ensure_pbf(region: RegionConfig) -> tuple[RegionConfig, Path]:
    pbf_path = pbf_cache_path(region.name)
    if pbf_path.exists():
        print(f"PBF cache hit: {pbf_path}")
        return region, pbf_path

    url = region.pbf_url
    if not url:
        url = prompt_input("Enter a PBF download URL (Geofabrik or custom): ")
        if not url:
            raise SystemExit("No PBF URL provided.")
        region = replace(region, pbf_url=url)
    print(f"Downloading PBF from {url} ...")
    download_pbf(url, pbf_path)
    return region, pbf_path


def run_pipeline(region: RegionConfig, pbf_path: Path) -> None:
    paths = build_output_paths(region)
    paths.output_root.mkdir(parents=True, exist_ok=True)

    print("Extracting fire stations from PBF...")
    extract_fire_stations_lowmem(pbf_path, paths.input_file)

    print("Loading extracted stations...")
    stations = gpd.read_file(paths.input_file)

    print("Assigning rings...")
    stations = add_distance_and_rings(
        stations, region.center_lat, region.center_lon, region.rings
    )
    stations_in_scope = stations[stations["ring"] != ">100 miles"].copy()

    export_geojson(stations, paths.output_geojson)
    print(f"Saved ring-assigned GeoJSON to: {paths.output_geojson}")

    print("Exporting CSVs per ring...")
    export_ring_csvs(stations_in_scope, region.rings, paths.rings_output_dir)

    print("Creating interactive map...")
    create_interactive_map(
        stations_in_scope,
        region.center_lat,
        region.center_lon,
        region.rings,
        paths.map_file,
        center_label=region.name,
    )
    print(f"Interactive map saved to: {paths.map_file}")


def main() -> None:
    PBF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    regions = load_regions(REGIONS_PATH)
    region = choose_region(regions)
    regions[region.name] = region
    region, pbf_path = ensure_pbf(region)
    regions[region.name] = region
    save_regions(regions, REGIONS_PATH)
    run_pipeline(region, pbf_path)


if __name__ == "__main__":
    main()
