#!/usr/bin/env python3
"""
Fill missing addresses in CSV exports using Nominatim reverse geocoding.

Default behavior:
- Reads all .csv files in the input directory (rings_csv by default).
- Replaces rows with "No address tags" in the address column.
- Writes updated CSVs to a separate output directory to avoid overwriting.
"""

import argparse
import socket
from pathlib import Path

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from tqdm import tqdm

DEFAULT_INPUT_DIR = Path("rings_csv")
DEFAULT_OUTPUT_DIR = Path("rings_csv_with_addresses")
DEFAULT_USER_AGENT = "FireStation Finder-Mark-LaHabra (mark@boondocktechnologies.com)"


def require_network(host: str = "nominatim.openstreetmap.org", port: int = 443, timeout: int = 5) -> None:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as exc:
        raise SystemExit(
            f"\nNo outbound network to {host}:{port} ({exc}).\n"
            "Fix routing/DNS/VPN/firewall first, then re-run.\n"
        )


def build_address(address: dict) -> str:
    street = " ".join(filter(None, [address.get("house_number"), address.get("road")])).strip()
    locality = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet")
    parts = [
        street or None,
        locality,
        address.get("state"),
        address.get("postcode"),
    ]
    return ", ".join([part for part in parts if part])


def get_address(row: pd.Series, geocode, cache: dict) -> str:
    lat = row.get("lat")
    lon = row.get("lon")
    if pd.isna(lat) or pd.isna(lon):
        return "Missing lat/lon"

    key = (float(lat), float(lon))
    if key in cache:
        return cache[key]

    try:
        location = geocode((lat, lon), exactly_one=True, addressdetails=True)
        if not location or not getattr(location, "raw", None):
            cache[key] = "No address found via reverse geocoding"
            return cache[key]

        address = location.raw.get("address") or {}
        formatted = build_address(address)
        cache[key] = formatted if formatted else "Address found but incomplete"
        return cache[key]
    except (GeocoderUnavailable, GeocoderTimedOut, GeocoderServiceError) as exc:
        cache[key] = f"Lookup failed: {type(exc).__name__}"
        return cache[key]
    except Exception:
        cache[key] = "Error during lookup"
        return cache[key]


def process_file(path: Path, output_dir: Path, geocode, cache: dict, in_place: bool) -> tuple[int, int]:
    df = pd.read_csv(path)
    if "address" not in df.columns:
        print(f"Skipping {path.name}: missing address column.")
        return 0, 0

    missing_mask = df["address"].astype(str).str.contains("No address tags", na=False)
    missing_count = int(missing_mask.sum())
    if missing_count == 0:
        print(f"{path.name}: no missing addresses found.")
    else:
        missing_rows = df.loc[missing_mask]
        addresses = [
            get_address(row, geocode, cache)
            for _, row in tqdm(
                missing_rows.iterrows(),
                total=missing_count,
                desc=f"Reverse geocoding {path.name}",
            )
        ]
        df.loc[missing_mask, "address"] = addresses

    updated_count = int(
        df.loc[missing_mask, "address"].astype(str).str.contains("No address tags").sum()
    )

    output_path = path if in_place else output_dir / path.name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return missing_count, missing_count - updated_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill missing addresses in fire station CSV exports.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--user-agent", type=str, default=DEFAULT_USER_AGENT)
    parser.add_argument("--in-place", action="store_true", help="Overwrite CSVs in the input directory.")
    parser.add_argument("--skip-network-check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir
    output_dir = args.output_dir

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
