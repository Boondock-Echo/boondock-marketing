# tools
Utility tooling for fire station data extraction, cleanup, and exports.

## Fire station tooling package layout

Reusable Fire Station tooling logic now lives in the `fire_station_tools/` package:

- `config.py`: region centers, ring definitions, and output paths
- `osm.py`: PBF download/loading helpers plus fire station extraction
- `rings.py`: distance computations, ring assignment, and buffer-based ring filtering
- `geocode.py`: reverse-geocoding utilities
- `export.py`: GeoJSON/CSV/HTML map exporters

Scripts in the repo are thin entry points that call into this package.

## Primary entry points

- `extract_fire_stations.py`: stream fire station extraction from a `.osm.pbf`
- `assign_rings_map_and_csv_export.py`: assign distance rings and export GeoJSON/CSV/HTML
- `address_cleanup.py`: interactively repair missing or incomplete addresses in GeoJSON/CSV exports

## Outputs and caches

Pipeline outputs now live under `outputs/<region>/` (default region: `default`).
Set `REGION=your-region-name` to keep multiple runs separate. The core scripts
write:

- `outputs/<region>/fire_stations.geojson`
- `outputs/<region>/fire_stations_with_rings.geojson`
- `outputs/<region>/fire_stations_map.html`
- `outputs/<region>/rings_csv/`

Intermediate or third-party caches (for example, Overpass/OSM downloads) should
go in `cache/` and are ignored by git.

## Fire station tooling: address cleanup

If the `rings_csv` exports contain `No address tags` entries or incomplete mailing
addresses, use the interactive address cleanup helper to fill or repair them.

```bash
python address_cleanup.py \
  --input-dir outputs/<region>/rings_csv \
  --output-dir outputs/<region>/rings_csv_with_complete_addresses \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

Use `--input-dir` to process a folder and `--in-place` to overwrite files after
review. Add `--non-interactive` to skip prompts and rely on reverse geocoding.
Use `--enable-forward-search` to fall back to a forward lookup (web search style)
when reverse geocoding returns no results.

## Examples

To validate that every address has a house number, street, city, state, and ZIP
code (and repair incomplete rows), use:

```bash
python address_cleanup.py \
  --input outputs/<region>/fire_stations_with_rings.geojson \
  --output outputs/<region>/fire_stations_with_complete_addresses.geojson \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

The script also supports CSV inputs. Use `--in-place` to overwrite the original
file once you have reviewed the output.

To process every CSV in `outputs/<region>/rings_csv_with_addresses`, point the script at the
directory:

```bash
python address_cleanup.py \
  --input-dir outputs/<region>/rings_csv_with_addresses \
  --output-dir outputs/<region>/rings_csv_with_complete_addresses \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

## Checks

Run the automated checks with:

```bash
make check
```

Or run the test suite directly:

```bash
python -m pytest
```
