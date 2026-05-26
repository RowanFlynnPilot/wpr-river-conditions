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
    {
        "id": "05394500",
        "nws_lid": None,
        "name": "Prairie River near Merrill",
        "short_name": "Prairie River",
        "lat": 45.1894,
        "lon": -89.7120,
        "flood_stages": None,
        "description": "Designated trout stream north of Wausau near Merrill",
        "has_temp_sensor": False,
    },
    {
        "id": "05395000",
        "nws_lid": "RRLW3",
        "name": "Wisconsin River at Merrill",
        "short_name": "WI River — Merrill",
        "lat": 45.1781,
        "lon": -89.6811,
        "flood_stages": {"action": 10.0, "minor": 11.0, "moderate": 13.5, "major": 15.0},
        "description": "Main stem upstream of Wausau — early warning for downstream gauges",
        "has_temp_sensor": False,
    },
    {
        "id": "05400760",
        "nws_lid": "WIRW3",
        "name": "Wisconsin River at Wisconsin Rapids",
        "short_name": "WI River — Wisconsin Rapids",
        "lat": 44.3922,
        "lon": -89.8269,
        "flood_stages": {"action": 10.0, "minor": 12.0, "moderate": 13.5, "major": 14.5},
        "description": "Main stem downstream of Wausau — largest city in the chain",
        "has_temp_sensor": False,
    },
    {
        "id": "04074950",
        "nws_lid": "LGLW3",
        "name": "Wolf River at Langlade",
        "short_name": "Wolf River — Langlade",
        "lat": 45.1900,
        "lon": -88.7333,
        "flood_stages": {"action": 9.5, "minor": 11.5, "moderate": 12.5, "major": 14.0},
        "description": "Iconic Class I trout & whitewater destination northeast of Wausau",
        "has_temp_sensor": False,
    },
    {
        "id": "05400625",
        "nws_lid": None,
        "name": "Little Plover River near Plover",
        "short_name": "Little Plover River",
        "lat": 44.4708,
        "lon": -89.5082,
        "flood_stages": None,
        "description": "Groundwater-fed trout stream near Stevens Point",
        "has_temp_sensor": False,
    },
    {
        "id": "04080798",
        "nws_lid": None,
        "name": "Tomorrow River near Nelsonville",
        "short_name": "Tomorrow River",
        "lat": 44.5240,
        "lon": -89.3380,
        "flood_stages": None,
        "description": "Class I trout stream destination near Stevens Point",
        "has_temp_sensor": False,
    },
]

# USGS parameter codes
PARAM_GAGE_HEIGHT = "00065"   # ft
PARAM_STREAMFLOW = "00060"    # cfs (cubic feet per second)
PARAM_WATER_TEMP = "00010"    # °C
PARAM_PRECIP = "00045"        # inches (incremental precipitation)

# NWS alert zones for Marathon County
NWS_ZONE = "WIC073"  # Marathon County zone code
NWS_COUNTY_FIPS = "055073"

# WVIC reservoirs to track (scraped from wvic.com)
WVIC_RESERVOIRS = [
    {"name": "Rainbow Reservoir", "slug": "rainbow", "description": "Controls upper WI River flow north of Wausau"},
    {"name": "Willow Reservoir", "slug": "willow", "description": "Regulates Willow Creek into the WI River"},
    {"name": "Spirit Reservoir", "slug": "spirit", "description": "Feeds Spirit River \u2014 affects WI River levels"},
    {"name": "Eau Pleine Reservoir", "slug": "eau-pleine", "description": "Directly feeds Big Eau Pleine gauge at Stratford"},
    {"name": "Rice Reservoir", "slug": "rice", "description": "Controls Rice Creek flow into the WI River"},
    {"name": "Lake Wausau", "slug": "lake-wausau", "description": "Run-of-river impoundment in downtown Wausau"},
]

# Wausau area coordinates (used for weather/solunar APIs)
WAUSAU_LAT = 44.886
WAUSAU_LON = -89.622

# Static fishing reference data per gauge (rarely changes)
FISHING_REFERENCE = {
    "05398000": {  # WI River at Rothschild
        "species": ["Walleye", "Smallmouth Bass", "Musky", "Channel Catfish", "Sturgeon"],
        "trout_class": None,
        "tips": {
            "Walleye": "Jigs tipped with minnows near current breaks and dam tailwaters. Best at dawn/dusk. Try 1/4 oz jig heads bounced along sandy bottoms.",
            "Smallmouth Bass": "Crankbaits and tube jigs around rocky shorelines and bridge pilings. Topwater action in summer evenings.",
            "Musky": "Large bucktails and jerkbaits along weed edges and deep structure. Fall is prime \u2014 focus on figure-8s at the boat.",
            "Channel Catfish": "Cut bait or stink bait on the bottom near deeper holes. Night fishing in summer is most productive.",
            "Sturgeon": "Catch-and-release only. Observe from shore during the spring spawning run \u2014 a spectacular sight near Rothschild dam.",
        },
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
        "tips": {
            "Walleye": "Work the Mosinee dam tailrace with jigs and live bait. Current seams hold fish especially in spring.",
            "Smallmouth Bass": "Crawfish-pattern crankbaits and ned rigs along the rocky banks below the dam.",
            "Musky": "Trolling large crankbaits through the deeper pools downstream. Look for baitfish schools on electronics.",
            "Channel Catfish": "Chicken liver or nightcrawlers fished on bottom rigs in the slower pools below the dam.",
        },
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
        "tips": {
            "Brook Trout": "Small spinners (#0\u2013#2 Mepps) and worms in the upper Class I reaches. Wade quietly upstream \u2014 brookies spook easily.",
            "Brown Trout": "Larger streamers and Rapala minnows in the deeper pools. Best fishing is early morning or after dark in summer.",
            "Smallmouth Bass": "Small crankbaits and soft plastics in the lower reaches near Rib Falls. Look for them near log jams.",
        },
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
        "tips": {
            "Brook Trout": "Ultra-light gear with small spinners or live worms. A small, brushy stream \u2014 short casts and stealth are key. Best in spring and early summer.",
        },
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
        "tips": {
            "Smallmouth Bass": "Tube jigs and soft plastic crawfish along rocky runs. The Eau Claire has excellent wade fishing for bronzebacks.",
            "Walleye": "Jig and minnow combos in deeper pools near Kelly dam. Evening and night fishing most productive.",
            "Brown Trout": "Found in the cooler upper reaches. Drift nymphs or swing wet flies through the riffles.",
        },
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
    "05394500": {  # Prairie River near Merrill
        "species": ["Brook Trout", "Brown Trout", "Rainbow Trout"],
        "trout_class": "Class I (designated trout stream)",
        "tips": {
            "Brook Trout": "Small spinners (#0–#2 Mepps) or live worms in the upper reaches. Wade upstream quietly — brookies hold in cold, shaded pools and undercut banks.",
            "Brown Trout": "Streamers and Rapala minnows through the deeper runs. Best early morning or after dark. Dry fly action in summer evenings with caddis and PMD patterns.",
            "Rainbow Trout": "Drift nymphs (hare's ear, pheasant tail) through the riffles. Egg patterns effective in fall. Check DNR stocking reports for timing.",
        },
        "regulations": [
            {"species": "Trout", "rule": 'Category 3: 3 daily bag, 8" min'},
            {"species": "Note", "rule": "Inland trout stamp required"},
        ],
        "season_notes": [
            "Early catch-and-release season opens first Sat in Jan",
            "Harvest season opens first Sat in April (new for 2026)",
            "Regular season first Sat in May",
        ],
        "access_points": [
            {"name": "Prairie River Fishery Area", "directions": "Off Cty Rd K north of Merrill", "lat": 45.1894, "lng": -89.7120},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "05395000": {  # WI River at Merrill
        "species": ["Walleye", "Smallmouth Bass", "Musky", "Channel Catfish"],
        "trout_class": None,
        "tips": {
            "Walleye": "Jigs tipped with minnows in the deeper pools below the Merrill dam. Spring is prime — fish stage here pre-spawn.",
            "Smallmouth Bass": "Tube jigs and ned rigs along the rocky banks above and below the dam.",
            "Musky": "Bucktails and large crankbaits along weed edges in the wider stretches downstream.",
            "Channel Catfish": "Cut bait or nightcrawlers fished on bottom rigs after dark, especially in summer.",
        },
        "regulations": [
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
            {"species": "Musky", "rule": '50" min, 1 daily'},
            {"species": "Bass", "rule": '14" min, 5 daily'},
        ],
        "season_notes": [
            "Walleye/Sauger open first Sat in May",
            "Catch-and-release bass season Mar–Jun",
        ],
        "access_points": [
            {"name": "Merrill Riverside Park", "directions": "East Main St in downtown Merrill", "lat": 45.1810, "lng": -89.6840},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "05400760": {  # WI River at Wisconsin Rapids
        "species": ["Walleye", "Smallmouth Bass", "Musky", "Channel Catfish", "White Bass"],
        "trout_class": None,
        "tips": {
            "Walleye": "Jig and minnow combos in the deep holes near the Wisconsin Rapids dam. Spring walleye run draws anglers from across the state.",
            "Smallmouth Bass": "Tubes and crawfish-pattern crankbaits along the rocky banks — strong smallmouth population.",
            "Musky": "Trolling large crankbaits through the deeper pools and along current breaks downstream of the dam.",
            "Channel Catfish": "Cut bait or chicken liver in the deeper pools below the dam at night.",
            "White Bass": "Small spoons and inline spinners during the spring run — schools of fish stack up below the dam.",
        },
        "regulations": [
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
            {"species": "Musky", "rule": '50" min, 1 daily'},
            {"species": "Bass", "rule": '14" min, 5 daily'},
        ],
        "season_notes": [
            "Walleye/Sauger open first Sat in May",
            "White bass run typically peaks late April–May",
        ],
        "access_points": [
            {"name": "Wisconsin Rapids Boat Landing", "directions": "Riverview Expressway near downtown", "lat": 44.3895, "lng": -89.8175},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "04074950": {  # Wolf River at Langlade
        "species": ["Brown Trout", "Brook Trout", "Smallmouth Bass", "Walleye"],
        "trout_class": "Class I (designated trout stream)",
        "tips": {
            "Brown Trout": "Streamers and Rapala minnows through the deeper runs and pocket water. Best in early morning or evening.",
            "Brook Trout": "Small spinners and dry flies in the upper reaches and feeder streams. The Wolf has a strong native population.",
            "Smallmouth Bass": "Tube jigs and topwater poppers in the slower stretches and pools downstream of the rapids.",
            "Walleye": "Found in the deeper runs and below the rapids — jig and minnow combos work well.",
        },
        "regulations": [
            {"species": "Trout", "rule": "Category 3 in most reaches; check DNR maps for special regs"},
            {"species": "Bass", "rule": '14" min, 5 daily'},
            {"species": "Walleye", "rule": '15" min, 5 daily bag'},
        ],
        "season_notes": [
            "Early catch-and-release trout opens first Sat in Jan",
            "Famous whitewater paddling section — exercise caution at high flows",
        ],
        "access_points": [
            {"name": "Langlade Boat Landing", "directions": "Off Hwy 55 in Langlade", "lat": 45.1900, "lng": -88.7333},
            {"name": "Wolf River State Wildlife Area", "directions": "Multiple access points along Hwy 55", "lat": 45.1750, "lng": -88.7400},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Lands/WolfRiver",
    },
    "05400625": {  # Little Plover River near Plover
        "species": ["Brook Trout", "Brown Trout"],
        "trout_class": "Class II",
        "tips": {
            "Brook Trout": "Ultra-light gear with small spinners or live worms. Sensitive groundwater-fed stream — wade quietly and limit your impact.",
            "Brown Trout": "Drift small nymphs through the deeper holes. Browns hold tight to undercut banks and woody cover.",
        },
        "regulations": [
            {"species": "Trout", "rule": 'Category 3: 3 daily bag, 8" min'},
        ],
        "season_notes": [
            "Early catch-and-release trout opens first Sat in Jan",
            "Regular season first Sat in May",
            "Famously sensitive to drought — flows can drop dramatically in summer",
        ],
        "access_points": [
            {"name": "Springville Pond Access", "directions": "Off Cty Rd HH in Plover", "lat": 44.4708, "lng": -89.5082},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Fishing",
    },
    "04080798": {  # Tomorrow River near Nelsonville
        "species": ["Brown Trout", "Brook Trout"],
        "trout_class": "Class I (designated trout stream)",
        "tips": {
            "Brown Trout": "One of central Wisconsin's premier brown trout streams. Drift hopper-dropper rigs through the riffles, or fish streamers in the deeper runs at dawn and dusk.",
            "Brook Trout": "Small Mepps spinners or dry flies in the upper reaches. Native population — handle with care if releasing.",
        },
        "regulations": [
            {"species": "Trout", "rule": 'Category 3: 3 daily bag, 8" min'},
            {"species": "Note", "rule": "Some sections have artificial-lure-only and special length regs — check DNR maps"},
        ],
        "season_notes": [
            "Early catch-and-release trout opens first Sat in Jan",
            "Regular season first Sat in May",
            "Best fishing typically May through early July before water warms",
        ],
        "access_points": [
            {"name": "Tomorrow River State Trail Access", "directions": "Off Cty Rd A near Nelsonville", "lat": 44.5240, "lng": -89.3380},
        ],
        "dnr_url": "https://dnr.wisconsin.gov/topic/Lands/FisheriesAreas",
    },
    "05399500": {  # Big Eau Pleine at Stratford
        "species": ["Walleye", "Northern Pike", "Panfish", "Largemouth Bass"],
        "trout_class": None,
        "tips": {
            "Walleye": "Jig and minnow near the reservoir inlet in spring. Troll crankbaits along drop-offs in summer.",
            "Northern Pike": "Spinnerbaits and large spoons along weed edges. Spring pike stack up near creek inlets after ice-out.",
            "Panfish": "Small jigs tipped with wax worms near submerged timber. Excellent ice fishing for crappie and bluegill in winter.",
            "Largemouth Bass": "Texas-rigged soft plastics and spinnerbaits around fallen trees and lily pad edges in summer.",
        },
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

# Upcoming local events — manually updated as events are announced
# To add an event: append a dict with date, name, description, location, url
# To remove: delete the dict. Events with past dates are auto-filtered out.
LOCAL_EVENTS = [
    {
        "date": "2026-04-04",
        "name": "Inland Trout Harvest Opener",
        "description": "NEW for 2026 \u2014 harvest season opens a full month earlier than prior years. Streams, springs, and spring ponds. Requires inland trout stamp.",
        "location": "Statewide",
        "category": "season",
        "url": "https://wausaupilotandreview.com/2026/03/18/dnr-reminds-anglers-of-new-opening-day-for-inland-trout-harvest-season/",
    },
    {
        "date": "2026-05-01",
        "name": "Governor's Fishing Opener",
        "description": "Annual tradition since 1966. Family Fishing Day on May 2 at Lake Hayward Beach with casting lessons, DNR Fishmobile, and giveaways.",
        "location": "Nelson Lake, Hayward",
        "category": "event",
        "url": None,
    },
    {
        "date": "2026-05-02",
        "name": "General Inland Fishing Opener",
        "description": "Walleye, bass (harvest), northern pike, and musky all open statewide. Musky opener now unified to May 2 (previously Memorial Day weekend for northern zone).",
        "location": "Statewide",
        "category": "season",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/seasons",
    },
    {
        "date": "2026-05-02",
        "name": "Lake & Pond Trout Season Opens",
        "description": "Trout season on inland lakes and ponds. The earlier April 4 opener applies only to streams and springs.",
        "location": "Statewide",
        "category": "season",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/seasons",
    },
    {
        "date": "2026-06-06",
        "name": "Free Fishing Weekend",
        "description": "June 6\u20137. No license, trout stamp, or salmon stamp required for residents or nonresidents. All bag/size limits still apply. Great for families!",
        "location": "Statewide",
        "category": "event",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/anglereducation/freeFishingWeekend",
    },
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
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError, OSError) as e:
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
    except (URLError, HTTPError, TimeoutError, OSError) as e:
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
    params = f"{PARAM_GAGE_HEIGHT},{PARAM_STREAMFLOW},{PARAM_WATER_TEMP},{PARAM_PRECIP}"
    # period=P1D so precip can be summed over the past 24h
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?format=json&sites={site}&parameterCd={params}&period=P1D&siteStatus=all"
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

            # Precip is incremental — sum the last 24h to get a rolling total
            if var_code == PARAM_PRECIP:
                total = 0.0
                has_data = False
                for v in values:
                    raw = v.get("value", "")
                    if raw == "":
                        continue
                    try:
                        x = float(raw)
                    except ValueError:
                        continue
                    if x < 0:  # USGS sentinel for missing
                        continue
                    total += x
                    has_data = True
                if has_data:
                    result["precip_24h_in"] = round(total, 2)
                continue

            # For all other params, take the latest reading
            latest = values[-1]
            val = float(latest["value"]) if latest["value"] != "" else None
            if val is not None and val < 0:
                val = None

            if var_code == PARAM_GAGE_HEIGHT:
                result["gage_height_ft"] = round(val, 2) if val else None
            elif var_code == PARAM_STREAMFLOW:
                result["streamflow_cfs"] = round(val, 1) if val else None
            elif var_code == PARAM_WATER_TEMP:
                result["water_temp_f"] = round(val * 9 / 5 + 32, 1) if val else None
                result["water_temp_c"] = round(val, 1) if val else None

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
    Fetch active outdoor-relevant alerts from the NWS API for Marathon County.
    Includes flood, severe weather, fire weather, winter, and wind events —
    anything an outdoor or floodplain audience would want to know about.
    Returns: [{event, category, headline, severity, description, onset, expires, url}, ...]
    """
    url = f"https://api.weather.gov/alerts/active?zone={NWS_ZONE}"
    data = fetch_json(url)
    if not data:
        return []

    # Map keywords → category for frontend styling
    CATEGORY_RULES = [
        ("flood", ["flood", "flash flood", "river", "hydrologic"]),
        ("severe", ["tornado", "severe thunderstorm", "severe weather"]),
        ("winter", ["winter storm", "blizzard", "ice storm", "winter weather", "freeze", "frost"]),
        ("fire", ["red flag", "fire weather"]),
        ("wind", ["wind", "gale"]),
        ("heat", ["heat", "excessive heat"]),
    ]

    def categorize(event_lower: str) -> str | None:
        for category, kws in CATEGORY_RULES:
            if any(kw in event_lower for kw in kws):
                return category
        return None

    alerts = []
    try:
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            event = (props.get("event") or "").lower()
            category = categorize(event)
            if category is None:
                continue

            alerts.append({
                "event": props.get("event"),
                "category": category,
                "headline": props.get("headline"),
                "severity": props.get("severity"),
                "urgency": props.get("urgency"),
                "description": props.get("description", "")[:500],
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


def fetch_nws_forecast(nws_lid: str) -> dict | None:
    """
    Fetch the NWS forecast hydrograph for a gauge. NWS only publishes
    forecasts when flooding is active or imminent — most days this
    returns an empty array, which we render as None.

    Returns: {peak_stage, peak_time, issued_time, units, points} or None
    """
    if not nws_lid:
        return None

    url = f"https://api.water.noaa.gov/nwps/v1/gauges/{nws_lid}/stageflow/forecast"
    data = fetch_json(url)
    if not data:
        return None

    points = data.get("data") or []
    if not points:
        return None

    # Find the peak stage in the forecast
    try:
        valid_points = [p for p in points if p.get("primary") is not None]
        if not valid_points:
            return None
        peak = max(valid_points, key=lambda p: p["primary"])
        return {
            "peak_stage": round(float(peak["primary"]), 2),
            "peak_time": peak.get("validTime"),
            "issued_time": data.get("issuedTime"),
            "units": data.get("primaryUnits") or "ft",
            "points": [
                {"time": p.get("validTime"), "stage": p.get("primary")}
                for p in valid_points
            ],
        }
    except (KeyError, TypeError, ValueError) as e:
        log.warning(f"Error parsing NWS forecast for {nws_lid}: {e}")
        return None


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
            "description": res.get("description", ""),
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


def _nws_get(url: str) -> dict | None:
    """NWS API requires User-Agent + accepts the geo+json content type."""
    headers = {
        "User-Agent": "WPR-RiverConditions/1.0 (wausaupilotandreview.com)",
        "Accept": "application/geo+json",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError, OSError) as e:
        log.warning(f"NWS fetch failed for {url}: {e}")
        return None
    except Exception as e:
        # Last-ditch safety net so a transient network blip never crashes the
        # whole scraper run on GitHub Actions.
        log.warning(f"NWS fetch unexpected error for {url}: {type(e).__name__}: {e}")
        return None


def fetch_open_meteo_uv() -> float | None:
    """Best-effort UV index from Open-Meteo. Returns None on failure."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WAUSAU_LAT}&longitude={WAUSAU_LON}"
        f"&hourly=uv_index&timezone=America/Chicago&forecast_days=1"
    )
    data = fetch_json(url)
    if not data:
        return None
    try:
        hourly = data["hourly"]
        times = hourly["time"]
        uvs = hourly.get("uv_index", [])
        now_str = datetime.now().strftime("%Y-%m-%dT%H:00")
        idx = None
        for i, t in enumerate(times):
            if t <= now_str:
                idx = i
        if idx is not None and 0 <= idx < len(uvs) and uvs[idx] is not None:
            return round(uvs[idx], 1)
    except (KeyError, IndexError, TypeError):
        pass
    return None


def fetch_weather_conditions() -> dict:
    """
    Fetch current observed weather from NWS (api.weather.gov). The .gov
    backbone is the most reliable free source available — we already
    use it for flood data, so this consolidates dependencies.

    Returns: pressure, pressure trend (computed from recent obs history),
    wind speed/direction. UV is attempted via Open-Meteo as an optional
    enrichment; absence does not fail the function.
    """
    # 1. Resolve gridpoint → list of nearby observation stations
    pt = _nws_get(f"https://api.weather.gov/points/{WAUSAU_LAT},{WAUSAU_LON}")
    if not pt:
        return {}
    stations_url = (pt.get("properties") or {}).get("observationStations")
    if not stations_url:
        return {}

    stations = _nws_get(stations_url)
    if not stations:
        return {}

    candidates = [
        s["properties"]["stationIdentifier"]
        for s in stations.get("features", [])[:3]
        if (s.get("properties") or {}).get("stationIdentifier")
    ]

    # 2. Try each station in order until one returns usable observations.
    #    Pulling ~12 records gives us a window for the 3-hour pressure trend.
    result = {}
    for stid in candidates:
        obs_list = _nws_get(
            f"https://api.weather.gov/stations/{stid}/observations?limit=12"
        )
        if not obs_list or not obs_list.get("features"):
            continue

        # Find latest observation with non-null pressure + wind values
        latest = None
        for f in obs_list["features"]:
            p = f.get("properties") or {}
            bp = (p.get("barometricPressure") or {}).get("value")
            ws = (p.get("windSpeed") or {}).get("value")
            if bp is not None and ws is not None:
                latest = p
                break
        if not latest:
            continue

        bp_pa = (latest.get("barometricPressure") or {}).get("value")
        # Pa → hPa (mb)
        pressure_hpa = round(bp_pa / 100, 1) if bp_pa else None

        wind_kmh = (latest.get("windSpeed") or {}).get("value")
        wind_mph = round(wind_kmh * 0.621371, 1) if wind_kmh is not None else None

        wind_dir_deg = (latest.get("windDirection") or {}).get("value")
        wind_dir = deg_to_cardinal(wind_dir_deg) if wind_dir_deg is not None else None

        # 3. Pressure trend: compare to obs ~3 hours older.
        trend = "steady"
        try:
            latest_ts = datetime.fromisoformat(
                latest["timestamp"].replace("Z", "+00:00")
            )
            threshold = latest_ts - timedelta(hours=3)
            older_bp_hpa = None
            for f in obs_list["features"]:
                p = f.get("properties") or {}
                ts_str = p.get("timestamp")
                bp = (p.get("barometricPressure") or {}).get("value")
                if not ts_str or bp is None:
                    continue
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts <= threshold:
                    older_bp_hpa = bp / 100
                    break
            if older_bp_hpa is not None and pressure_hpa is not None:
                diff = pressure_hpa - older_bp_hpa
                if diff > 1.0:
                    trend = "rising"
                elif diff < -1.0:
                    trend = "falling"
        except (KeyError, ValueError, TypeError):
            pass

        result = {
            "pressure_hpa": pressure_hpa,
            "pressure_trend": trend,
            "wind_speed_mph": wind_mph,
            "wind_direction_deg": round(wind_dir_deg) if wind_dir_deg is not None else None,
            "wind_direction": wind_dir,
            "observation_station": stid,
        }
        break

    # 4. Best-effort UV from Open-Meteo (optional; NWS doesn't publish UV).
    uv = fetch_open_meteo_uv()
    if uv is not None:
        result["uv_index"] = uv

    return result


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


def _parse_usno_time(s: str) -> str | None:
    """USNO returns times like '17:12  DT' or '22:43  ST'. Return 'HH:MM'."""
    if not s:
        return None
    return s.strip().split()[0]


def _hhmm_to_min(s: str) -> int | None:
    if not s:
        return None
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _min_to_hhmm(mins: int) -> str:
    mins = mins % 1440
    return f"{mins // 60:02d}:{mins % 60:02d}"


def fetch_solunar() -> dict:
    """
    Build solunar fishing data from USNO Naval Observatory.

    USNO supplies: sunrise/sunset, moonrise/moonset, moon upper transit,
    current moon phase name, fraction illuminated.

    From those we derive:
      - major feeding periods (~2 hr each, centered on moon upper + lower transit)
      - minor feeding periods (~1 hr each, centered on moonrise + moonset)
      - day rating (1-10, based on moon-phase strength — strongest at new/full)

    The legacy solunar.org API used to provide these directly but has
    been offline; this computes them locally so the widget keeps working.
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    # Central Time offset (CDT vs CST by month heuristic)
    offset = -5 if 3 <= now.month <= 10 else -6
    is_dst = "true" if 3 <= now.month <= 10 else "false"

    url = (
        f"https://aa.usno.navy.mil/api/rstt/oneday"
        f"?date={date_str}&coords={WAUSAU_LAT},{WAUSAU_LON}"
        f"&tz={offset}&dst={is_dst}"
    )
    data = fetch_json(url)
    if not data:
        return {}

    try:
        props = (data.get("properties") or {}).get("data") or {}
        moondata = props.get("moondata") or []
        sundata = props.get("sundata") or []
        moon_phase = props.get("curphase")
        fracillum = props.get("fracillum") or "0%"

        # Parse fracillum "81%" → 81
        try:
            fpct = float(fracillum.rstrip("%"))
        except ValueError:
            fpct = 50.0

        # Day rating: stronger near new (0%) and full (100%) moon
        # Distance from either extreme determines strength
        dist = min(fpct, 100 - fpct)  # 0 (full/new) to 50 (quarter)
        if dist < 5:
            rating = 10
        elif dist < 12:
            rating = 8
        elif dist < 22:
            rating = 7
        elif dist < 35:
            rating = 5
        else:
            rating = 4

        # Extract event times by phenomenon
        moon_events = {e["phen"]: _parse_usno_time(e.get("time", "")) for e in moondata}
        moonrise = moon_events.get("Rise")
        moonset = moon_events.get("Set")
        upper_transit = moon_events.get("Upper Transit")
        lower_transit = moon_events.get("Lower Transit")

        # Compute lower transit if missing (12h offset from upper)
        if upper_transit and not lower_transit:
            u_min = _hhmm_to_min(upper_transit)
            if u_min is not None:
                lower_transit = _min_to_hhmm(u_min + 720)

        # Build period helpers
        def period_around(time_str, half_window_min):
            mins = _hhmm_to_min(time_str)
            if mins is None:
                return None
            return {
                "start": _min_to_hhmm(mins - half_window_min),
                "end": _min_to_hhmm(mins + half_window_min),
            }

        # Major: 2-hr windows around upper + lower transit
        major_periods = []
        for t in [upper_transit, lower_transit]:
            p = period_around(t, 60)
            if p:
                major_periods.append(p)

        # Minor: 1-hr windows around moonrise + moonset
        minor_periods = []
        for t in [moonrise, moonset]:
            p = period_around(t, 30)
            if p:
                minor_periods.append(p)

        return {
            "moon_phase": moon_phase,
            "moon_illumination_pct": round(fpct),
            "day_rating": rating,
            "major_periods": major_periods,
            "minor_periods": minor_periods,
        }
    except (KeyError, TypeError) as e:
        log.warning(f"Error parsing USNO data: {e}")
        return {}


def _nws_icon_to_code(icon_url: str) -> int:
    """
    Map an NWS icon URL like ".../icons/land/day/tsra_hi,30?size=medium"
    to a numeric weather code compatible with the frontend's existing
    WMO-style code mapping (used by Open-Meteo previously).
    """
    if not icon_url:
        return 3
    try:
        # Extract the condition slug — strip path, query, and optional %-suffix
        cond = icon_url.split("/icons/land/")[1].split("/")[1]
        cond = cond.split("?")[0].split(",")[0]
    except (IndexError, AttributeError):
        return 3

    MAPPING = {
        # Sky cover
        "skc": 0, "few": 1, "sct": 2, "bkn": 3, "ovc": 3,
        "wind_skc": 0, "wind_few": 1, "wind_sct": 2, "wind_bkn": 3, "wind_ovc": 3,
        # Precip
        "rain": 63, "rain_showers": 80, "rain_showers_hi": 80,
        "snow": 73, "rain_snow": 67, "rain_sleet": 67, "snow_sleet": 67,
        "fzra": 67, "rain_fzra": 67, "snow_fzra": 67, "sleet": 67,
        "blizzard": 73,
        # Storms
        "tsra": 95, "tsra_sct": 95, "tsra_hi": 95,
        "tornado": 95, "hurricane": 95, "tropical_storm": 95,
        # Visibility
        "dust": 45, "smoke": 45, "haze": 45, "fog": 45,
        # Misc
        "hot": 0, "cold": 0,
    }
    return MAPPING.get(cond, 3)


def fetch_weather_forecast() -> list[dict]:
    """
    5-day forecast from NWS api.weather.gov. NWS returns day/night
    period pairs which we collapse into one row per calendar day with
    high (daytime temp), low (nighttime temp), max precip probability,
    and a weather code derived from the daytime icon.
    """
    pt = _nws_get(f"https://api.weather.gov/points/{WAUSAU_LAT},{WAUSAU_LON}")
    if not pt:
        return []

    forecast_url = (pt.get("properties") or {}).get("forecast")
    if not forecast_url:
        return []

    fc = _nws_get(forecast_url)
    if not fc:
        return []

    periods = (fc.get("properties") or {}).get("periods") or []
    if not periods:
        return []

    # Group by calendar date
    by_date: dict[str, dict] = {}
    for p in periods:
        start = p.get("startTime", "")[:10]
        if not start:
            continue

        if start not in by_date:
            by_date[start] = {
                "date": start,
                "high_f": None,
                "low_f": None,
                "precip_pct": 0,
                "weather_code": None,
            }
        bucket = by_date[start]

        temp = p.get("temperature")
        precip_obj = p.get("probabilityOfPrecipitation") or {}
        precip = precip_obj.get("value") or 0
        is_day = p.get("isDaytime", True)
        icon = p.get("icon") or ""

        if is_day:
            bucket["high_f"] = temp
            bucket["weather_code"] = _nws_icon_to_code(icon)
        else:
            bucket["low_f"] = temp
            # Use night icon only if no daytime code was seen (first day after dark)
            if bucket["weather_code"] is None:
                bucket["weather_code"] = _nws_icon_to_code(icon)

        if precip is not None:
            bucket["precip_pct"] = max(bucket["precip_pct"] or 0, precip)

    # Sort by date, take first 5
    days = sorted(by_date.values(), key=lambda d: d["date"])[:5]
    # Ensure weather_code is never None for the renderer
    for d in days:
        if d["weather_code"] is None:
            d["weather_code"] = 3
    return days


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

# ---------------------------------------------------------------------------
# Lure suggestions: species + month + water temp → 2-3 picks per gauge
# ---------------------------------------------------------------------------

LURE_DATABASE = {
    "Walleye": [
        {"lure": "Jig + minnow", "months": [3, 4, 5, 10, 11], "temp_range": [35, 55], "why": "Cold-water staple — slow presentation near current breaks"},
        {"lure": "Shad Rap crankbait (size 5)", "months": [5, 6, 7, 8, 9], "temp_range": [55, 75], "why": "Cover water and find active fish on drop-offs"},
        {"lure": "Jig + nightcrawler harness", "months": [6, 7, 8], "temp_range": [65, 80], "why": "Slow troll over sandbars in summer warmth"},
        {"lure": "Glow jig (night fishing)", "months": [6, 7, 8, 9], "temp_range": [60, 80], "why": "After-dark peak below dam tailwaters"},
    ],
    "Smallmouth Bass": [
        {"lure": "Tube jig (green pumpkin)", "months": [5, 6, 7, 8, 9, 10], "temp_range": [55, 80], "why": "Rocky-bank standby — drag it slowly"},
        {"lure": "Crawfish crankbait", "months": [5, 6, 7, 8, 9], "temp_range": [60, 80], "why": "Match the forage along riprap and bridge pilings"},
        {"lure": "Topwater popper (dawn/dusk)", "months": [6, 7, 8], "temp_range": [65, 80], "why": "Explosive strikes in low light when water is warm"},
        {"lure": "Ned rig (3-inch)", "months": [4, 5, 9, 10], "temp_range": [50, 65], "why": "Finesse approach for pressured or cool-water bass"},
    ],
    "Musky": [
        {"lure": "Size 9 bucktail (black/orange)", "months": [5, 6, 7], "temp_range": [55, 75], "why": "Cover early-season weed edges fast"},
        {"lure": "Glide bait (slow retrieve)", "months": [9, 10, 11], "temp_range": [45, 65], "why": "Fall prime time — slower presentation triggers giants"},
        {"lure": "Topwater (Pacemaker, Hawg Wobbler)", "months": [6, 7, 8], "temp_range": [65, 80], "why": "Calm summer mornings or evenings"},
    ],
    "Brook Trout": [
        {"lure": "#0 Mepps spinner (gold)", "months": [4, 5, 6, 9, 10], "temp_range": [45, 65], "why": "Short casts in small streams — brookies hammer it"},
        {"lure": "Live worm + split-shot", "months": [4, 5, 6, 7, 8, 9], "temp_range": [45, 70], "why": "Classic drift through undercut banks"},
        {"lure": "Dry fly (Adams, Elk Hair Caddis)", "months": [5, 6, 7, 8], "temp_range": [55, 70], "why": "Match summer hatches on the water surface"},
    ],
    "Brown Trout": [
        {"lure": "Woolly Bugger streamer (black)", "months": [4, 5, 9, 10, 11], "temp_range": [40, 60], "why": "Browns hunt big — strip through deep pools"},
        {"lure": "#5 Rapala (black/gold)", "months": [4, 5, 6, 9, 10], "temp_range": [45, 65], "why": "After-dark prowler in summer pools"},
        {"lure": "Dry fly (PMD, Caddis)", "months": [5, 6, 7, 8], "temp_range": [55, 68], "why": "Evening hatches on cool summer water"},
    ],
    "Rainbow Trout": [
        {"lure": "Hare's ear nymph", "months": [4, 5, 6, 7, 8, 9, 10], "temp_range": [45, 68], "why": "Subsurface workhorse — drift through riffles"},
        {"lure": "Egg pattern", "months": [9, 10, 11], "temp_range": [40, 55], "why": "Fall spawn — drift downstream of redds"},
        {"lure": "Pheasant tail nymph", "months": [4, 5, 6, 9, 10], "temp_range": [45, 65], "why": "Mimic mayfly nymphs in pocket water"},
    ],
    "Northern Pike": [
        {"lure": "Daredevle spoon (red/white)", "months": [4, 5, 9, 10, 11], "temp_range": [40, 60], "why": "Spring and fall pike crush a flashy spoon"},
        {"lure": "Spinnerbait (white, 3/8 oz)", "months": [5, 6, 7, 8, 9], "temp_range": [55, 75], "why": "Cover weed edges — pike ambush from cover"},
        {"lure": "Swimbait (4–6 inch)", "months": [6, 7, 8], "temp_range": [60, 75], "why": "Summer pike chase bigger meals in cooler depths"},
    ],
    "Panfish": [
        {"lure": "Tungsten jig + waxworm", "months": [1, 2, 3, 4, 11, 12], "temp_range": [32, 55], "why": "Cold-water bluegill and crappie — ice or open water"},
        {"lure": "Slip bobber + minnow", "months": [4, 5, 6, 9, 10], "temp_range": [45, 70], "why": "Crappie schools near brush in spring and fall"},
        {"lure": "#0 inline spinner", "months": [5, 6, 7, 8], "temp_range": [60, 75], "why": "Aggressive bluegill on spawning beds"},
    ],
    "Largemouth Bass": [
        {"lure": "Texas-rigged worm", "months": [5, 6, 7, 8, 9], "temp_range": [60, 80], "why": "Pitch into lily pads and laydowns"},
        {"lure": "Spinnerbait", "months": [4, 5, 6, 9, 10], "temp_range": [55, 75], "why": "Search lure for active fish along weed edges"},
        {"lure": "Topwater frog", "months": [6, 7, 8], "temp_range": [65, 80], "why": "Pad fields explode on a slow-walked frog"},
    ],
    "Channel Catfish": [
        {"lure": "Cut bait on bottom rig", "months": [5, 6, 7, 8, 9, 10], "temp_range": [55, 80], "why": "Stinky bait in deep holes — especially after dark"},
        {"lure": "Chicken liver", "months": [5, 6, 7, 8, 9], "temp_range": [60, 80], "why": "Classic catfish offering below dam tailwaters"},
    ],
    "Sturgeon": [
        {"lure": "Catch-and-release viewing only", "months": [4, 5], "temp_range": [40, 60], "why": "Spawning run — watch from shore at Rothschild dam"},
    ],
    "White Bass": [
        {"lure": "Small spoon (white/chrome)", "months": [4, 5, 6], "temp_range": [50, 65], "why": "Spring run below dams — schools push baitfish to the surface"},
        {"lure": "Inline spinner (#2 silver)", "months": [4, 5, 6, 7], "temp_range": [50, 70], "why": "Cast into current breaks where schools stage"},
    ],
}

# Fallback monthly water temps for central Wisconsin (°F) when no sensor reading
SEASONAL_WATER_TEMP_F = {
    1: 33, 2: 33, 3: 36, 4: 45, 5: 58, 6: 68,
    7: 74, 8: 73, 9: 65, 10: 53, 11: 42, 12: 35,
}


def compute_lure_suggestions(gauge_record: dict, current_temp_f: float | None, month: int) -> list[dict]:
    """
    Pick up to 3 lure recommendations for this gauge given current
    water temp (or seasonal fallback) and month. Returns one suggestion
    per species, ordered by best fit.
    """
    fishing = gauge_record.get("fishing") or {}
    species_list = fishing.get("species") or []
    if not species_list:
        return []

    if current_temp_f is None:
        current_temp_f = SEASONAL_WATER_TEMP_F.get(month, 50)

    candidates = []
    for species in species_list:
        for entry in LURE_DATABASE.get(species, []):
            in_season = month in entry["months"]
            t_low, t_high = entry["temp_range"]
            temp_ok = t_low <= current_temp_f <= t_high
            score = (2 if in_season else 0) + (2 if temp_ok else 0)
            if score == 0:
                continue
            candidates.append({
                "species": species,
                "lure": entry["lure"],
                "why": entry["why"],
                "score": score,
            })

    candidates.sort(key=lambda x: -x["score"])
    seen, top = set(), []
    for c in candidates:
        if c["species"] in seen:
            continue
        seen.add(c["species"])
        top.append({"species": c["species"], "lure": c["lure"], "why": c["why"]})
        if len(top) >= 3:
            break
    return top


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


def compute_best_fishing_time(fishing_conditions: dict) -> dict | None:
    """
    Determine the best fishing window today by combining solunar major
    periods with sunrise/sunset to find the best daylight feeding window.
    """
    if not fishing_conditions:
        return None

    sunrise = fishing_conditions.get("sunrise")
    sunset = fishing_conditions.get("sunset")
    major_periods = fishing_conditions.get("major_periods", [])
    minor_periods = fishing_conditions.get("minor_periods", [])
    pressure_trend = fishing_conditions.get("pressure_trend")
    day_rating = fishing_conditions.get("day_rating")

    if not major_periods and not minor_periods:
        return None

    def time_to_minutes(t_str):
        """Convert 'H:MM AM/PM' or 'HH:MM' to minutes since midnight."""
        if not t_str:
            return None
        t_str = t_str.strip()
        try:
            if "AM" in t_str or "PM" in t_str:
                parts = t_str.replace("AM", "").replace("PM", "").strip().split(":")
                h, m = int(parts[0]), int(parts[1])
                if "PM" in t_str and h != 12:
                    h += 12
                if "AM" in t_str and h == 12:
                    h = 0
                return h * 60 + m
            else:
                parts = t_str.split(":")
                return int(parts[0]) * 60 + int(parts[1])
        except (ValueError, IndexError):
            return None

    sunrise_min = time_to_minutes(sunrise) or 360  # default 6am
    sunset_min = time_to_minutes(sunset) or 1140   # default 7pm

    # Score each period: major periods get higher base score
    best = None
    best_score = -1

    all_periods = [(p, "major") for p in major_periods] + [(p, "minor") for p in minor_periods]

    for period, ptype in all_periods:
        start_min = time_to_minutes(period.get("start"))
        end_min = time_to_minutes(period.get("end"))
        if start_min is None or end_min is None:
            continue

        # Handle overnight periods
        if end_min < start_min:
            end_min += 1440

        mid = (start_min + end_min) / 2

        # Score: base points for type
        score = 10 if ptype == "major" else 5

        # Bonus for daylight hours
        if sunrise_min <= mid <= sunset_min:
            score += 5

        # Bonus for dawn/dusk (golden hours)
        if abs(mid - sunrise_min) < 90 or abs(mid - sunset_min) < 90:
            score += 3

        # Bonus for falling pressure
        if pressure_trend == "falling":
            score += 2

        if score > best_score:
            best_score = score
            best = {
                "start": period["start"],
                "end": period["end"],
                "type": ptype,
                "score": score,
            }

    if not best:
        return None

    # Generate recommendation text
    qualifiers = []
    if pressure_trend == "falling":
        qualifiers.append("falling barometer")
    if day_rating and day_rating >= 7:
        qualifiers.append("strong solunar activity")

    reason = ""
    if qualifiers:
        reason = f" ({', '.join(qualifiers)})"

    return {
        "start": best["start"],
        "end": best["end"],
        "type": best["type"],
        "reason": reason,
    }


# Seasonal fish activity by month (central Wisconsin)
SEASONAL_CALENDAR = {
    1:  {"label": "January",   "activity": ["Ice fishing for panfish & walleye", "Early catch-and-release trout season opens", "Target crappie in deep basin areas"]},
    2:  {"label": "February",  "activity": ["Late ice fishing \u2014 panfish remain active", "Walleye start moving shallower under ice", "Scout open-water spots for early spring"]},
    3:  {"label": "March",     "activity": ["Ice-out approaching \u2014 use caution on ice", "Walleye pre-spawn staging in river mouths", "Suckers running \u2014 good live bait source"]},
    4:  {"label": "April",     "activity": ["Walleye spawning run in the WI River", "Smallmouth bass moving to shallow gravel", "Trout stocking by DNR in area streams"]},
    5:  {"label": "May",       "activity": ["General fishing opener first Saturday", "Walleye & bass seasons open", "Musky opener \u2014 try big bucktails"]},
    6:  {"label": "June",      "activity": ["Topwater bass fishing peaks", "Musky active on weed edges", "Mayfly hatches on trout streams"]},
    7:  {"label": "July",      "activity": ["Early morning & evening best \u2014 fish go deep midday", "Catfish active at night on the WI River", "Panfish on beds in reservoir shallows"]},
    8:  {"label": "August",    "activity": ["Smallmouth bass schooling on river sandbars", "Night fishing for walleye and catfish", "Trout in spring-fed streams seeking cold water"]},
    9:  {"label": "September", "activity": ["Fall musky season begins \u2014 prime time", "Walleye transition to fall patterns", "Cooling water temps improve all fishing"]},
    10: {"label": "October",   "activity": ["Peak musky fishing \u2014 figure-8s at the boat", "Walleye stacking up near dam tailwaters", "Brown trout spawning run in tributaries"]},
    11: {"label": "November",  "activity": ["Late fall walleye in deep holes", "First ice forming \u2014 do NOT venture out yet", "Musky season closing \u2014 last chance"]},
    12: {"label": "December",  "activity": ["Early ice fishing when safe (4\"+ clear ice)", "Panfish in deep weed edges", "Walleye in basin areas of reservoirs"]},
}


def compute_conditions_summary(gauges_data: list[dict]) -> list[str]:
    """
    Auto-generate a narrative summary of recent conditions based on
    flow trends across all gauges.
    """
    summaries = []

    # Analyze flow trends across reporting gauges
    rising = []
    falling = []
    stable = []
    flood_alerts = []

    for g in gauges_data:
        name = g["short_name"]
        current_cfs = g["current"].get("streamflow_cfs")
        history = g.get("history", [])
        status = g.get("flood_status", "normal")

        if status in ("minor", "moderate", "major"):
            flood_alerts.append(f"{name} at {status} flood stage")

        if current_cfs is None or len(history) < 24:
            continue

        # Compare current to 24h ago
        old_flows = [h["streamflow_cfs"] for h in history[:24] if h.get("streamflow_cfs")]
        if not old_flows:
            continue

        avg_24h_ago = sum(old_flows) / len(old_flows)
        pct = ((current_cfs - avg_24h_ago) / avg_24h_ago * 100) if avg_24h_ago > 0 else 0

        if pct > 15:
            rising.append((name, round(pct)))
        elif pct < -15:
            falling.append((name, round(abs(pct))))
        else:
            stable.append(name)

    # Build summary sentences
    if flood_alerts:
        summaries.append("\u26a0\ufe0f " + "; ".join(flood_alerts) + ".")

    if rising:
        parts = [f"{n} (+{p}%)" for n, p in rising]
        summaries.append(f"Flows rising on {', '.join(parts)} \u2014 expect reduced clarity.")

    if falling:
        parts = [f"{n} (-{p}%)" for n, p in falling]
        summaries.append(f"Flows dropping on {', '.join(parts)} \u2014 clarity improving.")

    if stable and not rising and not falling:
        summaries.append("All gauges showing stable flows \u2014 consistent conditions.")
    elif stable:
        summaries.append(f"Stable on {', '.join(stable)}.")

    if not summaries:
        summaries.append("Conditions data is limited \u2014 check individual gauges for details.")

    return summaries


def generate_daily_summary(
    gauges: list, fishing_conditions: dict | None, forecast: list,
    conditions_summary: list, upcoming_events: list, seasonal: dict | None,
) -> str:
    """
    Generate a concise AP-style daily fishing conditions summary as an
    HTML snippet. Sentence case headline, <=30 words. Body is 2-3 sentences.
    """
    today = datetime.now()
    date_str = f"{today.strftime('%B')} {today.day}, {today.year}"

    # --- Key data ---
    primary_gauge = next((g for g in gauges if g["id"] == "05398000"), None)
    primary_flow = primary_gauge["current"].get("streamflow_cfs") if primary_gauge else None
    primary_ht = primary_gauge["current"].get("gage_height_ft") if primary_gauge else None

    rating = fishing_conditions.get("day_rating") if fishing_conditions else None
    pressure_trend = fishing_conditions.get("pressure_trend") if fishing_conditions else None
    pressure_hpa = fishing_conditions.get("pressure_hpa") if fishing_conditions else None

    today_wx = forecast[0] if forecast else None
    high_temp = today_wx["high_f"] if today_wx else None

    def fmt_time(t):
        """Convert '11:09' to '11:09 a.m.' AP style."""
        h, m = int(t.split(":")[0]), int(t.split(":")[1])
        ampm = "a.m." if h < 12 else "p.m."
        hr = h % 12 or 12
        return f"{hr}:{m:02d} {ampm}"

    # Best fishing window
    best_window = None
    if fishing_conditions and fishing_conditions.get("best_time"):
        bt = fishing_conditions["best_time"]
        best_window = f"{fmt_time(bt['start'])}\u2013{fmt_time(bt['end'])}"

    # Rating word
    rating_word = ""
    if rating:
        rating_word = "poor" if rating <= 3 else "fair" if rating <= 5 else "good" if rating <= 7 else "excellent"

    # Pressure description
    pressure_desc = {"falling": "falling", "rising": "rising", "steady": "steady"}.get(pressure_trend, "")

    # --- Headline: no numbers, SEO keywords, editorial hook ---
    day_name = today.strftime("%A")

    # Pressure-based hooks — always encouraging, find the angle
    pressure_hooks = {
        "falling": {
            "excellent": f"Falling pressure and strong solunar activity set the stage for hot fishing near Wausau",
            "good":      f"Dropping barometer brings prime conditions for Wausau-area anglers this {day_name}",
            "fair":      f"Falling pressure could fire up the bite on central Wisconsin rivers this {day_name}",
            "poor":      f"Dropping barometer gives patient anglers an edge on central Wisconsin waters today",
        },
        "rising": {
            "excellent": f"Strong feeding activity expected on central Wisconsin rivers despite rising pressure",
            "good":      f"Wausau-area anglers can find action this {day_name} by targeting the right windows",
            "fair":      f"Timing is key for central Wisconsin anglers as pressure climbs this {day_name}",
            "poor":      f"Hit the midday feeding window for your best shot on central Wisconsin rivers today",
        },
        "steady": {
            "excellent": f"Excellent fishing conditions hold steady across central Wisconsin waters",
            "good":      f"Consistent conditions make for a solid day on Wausau-area rivers and streams",
            "fair":      f"Steady conditions give anglers a reliable window on central Wisconsin waters",
            "poor":      f"Central Wisconsin waters are worth a cast this {day_name} during peak feeding times",
        },
    }

    # Select headline
    trend_key = pressure_trend if pressure_trend in pressure_hooks else "steady"
    rating_key = rating_word if rating_word in pressure_hooks[trend_key] else "fair"
    headline = pressure_hooks[trend_key][rating_key]

    # --- Body: natural AP-style prose ---
    body_parts = []

    # Gather sun/wind data
    sunrise = fishing_conditions.get("sunrise") if fishing_conditions else None
    sunset = fishing_conditions.get("sunset") if fishing_conditions else None
    wind_speed = fishing_conditions.get("wind_speed_mph") if fishing_conditions else None
    wind_dir = fishing_conditions.get("wind_direction") if fishing_conditions else None

    # Wind description — use full cardinal names
    cardinal_names = {
        "N": "northerly", "NE": "northeasterly", "E": "easterly",
        "SE": "southeasterly", "S": "southerly", "SW": "southwesterly",
        "W": "westerly", "NW": "northwesterly",
    }
    wind_desc = ""
    if wind_speed and wind_dir:
        dir_name = cardinal_names.get(wind_dir, wind_dir.lower())
        if wind_speed < 5:
            wind_desc = f"a light {dir_name} breeze"
        elif wind_speed < 15:
            wind_desc = f"a {wind_speed} mph {dir_name} wind"
        else:
            wind_desc = f"gusty {wind_speed} mph {dir_name} winds"

    # Pressure narrative (body version — encouraging, different phrasing than headline)
    pressure_narrative = ""
    if pressure_trend == "falling":
        pressure_narrative = "a falling barometer that should get fish moving"
    elif pressure_trend == "rising":
        pressure_narrative = "rising barometric pressure \u2014 focus on shaded structure and slow presentations"
    elif pressure_trend == "steady":
        pressure_narrative = "steady barometric pressure keeping conditions consistent"

    # Sentence 1: Lead with the scene
    if primary_flow and wind_desc:
        body_parts.append(
            f"Anglers heading out to the Wisconsin River will find flows running at "
            f"{int(primary_flow):,} cfs with {wind_desc} and {pressure_narrative}."
        )
    elif primary_flow:
        body_parts.append(
            f"The Wisconsin River is running at {int(primary_flow):,} cfs "
            f"with {pressure_narrative}."
        )

    # Convert sunrise/sunset to AP style (6:38 AM -> 6:38 a.m.)
    def to_ap_time(t):
        return t.replace(" AM", " a.m.").replace(" PM", " p.m.") if t else None

    # Sentence 2: Weather + daylight
    wx_parts = []
    if high_temp:
        wx_parts.append(f"a high near {high_temp}\u00b0F")
    if sunrise and sunset:
        wx_parts.append(f"daylight from {to_ap_time(sunrise)} to {to_ap_time(sunset)}")
    if wx_parts:
        sentence = f"Expect {' with '.join(wx_parts)}"
        # Avoid double period after abbreviations like "p.m."
        if not sentence.endswith("."):
            sentence += "."
        body_parts.append(sentence)

    # --- Weekly outlook: score each forecast day and find the best ---
    if forecast and len(forecast) >= 3:
        best_day = None
        best_score = -999

        for i, fc_day in enumerate(forecast):
            score = 0
            temp = fc_day.get("high_f")
            precip = fc_day.get("precip_pct", 0)
            wx_code = fc_day.get("weather_code", 0)

            # Warmer is better for most fishing (up to a point)
            if temp:
                if 55 <= temp <= 75:
                    score += 3  # ideal range
                elif 45 <= temp <= 55 or 75 <= temp <= 85:
                    score += 1
                elif temp < 35:
                    score -= 2

            # Low precipitation = better
            if precip < 20:
                score += 2
            elif precip < 50:
                score += 0
            else:
                score -= 1

            # Clear/partly cloudy better than storms
            if wx_code <= 3:
                score += 2  # clear to overcast
            elif wx_code >= 95:
                score -= 2  # thunderstorm

            # Slight preference for weekends (index 0=today)
            fc_date = datetime.strptime(fc_day["date"], "%Y-%m-%d")
            if fc_date.weekday() >= 5:  # Sat/Sun
                score += 1

            if score > best_score:
                best_score = score
                best_day = fc_day

        if best_day:
            bd = datetime.strptime(best_day["date"], "%Y-%m-%d")
            bd_name = bd.strftime("%A")
            bd_temp = best_day.get("high_f")
            bd_precip = best_day.get("precip_pct", 0)

            # Is it today?
            if bd.date() == today.date():
                outlook = f"Today looks like the best fishing day this week"
            else:
                outlook = f"Fishing conditions this week peak on {bd_name}"

            # Why?
            reasons = []
            if bd_temp and bd_temp >= 55:
                reasons.append(f"a high near {bd_temp}\u00b0F")
            elif bd_temp:
                reasons.append(f"a high of {bd_temp}\u00b0F")
            if bd_precip < 15:
                reasons.append("dry skies")
            elif bd_precip < 40:
                reasons.append("low chance of rain")

            if reasons:
                outlook += f", with {' and '.join(reasons)}"

            outlook += " on area rivers and lakes."
            body_parts.append(outlook)

    body = " ".join(body_parts)

    # --- Format as HTML snippet ---
    widget_url = "https://rowanflynnpilot.github.io/wpr-river-conditions/"
    html = f"""<div class="wpr-fishing-summary">
  <p class="wpr-fishing-summary__date">{date_str}</p>
  <h3 class="wpr-fishing-summary__headline">{headline}</h3>
  <p class="wpr-fishing-summary__body">{body}</p>
  <p class="wpr-fishing-summary__cta"><a href="{widget_url}">View full river conditions, fishing forecast and more \u2192</a></p>
  <p class="wpr-fishing-summary__credit"><small>Data from USGS, National Weather Service and Solunar.org. Updated every 30 minutes.</small></p>
</div>"""

    return html


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

        # Fetch NWS flood category + forecast crest if available
        nws_data = {}
        nws_forecast = None
        if gauge.get("nws_lid"):
            log.info(f"  Fetching NWS NWPS data for {gauge['nws_lid']}...")
            nws_data = fetch_nws_flood_category(gauge["nws_lid"])
            nws_forecast = fetch_nws_forecast(gauge["nws_lid"])
            if nws_forecast:
                log.info(f"    Forecast: peak {nws_forecast['peak_stage']} {nws_forecast['units']} at {nws_forecast['peak_time']}")

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

        gauge_record = {
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
            "nws_forecast": nws_forecast,
            "current": current,
            "history": history,
            "fishing": FISHING_REFERENCE.get(gauge["id"]),
            "recreation": compute_recreation_status(gauge["id"], current.get("streamflow_cfs")),
            "water_clarity": estimate_water_clarity(current.get("streamflow_cfs"), history),
            "usgs_url": f"https://waterdata.usgs.gov/monitoring-location/USGS-{gauge['id']}/",
            "nws_url": f"https://water.noaa.gov/gauges/{gauge['nws_lid'].lower()}" if gauge.get("nws_lid") else None,
        }
        gauge_record["current_lures"] = compute_lure_suggestions(
            gauge_record,
            current.get("water_temp_f"),
            datetime.now().month,
        )
        gauges_data.append(gauge_record)

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

    # Compute best fishing time
    best_time = compute_best_fishing_time(fishing_conditions)
    if fishing_conditions and best_time:
        fishing_conditions["best_time"] = best_time

    # Seasonal calendar for current month
    current_month = datetime.now().month
    seasonal = SEASONAL_CALENDAR.get(current_month)

    # Auto-generated conditions summary
    conditions_summary = compute_conditions_summary(gauges_data)

    # Filter events to upcoming only (today and future)
    today_str = datetime.now().strftime("%Y-%m-%d")
    upcoming_events = [e for e in LOCAL_EVENTS if e["date"] >= today_str]

    # Assemble output
    output = {
        "generated_at": now,
        "region": "Central Wisconsin \u2014 Marathon County",
        "gauges": gauges_data,
        "alerts": alerts,
        "reservoirs": reservoirs,
        "fishing_conditions": fishing_conditions,
        "weather_forecast": weather_forecast,
        "seasonal_activity": seasonal,
        "upcoming_events": upcoming_events,
        "conditions_summary": conditions_summary,
        "community_links": COMMUNITY_LINKS,
        "sources": {
            "usgs": "https://waterservices.usgs.gov/",
            "nws": "https://api.weather.gov/",
            "wvic": "https://wvic.com/",
            "open_meteo": "https://open-meteo.com/",
            "solunar": "https://solunar.org/",
        },
    }

    # Generate daily fishing summary (AP style)
    daily_summary = generate_daily_summary(
        gauges_data, fishing_conditions, weather_forecast,
        conditions_summary, upcoming_events, seasonal
    )

    # Write summary as standalone HTML snippet
    summary_path = Path(__file__).parent.parent / "src" / "data" / "daily-summary.html"
    summary_path.write_text(daily_summary, encoding="utf-8")
    log.info(f"Wrote daily summary ({summary_path.stat().st_size:,} bytes)")

    # Also write as JSON for programmatic consumption
    summary_json_path = Path(__file__).parent.parent / "src" / "data" / "daily-summary.json"
    summary_json_path.write_text(json.dumps({
        "generated_at": now,
        "html": daily_summary,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

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
