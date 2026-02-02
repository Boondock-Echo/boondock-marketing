import json

import pytest

from firefighter_finder.config import load_regions


@pytest.mark.parametrize(
    "payload, match",
    [
        ([], "regions.json root"),
        ({"la": {"center_lat": 33.9, "center_lon": -117.9}}, "missing required key"),
        (
            {
                "la": {
                    "center_lat": 33.9,
                    "center_lon": -117.9,
                    "rings": [{"min_miles": 0, "max_miles": 25, "label": "0-25 miles"}],
                }
            },
            "missing required key",
        ),
        (
            {
                "la": {
                    "center_lat": "not-a-number",
                    "center_lon": -117.9,
                    "rings": [],
                }
            },
            "center_lat must be a number",
        ),
    ],
)
def test_load_regions_invalid_payloads(tmp_path, payload, match):
    regions_path = tmp_path / "regions.json"
    regions_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_regions(regions_path)
