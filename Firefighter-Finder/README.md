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
