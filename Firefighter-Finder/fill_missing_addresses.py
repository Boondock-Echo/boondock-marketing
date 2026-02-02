#!/usr/bin/env python3
"""
Fill missing addresses in GeoJSON exports using Nominatim reverse geocoding.
Only processes rows with "No address tags".
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from tqdm import tqdm

from firefighter_finder.address_utils import (
    DEFAULT_USER_AGENT,
    ensure_lat_lon,
    find_output_root,
    load_input,
    require_network,
    reverse_geocode,
    write_output,
)

REGION = os.environ.get("REGION", "default")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill missing addresses in fire station GeoJSON exports."
    )
    parser.add_argument("--region", default=REGION, help="Region name for outputs/REGION.")
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Input GeoJSON file (defaults to outputs/REGION/fire_stations_with_rings.geojson).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output GeoJSON file (defaults to outputs/REGION/fire_stations_with_filled_addresses.geojson).",
    )
    parser.add_argument("--address-column", default="address")
    parser.add_argument("--lat-column", default="lat")
    parser.add_argument("--lon-column", default="lon")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--skip-network-check", action="store_true")
    parser.add_argument("--in-place", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = find_output_root(args.region, args.project_dir)
    input_path = args.input or (output_root / "fire_stations_with_rings.geojson")
    output_path = input_path if args.in_place else args.output or (
        output_root / "fire_stations_with_filled_addresses.geojson"
    )

    if not args.skip_network_check:
        require_network()

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    geolocator = Nominatim(user_agent=args.user_agent, timeout=10)
    geocode = RateLimiter(
        geolocator.reverse,
        min_delay_seconds=1.1,
        max_retries=2,
        error_wait_seconds=2.0,
        swallow_exceptions=True,
        return_value_on_exception=None,
    )

    print("Loading data...")
    df = load_input(input_path)
    df = ensure_lat_lon(df, args.lat_column, args.lon_column)

    cache: dict[tuple[float, float], str] = {}
    missing_mask = df[args.address_column].astype(str).str.contains("No address tags", na=False)
    missing_count = int(missing_mask.sum())
    print(f"Found {missing_count} stations with missing addresses.")

    if missing_count == 0:
        print("All addresses already present — nothing to do.")
        return

    print("Performing reverse geocoding (this may take a few minutes)...")
    corrected_addresses = []
    for _, row in tqdm(df.loc[missing_mask].iterrows(), total=missing_count, desc="Reverse geocoding"):
        lat = row.get(args.lat_column)
        lon = row.get(args.lon_column)
        if pd.isna(lat) or pd.isna(lon):
            corrected_addresses.append("Missing lat/lon")
            continue
        corrected_addresses.append(reverse_geocode(lat, lon, geocode, cache))

    df.loc[missing_mask, args.address_column] = corrected_addresses

    write_output(df, output_path, input_path)
    filled_count = int(
        (~df.loc[missing_mask, args.address_column].astype(str).str.contains("No address tags", na=False)).sum()
    )

    print(f"\nUpdated file saved to: {output_path}")
    print(f"\nSuccessfully filled {filled_count} out of {missing_count} missing addresses.")


if __name__ == "__main__":
    main()
