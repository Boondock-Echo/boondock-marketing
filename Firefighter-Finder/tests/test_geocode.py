from firefighter_finder.geocode import (
    ReverseGeocodeCache,
    reverse_geocode_address,
    reverse_geocode_address_cached,
)


class DummyLocation:
    def __init__(self, address):
        self.raw = {"address": address}


def test_reverse_geocode_address_formats_address():
    def geocode(_coords, exactly_one=True, addressdetails=True):
        return DummyLocation(
            {
                "house_number": "123",
                "road": "Main St",
                "city": "Springfield",
                "state": "CA",
                "postcode": "90210",
            }
        )

    result = reverse_geocode_address(34.0, -118.0, geocode)
    assert result.value == "123, Main St, Springfield, CA, 90210"
    assert result.error_code is None


def test_reverse_geocode_address_formats_with_town():
    def geocode(_coords, exactly_one=True, addressdetails=True):
        return DummyLocation(
            {
                "house_number": "77",
                "road": "Broadway",
                "town": "Smallville",
                "state": "KS",
                "postcode": "66002",
            }
        )

    result = reverse_geocode_address(39.0, -95.0, geocode)
    assert result.value == "77, Broadway, Smallville, KS, 66002"
    assert result.error_code is None


def test_reverse_geocode_address_cached_uses_cache(tmp_path):
    calls = {"count": 0}

    def geocode(_coords, exactly_one=True, addressdetails=True):
        calls["count"] += 1
        return DummyLocation(
            {
                "house_number": "500",
                "road": "Market St",
                "city": "Metropolis",
                "state": "NY",
                "postcode": "10001",
            }
        )

    cache_path = tmp_path / "reverse_cache.json"
    cache = ReverseGeocodeCache.load(cache_path)
    first = reverse_geocode_address_cached(40.0, -73.0, geocode, cache)
    second = reverse_geocode_address_cached(40.0, -73.0, geocode, cache)
    persisted = ReverseGeocodeCache.load(cache_path)

    assert first.value == second.value
    assert persisted.get((40.0, -73.0)) is not None
    assert calls["count"] == 1
