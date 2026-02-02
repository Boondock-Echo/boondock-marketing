from __future__ import annotations

import importlib.util
import re
import socket
from pathlib import Path

import pandas as pd
from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable

DEFAULT_USER_AGENT = "FireStationFinder-Mark-LaHabra (your.email@example.com)"
STATE_ZIP_RE = re.compile(r"\b([A-Z]{2})\s*,?\s+(\d{5}(?:-\d{4})?)\b")

_HAS_GEOPANDAS = importlib.util.find_spec("geopandas") is not None
if _HAS_GEOPANDAS:
    import geopandas as gpd
else:
    gpd = None


def require_network(host: str = "nominatim.openstreetmap.org", port: int = 443, timeout: int = 5) -> None:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as exc:
        raise SystemExit(
            f"\nNo outbound network to {host}:{port} ({exc}).\n"
            "Fix routing/DNS/VPN/firewall first, then re-run.\n"
        )


def find_output_root(region: str, start_dir: Path | None = None) -> Path:
    start_dir = (start_dir or Path.cwd()).resolve()
    for candidate_base in (start_dir, *start_dir.parents):
        candidate = candidate_base / "outputs" / region
        if candidate.exists():
            return candidate
    return (start_dir / "outputs" / region).resolve()


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


def reverse_geocode(lat: float, lon: float, geocode, cache: dict[tuple[float, float], str]) -> str:
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


def fill_missing_addresses(
    df: pd.DataFrame,
    geocode,
    cache: dict[tuple[float, float], str],
    address_column: str,
    lat_column: str,
    lon_column: str,
    missing_pattern: str = "No address tags",
) -> tuple[pd.DataFrame, int, int]:
    df = ensure_lat_lon(df, lat_column, lon_column)
    missing_mask = df[address_column].astype(str).str.contains(missing_pattern, na=False)
    missing_count = int(missing_mask.sum())

    if missing_count == 0:
        return df, 0, 0

    corrected_addresses = []
    for _, row in df.loc[missing_mask].iterrows():
        lat = row.get(lat_column)
        lon = row.get(lon_column)
        if pd.isna(lat) or pd.isna(lon):
            corrected_addresses.append("Missing lat/lon")
            continue
        corrected_addresses.append(reverse_geocode(lat, lon, geocode, cache))

    df.loc[missing_mask, address_column] = corrected_addresses
    remaining_missing = int(
        df.loc[missing_mask, address_column]
        .astype(str)
        .str.contains(missing_pattern, na=False)
        .sum()
    )
    return df, missing_count, missing_count - remaining_missing
