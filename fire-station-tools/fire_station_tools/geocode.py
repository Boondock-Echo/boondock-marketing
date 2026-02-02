from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import logging
from pathlib import Path
import socket
from typing import Callable, Generic, Optional, TypeVar

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

logger = logging.getLogger(__name__)
T = TypeVar("T")


class GeocodeErrorCode(str, Enum):
    EMPTY_QUERY = "empty-query"
    MISSING_LAT_LON = "missing-lat-lon"
    NO_RESULTS = "no-results"
    INCOMPLETE_ADDRESS = "incomplete-address"
    TIMEOUT = "timeout"
    SERVICE_UNAVAILABLE = "service-unavailable"
    SERVICE_ERROR = "service-error"
    UNEXPECTED_ERROR = "unexpected-error"


@dataclass(frozen=True)
class GeocodeResult(Generic[T]):
    value: T | None
    error_code: GeocodeErrorCode | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


@dataclass
class ReverseGeocodeCache:
    data: dict[tuple[float, float], GeocodeResult]
    path: Path | None = None

    @classmethod
    def load(cls, path: Path) -> "ReverseGeocodeCache":
        if not path.exists():
            return cls({}, path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Reverse geocode cache file is invalid JSON: %s", path)
            return cls({}, path)

        if not isinstance(raw, dict):
            logger.warning("Reverse geocode cache file has unexpected format: %s", path)
            return cls({}, path)

        data: dict[tuple[float, float], GeocodeResult] = {}
        for key, payload in raw.items():
            try:
                lat_str, lon_str = key.split(",", 1)
                lat = float(lat_str)
                lon = float(lon_str)
            except (ValueError, AttributeError):
                continue

            if not isinstance(payload, dict):
                continue

            error_code = payload.get("error_code")
            data[(lat, lon)] = GeocodeResult(
                value=payload.get("value"),
                error_code=GeocodeErrorCode(error_code) if error_code else None,
                error_message=payload.get("error_message"),
            )

        return cls(data, path)

    def get(self, key: tuple[float, float]) -> GeocodeResult | None:
        return self.data.get(key)

    def set(self, key: tuple[float, float], value: GeocodeResult) -> None:
        self.data[key] = value
        if self.path:
            self.save()

    def save(self) -> None:
        if not self.path:
            return
        payload = {
            f"{lat},{lon}": {
                "value": result.value,
                "error_code": result.error_code.value if result.error_code else None,
                "error_message": result.error_message,
            }
            for (lat, lon), result in self.data.items()
        }
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.path)


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


def build_forward_geocoder(user_agent: str, timeout: int = 10) -> Nominatim:
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


def build_rate_limited_forward_geocoder(
    geolocator: Nominatim,
    min_delay_seconds: float = 1.1,
    max_retries: int = 2,
    error_wait_seconds: float = 2.0,
    swallow_exceptions: bool = True,
) -> Callable:
    return RateLimiter(
        geolocator.geocode,
        min_delay_seconds=min_delay_seconds,
        max_retries=max_retries,
        error_wait_seconds=error_wait_seconds,
        swallow_exceptions=swallow_exceptions,
        return_value_on_exception=None,
    )


def geocode_place(query: str, geocode: Callable) -> GeocodeResult:
    if not query:
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.EMPTY_QUERY,
            error_message="Query cannot be empty.",
        )

    try:
        location = geocode(query, exactly_one=True, addressdetails=True)
        if not location or not getattr(location, "raw", None):
            return GeocodeResult(
                value=None,
                error_code=GeocodeErrorCode.NO_RESULTS,
                error_message="No results found.",
            )
        return GeocodeResult(value=(location.latitude, location.longitude))
    except GeocoderTimedOut as exc:
        logger.warning("Geocode lookup timed out: %s", exc)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.TIMEOUT,
            error_message=str(exc),
        )
    except GeocoderUnavailable as exc:
        logger.warning("Geocode service unavailable: %s", exc)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.SERVICE_UNAVAILABLE,
            error_message=str(exc),
        )
    except GeocoderServiceError as exc:
        logger.warning("Geocode service error: %s", exc)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.SERVICE_ERROR,
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("Unexpected error during geocode lookup.")
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.UNEXPECTED_ERROR,
            error_message=str(exc),
        )


def reverse_geocode_address(
    lat: Optional[float],
    lon: Optional[float],
    geocode: Callable,
) -> GeocodeResult:
    if lat is None or lon is None:
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.MISSING_LAT_LON,
            error_message="Missing lat/lon.",
        )

    try:
        location = geocode((lat, lon), exactly_one=True, addressdetails=True)
        if not location or not getattr(location, "raw", None):
            return GeocodeResult(
                value=None,
                error_code=GeocodeErrorCode.NO_RESULTS,
                error_message="No address found via reverse geocoding.",
            )

        addr = location.raw.get("address") or {}
        parts = [
            addr.get("house_number"),
            addr.get("road"),
            addr.get("city") or addr.get("town") or addr.get("village"),
            addr.get("state"),
            addr.get("postcode"),
        ]
        full_addr = ", ".join([p for p in parts if p])
        if full_addr:
            return GeocodeResult(value=full_addr)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.INCOMPLETE_ADDRESS,
            error_message="Address found but incomplete.",
        )

    except GeocoderTimedOut as exc:
        logger.warning("Reverse geocode timed out: %s", exc)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.TIMEOUT,
            error_message=str(exc),
        )
    except GeocoderUnavailable as exc:
        logger.warning("Reverse geocode unavailable: %s", exc)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.SERVICE_UNAVAILABLE,
            error_message=str(exc),
        )
    except GeocoderServiceError as exc:
        logger.warning("Reverse geocode service error: %s", exc)
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.SERVICE_ERROR,
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("Unexpected error during reverse geocode lookup.")
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.UNEXPECTED_ERROR,
            error_message=str(exc),
        )


def reverse_geocode_address_cached(
    lat: Optional[float],
    lon: Optional[float],
    geocode: Callable,
    cache: ReverseGeocodeCache,
) -> GeocodeResult:
    if lat is None or lon is None:
        return GeocodeResult(
            value=None,
            error_code=GeocodeErrorCode.MISSING_LAT_LON,
            error_message="Missing lat/lon.",
        )

    key = (float(lat), float(lon))
    cached = cache.get(key)
    if cached is not None:
        return cached

    result = reverse_geocode_address(lat, lon, geocode)
    cache.set(key, result)
    return result
