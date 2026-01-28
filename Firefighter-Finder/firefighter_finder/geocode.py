from __future__ import annotations

import socket
from typing import Callable, Optional

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


def require_network(host: str = "nominatim.openstreetmap.org", port: int = 443, timeout: int = 5) -> None:
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as e:
        raise SystemExit(
            f"\nNo outbound network to {host}:{port} ({e}).\n"
            "Fix routing/DNS/VPN/firewall first, then re-run.\n"
        )


def build_reverse_geocoder(user_agent: str, timeout: int = 10) -> Nominatim:
    return Nominatim(user_agent=user_agent, timeout=timeout)


def build_rate_limited_reverse_geocoder(
    geolocator: Nominatim,
    min_delay_seconds: float = 1.1,
    max_retries: int = 2,
    error_wait_seconds: float = 2.0,
    swallow_exceptions: bool = True,
) -> Callable:
    return RateLimiter(
        geolocator.reverse,
        min_delay_seconds=min_delay_seconds,
        max_retries=max_retries,
        error_wait_seconds=error_wait_seconds,
        swallow_exceptions=swallow_exceptions,
        return_value_on_exception=None,
    )


def reverse_geocode_address(
    lat: Optional[float],
    lon: Optional[float],
    geocode: Callable,
) -> str:
    if lat is None or lon is None:
        return "Missing lat/lon"

    try:
        location = geocode((lat, lon), exactly_one=True, addressdetails=True)
        if not location or not getattr(location, "raw", None):
            return "No address found via reverse geocoding"

        addr = location.raw.get("address") or {}
        parts = [
            addr.get("house_number"),
            addr.get("road"),
            addr.get("city") or addr.get("town") or addr.get("village"),
            addr.get("state"),
            addr.get("postcode"),
        ]
        full_addr = ", ".join([p for p in parts if p])
        return full_addr if full_addr else "Address found but incomplete"

    except (GeocoderUnavailable, GeocoderTimedOut, GeocoderServiceError) as exc:
        return f"Lookup failed: {type(exc).__name__}"
    except Exception:
        return "Error during lookup"
