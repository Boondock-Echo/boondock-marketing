#!/usr/bin/env python3
"""
Ensure addresses contain house number, street, city, state, and ZIP.

Rows with missing or incomplete addresses are corrected via reverse geocoding
using the row's latitude/longitude (or GeoJSON geometry).
"""

import argparse
import re
import socket
from pathlib import Path

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover - geopandas optional for CSV-only usage
    gpd = None


DEFAULT_USER_AGENT = "FireStationFinder-Mark-LaHabra (your.email@example.com)"
STATE_ZIP_RE = re.compile(r"\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b")


def require_network(host: str = "nominatim.openstreetmap.org", port: int = 443, timeout: int = 5) -> None:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as exc:
        raise SystemExit(
            f"\nNo outbound network to {host}:{port} ({exc}).\n"
            "Fix routing/DNS/VPN/firewall first, then re-run.\n"
        )


def address_is_complete(address: str) -> bool:
    if not isinstance(address, str) or not address.strip():
        return False

    address = address.strip()
    state_zip_match = STATE_ZIP_RE.search(address)
    if not state_zip_match:
        return False

    street_part = address.split(",")[0].strip()
    if not re.match(r"^\s*\d", street_part):
        return False
    if not re.search(r"[A-Za-z]", street_part):
        return False

    before_state = address[: state_zip_match.start()].rstrip(", ")
    if not before_state:
        return False
    city_candidate = before_state.split(",")[-1].strip()
    if not re.search(r"[A-Za-z]", city_candidate):
        return False

    return True


def build_address(address: dict) -> str:
    street = " ".join(filter(None, [address.get("house_number"), address.get("road")])).strip()
    locality = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
    )
    parts = [street or None, locality, address.get("state"), address.get("postcode")]
    formatted = ", ".join([part for part in parts if part])
    return formatted


def reverse_geocode(lat: float, lon: float, geocode, cache: dict) -> str:
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


def ensure_lat_lon(df: pd.DataFrame, lat_column: str, lon_column: str) -> pd.DataFrame:
    if lat_column in df.columns and lon_column in df.columns:
        return df

    if gpd is None:
        raise SystemExit("GeoPandas is required to derive lat/lon from geometry.")

    if "geometry" not in df.columns:
        raise SystemExit("Missing lat/lon columns and no geometry column found.")

    df[lat_column] = df.geometry.y
    df[lon_column] = df.geometry.x
    return df


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


def load_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json"}:
        if gpd is None:
            raise SystemExit("GeoPandas is required to read GeoJSON files.")
        return gpd.read_file(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise SystemExit(f"Unsupported input type: {suffix}")


def write_output(df: pd.DataFrame, output: Path, input_path: Path) -> None:
    if output is None:
        output = input_path
    suffix = output.suffix.lower()
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix in {".geojson", ".json"}:
        df.to_file(output, driver="GeoJSON")
    elif suffix == ".csv":
        df.to_csv(output, index=False)
    else:
        raise SystemExit(f"Unsupported output type: {suffix}")


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
