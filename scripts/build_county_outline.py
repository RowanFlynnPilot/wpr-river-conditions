#!/usr/bin/env python3
"""
One-time builder: fetches the NWS county-zone geometry for every county with
a monitored gauge and writes a simplified GeoJSON the overview map draws as
a dashed orientation outline (and, later, shades during active alerts).

Output: public/data/counties.geojson (committed — county lines don't change).
Rerun only if the gauge roster grows into a new county.

Usage: python scripts/build_county_outline.py
"""

import json
from pathlib import Path
from urllib.request import Request, urlopen

# Keep in sync with NWS_ZONES in fetch_data.py.
ZONES = {
    "WIC067": "Langlade",
    "WIC069": "Lincoln",
    "WIC073": "Marathon",
    "WIC097": "Portage",
    "WIC141": "Wood",
}

PRECISION = 4          # ~11 m at this latitude — plenty for a dashed outline
DECIMATE_EVERY = 3     # keep every 3rd vertex (plus ring endpoints)


def fetch(url: str):
    req = Request(url, headers={
        "User-Agent": "WPR-RiverConditions/1.0 (wausaupilotandreview.com)",
        "Accept": "application/geo+json",
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def simplify_ring(ring):
    kept = [
        [round(x, PRECISION), round(y, PRECISION)]
        for i, (x, y) in enumerate(ring)
        if i % DECIMATE_EVERY == 0
    ]
    # Rings must stay closed.
    if kept and kept[0] != kept[-1]:
        kept.append(kept[0])
    return kept


def simplify_geometry(geom):
    t = geom["type"]
    if t == "Polygon":
        coords = [simplify_ring(r) for r in geom["coordinates"]]
    elif t == "MultiPolygon":
        coords = [[simplify_ring(r) for r in poly] for poly in geom["coordinates"]]
    else:
        return geom
    return {"type": t, "coordinates": coords}


def main():
    features = []
    for zone, name in ZONES.items():
        url = f"https://api.weather.gov/zones/county/{zone}"
        data = fetch(url)
        geom = data.get("geometry")
        if not geom:
            print(f"  !! no geometry for {zone} ({name}) — skipped")
            continue
        features.append({
            "type": "Feature",
            "properties": {"zone": zone, "name": name},
            "geometry": simplify_geometry(geom),
        })
        print(f"  {zone} {name}: ok")

    out = {"type": "FeatureCollection", "features": features}
    out_path = Path(__file__).parent.parent / "public" / "data" / "counties.geojson"
    out_path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes, {len(features)} counties)")


if __name__ == "__main__":
    main()
