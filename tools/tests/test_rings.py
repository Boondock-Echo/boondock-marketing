from fire_station_tools.config import DEFAULT_RINGS
from fire_station_tools.rings import assign_ring


def test_assign_ring_boundary_distances():
    assert assign_ring(0, DEFAULT_RINGS) == ("0-25 miles", "green")
    assert assign_ring(24.999, DEFAULT_RINGS) == ("0-25 miles", "green")
    assert assign_ring(25, DEFAULT_RINGS) == ("25-50 miles", "blue")
    assert assign_ring(49.999, DEFAULT_RINGS) == ("25-50 miles", "blue")
    assert assign_ring(50, DEFAULT_RINGS) == ("50-75 miles", "orange")
    assert assign_ring(74.999, DEFAULT_RINGS) == ("50-75 miles", "orange")
    assert assign_ring(75, DEFAULT_RINGS) == ("75-100 miles", "red")
    assert assign_ring(99.999, DEFAULT_RINGS) == ("75-100 miles", "red")
    assert assign_ring(100, DEFAULT_RINGS) == (">100 miles", "gray")
