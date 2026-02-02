#!/usr/bin/env python3
"""
Fill missing addresses in CSV exports using Nominatim reverse geocoding.

Default behavior:
- Reads all .csv files in the input directory (rings_csv by default).
- Replaces rows with "No address tags" in the address column.
- Writes updated CSVs to a separate output directory to avoid overwriting.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

from firefighter_finder.address_utils import (
    DEFAULT_USER_AGENT,
    fill_missing_addresses,
    find_output_root,
    require_network,
)

REGION = os.environ.get("REGION", "default")


def process_file(path: Path, output_dir: Path, geocode, cache: dict, in_place: bool) -> tuple[int, int]:
    df = pd.read_csv(path)
    if "address" not in df.columns:
        print(f"Skipping {path.name}: missing address column.")
        return 0, 0

    df, missing_count, filled_count = fill_missing_addresses(
        df,
        geocode,
        cache,
        address_column="address",
        lat_column="lat",
        lon_column="lon",
        missing_pattern="No address tags",
    )

    if missing_count == 0:
        print(f"{path.name}: no missing addresses found.")
    else:
        print(f"{path.name}: processed {missing_count} missing addresses.")

    output_path = path if in_place else output_dir / path.name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return missing_count, filled_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill missing addresses in fire station CSV exports.")
    parser.add_argument("--region", default=REGION, help="Region name for outputs/REGION.")
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--user-agent", type=str, default=DEFAULT_USER_AGENT)
    parser.add_argument("--in-place", action="store_true", help="Overwrite CSVs in the input directory.")
    parser.add_argument("--skip-network-check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = find_output_root(args.region, args.project_dir)
    input_dir = args.input_dir or (output_root / "rings_csv")
    output_dir = args.output_dir or (output_root / "rings_csv_with_addresses")

    if not args.skip_network_check:
        require_network()

    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        raise SystemExit(f"No CSV files found in {input_dir}")

    geolocator = Nominatim(user_agent=args.user_agent, timeout=10)
    geocode = RateLimiter(
        geolocator.reverse,
        min_delay_seconds=1.1,
        max_retries=2,
        error_wait_seconds=2.0,
        swallow_exceptions=True,
        return_value_on_exception=None,
    )

    cache: dict[tuple[float, float], str] = {}
    total_missing = 0
    total_filled = 0

    for csv_path in csv_files:
        missing, filled = process_file(csv_path, output_dir, geocode, cache, args.in_place)
        total_missing += missing
        total_filled += filled

    print("\nSummary")
    print("-------")
    print(f"Files processed: {len(csv_files)}")
    print(f"Missing addresses found: {total_missing}")
    print(f"Addresses updated: {total_filled}")
    if not args.in_place:
        print(f"Updated CSVs written to: {output_dir}")


if __name__ == "__main__":
    main()
