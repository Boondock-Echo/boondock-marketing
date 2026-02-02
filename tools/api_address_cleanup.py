#!/usr/bin/env python3
"""
Repair missing or incomplete addresses using a third-party geocoding API.

This script is similar to address_cleanup.py but uses a forward-search API
(e.g., Google Geocoding) rather than reverse geocoding.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from fire_station_tools.address_utils import (
    address_is_complete,
    build_search_query,
    load_input,
    write_output,
)


@dataclass
class ApiResponse:
    address: str | None
    results: list[dict[str, Any]] | None = None
    error: str | None = None


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> Any:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    return 2 * radius_miles * asin(sqrt(a))


def google_geocode(query: str, api_key: str, timeout: int = 10) -> ApiResponse:
    params = urlencode({"address": query, "key": api_key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
    try:
        payload = fetch_json(url, timeout=timeout)
    except (HTTPError, URLError) as exc:
        return ApiResponse(address=None, error=f"Request failed: {exc}")
    except json.JSONDecodeError as exc:
        return ApiResponse(address=None, error=f"Invalid JSON response: {exc}")

    status = payload.get("status")
    if status != "OK":
        error_message = payload.get("error_message") or status
        return ApiResponse(address=None, error=f"Geocode failed: {error_message}")

    results = payload.get("results") or []
    if not results:
        return ApiResponse(address=None, error="No results returned")

    formatted = results[0].get("formatted_address")
    if not formatted:
        return ApiResponse(address=None, error="No formatted address returned")

    return ApiResponse(address=formatted, results=results)


def find_matching_result(
    results: list[dict[str, Any]],
    lat: float | None,
    lon: float | None,
    max_distance_miles: float,
) -> str | None:
    if lat is None or lon is None:
        return None

    best_address = None
    best_distance = None
    for result in results:
        geometry = result.get("geometry") or {}
        location = geometry.get("location") or {}
        res_lat = location.get("lat")
        res_lon = location.get("lng")
        if res_lat is None or res_lon is None:
            continue
        distance = haversine_miles(float(lat), float(lon), float(res_lat), float(res_lon))
        if distance > max_distance_miles:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_address = result.get("formatted_address")

    return best_address


def build_target_mask(
    df: pd.DataFrame,
    address_column: str,
    missing_pattern: str,
    only_missing: bool,
    only_incomplete: bool,
) -> pd.Series:
    address_series = df[address_column].astype(str)
    missing_mask = address_series.str.contains(missing_pattern, na=False)
    incomplete_mask = ~address_series.map(address_is_complete)

    if only_missing:
        return missing_mask
    if only_incomplete:
        return incomplete_mask
    return missing_mask | incomplete_mask


def process_dataframe(
    df: pd.DataFrame,
    address_column: str,
    lat_column: str,
    lon_column: str,
    api_key: str,
    min_delay: float,
    timeout: int,
    only_missing: bool,
    only_incomplete: bool,
    max_distance_miles: float,
    missing_pattern: str = "No address tags",
) -> tuple[pd.DataFrame, int, int]:
    if address_column not in df.columns:
        raise SystemExit(f"Missing '{address_column}' column in input data.")
    if lat_column not in df.columns or lon_column not in df.columns:
        raise SystemExit(
            f"Missing '{lat_column}'/'{lon_column}' columns in input data."
        )

    target_mask = build_target_mask(
        df,
        address_column,
        missing_pattern,
        only_missing,
        only_incomplete,
    )
    target_count = int(target_mask.sum())
    if target_count == 0:
        return df, 0, 0

    corrected_addresses: list[tuple[int, str]] = []
    for idx, row in df.loc[target_mask].iterrows():
        existing = str(row.get(address_column) or "").strip()
        lat = row.get(lat_column)
        lon = row.get(lon_column)
        if pd.isna(lat) or pd.isna(lon):
            corrected_addresses.append((idx, existing or "Missing lat/lon"))
            continue
        query = build_search_query(row, existing)
        if not query:
            corrected_addresses.append((idx, existing))
            continue

        result = google_geocode(query, api_key=api_key, timeout=timeout)
        if result.address and result.results:
            matched = find_matching_result(
                result.results,
                float(lat),
                float(lon),
                max_distance_miles,
            )
            if matched:
                corrected_addresses.append((idx, matched))
            else:
                fallback = existing or "No address found within distance threshold"
                corrected_addresses.append((idx, fallback))
        else:
            fallback = existing or (result.error or "No address found")
            corrected_addresses.append((idx, fallback))

        if min_delay > 0:
            time.sleep(min_delay)

    for idx, corrected in corrected_addresses:
        df.at[idx, address_column] = corrected

    corrected_count = int(
        df.loc[target_mask, address_column]
        .astype(str)
        .map(address_is_complete)
        .sum()
    )
    return df, target_count, corrected_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair missing or incomplete addresses using an API geocoder."
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory when --input-dir is provided.",
    )
    parser.add_argument("--address-column", default="address")
    parser.add_argument("--lat-column", default="lat")
    parser.add_argument("--lon-column", default="lon")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--min-delay", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--max-distance-miles", type=float, default=0.1)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--only-incomplete", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input
    input_dir = args.input_dir

    if not input_path and not input_dir:
        raise SystemExit("Provide --input or --input-dir.")

    if args.only_missing and args.only_incomplete:
        raise SystemExit("Choose only one of --only-missing or --only-incomplete.")

    api_key = args.api_key
    if not api_key:
        raise SystemExit("Provide --api-key for the geocoding API.")

    if input_dir:
        if not input_dir.exists():
            raise SystemExit(f"Input directory not found: {input_dir}")
        files = sorted([*input_dir.glob("*.csv"), *input_dir.glob("*.geojson")])
        if not files:
            raise SystemExit(f"No CSV or GeoJSON files found in {input_dir}")

        output_dir = input_dir if args.in_place else args.output_dir
        if output_dir is None:
            raise SystemExit("Provide --output-dir or use --in-place for directory mode.")
        output_dir.mkdir(parents=True, exist_ok=True)

        total_targets = 0
        total_corrected = 0
        for path in files:
            df = load_input(path)
            df, target_count, corrected_count = process_dataframe(
                df,
                args.address_column,
                args.lat_column,
                args.lon_column,
                api_key,
                args.min_delay,
                args.timeout,
                args.only_missing,
                args.only_incomplete,
                args.max_distance_miles,
            )
            output_path = path if args.in_place else output_dir / path.name
            write_output(df, output_path, path)
            total_targets += target_count
            total_corrected += corrected_count

        print("\nSummary")
        print("-------")
        print(f"Files processed: {len(files)}")
        print(f"Rows requiring attention: {total_targets}")
        print(f"Addresses now complete: {total_corrected}")
        print(f"Output written to: {output_dir}")
    else:
        if not input_path.exists():
            raise SystemExit(f"Input file not found: {input_path}")

        output_path = input_path if args.in_place else args.output
        if output_path is None:
            raise SystemExit("Provide --output or use --in-place.")

        df = load_input(input_path)
        df, target_count, corrected_count = process_dataframe(
            df,
            args.address_column,
            args.lat_column,
            args.lon_column,
            api_key,
            args.min_delay,
            args.timeout,
            args.only_missing,
            args.only_incomplete,
            args.max_distance_miles,
        )
        write_output(df, output_path, input_path)

        print("\nSummary")
        print("-------")
        print(f"Rows requiring attention: {target_count}")
        print(f"Addresses now complete: {corrected_count}")
        print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
