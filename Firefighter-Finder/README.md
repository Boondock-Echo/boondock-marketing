# boondock-marketing
Tools for marketing including address discovery and CRM

## Firefighter Finder: filling missing CSV addresses

If the `rings_csv` exports contain `No address tags` entries, you can use the
CSV reverse-geocoding helper to fill them with mailing addresses.

```bash
python fill_missing_addresses_csv.py \
  --input-dir rings_csv \
  --output-dir rings_csv_with_addresses \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

By default, the script writes updated CSVs to `rings_csv_with_addresses` so you
can review the results. Use `--in-place` to overwrite the originals once you
are satisfied.

## Ensure complete mailing addresses

To validate that every address has a house number, street, city, state, and ZIP
code (and repair incomplete rows using reverse geocoding), use:

```bash
python ensure_complete_addresses.py \
  --input fire_stations_with_rings.geojson \
  --output fire_stations_with_complete_addresses.geojson \
  --user-agent "FireStationFinder-Mark-LaHabra (your.email@example.com)"
```

The script also supports CSV inputs. Use `--in-place` to overwrite the original
file once you have reviewed the output.
