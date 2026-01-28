import socket
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderUnavailable, GeocoderTimedOut, GeocoderServiceError

def require_network(host="nominatim.openstreetmap.org", port=443, timeout=5):
    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as e:
        raise SystemExit(
            f"\nNo outbound network to {host}:{port} ({e}).\n"
            "Fix routing/DNS/VPN/firewall first, then re-run.\n"
        )

# call this once near the top, before progress_apply:
require_network()

USER_AGENT = "FireStationFinder-Mark-LaHabra (mark@yourdomain.com)"  # use a real email/identifier
geolocator = Nominatim(user_agent=USER_AGENT, timeout=10)

geocode = RateLimiter(
    geolocator.reverse,
    min_delay_seconds=1.1,          # Nominatim policy: max 1 req/sec :contentReference[oaicite:2]{index=2}
    max_retries=2,                  # don't spin forever
    error_wait_seconds=2.0,         # wait a bit then retry
    swallow_exceptions=True,        # return None on failure instead of raising
    return_value_on_exception=None,
)

def get_address(row):
    # be defensive about missing lat/lon
    lat = row.get("lat")
    lon = row.get("lon")
    if lat is None or lon is None:
        return "Missing lat/lon"

    try:
        # Ask for a single result; include addressdetails
        location = geocode((lat, lon), exactly_one=True, addressdetails=True)

        if not location or not getattr(location, "raw", None):
            return "No address found via reverse geocoding"

        addr = location.raw.get("address") or {}
        # Build a readable address; expand as desired
        parts = [
            addr.get("house_number"),
            addr.get("road"),
            addr.get("city") or addr.get("town") or addr.get("village"),
            addr.get("state"),
            addr.get("postcode"),
        ]
        full_addr = ", ".join([p for p in parts if p])
        return full_addr if full_addr else "Address found but incomplete"

    except (GeocoderUnavailable, GeocoderTimedOut, GeocoderServiceError) as e:
        # service/network class errors
        return f"Lookup failed: {type(e).__name__}"
    except Exception:
        # unexpected parse/row errors
        return "Error during lookup"
