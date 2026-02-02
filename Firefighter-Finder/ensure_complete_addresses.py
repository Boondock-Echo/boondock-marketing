#!/usr/bin/env python3
"""
Ensure addresses contain house number, street, city, state, and ZIP.

Rows with missing or incomplete addresses are corrected via reverse geocoding
using the row's latitude/longitude (or GeoJSON geometry).
"""

import argparse
from pathlib import Path

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from firefighter_finder.address_utils import (
    DEFAULT_USER_AGENT,
    address_is_complete,
    ensure_lat_lon,
    load_input,
    require_network,
    reverse_geocode,
    write_output,
)


def process_dataframe(
    df: pd.DataFrame,
    geocode,
    cache: dict,
    address_column: str,
    lat_column: str,
    lon_column: str,
) -> tuple[pd.DataFrame, int, int]:
    df = ensure_lat_lon(df, lat_column, lon_column)
    address_series = df[address_column].astype(str)
    invalid_mask = ~address_series.map(address_is_complete)
    invalid_count = int(invalid_mask.sum())

    if invalid_count == 0:
        return df, 0, 0

    corrected_addresses = []
    for _, row in df.loc[invalid_mask].iterrows():
        lat = row.get(lat_column)
        lon = row.get(lon_column)
        if pd.isna(lat) or pd.isna(lon):
            corrected_addresses.append("Missing lat/lon")
            continue
        corrected_addresses.append(reverse_geocode(lat, lon, geocode, cache))

    df.loc[invalid_mask, address_column] = corrected_addresses
    corrected_count = int(
        df.loc[invalid_mask, address_column]
        .astype(str)
        .map(address_is_complete)
        .sum()
    )
    return df, invalid_count, corrected_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure addresses have house number, street, city, state, and ZIP."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Process every CSV in the directory (overrides --input).",
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
    input_path = args.input
    input_dir = args.input_dir

    if not args.skip_network_check:
        require_network()

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
    if input_dir:
        if not input_dir.exists():
            raise SystemExit(f"Input directory not found: {input_dir}")
        csv_files = sorted(input_dir.glob("*.csv"))
        if not csv_files:
            raise SystemExit(f"No CSV files found in {input_dir}")

        output_dir = input_dir if args.in_place else args.output
        if output_dir is None:
            raise SystemExit("Provide --output or use --in-place for directory mode.")
        output_dir.mkdir(parents=True, exist_ok=True)

        total_invalid = 0
        total_corrected = 0
        for csv_path in csv_files:
            df = load_input(csv_path)
            df, invalid_count, corrected_count = process_dataframe(
                df,
                geocode,
                cache,
                args.address_column,
                args.lat_column,
                args.lon_column,
            )
            write_output(df, output_dir / csv_path.name, csv_path)
            total_invalid += invalid_count
            total_corrected += corrected_count

        print("\nSummary")
        print("-------")
        print(f"Files processed: {len(csv_files)}")
        print(f"Rows with incomplete addresses: {total_invalid}")
        print(f"Addresses corrected to complete format: {total_corrected}")
        print(f"Output written to: {output_dir}")
    else:
        if not input_path.exists():
            raise SystemExit(f"Input file not found: {input_path}")

        output_path = input_path if args.in_place else args.output
        if output_path is None:
            raise SystemExit("Provide --output or use --in-place.")

        df = load_input(input_path)
        df, invalid_count, corrected_count = process_dataframe(
            df,
            geocode,
            cache,
            args.address_column,
            args.lat_column,
            args.lon_column,
        )
        write_output(df, output_path, input_path)

        print("\nSummary")
        print("-------")
        print(f"Rows with incomplete addresses: {invalid_count}")
        print(f"Addresses corrected to complete format: {corrected_count}")
        print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
