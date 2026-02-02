from __future__ import annotations

from pathlib import Path
from typing import Iterable

import folium
import geopandas as gpd

from .config import RingDefinition


def export_geojson(stations: gpd.GeoDataFrame, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    stations.to_file(output_file, driver="GeoJSON")


def export_ring_csvs(
    stations: gpd.GeoDataFrame,
    rings: Iterable[RingDefinition],
    output_dir: Path,
    fields: list[str] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    columns = fields or ["name", "address", "distance_mi", "lat", "lon", "osm_id", "ring"]
    if "ring" not in stations.columns:
        print(
            "  → Missing required column 'ring' for CSV export; "
            "unable to filter stations into rings."
        )
        return
    missing_columns = [column for column in columns if column not in stations.columns]
    if missing_columns:
        print(
            "  → Warning: missing columns for CSV export; filling with blanks: "
            f"{', '.join(missing_columns)}"
        )

    for ring in rings:
        ring_df = stations[stations["ring"] == ring.label].copy()
        if ring_df.empty:
            print(f"  → No stations in {ring.label}")
            continue
        for column in missing_columns:
            ring_df[column] = None
        csv_path = output_dir / f"fire_stations_{ring.label.replace(' ', '_')}.csv"
        ring_df[columns].to_csv(csv_path, index=False)
        print(f"  → {len(ring_df)} stations → {csv_path}")


def create_interactive_map(
    stations: gpd.GeoDataFrame,
    center_lat: float,
    center_lon: float,
    rings: Iterable[RingDefinition],
    map_file: Path,
    center_label: str = "Center",
) -> None:
    m = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles="CartoDB positron")
    folium.Marker(
        [center_lat, center_lon],
        popup=f"Center: {center_label}",
        icon=folium.Icon(color="black", icon="home"),
    ).add_to(m)

    for _, row in stations.iterrows():
        if row.get("lat") is None or row.get("lon") is None:
            continue
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=6,
            color=row.get("color", "gray"),
            fill=True,
            fill_color=row.get("color", "gray"),
            fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>{row.get('name', 'Unnamed')}</b><br>"
                f"{row.get('address', 'No address')}<br>"
                f"Distance: {row.get('distance_mi', 0):.1f} miles<br>"
                f"Ring: {row.get('ring', 'n/a')}",
                max_width=300,
            ),
        ).add_to(m)

    legend_rows = "\n".join(
        f"&nbsp; {ring.label} &nbsp; <i style=\"background:{ring.color}\"></i><br>"
        for ring in rings
    )
    legend_html = f"""
    <div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 140px;
                border:2px solid grey; z-index:9999; font-size:14px; background-color:white;
                padding: 10px;">
    &nbsp; <b>Ring Legend</b> <br>
    {legend_rows}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    map_file.parent.mkdir(parents=True, exist_ok=True)
    m.save(map_file)
