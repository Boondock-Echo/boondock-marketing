# boondock-marketing
Tools for marketing including address discovery and CRM

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

## Firefighter Finder: filling missing CSV addresses

If the `rings_csv` exports contain `No address tags` entries, you can use the
CSV reverse-geocoding helper to fill them with mailing addresses.

```bash
python fill_missing_addresses_csv.py \
  --input-dir outputs/<region>/rings_csv \
  --output-dir outputs/<region>/rings_csv_with_addresses \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

By default, the script writes updated CSVs to
`outputs/<region>/rings_csv_with_addresses` so you can review the results. Use
`--in-place` to overwrite the originals once you are satisfied.

## Ensure complete mailing addresses

To validate that every address has a house number, street, city, state, and ZIP
code (and repair incomplete rows using reverse geocoding), use:

```bash
python ensure_complete_addresses.py \
  --input outputs/<region>/fire_stations_with_rings.geojson \
  --output outputs/<region>/fire_stations_with_complete_addresses.geojson \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

The script also supports CSV inputs. Use `--in-place` to overwrite the original
file once you have reviewed the output.

To process every CSV in `outputs/<region>/rings_csv_with_addresses`, point the script at the
directory:

```bash
python ensure_complete_addresses.py \
  --input-dir outputs/<region>/rings_csv_with_addresses \
  --output outputs/<region>/rings_csv_with_complete_addresses \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```
