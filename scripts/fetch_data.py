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
import re
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
        "has_temp_sensor": False,
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
        "has_temp_sensor": False,
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
        "has_temp_sensor": False,
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
        "has_temp_sensor": False,
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
        "has_temp_sensor": False,
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
        "has_temp_sensor": False,
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

# Wausau area coordinates (used for weather/solunar APIs)
WAUSAU_LAT = 44.886
WAUSAU_LON = -89.622

# Static fishing reference data per gauge (rarely changes)
FISHING_REFERENCE = {
    "05398000": {  # WI River at Rothschild
        "species": ["Walleye", "Smallmouth Bass", "Musky", "Channel Catfish", "Sturgeon"],
        "trout_class": None,
        "regulations": [
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
            {"species": "Musky", "rule": '50" min, 1 daily'},
            {"species": "Bass", "rule": '14" min, 5 daily'},
        ],
        "season_notes": [
            "Walleye/Sauger open first Sat in May",
            "Catch-and-release bass season Mar\u2013Jun",
        ],
        "access_points": [
            {"name": "Rothschild Boat Landing", "directions": "Off River Dr, east of Hwy 51 bridge", "lat": 44.8872, "lng": -89.6173},
            {"name": "Wausau Whitewater Park", "directions": "River Dr near downtown Wausau", "lat": 44.9619, "lng": -89.6301},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "05398100": {  # WI River at Mosinee
        "species": ["Walleye", "Smallmouth Bass", "Musky", "Channel Catfish"],
        "trout_class": None,
        "regulations": [
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
            {"species": "Musky", "rule": '50" min, 1 daily'},
            {"species": "Bass", "rule": '14" min, 5 daily'},
        ],
        "season_notes": [
            "Walleye/Sauger open first Sat in May",
            "Catch-and-release bass season Mar\u2013Jun",
        ],
        "access_points": [
            {"name": "Mosinee Boat Landing", "directions": "Off Main St near the Mosinee dam", "lat": 44.7931, "lng": -89.6906},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "05396000": {  # Big Rib River at Rib Falls
        "species": ["Brook Trout", "Brown Trout", "Smallmouth Bass"],
        "trout_class": "Class I\u2013III (varies by reach)",
        "regulations": [
            {"species": "Trout", "rule": 'Category 3: 3 daily bag, 8" min'},
            {"species": "Note", "rule": "Special regs on some upstream reaches"},
        ],
        "season_notes": [
            "Early catch-and-release trout opens first Sat in Jan",
            "Regular season first Sat in May",
        ],
        "access_points": [
            {"name": "Rib Falls Dam", "directions": "County Rd N at Rib Falls", "lat": 44.9653, "lng": -89.8134},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Lands/FisheriesAreas/185bigribriver",
    },
    "05396500": {  # Little Rib River near Wausau
        "species": ["Brook Trout"],
        "trout_class": "Class II",
        "regulations": [
            {"species": "Trout", "rule": 'Category 3: 3 daily bag, 8" min'},
        ],
        "season_notes": [
            "Early catch-and-release trout opens first Sat in Jan",
            "Regular season first Sat in May",
        ],
        "access_points": [
            {"name": "Cty Rd J Crossing", "directions": "County Rd J west of Wausau", "lat": 44.9472, "lng": -89.6793},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "05397500": {  # Eau Claire River near Kelly
        "species": ["Smallmouth Bass", "Walleye", "Brown Trout"],
        "trout_class": None,
        "regulations": [
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
            {"species": "Bass", "rule": '14" min, 5 daily'},
            {"species": "Trout", "rule": "3 daily bag on upper reaches"},
        ],
        "season_notes": [
            "Trout regs apply on upper reaches",
            "General inland rules downstream",
        ],
        "access_points": [
            {"name": "Kelly Dam Landing", "directions": "Off Cty Rd Y near Kelly", "lat": 44.8583, "lng": -89.4417},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "05399500": {  # Big Eau Pleine at Stratford
        "species": ["Walleye", "Northern Pike", "Panfish", "Largemouth Bass"],
        "trout_class": None,
        "regulations": [
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
            {"species": "Northern Pike", "rule": '24" min, 5 daily'},
            {"species": "Bass", "rule": '14" min, 5 daily'},
        ],
        "season_notes": [
            "Walleye open first Sat in May",
            "Reservoir influence \u2014 good ice fishing in winter",
        ],
        "access_points": [
            {"name": "Eau Pleine County Park", "directions": "Off Cty Rd HH south of Stratford", "lat": 44.7800, "lng": -90.0700},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
}

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
    Fetch instantaneous values (IV) for the past N days for sparkline charts.
    Uses ~15-min interval data, sampled to hourly for smooth sparklines
    without excessive JSON size.
    Returns: [{timestamp, gage_height_ft, streamflow_cfs}, ...]
    """
    params = f"{PARAM_GAGE_HEIGHT},{PARAM_STREAMFLOW}"
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?format=json&sites={gauge_id}&parameterCd={params}"
        f"&period=P{days}D&siteStatus=all"
    )
    data = fetch_json(url)
    if not data:
        return []

    # Build a dict keyed by hour (YYYY-MM-DD HH) to sample ~hourly
    by_hour: dict[str, dict] = {}
    try:
        for ts in data["value"]["timeSeries"]:
            var_code = ts["variable"]["variableCode"][0]["value"]
            for val_entry in ts["values"][0]["value"]:
                dt_str = val_entry["dateTime"]
                # Key by hour to downsample 15-min data to hourly
                hour_key = dt_str[:13]  # "YYYY-MM-DDTHH"
                raw = val_entry["value"]
                val = float(raw) if raw != "" else None
                if val is not None and val < 0:
                    val = None

                if hour_key not in by_hour:
                    by_hour[hour_key] = {"timestamp": dt_str}

                if var_code == PARAM_GAGE_HEIGHT:
                    by_hour[hour_key]["gage_height_ft"] = round(val, 2) if val else None
                elif var_code == PARAM_STREAMFLOW:
                    by_hour[hour_key]["streamflow_cfs"] = round(val, 1) if val else None
    except (KeyError, IndexError, TypeError) as e:
        log.warning(f"Error parsing USGS history for {gauge_id}: {e}")

    return sorted(by_hour.values(), key=lambda x: x["timestamp"])


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

WVIC_DATA_URL = "https://wvic.com/Content/Data--Reports.cfm"

# Map WVIC chart names to our reservoir slugs
WVIC_NAME_MAP = {
    "big eau pleine": "eau-pleine",
    "rainbow": "rainbow",
    "rice": "rice",
    "spirit": "spirit",
    "willow": "willow",
}


def fetch_wvic_reservoirs() -> list[dict]:
    """
    Fetch WVIC reservoir levels from the Data & Reports page.
    The page embeds current "feet below maximum" values in a Google Charts
    arrayToDataTable() call, which we extract with regex. No browser needed.
    Falls back gracefully if scraping fails.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Fetch the page and parse the Google Chart data
    parsed_data = {}
    html = fetch_text(WVIC_DATA_URL)
    if html:
        # Look for the arrayToDataTable block with reservoir data rows
        # Pattern matches: ['Reservoir Name', -6.28]
        matches = re.findall(r"\['([^']+)',\s*([-\d.]+)\]", html)
        for name, value in matches:
            slug = WVIC_NAME_MAP.get(name.strip().lower())
            if slug:
                try:
                    parsed_data[slug] = float(value)
                except ValueError:
                    pass

        if parsed_data:
            log.info(f"  Parsed WVIC data for {len(parsed_data)} reservoirs")
        else:
            log.warning("Could not parse WVIC reservoir data from page")
    else:
        log.warning("Failed to fetch WVIC Data & Reports page")

    # Build results for all configured reservoirs
    results = []
    for res in WVIC_RESERVOIRS:
        slug = res["slug"]
        feet_below_max = parsed_data.get(slug)
        results.append({
            "name": res["name"],
            "slug": slug,
            "feet_below_max": feet_below_max,
            "has_data": feet_below_max is not None,
            "source_url": WVIC_DATA_URL,
            "last_updated": now if feet_below_max is not None else None,
        })

    return results


# ---------------------------------------------------------------------------
# Fishing conditions: Weather, Sun, Solunar
# ---------------------------------------------------------------------------

CARDINAL_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def deg_to_cardinal(deg: float) -> str:
    """Convert wind direction degrees to cardinal direction."""
    idx = round(deg / 45) % 8
    return CARDINAL_DIRS[idx]


def fetch_weather_conditions() -> dict:
    """Fetch barometric pressure and wind from Open-Meteo (no API key)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WAUSAU_LAT}&longitude={WAUSAU_LON}"
        f"&hourly=pressure_msl,wind_speed_10m,wind_direction_10m,uv_index"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone=America/Chicago&forecast_days=1&past_days=1"
    )
    data = fetch_json(url)
    if not data:
        return {}

    try:
        hourly = data["hourly"]
        times = hourly["time"]
        pressures = hourly["pressure_msl"]
        winds = hourly["wind_speed_10m"]
        wind_dirs = hourly["wind_direction_10m"]

        # Find the most recent hour with data
        now_str = datetime.now().strftime("%Y-%m-%dT%H:00")
        idx = None
        for i, t in enumerate(times):
            if t <= now_str:
                idx = i

        if idx is None:
            return {}

        pressure = pressures[idx]
        wind_speed = winds[idx]
        wind_dir_deg = wind_dirs[idx]
        uv_values = hourly.get("uv_index", [])
        uv_index = uv_values[idx] if idx < len(uv_values) else None

        # Calculate trend (compare to 3 hours ago)
        trend = "steady"
        if idx >= 3 and pressures[idx - 3] is not None and pressure is not None:
            diff = pressure - pressures[idx - 3]
            if diff > 1:
                trend = "rising"
            elif diff < -1:
                trend = "falling"

        return {
            "pressure_hpa": round(pressure, 1) if pressure else None,
            "pressure_trend": trend,
            "wind_speed_mph": round(wind_speed, 1) if wind_speed else None,
            "wind_direction_deg": round(wind_dir_deg) if wind_dir_deg else None,
            "wind_direction": deg_to_cardinal(wind_dir_deg) if wind_dir_deg else None,
            "uv_index": round(uv_index, 1) if uv_index is not None else None,
        }
    except (KeyError, IndexError, TypeError) as e:
        log.warning(f"Error parsing Open-Meteo data: {e}")
        return {}


def fetch_sun_times() -> dict:
    """Fetch sunrise/sunset from Sunrise-Sunset API (no API key)."""
    url = (
        f"https://api.sunrise-sunset.org/json"
        f"?lat={WAUSAU_LAT}&lng={WAUSAU_LON}&formatted=0&date=today"
    )
    data = fetch_json(url)
    if not data or data.get("status") != "OK":
        return {}

    try:
        results = data["results"]

        def utc_to_local(iso_str):
            """Convert UTC ISO string to Central Time formatted string."""
            # Parse the UTC timestamp
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            # Determine CDT (-5) vs CST (-6) using month heuristic
            # CDT: roughly second Sun in Mar through first Sun in Nov
            month = datetime.now().month
            offset_hours = -5 if 3 <= month <= 10 else -6
            local = dt + timedelta(hours=offset_hours)
            # Format as "H:MM AM/PM"
            hour = local.hour % 12 or 12
            ampm = "AM" if local.hour < 12 else "PM"
            return f"{hour}:{local.minute:02d} {ampm}"

        return {
            "sunrise": utc_to_local(results["sunrise"]),
            "sunset": utc_to_local(results["sunset"]),
            "civil_dawn": utc_to_local(results["civil_twilight_begin"]),
            "civil_dusk": utc_to_local(results["civil_twilight_end"]),
        }
    except (KeyError, ValueError, TypeError) as e:
        log.warning(f"Error parsing sunrise-sunset data: {e}")
        return {}


def fetch_solunar() -> dict:
    """Fetch solunar fishing data (moon phase, feeding periods, rating)."""
    date_str = datetime.now().strftime("%Y%m%d")
    # Determine UTC offset for Central Time
    month = datetime.now().month
    offset = -5 if 3 <= month <= 10 else -6
    url = f"https://api.solunar.org/solunar/{WAUSAU_LAT},{WAUSAU_LON},{date_str},{offset}"
    data = fetch_json(url)
    if not data:
        return {}

    try:
        major_periods = []
        minor_periods = []
        for prefix, dest in [("major", major_periods), ("minor", minor_periods)]:
            for n in [1, 2]:
                start = data.get(f"{prefix}{n}Start")
                stop = data.get(f"{prefix}{n}Stop")
                if start and stop:
                    dest.append({"start": start, "end": stop})

        return {
            "moon_phase": data.get("moonPhase"),
            "day_rating": data.get("dayRating"),
            "major_periods": major_periods,
            "minor_periods": minor_periods,
            "hourly_ratings": data.get("hourlyRating"),
        }
    except (KeyError, TypeError) as e:
        log.warning(f"Error parsing solunar data: {e}")
        return {}


def fetch_weather_forecast() -> list[dict]:
    """Fetch 5-day weather forecast from Open-Meteo (no API key)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WAUSAU_LAT}&longitude={WAUSAU_LON}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
        f"&temperature_unit=fahrenheit&timezone=America/Chicago&forecast_days=5"
    )
    data = fetch_json(url)
    if not data:
        return []

    try:
        daily = data["daily"]
        forecast = []
        for i in range(len(daily["time"])):
            forecast.append({
                "date": daily["time"][i],
                "high_f": round(daily["temperature_2m_max"][i]) if daily["temperature_2m_max"][i] is not None else None,
                "low_f": round(daily["temperature_2m_min"][i]) if daily["temperature_2m_min"][i] is not None else None,
                "precip_pct": daily["precipitation_probability_max"][i],
                "weather_code": daily["weather_code"][i],
            })
        return forecast
    except (KeyError, IndexError, TypeError) as e:
        log.warning(f"Error parsing Open-Meteo forecast: {e}")
        return []


# ---------------------------------------------------------------------------
# Recreation: Flow-based conditions for river activities
# ---------------------------------------------------------------------------

# Flow thresholds (CFS) for recreation activities per gauge
# Only defined for rivers where paddling/tubing is common
RECREATION_THRESHOLDS = {
    "05398000": {  # WI River at Rothschild
        "kayaking": {"ideal": [3000, 10000], "caution": [10000, 17000], "dangerous": 17000},
        "tubing": {"ideal": [3000, 10000], "caution": [10000, 17000], "dangerous": 17000},
    },
    "05398100": {  # WI River at Mosinee
        "kayaking": {"ideal": [3000, 10000], "caution": [10000, 17000], "dangerous": 17000},
        "tubing": {"ideal": [3000, 10000], "caution": [10000, 17000], "dangerous": 17000},
    },
    "05397500": {  # Eau Claire River near Kelly
        "kayaking": {"ideal": [200, 800], "caution": [800, 1500], "dangerous": 1500},
    },
}

# Community engagement links (static)
COMMUNITY_LINKS = {
    "fishing_report_form": "https://forms.gle/YOUR_FORM_ID",
    "photo_hashtag": "#WausauFishing",
    "social_url": "https://facebook.com/wausaupilotandreview",
    "email": "editor@wausaupilotandreview.com",
}


def compute_recreation_status(gauge_id: str, streamflow_cfs: float | None) -> dict | None:
    """Compute recreation conditions based on current flow."""
    thresholds = RECREATION_THRESHOLDS.get(gauge_id)
    if not thresholds or streamflow_cfs is None:
        return None

    result = {}
    for activity, levels in thresholds.items():
        if streamflow_cfs >= levels["dangerous"]:
            result[activity] = "dangerous"
        elif levels["caution"][0] <= streamflow_cfs < levels["caution"][1]:
            result[activity] = "caution"
        elif levels["ideal"][0] <= streamflow_cfs <= levels["ideal"][1]:
            result[activity] = "ideal"
        elif streamflow_cfs < levels["ideal"][0]:
            result[activity] = "low"
        else:
            result[activity] = "caution"
    return result


def estimate_water_clarity(current_cfs: float | None, history: list[dict]) -> dict | None:
    """
    Estimate water clarity based on flow trends.
    Rising flows (especially rapid rises) churn sediment and reduce clarity.
    Stable or falling flows allow sediment to settle = better clarity.
    """
    if current_cfs is None:
        return None

    # Calculate average flow over the past 24-48 hours from history
    recent_flows = [
        h["streamflow_cfs"] for h in history[-48:]
        if h.get("streamflow_cfs") is not None
    ]
    if not recent_flows:
        return None

    avg_flow = sum(recent_flows) / len(recent_flows)
    pct_change = ((current_cfs - avg_flow) / avg_flow * 100) if avg_flow > 0 else 0

    if pct_change > 50:
        return {"rating": "poor", "description": "Rapidly rising flow \u2014 high sediment"}
    elif pct_change > 20:
        return {"rating": "murky", "description": "Rising flow \u2014 reduced visibility"}
    elif pct_change > -5:
        return {"rating": "moderate", "description": "Stable flow \u2014 moderate visibility"}
    elif pct_change > -20:
        return {"rating": "good", "description": "Falling flow \u2014 sediment settling"}
    else:
        return {"rating": "clear", "description": "Low, stable flow \u2014 good visibility"}


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
            "has_temp_sensor": gauge.get("has_temp_sensor", False),
            "nws_flood_category": nws_data.get("nws_flood_category"),
            "current": current,
            "history": history,
            "fishing": FISHING_REFERENCE.get(gauge["id"]),
            "recreation": compute_recreation_status(gauge["id"], current.get("streamflow_cfs")),
            "water_clarity": estimate_water_clarity(current.get("streamflow_cfs"), history),
            "usgs_url": f"https://waterdata.usgs.gov/monitoring-location/USGS-{gauge['id']}/",
            "nws_url": f"https://water.noaa.gov/gauges/{gauge['nws_lid'].lower()}" if gauge.get("nws_lid") else None,
        })

    # Fetch NWS alerts
    log.info("Fetching NWS flood alerts for Marathon County...")
    alerts = fetch_nws_alerts()

    # Fetch WVIC reservoirs
    log.info("Fetching WVIC reservoir data...")
    reservoirs = fetch_wvic_reservoirs()

    # Fetch fishing conditions
    log.info("Fetching fishing conditions...")
    weather = fetch_weather_conditions()
    sun = fetch_sun_times()
    solunar = fetch_solunar()

    fishing_conditions = {
        **weather,
        **sun,
        **solunar,
    } if (weather or sun or solunar) else None

    # Fetch weather forecast
    log.info("Fetching 5-day weather forecast...")
    weather_forecast = fetch_weather_forecast()

    # Assemble output
    output = {
        "generated_at": now,
        "region": "Central Wisconsin \u2014 Marathon County",
        "gauges": gauges_data,
        "alerts": alerts,
        "reservoirs": reservoirs,
        "fishing_conditions": fishing_conditions,
        "weather_forecast": weather_forecast,
        "community_links": COMMUNITY_LINKS,
        "sources": {
            "usgs": "https://waterservices.usgs.gov/",
            "nws": "https://api.weather.gov/",
            "wvic": "https://wvic.com/",
            "open_meteo": "https://open-meteo.com/",
            "solunar": "https://solunar.org/",
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
