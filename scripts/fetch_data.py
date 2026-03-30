#!/usr/bin/env python3
"""
WPR River & Lake Conditions — Data Scraper
Fetches real-time data from USGS stream gauges, NWS flood alerts,
and WVIC reservoir levels for central Wisconsin.

Output: src/data/river-data.json (consumed by the React frontend)
Schedule: Every 30 minutes via GitHub Actions
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# USGS gauges in the Wausau / Marathon County area
# NWS flood stages sourced from api.water.noaa.gov/nwps/v1/gauges/{nws_lid}
GAUGES = [
    {
        "id": "05398000",
        "nws_lid": "ROTW3",  # NWS gauge ID for NWPS API
        "name": "Wisconsin River at Rothschild",
        "short_name": "WI River — Rothschild",
        "lat": 44.8861,
        "lon": -89.6218,
        "flood_stages": {  # NWS AHPS/NWPS, gage height in ft
            "action": 18.0,
            "minor": 25.0,
            "moderate": 27.0,
            "major": 28.0,
        },
        "description": "Primary gauge for the Wausau metro area",
    },
    {
        "id": "05398100",
        "nws_lid": None,  # No NWS match — Mosinee
        "name": "Wisconsin River at Mosinee",
        "short_name": "WI River — Mosinee",
        "lat": 44.7933,
        "lon": -89.6884,
        "flood_stages": None,
        "description": "Downstream of Wausau, near Mosinee",
    },
    {
        "id": "05396000",
        "nws_lid": "RIBW3",
        "name": "Big Rib River at Rib Falls",
        "short_name": "Big Rib River",
        "lat": 44.9653,
        "lon": -89.8134,
        "flood_stages": {
            "action": 7.0,
            "minor": 10.0,
            "moderate": 13.8,
            "major": 15.0,
        },
        "description": "Major tributary west of Wausau",
    },
    {
        "id": "05396500",
        "nws_lid": None,  # No NWS match
        "name": "Little Rib River near Wausau",
        "short_name": "Little Rib River",
        "lat": 44.9472,
        "lon": -89.6793,
        "flood_stages": None,
        "description": "Tributary flowing through western Marathon County",
    },
    {
        "id": "05397500",
        "nws_lid": "KELW3",
        "name": "Eau Claire River near Kelly",
        "short_name": "Eau Claire River",
        "lat": 44.8583,
        "lon": -89.4417,
        "flood_stages": {
            "action": 7.0,
            "minor": 9.0,
            "moderate": 12.0,
            "major": 15.0,
        },
        "description": "Major eastern tributary of the Wisconsin River",
    },
    {
        "id": "05399500",
        "nws_lid": "STRW3",
        "name": "Big Eau Pleine River at Stratford",
        "short_name": "Big Eau Pleine",
        "lat": 44.8014,
        "lon": -90.0781,
        "flood_stages": {
            "action": 11.0,
            "minor": 15.5,
            "moderate": 19.0,
            "major": 22.5,
        },
        "description": "Feeds the Eau Pleine Reservoir southwest of Wausau",
    },
]

# USGS parameter codes
PARAM_GAGE_HEIGHT = "00065"   # ft
PARAM_STREAMFLOW = "00060"    # cfs (cubic feet per second)
PARAM_WATER_TEMP = "00010"    # °C

# NWS alert zones for Marathon County
NWS_ZONE = "WIC073"  # Marathon County zone code
NWS_COUNTY_FIPS = "055073"

# WVIC reservoirs to track (scraped from wvic.com)
WVIC_RESERVOIRS = [
    {"name": "Rainbow Reservoir", "slug": "rainbow"},
    {"name": "Willow Reservoir", "slug": "willow"},
    {"name": "Spirit Reservoir", "slug": "spirit"},
    {"name": "Eau Pleine Reservoir", "slug": "eau-pleine"},
    {"name": "Rice Reservoir", "slug": "rice"},
    {"name": "Lake Wausau", "slug": "lake-wausau"},
]

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_json(url: str, timeout: int = 30) -> dict | list | None:
    """Fetch JSON from a URL with a User-Agent header (required by USGS/NWS)."""
    headers = {
        "User-Agent": "WPR-RiverConditions/1.0 (wausaupilotandreview.com)",
        "Accept": "application/json",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError) as e:
        log.error(f"Failed to fetch {url}: {e}")
        return None


def fetch_text(url: str, timeout: int = 30) -> str | None:
    """Fetch raw text from a URL."""
    headers = {
        "User-Agent": "WPR-RiverConditions/1.0 (wausaupilotandreview.com)",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (URLError, HTTPError) as e:
        log.error(f"Failed to fetch {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# USGS: Current instantaneous values
# ---------------------------------------------------------------------------

def fetch_usgs_current(gauge_id: str) -> dict:
    """
    Fetch the most recent instantaneous values for a gauge.
    Uses the legacy WaterServices IV endpoint (still active, migrating to OGC API).
    Returns: {gage_height_ft, streamflow_cfs, water_temp_f, timestamp}
    """
    site = gauge_id
    params = f"{PARAM_GAGE_HEIGHT},{PARAM_STREAMFLOW},{PARAM_WATER_TEMP}"
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?format=json&sites={site}&parameterCd={params}&siteStatus=all"
    )
    data = fetch_json(url)
    if not data:
        return {}

    result = {"timestamp": None}
    try:
        time_series = data["value"]["timeSeries"]
        for ts in time_series:
            var_code = ts["variable"]["variableCode"][0]["value"]
            values = ts["values"][0]["value"]
            if not values:
                continue
            latest = values[-1]
            val = float(latest["value"]) if latest["value"] != "" else None

            if val is not None and val < 0:
                val = None  # USGS uses negative values for missing data sometimes

            if var_code == PARAM_GAGE_HEIGHT:
                result["gage_height_ft"] = round(val, 2) if val else None
            elif var_code == PARAM_STREAMFLOW:
                result["streamflow_cfs"] = round(val, 1) if val else None
            elif var_code == PARAM_WATER_TEMP:
                # Convert °C to °F for the audience
                result["water_temp_f"] = round(val * 9 / 5 + 32, 1) if val else None
                result["water_temp_c"] = round(val, 1) if val else None

            # Use the most recent timestamp from any parameter
            ts_str = latest.get("dateTime")
            if ts_str and (result["timestamp"] is None or ts_str > result["timestamp"]):
                result["timestamp"] = ts_str
    except (KeyError, IndexError, TypeError) as e:
        log.warning(f"Error parsing USGS data for {gauge_id}: {e}")

    return result


def fetch_usgs_history(gauge_id: str, days: int = 7) -> list[dict]:
    """
    Fetch daily mean values for the past N days for sparkline charts.
    Returns: [{date, gage_height_ft, streamflow_cfs}, ...]
    """
    params = f"{PARAM_GAGE_HEIGHT},{PARAM_STREAMFLOW}"
    url = (
        f"https://waterservices.usgs.gov/nwis/dv/"
        f"?format=json&sites={gauge_id}&parameterCd={params}"
        f"&period=P{days}D&siteStatus=all"
    )
    data = fetch_json(url)
    if not data:
        return []

    # Build a dict keyed by date
    by_date: dict[str, dict] = {}
    try:
        for ts in data["value"]["timeSeries"]:
            var_code = ts["variable"]["variableCode"][0]["value"]
            for val_entry in ts["values"][0]["value"]:
                date_str = val_entry["dateTime"][:10]  # YYYY-MM-DD
                raw = val_entry["value"]
                val = float(raw) if raw != "" else None
                if val is not None and val < 0:
                    val = None

                if date_str not in by_date:
                    by_date[date_str] = {"date": date_str}

                if var_code == PARAM_GAGE_HEIGHT:
                    by_date[date_str]["gage_height_ft"] = round(val, 2) if val else None
                elif var_code == PARAM_STREAMFLOW:
                    by_date[date_str]["streamflow_cfs"] = round(val, 1) if val else None
    except (KeyError, IndexError, TypeError) as e:
        log.warning(f"Error parsing USGS history for {gauge_id}: {e}")

    return sorted(by_date.values(), key=lambda x: x["date"])


# ---------------------------------------------------------------------------
# NWS: Flood alerts for Marathon County
# ---------------------------------------------------------------------------

def fetch_nws_alerts() -> list[dict]:
    """
    Fetch active flood-related alerts from the NWS API for Marathon County.
    Returns: [{event, headline, severity, description, onset, expires, url}, ...]
    """
    url = f"https://api.weather.gov/alerts/active?zone={NWS_ZONE}"
    data = fetch_json(url)
    if not data:
        return []

    flood_keywords = {"flood", "flash flood", "river", "hydrologic"}
    alerts = []
    try:
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            event = (props.get("event") or "").lower()

            # Filter to flood-related alerts only
            if not any(kw in event for kw in flood_keywords):
                continue

            alerts.append({
                "event": props.get("event"),
                "headline": props.get("headline"),
                "severity": props.get("severity"),
                "urgency": props.get("urgency"),
                "description": props.get("description", "")[:500],  # Truncate
                "onset": props.get("onset"),
                "expires": props.get("expires"),
                "url": props.get("@id"),
            })
    except (KeyError, TypeError) as e:
        log.warning(f"Error parsing NWS alerts: {e}")

    return alerts


# ---------------------------------------------------------------------------
# NWS NWPS: Flood category from the National Water Prediction Service
# ---------------------------------------------------------------------------

def fetch_nws_flood_category(nws_lid: str) -> dict:
    """
    Fetch the current flood category from the NWS NWPS API.
    Returns: {flood_category, observed_stage, observed_unit, valid_time}
    """
    if not nws_lid:
        return {}

    url = f"https://api.water.noaa.gov/nwps/v1/gauges/{nws_lid}"
    data = fetch_json(url)
    if not data:
        return {}

    try:
        observed = data.get("status", {}).get("observed", {})
        return {
            "nws_flood_category": observed.get("floodCategory"),
            "nws_observed_stage": observed.get("primary"),
            "nws_observed_unit": observed.get("primaryUnit"),
            "nws_valid_time": observed.get("validTime"),
        }
    except (KeyError, TypeError) as e:
        log.warning(f"Error parsing NWS NWPS data for {nws_lid}: {e}")
        return {}


# ---------------------------------------------------------------------------
# WVIC: Reservoir levels
# ---------------------------------------------------------------------------

def fetch_wvic_reservoirs() -> list[dict]:
    """
    Fetch WVIC reservoir data from their level/flow report pages.
    These pages serve simple HTML tables — we use basic string parsing.
    Falls back gracefully if scraping fails.
    """
    results = []
    for res in WVIC_RESERVOIRS:
        slug = res["slug"]
        # WVIC publishes individual level+flow pages
        url = f"https://wvic.com/Content/{slug.replace('-', '_')}_Level_Flows.cfm"
        html = fetch_text(url)

        level_ft = None
        if html:
            # WVIC pages contain the current level in their data tables
            # Try a simple extraction — this may need adjustment if format changes
            import re
            # Look for elevation values (typically 4-digit numbers with decimals)
            matches = re.findall(r'(\d{3,4}\.\d{1,2})', html)
            if matches:
                try:
                    level_ft = float(matches[0])
                except ValueError:
                    pass

        results.append({
            "name": res["name"],
            "slug": slug,
            "current_level_ft": level_ft,
            "source_url": url,
            "last_updated": datetime.now(timezone.utc).isoformat() if level_ft else None,
        })

    return results


# ---------------------------------------------------------------------------
# Main: Assemble and write JSON
# ---------------------------------------------------------------------------

def main():
    log.info("Starting WPR River Conditions data fetch...")
    now = datetime.now(timezone.utc).isoformat()

    # Fetch gauge data
    gauges_data = []
    for gauge in GAUGES:
        log.info(f"Fetching USGS data for {gauge['name']} ({gauge['id']})...")
        current = fetch_usgs_current(gauge["id"])
        history = fetch_usgs_history(gauge["id"], days=7)

        # Fetch NWS flood category if available
        nws_data = {}
        if gauge.get("nws_lid"):
            log.info(f"  Fetching NWS NWPS data for {gauge['nws_lid']}...")
            nws_data = fetch_nws_flood_category(gauge["nws_lid"])

        # Determine flood status using NWS thresholds
        flood_status = "normal"
        stages = gauge.get("flood_stages")
        gage_ht = current.get("gage_height_ft")

        if stages and gage_ht is not None:
            if gage_ht >= stages["major"]:
                flood_status = "major"
            elif gage_ht >= stages["moderate"]:
                flood_status = "moderate"
            elif gage_ht >= stages["minor"]:
                flood_status = "minor"
            elif gage_ht >= stages["action"]:
                flood_status = "action"

        gauges_data.append({
            "id": gauge["id"],
            "nws_lid": gauge.get("nws_lid"),
            "name": gauge["name"],
            "short_name": gauge["short_name"],
            "description": gauge["description"],
            "lat": gauge["lat"],
            "lon": gauge["lon"],
            "flood_stages": stages,
            "flood_status": flood_status,
            "nws_flood_category": nws_data.get("nws_flood_category"),
            "current": current,
            "history": history,
            "usgs_url": f"https://waterdata.usgs.gov/monitoring-location/USGS-{gauge['id']}/",
            "nws_url": f"https://water.noaa.gov/gauges/{gauge['nws_lid'].lower()}" if gauge.get("nws_lid") else None,
        })

    # Fetch NWS alerts
    log.info("Fetching NWS flood alerts for Marathon County...")
    alerts = fetch_nws_alerts()

    # Fetch WVIC reservoirs (placeholder)
    log.info("Fetching WVIC reservoir data...")
    reservoirs = fetch_wvic_reservoirs()

    # Assemble output
    output = {
        "generated_at": now,
        "region": "Central Wisconsin — Marathon County",
        "gauges": gauges_data,
        "alerts": alerts,
        "reservoirs": reservoirs,
        "sources": {
            "usgs": "https://waterservices.usgs.gov/",
            "nws": "https://api.weather.gov/",
            "wvic": "https://wvic.com/",
        },
    }

    # Write to src/data/
    out_path = Path(__file__).parent.parent / "src" / "data" / "river-data.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    log.info(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")

    # Summary
    active_gauges = sum(1 for g in gauges_data if g["current"].get("gage_height_ft"))
    log.info(
        f"Done: {active_gauges}/{len(gauges_data)} gauges reporting, "
        f"{len(alerts)} active alerts"
    )


if __name__ == "__main__":
    main()
