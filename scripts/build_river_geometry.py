#!/usr/bin/env python3
"""
One-time builder: traces the monitored river network through the USGS NLDI
API and writes a simplified GeoJSON of flow-oriented polylines for the
overview map's animated river layer.

Each output feature:
  properties.gauge — USGS id of the owning gauge (nearest main-stem gauge
                     for Wisconsin River segments; the tributary's own gauge
                     otherwise). The map colors and paces each segment from
                     that gauge's flood_status / normal_flow.
  properties.river — river slug
  properties.stem  — true for Wisconsin River main-stem segments
  geometry         — LineString whose coordinate order follows the flow
                     (upstream → downstream). The map's dash animation
                     depends on this order — don't reverse it.

Output: public/data/rivers.geojson (committed — rerun only if the gauge
roster changes). Tributary traces are trimmed where they reach reaches
already claimed by the main stem, so nothing double-draws.

Usage: python scripts/build_river_geometry.py
"""

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import GAUGES  # gauge coordinates for ownership assignment

NLDI = "https://api.water.usgs.gov/nldi/linked-data/nwissite"

# Rivers monitored by more than one gauge get their chains split into
# nearest-gauge ownership runs (each run colors/paces from its gauge).
RIVER_GAUGES = {
    "wisconsin": ["05391000", "05395000", "05398000", "05398100", "05400760"],
    "wolf": ["04074950", "04077400"],
}

# (river slug, origin gauge, [(navigation mode, km), ...])
# UM = upstream-main context tail, DM = downstream-main trace.
# Order matters: earlier traces claim reaches; later ones trim where they
# meet them (tributaries at confluences, extensions at overlaps).
TRACES = [
    ("wisconsin",      "05395000", [("UM", 20), ("DM", 140)]),
    ("wisconsin",      "05391000", [("DM", 95)]),   # Rainbow → Tomahawk → Merrill
    ("prairie",        "05394500", [("UM", 15), ("DM", 25)]),
    ("big-rib",        "05396000", [("UM", 15), ("DM", 60)]),
    ("little-rib",     "05396500", [("UM", 12), ("DM", 40)]),
    ("eau-claire",     "05397500", [("UM", 15), ("DM", 50)]),
    ("big-eau-pleine", "05399500", [("UM", 15), ("DM", 70)]),
    ("little-plover",  "05400625", [("UM", 8),  ("DM", 30)]),
    ("wolf",           "04074950", [("UM", 18), ("DM", 22)]),
    ("wolf",           "04077400", [("UM", 75), ("DM", 15)]),  # Langlade → Shawano
    ("red",            "04077630", [("UM", 12), ("DM", 25)]),
    ("embarrass",      "04078500", [("UM", 15), ("DM", 30)]),
    ("nf-yellow",      "05363600", [("UM", 10), ("DM", 20)]),
    ("tomorrow",       "04080798", [("UM", 10), ("DM", 18)]),
]

GAUGE_LONLAT = {g["id"]: (g["lon"], g["lat"]) for g in GAUGES}


def fetch(url):
    req = Request(url, headers={
        "User-Agent": "WPR-RiverConditions/1.0 (wausaupilotandreview.com)",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def endkey(pt):
    return (round(pt[0], 6), round(pt[1], 6))


def chain_segments(segments):
    """
    segments: list of {comid, mode, coords}. Joins them end-to-end (with
    reversal tolerance) into chains. Returns a list of chains, each a dict
    {coords, modes} where modes is the per-vertex-run provenance list
    aligned with segment order.
    """
    remaining = list(range(len(segments)))
    chains = []

    while remaining:
        idx = remaining.pop(0)
        seg = segments[idx]
        coords = list(seg["coords"])
        modes = [seg["mode"]]
        first_mode, last_mode = seg["mode"], seg["mode"]

        grew = True
        while grew:
            grew = False
            head, tail = endkey(coords[0]), endkey(coords[-1])
            for j in list(remaining):
                s = segments[j]
                s0, s1 = endkey(s["coords"][0]), endkey(s["coords"][-1])
                if s0 == tail:                     # append forward
                    coords.extend(s["coords"][1:])
                    last_mode = s["mode"]
                elif s1 == tail:                   # append reversed
                    coords.extend(list(reversed(s["coords"]))[1:])
                    last_mode = s["mode"]
                elif s1 == head:                   # prepend forward
                    coords = s["coords"][:-1] + coords
                    first_mode = s["mode"]
                elif s0 == head:                   # prepend reversed
                    coords = list(reversed(s["coords"]))[:-1] + coords
                    first_mode = s["mode"]
                else:
                    continue
                remaining.remove(j)
                grew = True
                break

        chains.append({"coords": coords, "first_mode": first_mode, "last_mode": last_mode})

    return chains


def orient_chain(chain, gauge_lonlat):
    """
    Ensure coordinate order = flow direction (upstream → downstream).
    Provenance rule: a UM endpoint is upstream, a DM endpoint is downstream.
    For single-mode chains, fall back to distance from the origin gauge
    (DM chains start at the gauge; UM chains end at it).
    """
    coords = chain["coords"]
    fm, lm = chain["first_mode"], chain["last_mode"]

    if fm != lm:
        if fm == "DM" and lm == "UM":
            coords.reverse()
    else:
        d_start = dist2(coords[0], gauge_lonlat)
        d_end = dist2(coords[-1], gauge_lonlat)
        if fm == "DM" and d_start > d_end:
            coords.reverse()
        elif fm == "UM" and d_end > d_start:
            coords.reverse()
    return coords


def clean(coords, step=1):
    """Round to 5 decimals (~1 m), optionally decimate (endpoints kept),
    and drop consecutive duplicates."""
    picked = coords[::step]
    if step > 1 and coords and picked[-1] != coords[-1]:
        picked.append(coords[-1])
    out = []
    for lon, lat in picked:
        pt = [round(lon, 5), round(lat, 5)]
        if not out or out[-1] != pt:
            out.append(pt)
    return out


def nearest_gauge(pt, gauge_ids):
    best, best_d = None, None
    for gid in gauge_ids:
        d = dist2(pt, GAUGE_LONLAT[gid])
        if best_d is None or d < best_d:
            best, best_d = gid, d
    return best


def split_by_owner(coords, gauge_ids, min_run=8):
    """Split a multi-gauge river chain into runs owned by the nearest of
    its gauges. Runs shorter than min_run vertices (meander flip-flops
    across the equidistant line between two gauges) merge into their
    neighbor."""
    runs = []
    cur_owner, cur = None, []
    for pt in coords:
        owner = nearest_gauge(pt, gauge_ids)
        if owner != cur_owner and cur:
            cur.append(pt)  # share the boundary vertex so lines stay joined
            runs.append([cur_owner, cur])
            cur = [pt]
        else:
            cur.append(pt)
        cur_owner = owner
    if len(cur) > 1:
        runs.append([cur_owner, cur])

    # Absorb slivers, then re-merge adjacent runs with the same owner.
    while len(runs) > 1:
        short = next((i for i, r in enumerate(runs) if len(r[1]) < min_run), None)
        if short is None:
            break
        target = short - 1 if short > 0 else short + 1
        runs[target][1] = (
            runs[target][1] + runs[short][1][1:] if target < short
            else runs[short][1][:-1] + runs[target][1]
        )
        runs.pop(short)
    merged = []
    for owner, pts in runs:
        if merged and merged[-1][0] == owner:
            merged[-1][1].extend(pts[1:])
        else:
            merged.append([owner, pts])
    return [(o, p) for o, p in merged]


def main():
    features = []
    claimed = set()  # comids owned by earlier traces (main stem first)

    for river, gauge_id, navs in TRACES:
        segments = []
        seen_here = set()
        for mode, km in navs:
            url = f"{NLDI}/USGS-{gauge_id}/navigation/{mode}/flowlines?distance={km}"
            try:
                data = fetch(url)
            except Exception as e:  # noqa: BLE001 — report and continue
                print(f"  !! {river} {mode}{km}: {e}")
                continue
            for f in data.get("features", []):
                comid = str(f.get("properties", {}).get("nhdplus_comid") or "")
                coords = f.get("geometry", {}).get("coordinates") or []
                if len(coords) < 2 or comid in claimed or comid in seen_here:
                    continue
                seen_here.add(comid)
                segments.append({"comid": comid, "mode": mode, "coords": coords})

        claimed.update(seen_here)
        if not segments:
            print(f"  !! {river}: no segments")
            continue

        chains = chain_segments(segments)
        n_pts = 0
        stem = river == "wisconsin"
        multi = RIVER_GAUGES.get(river)
        for chain in chains:
            # Tributaries are ambience at regional zooms — thin them.
            step = 1 if stem else 2
            coords = clean(orient_chain(chain, GAUGE_LONLAT[gauge_id]), step=step)
            if len(coords) < 2:
                continue
            if multi and len(multi) > 1:
                for owner, run in split_by_owner(coords, multi):
                    features.append({
                        "type": "Feature",
                        "properties": {"gauge": owner, "river": river, "stem": stem},
                        "geometry": {"type": "LineString", "coordinates": run},
                    })
                    n_pts += len(run)
            else:
                features.append({
                    "type": "Feature",
                    "properties": {"gauge": gauge_id, "river": river, "stem": stem},
                    "geometry": {"type": "LineString", "coordinates": coords},
                })
                n_pts += len(coords)
        print(f"  {river} ({gauge_id}): {len(segments)} reaches -> {len(chains)} chain(s), {n_pts} pts")

    out = {"type": "FeatureCollection", "features": features}
    out_path = Path(__file__).parent.parent / "public" / "data" / "rivers.geojson"
    out_path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    total = sum(len(f["geometry"]["coordinates"]) for f in features)
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes, "
          f"{len(features)} features, {total} points)")


if __name__ == "__main__":
    main()
