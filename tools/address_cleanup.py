#!/usr/bin/env python3
"""
Interactively repair missing or incomplete addresses in GeoJSON/CSV exports.

By default, the script:
- Locates rows with missing address tags or incomplete mailing addresses.
- Uses reverse geocoding as a suggestion.
- Prompts for address fields when data is missing or incomplete.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

from fire_station_tools.address_utils import (
    DEFAULT_USER_AGENT,
    address_is_complete,
    forward_geocode_address,
    ensure_lat_lon,
    load_input,
    require_network,
    reverse_geocode,
    write_output,
)


def prompt_input(prompt: str) -> str:
    return input(prompt).strip()


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


def format_manual_address() -> str:
    street = prompt_input("  House number + street: ")
    city = prompt_input("  City: ")
    state = prompt_input("  State (2-letter): ").upper()
    postal = prompt_input("  ZIP code: ")

    state_zip = " ".join(part for part in [state, postal] if part).strip()
    parts = [part for part in [street, city, state_zip] if part]
    return ", ".join(parts)


def prompt_for_address(
    existing: str,
    suggestion: str | None,
    require_complete: bool,
    suggestion_source: str | None = None,
) -> str:
    print("\nAddress repair")
    print("---------------")
    print(f"Current:   {existing or '—'}")
    if suggestion:
        suggestion_is_complete = address_is_complete(suggestion)
        source_label = f" ({suggestion_source})" if suggestion_source else ""
        print(f"Suggested{source_label}: {suggestion}")
        if prompt_yes_no("Use suggested address?", default=suggestion_is_complete):
            return suggestion

    if existing and not existing.lower().startswith("no address"):
        if prompt_yes_no("Keep the current address?", default=False):
            return existing

    while True:
        if not prompt_yes_no("Enter address fields manually?", default=True):
            return existing
        manual = format_manual_address()
        if not manual:
            if prompt_yes_no("Leave the address unchanged?", default=True):
                return existing
            continue
        if require_complete and not address_is_complete(manual):
            if prompt_yes_no("Address looks incomplete. Keep anyway?", default=False):
                return manual
            print("Please re-enter the address fields.")
            continue
        return manual


def build_target_mask(
    df: pd.DataFrame,
    address_column: str,
    missing_pattern: str,
    only_missing: bool,
    only_incomplete: bool,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    address_series = df[address_column].astype(str)
    missing_mask = address_series.str.contains(missing_pattern, na=False)
    incomplete_mask = ~address_series.map(address_is_complete)

    if only_missing:
        target_mask = missing_mask
    elif only_incomplete:
        target_mask = incomplete_mask
    else:
        target_mask = missing_mask | incomplete_mask
    return target_mask, missing_mask, incomplete_mask


def build_search_query(row: pd.Series, existing: str) -> str | None:
    parts: list[str] = []
    name = str(row.get("name") or "").strip()
    if name:
        parts.append(name)

    if existing and not existing.lower().startswith("no address"):
        parts.append(existing)

    for field in ("city", "town", "state", "postcode", "zip", "zip_code", "county"):
        value = row.get(field)
        if pd.notna(value):
            text = str(value).strip()
            if text and text not in parts:
                parts.append(text)

    if not parts:
        return None
    return ", ".join(parts)


def process_dataframe(
    df: pd.DataFrame,
    geocode,
    cache: dict[tuple[float, float], str],
    forward_geocode,
    address_column: str,
    lat_column: str,
    lon_column: str,
    missing_pattern: str = "No address tags",
    interactive: bool = False,
    only_missing: bool = False,
    only_incomplete: bool = False,
    require_complete: bool = True,
    enable_forward_search: bool = False,
) -> tuple[pd.DataFrame, int, int]:
    if address_column not in df.columns:
        raise SystemExit(f"Missing '{address_column}' column in input data.")

    target_mask, _, _ = build_target_mask(
        df,
        address_column,
        missing_pattern,
        only_missing,
        only_incomplete,
    )
    target_count = int(target_mask.sum())
    if target_count == 0:
        return df, 0, 0

    lat_lon_ready = True
    if lat_column not in df.columns or lon_column not in df.columns:
        try:
            df = ensure_lat_lon(df, lat_column, lon_column)
        except SystemExit:
            lat_lon_ready = False
            if not interactive:
                raise

    corrected_addresses = []
    for idx, row in df.loc[target_mask].iterrows():
        existing = str(row.get(address_column) or "").strip()
        suggestion = None
        suggestion_source = None
        lat = row.get(lat_column) if lat_lon_ready else None
        lon = row.get(lon_column) if lat_lon_ready else None
        if lat_lon_ready and pd.notna(lat) and pd.notna(lon):
            try:
                suggestion = reverse_geocode(lat, lon, geocode, cache)
            except Exception as exc:
                suggestion = f"Lookup failed: {type(exc).__name__}"

        if enable_forward_search and forward_geocode:
            if not suggestion or suggestion.lower().startswith(
                (
                    "no address found",
                    "address found but incomplete",
                    "lookup failed",
                    "error during lookup",
                )
            ):
                query = build_search_query(row, existing)
                forward_suggestion = forward_geocode_address(query, forward_geocode)
                if forward_suggestion:
                    suggestion = forward_suggestion
                    suggestion_source = "forward search"
                elif suggestion:
                    suggestion_source = "reverse geocode"
            elif suggestion:
                suggestion_source = "reverse geocode"
        elif suggestion:
            suggestion_source = "reverse geocode"

        if interactive:
            name = row.get("name")
            if name:
                print(f"\nStation: {name}")
            if lat_lon_ready and pd.notna(lat) and pd.notna(lon):
                print(f"Coordinates: {lat}, {lon}")
            corrected = prompt_for_address(
                existing,
                suggestion,
                require_complete,
                suggestion_source=suggestion_source,
            )
        else:
            if not lat_lon_ready or pd.isna(lat) or pd.isna(lon):
                corrected = "Missing lat/lon"
            else:
                corrected = suggestion or existing

        corrected_addresses.append((idx, corrected))

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
        description="Repair missing or incomplete addresses in fire station exports."
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
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--skip-network-check", action="store_true")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--only-incomplete", action="store_true")
    parser.add_argument(
        "--enable-forward-search",
        action="store_true",
        help="Use a forward lookup (name/address web search style) when reverse geocoding fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input
    input_dir = args.input_dir

    logging.getLogger("geopy").setLevel(logging.ERROR)

    if not input_path and not input_dir:
        raise SystemExit("Provide --input or --input-dir.")

    if args.only_missing and args.only_incomplete:
        raise SystemExit("Choose only one of --only-missing or --only-incomplete.")

    interactive = not args.non_interactive and sys.stdin.isatty()

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
    forward_geocode = RateLimiter(
        geolocator.geocode,
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
                geocode,
                cache,
                forward_geocode,
                args.address_column,
                args.lat_column,
                args.lon_column,
                interactive=interactive,
                only_missing=args.only_missing,
                only_incomplete=args.only_incomplete,
                enable_forward_search=args.enable_forward_search,
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
            geocode,
            cache,
            forward_geocode,
            args.address_column,
            args.lat_column,
            args.lon_column,
            interactive=interactive,
            only_missing=args.only_missing,
            only_incomplete=args.only_incomplete,
            enable_forward_search=args.enable_forward_search,
        )
        write_output(df, output_path, input_path)

        print("\nSummary")
        print("-------")
        print(f"Rows requiring attention: {target_count}")
        print(f"Addresses now complete: {corrected_count}")
        print(f"Output written to: {output_path}")


if __name__ == "__main__":
    main()
