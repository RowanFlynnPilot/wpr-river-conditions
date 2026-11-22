#!/usr/bin/env python3
"""
Merge the current river-data.json into the long-term archive.

The widget's payload only carries seven days of history. This keeps
everything, as small CSV files on the repo's `data` branch:

  readings/YYYY-MM.csv    one row per gauge per 2-hour bucket
  forecasts/YYYY-MM.csv   one row per gauge per model run: what the National
                          Water Model predicted, and the flow when it did
  reservoirs/YYYY.csv     one row per reservoir per day (feet below maximum)
  snowpack/YYYY.csv       one row per basin per day: snow water equivalent and
                          depth from NOAA's snow analysis
  manifest.json           what exists, for anything that reads the archive

Merging is idempotent: running it twice on the same payload changes nothing,
and because each run re-reads the payload's seven days of history, gaps of up
to a week between runs are filled in afterwards.

Usage: python scripts/archive_history.py <archive-dir> [payload.json]
Stdlib only, like the scraper.
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

READING_FIELDS = ["bucket", "gauge_id", "timestamp", "gage_height_ft", "streamflow_cfs"]
FORECAST_FIELDS = ["issued", "gauge_id", "archived_at", "observed_cfs", "horizon_h",
                   "forecast_pct", "forecast_cfs", "baseline"]
RESERVOIR_FIELDS = ["date", "slug", "feet_below_max"]
SNOWPACK_FIELDS = ["date", "basin", "swe_in", "depth_in"]

BUCKET_HOURS = 2


def _utc(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp to an aware UTC datetime (None if unusable)."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _bucket(dt: datetime) -> str:
    """Start of the 2-hour UTC bucket a reading falls in. The scraper keeps
    the latest reading per bucket, so the newest bucket's reading changes
    from run to run — keying on the bucket lets a later run replace it."""
    return _stamp(dt.replace(hour=dt.hour // BUCKET_HOURS * BUCKET_HOURS, minute=0, second=0, microsecond=0))


def _num(value) -> str:
    """Compact number for a CSV cell: 936.0 -> "936", 13.79 -> "13.79"."""
    if value is None:
        return ""
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def _read(path: Path, key_fields: list[str]) -> dict[tuple, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {tuple(row[k] for k in key_fields): row for row in csv.DictReader(fh)}


def _write(path: Path, fields: list[str], rows: dict[tuple, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow({f: rows[key].get(f, "") for f in fields})


def _merge(root: Path, folder: str, fields: list[str], key_fields: list[str],
           new_rows: list[dict], period_len: int, keep_existing: bool = False) -> int:
    """Merge rows into per-period files (period = the key's leading
    characters: 7 for a month, 4 for a year). Returns rows added or changed.
    With keep_existing, a row already archived under the same key is left
    alone rather than replaced."""
    by_period: dict[str, list[dict]] = {}
    for row in new_rows:
        by_period.setdefault(row[key_fields[0]][:period_len], []).append(row)

    changed = 0
    for period, rows in by_period.items():
        path = root / folder / f"{period}.csv"
        existing = _read(path, key_fields)
        before = changed
        for row in rows:
            key = tuple(row[k] for k in key_fields)
            clean = {f: row.get(f, "") for f in fields}
            if keep_existing and key in existing:
                continue
            if existing.get(key) != clean:
                existing[key] = clean
                changed += 1
        if changed != before:
            _write(path, fields, existing)
    return changed


def reading_rows(payload: dict) -> list[dict]:
    rows = []
    for gauge in payload.get("gauges") or []:
        for point in gauge.get("history") or []:
            dt = _utc(point.get("timestamp"))
            height, flow = point.get("gage_height_ft"), point.get("streamflow_cfs")
            if dt is None or (height is None and flow is None):
                continue
            rows.append({
                "bucket": _bucket(dt), "gauge_id": gauge["id"], "timestamp": _stamp(dt),
                "gage_height_ft": _num(height), "streamflow_cfs": _num(flow),
            })
    return rows


def forecast_rows(payload: dict) -> list[dict]:
    """One row per gauge per model run. Carried-forward forecasts are
    skipped: they repeat an earlier run against a later observation."""
    archived_at = _utc(payload.get("generated_at"))
    rows = []
    for gauge in payload.get("gauges") or []:
        fc = gauge.get("nwm_forecast") or {}
        issued = _utc(fc.get("issued"))
        pct = fc.get("next24h_pct")
        if issued is None or pct is None or archived_at is None or fc.get("carried_forward"):
            continue
        observed = (gauge.get("current") or {}).get("streamflow_cfs")
        forecast_cfs = None
        if observed is not None and fc.get("baseline") == "observed":
            forecast_cfs = round(observed * (1 + pct / 100), 1)
        rows.append({
            "issued": _stamp(issued), "gauge_id": gauge["id"], "archived_at": _stamp(archived_at),
            "observed_cfs": _num(observed), "horizon_h": _num(fc.get("horizon_h")),
            "forecast_pct": _num(pct), "forecast_cfs": _num(forecast_cfs),
            "baseline": fc.get("baseline") or "",
        })
    return rows


def reservoir_rows(payload: dict) -> list[dict]:
    rows = []
    for res in payload.get("reservoirs") or []:
        updated = _utc(res.get("last_updated"))
        if not res.get("has_data") or res.get("feet_below_max") is None or updated is None:
            continue
        rows.append({"date": updated.strftime("%Y-%m-%d"), "slug": res["slug"],
                     "feet_below_max": _num(res["feet_below_max"])})
    return rows


def snowpack_rows(payload: dict) -> list[dict]:
    snow = payload.get("snowpack") or {}
    valid = _utc(snow.get("valid"))
    if valid is None:
        return []
    return [{"date": valid.strftime("%Y-%m-%d"), "basin": b["key"],
             "swe_in": _num(b.get("swe_in")), "depth_in": _num(b.get("depth_in"))}
            for b in snow.get("basins") or [] if b.get("swe_in") is not None]


def write_manifest(root: Path) -> None:
    def listing(folder):
        return sorted(p.stem for p in (root / folder).glob("*.csv")) if (root / folder).exists() else []

    manifest = {
        "updated": _stamp(datetime.now(timezone.utc)),
        "readings": listing("readings"),
        "forecasts": listing("forecasts"),
        "reservoirs": listing("reservoirs"),
        "snowpack": listing("snowpack"),
        "bucket_hours": BUCKET_HOURS,
        "fields": {"readings": READING_FIELDS, "forecasts": FORECAST_FIELDS, "reservoirs": RESERVOIR_FIELDS,
                   "snowpack": SNOWPACK_FIELDS},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def archive(payload: dict, root: Path) -> dict:
    """Merge one payload into the archive. Returns rows added/changed per set."""
    changed = {
        "readings": _merge(root, "readings", READING_FIELDS, ["bucket", "gauge_id"], reading_rows(payload), 7),
        # First sighting of a model run wins: its observed flow is the one
        # nearest the run's issue time, which is what the forecast started from.
        "forecasts": _merge(root, "forecasts", FORECAST_FIELDS, ["issued", "gauge_id"],
                            forecast_rows(payload), 7, keep_existing=True),
        "reservoirs": _merge(root, "reservoirs", RESERVOIR_FIELDS, ["date", "slug"], reservoir_rows(payload), 4),
        "snowpack": _merge(root, "snowpack", SNOWPACK_FIELDS, ["date", "basin"], snowpack_rows(payload), 4),
    }
    if any(changed.values()):
        write_manifest(root)
    return changed


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    payload_path = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path(__file__).parent.parent / "src" / "data" / "river-data.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    changed = archive(payload, root)
    print("Archive: " + ", ".join(f"{n} {k}" for k, n in changed.items()) + " added or updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
