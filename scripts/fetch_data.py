#!/usr/bin/env python3
"""
WPR River & Lake Conditions — Data Scraper
Fetches real-time data from USGS stream gauges, NWS flood alerts,
and WVIC reservoir levels for central Wisconsin.

Output: src/data/river-data.json (consumed by the React frontend)
Schedule: Every 30 minutes via GitHub Actions
"""

import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from http.client import HTTPException  # IncompleteRead, BadStatusLine, …
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
        "nwm_reach": "14732372",
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
        "nwm_reach": None,  # not an NWM output reach (no NLDI comid)
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
        "nwm_reach": "14730490",
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
        "nwm_reach": "14730636",
        "nws_lid": None,  # No NWS match
        "name": "Little Rib River near Wausau",
        "short_name": "Little Rib River",
        "lat": 44.9472,
        "lon": -89.6793,
        "flood_stages": None,
        # USGS has published no IV or DV data here for over a year
        # (verified 2026-07) — surface that honestly instead of "seasonal".
        "discontinued": True,
        "description": "Tributary flowing through western Marathon County",
        "has_temp_sensor": False,
    },
    {
        "id": "05397500",
        "nwm_reach": "14730982",
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
        "nwm_reach": "14733228",
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
        "nwm_reach": "14727088",
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
        "nwm_reach": "14728798",
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
        "nwm_reach": "14705230",
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
        "nwm_reach": "9027875",
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
        "nwm_reach": "14704932",
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
        "nwm_reach": "9033255",
        "nws_lid": None,
        "name": "Tomorrow River near Nelsonville",
        "short_name": "Tomorrow River",
        "lat": 44.5240,
        "lon": -89.3380,
        "flood_stages": None,
        "description": "Class I trout stream destination near Stevens Point",
        "has_temp_sensor": False,
    },
    # --- Eight-county expansion (Shawano, Taylor, Oneida) ---
    {
        "id": "04077400",
        "nwm_reach": "9031831",
        "nws_lid": "SHAW3",
        "name": "Wolf River near Shawano",
        "short_name": "Wolf River — Shawano",
        "lat": 44.8358,
        "lon": -88.6250,
        "flood_stages": {"action": 10.0, "minor": 11.0, "moderate": 13.0, "major": 15.0},
        # USGS's real-time record here ended in 2001 — the live stage comes
        # from the NWS sensor via NWPS (reading + history + flood status).
        "stage_from_nws": True,
        "description": "Lower Wolf at Shawano — the basin's flood-forecast point",
        "has_temp_sensor": False,
    },
    {
        "id": "04077630",
        "nwm_reach": "9030269",
        "nws_lid": "MORW3",
        "name": "Red River at Morgan Road near Morgan",
        "short_name": "Red River",
        "lat": 44.8980,
        "lon": -88.8443,
        "flood_stages": {"action": 9.0, "minor": 11.0, "moderate": 14.0, "major": 16.5},
        "description": "Wolf tributary near Gresham — live water-temp sensor",
        "has_temp_sensor": True,
    },
    {
        "id": "04078500",
        "nwm_reach": "9030507",
        "nws_lid": "EMBW3",
        "name": "Embarrass River near Embarrass",
        "short_name": "Embarrass River",
        "lat": 44.7247,
        "lon": -88.7361,
        "flood_stages": {"action": 6.0, "minor": 7.0, "moderate": 9.5, "major": 11.5},
        "description": "Wolf tributary draining western Shawano County",
        "has_temp_sensor": False,
    },
    {
        "id": "05363600",
        "nwm_reach": None,  # not an NWM output reach
        "nws_lid": "YELW3",
        "name": "North Fork Yellow River near Perkinstown",
        "short_name": "NF Yellow River",
        "lat": 45.2986,
        "lon": -90.5965,
        "flood_stages": None,
        "description": "Chequamegon country stream in Taylor County",
        "has_temp_sensor": False,
    },
    {
        "id": "05391000",
        "nwm_reach": "13396483",
        "nws_lid": "LTKW3",
        "name": "Wisconsin River at Rainbow Lake near Lake Tomahawk",
        "short_name": "WI River — Rainbow",
        "lat": 45.8305,
        "lon": -89.5524,
        "flood_stages": {"action": 4.0, "minor": 6.0, "moderate": 7.5, "major": 9.0},
        "description": "Headwaters gauge at Rainbow Reservoir — the top of the system",
        "has_temp_sensor": False,
    },
]

# USGS parameter codes
PARAM_GAGE_HEIGHT = "00065"   # ft
PARAM_STREAMFLOW = "00060"    # cfs (cubic feet per second)
PARAM_WATER_TEMP = "00010"    # °C
PARAM_PRECIP = "00045"        # inches (incremental precipitation)

# NWS county alert zones — the eight-county WPR coverage area:
# Langlade, Lincoln, Marathon, Oneida, Portage, Shawano, Taylor, Wood
NWS_ZONES = [
    "WIC067",  # Langlade
    "WIC069",  # Lincoln
    "WIC073",  # Marathon
    "WIC085",  # Oneida
    "WIC097",  # Portage
    "WIC115",  # Shawano
    "WIC119",  # Taylor
    "WIC141",  # Wood
]

# County FIPS (the SAME codes on an alert) → our county zone. Zone-based
# alerts carry forecast zones in UGC, so this is how they map to counties.
NWS_ZONE_BY_FIPS = {
    "055067": "WIC067",  # Langlade
    "055069": "WIC069",  # Lincoln
    "055073": "WIC073",  # Marathon
    "055085": "WIC085",  # Oneida
    "055097": "WIC097",  # Portage
    "055115": "WIC115",  # Shawano
    "055119": "WIC119",  # Taylor
    "055141": "WIC141",  # Wood
}

# WVIC reservoirs to track (scraped from wvic.com).
# lat/lon are the NWS NWPS gauge locations at each impoundment
# (LTKW3, WILW3, SPDW3, EPLW3, RRVW3) \u2014 used for the overview-map pins.
WVIC_RESERVOIRS = [
    {"name": "Rainbow Reservoir", "slug": "rainbow", "lat": 45.8306, "lon": -89.5522,
     "description": "Controls upper WI River flow north of Wausau"},
    {"name": "Willow Reservoir", "slug": "willow", "lat": 45.7128, "lon": -89.8450,
     "description": "Regulates Willow Creek into the WI River"},
    {"name": "Spirit Reservoir", "slug": "spirit", "lat": 45.4381, "lon": -89.7425,
     "description": "Feeds Spirit River \u2014 affects WI River levels"},
    {"name": "Eau Pleine Reservoir", "slug": "eau-pleine", "lat": 44.7331, "lon": -89.7581,
     "description": "Directly feeds Big Eau Pleine gauge at Stratford"},
    {"name": "Rice Reservoir", "slug": "rice", "lat": 45.5397, "lon": -89.7478,
     "description": "Controls Rice Creek flow into the WI River"},
    {"name": "Lake Wausau", "slug": "lake-wausau", "lat": 44.9420, "lon": -89.6560,
     "description": "Run-of-river impoundment in downtown Wausau"},
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
    # --- Eight-county expansion waters (researched + source-verified 2026-07;
    #     regulations reflect the 2026-27 season) ---
    "04077400": {  # Wolf River near Shawano
        "species": ["Walleye", "White Bass", "Smallmouth Bass", "Channel Catfish", "Northern Pike"],
        "trout_class": None,
        "tips": {
            "Walleye": "Winnebago-system walleye push upriver to the Shawano dam in April — but the dam-to-County-M reach is a posted no-fishing refuge Apr 1–May 1. Drift jig-and-minnow along current seams downstream of the County M bridge until it reopens.",
            "White Bass": "The famous run follows the walleye — May, classically peaking around Mother's Day. Small white jigs or inline spinners below the dam and off the Sturgeon Park pier.",
            "Smallmouth Bass": "DNR-designated smallmouth water through town — float it in summer, working tubes and topwater around boulders and wood.",
            "Channel Catfish": "Summer nights on cut bait or crawlers in the deeper holes below town; the river below the dam is open year-round for most species.",
            "Northern Pike": "Work spoons and large minnows along the weedy margins of the millpond above the dam in spring and fall.",
        },
        "regulations": [
            {"species": "Walleye", "rule": "Winnebago-system rules below the dam — 3 daily with new-for-2026 slot protection; check DNR for your reach"},
            {"species": "Sturgeon", "rule": "Closed to fishing on the river — the spring spawning run at the dam is watch-only"},
            {"species": "All species", "rule": "No fishing from the dam down to the Cty M bridge, Apr 1 until the Friday before the general opener (spring refuge)"},
            {"species": "Bass", "rule": '14" min, 5 daily (special smallmouth rules on some stretches — check DNR)'},
        ],
        "season_notes": [
            "Lake sturgeon spawn below the Shawano dam in the second half of April — thousands come to watch at Sturgeon Park. Look, don't cast.",
            "Spring walleye run late March–April; white bass peak mid-May; catfish take the deep holes June–August",
        ],
        "access_points": [
            {"name": "Sturgeon Park", "directions": "801 S. Water St., Shawano — east bank below the dam; accessible fishing pier", "lat": 44.7745, "lng": -88.6192},
            {"name": "Huckleberry Harbor", "directions": "220 N. Sawyer St., Shawano — main city landing above the dam; 4 ramps", "lat": 44.7849, "lng": -88.6087},
            {"name": "Judd Park", "directions": "1121 S. Water St., Shawano — small landing below the dam (city launch permit)", "lat": 44.7706, "lng": -88.6199},
        ],
        "dnr_url": "https://apps.dnr.wi.gov/fisheriesmanagement/Public/LakeRegulation/Details?WBIC=241300&WBIC_NAME=Wolf+River",
    },
    "04077630": {  # Red River at Morgan Road near Gresham
        "species": ["Brook Trout", "Smallmouth Bass", "Panfish"],
        "trout_class": "Class II (mainstem at the gauge; West Branch nearby is Class I)",
        "tips": {
            "Brook Trout": "Wild brookies through this reach — small inline spinners or attractor dries through the pockets. Harvest is allowed from opening day under the new season structure.",
            "Smallmouth Bass": "The Morgan Road area doubles as DNR-designated wadable smallmouth water — wade small craws and topwater through pocketwater after the May 2 opener.",
            "Panfish": "The Gresham millponds (Upper and Lower Red lakes) a few miles downstream hold bluegill, crappie, bass, and pike with public landings.",
        },
        "regulations": [
            {"species": "Trout", "rule": "5 daily, any length (county base rule) · season Apr 4 – Oct 15"},
            {"species": "Bass", "rule": '14" min, 5 daily'},
            {"species": "Sturgeon", "rule": "Closed — no fishing"},
        ],
        "season_notes": [
            "Below Gresham the river turns into a Class I–III whitewater paddling run (Monastery Falls, Ziemer's Falls) — the trout-and-smallmouth water is upstream, around the gauge",
        ],
        "access_points": [
            {"name": "Morgan Road bridge", "directions": "Road crossing at the gauge, ~5 mi NW of Gresham — carry-in/wade access; stay in the streambed", "lat": 44.8980, "lng": -88.8443},
            {"name": "Lower Red Lake Dam landing", "directions": "Off Lower Lake Rd, Gresham — parking, sandy put-in below the dam; carry-in", "lat": 44.8416, "lng": -88.7607},
        ],
        "dnr_url": "https://apps.dnr.wi.gov/fisheriesmanagement/Public/LakeRegulation/Details?WBIC=326600&WBIC_NAME=Red+River",
    },
    "04078500": {  # Embarrass River near Embarrass
        "species": ["Smallmouth Bass", "Northern Pike", "Freshwater Drum"],
        "trout_class": None,
        "tips": {
            "Smallmouth Bass": "The boulder gardens from the Pella dam down past Range Line Road are classic wade-and-float smallmouth water — tubes, craws, and topwater in summer low flows.",
            "Northern Pike": "After the May 2 opener, throw spinnerbaits and large minnows through the slower sloughs and deeper outside bends between the rapids.",
            "Freshwater Drum": "Underrated scrap on light tackle — bottom-fish crawlers in the deeper holes in summer.",
        },
        "regulations": [
            {"species": "All species", "rule": "No fishing from the Cty M bridge down to Rangeline Rd (the gauge), Apr 1 until the Friday before the general opener (spring refuge)"},
            {"species": "Walleye", "rule": "3 daily; minimum length varies by stretch — check DNR for your reach"},
            {"species": "Sturgeon", "rule": "Closed — no fishing; Winnebago sturgeon run the Embarrass in spring and are watch-only"},
        ],
        "season_notes": [
            "The reach just upstream of the gauge is a posted spring refuge protecting spawners (Apr 1 – May 1)",
            "Trout live in the cold tributaries (Beaver Creek Class I, Mill Creek Class II), not the mainstem here",
        ],
        "access_points": [
            {"name": "Old Mill Park at Pella Dam", "directions": "Island between the millrace and dam at Pella Pond, ~3.5 mi upstream of the gauge; carry-in", "lat": 44.7395, "lng": -88.8043},
            {"name": "Hayman Falls County Park", "directions": "N4386 Hayman Falls Ln, Town of Pella — 54-acre county park with rapids, trails, restroom", "lat": 44.7457, "lng": -88.8443},
            {"name": "East Range Line Road bridge", "directions": "Crossing at the gauge — informal carry-in via the path NW of the bridge", "lat": 44.7247, "lng": -88.7361},
        ],
        "dnr_url": "https://apps.dnr.wi.gov/fisheriesmanagement/Public/LakeRegulation/Details?WBIC=291900&WBIC_NAME=Embarrass+River",
    },
    "05363600": {  # NF Yellow River near Perkinstown → Chequamegon Waters Flowage
        "species": ["Largemouth Bass", "Northern Pike", "Panfish", "Walleye"],
        "trout_class": None,
        "tips": {
            "Largemouth Bass": "The nearby Chequamegon Waters Flowage is largemouth-first water — work weedlines and wild-rice bay edges with soft plastics or spinnerbaits.",
            "Northern Pike": "Pike are the flowage's top predator (DNR surveys found no musky) — larger baits along weed edges, and the bite holds through the ice season.",
            "Panfish": "Bluegill and crappie are the flowage's bread and butter — shallow wood early in the season, weed edges in summer.",
            "Walleye": "DNR calls walleye here a rare bonus fish — the few caught tend to be large.",
        },
        "regulations": [
            {"species": "Panfish", "rule": "25 daily in total, no size limit (Chequamegon Waters Flowage)"},
            {"species": "Largemouth Bass", "rule": '14" min, 5 daily'},
            {"species": "Northern Pike", "rule": "No size limit, 5 daily"},
            {"species": "Walleye", "rule": '15" min with 20–24" protected slot, 3 daily'},
        ],
        "season_notes": [
            "The gauge stream itself is not DNR-classified trout water — the local fishery is Chequamegon Waters Flowage (Miller Dam), ~8 miles southwest",
            "Ice fishing is popular on the flowage; an aeration system runs Jan–March near the Yellow River inlet",
        ],
        "access_points": [
            {"name": "Chippewa Recreation Area (USFS)", "directions": "East shore of Chequamegon Waters Flowage via CTH M and Forest Rd 1417 — ramp, campground, fish-cleaning station", "lat": 45.2225, "lng": -90.7056},
            {"name": "Miller Dam boat landing", "directions": "County ramp at the Miller Dam outlet (rebuilt 2024)", "lat": 45.2006, "lng": -90.7110},
            {"name": "Yellow River Road bridge", "directions": "Informal carry-in/wading access at the gauge crossing on national forest land", "lat": 45.2986, "lng": -90.5965},
        ],
        "dnr_url": "https://apps.dnr.wi.gov/lakes/lakepages/LakeDetail.aspx?wbic=2160700",
    },
    "05391000": {  # Wisconsin River at Rainbow Lake / Rainbow Flowage
        "species": ["Walleye", "Musky", "Smallmouth Bass", "Northern Pike", "Panfish"],
        "trout_class": None,
        "tips": {
            "Walleye": "May is the peak month by DNR creel data — work sand flats and drop-offs early; most keepers run 15–17 inches.",
            "Musky": "Dark-stained water warms early, making Rainbow a strong early-season pick — and with a special 50-inch minimum it fishes as trophy catch-and-release water.",
            "Smallmouth Bass": "July is the busiest smallmouth month here; DNR netting found most adults over 14 inches. Catch-and-release only until June 19.",
            "Northern Pike": "Pike action holds through the ice — January is the peak month. Tip-ups with large shiners over weed flats.",
            "Panfish": "Crappie are the most-sought panfish and genuinely quality-sized (11-inch average in the last creel survey) — wood and creek arms after ice-out.",
        },
        "regulations": [
            {"species": "Musky", "rule": '50" min on Rainbow Flowage (special — statewide is 40"), 1 daily'},
            {"species": "Walleye", "rule": '15" min, 20–24" protected slot (one over 24"), 3 daily'},
            {"species": "Bass", "rule": 'Catch-and-release until June 19, then 14" min, 5 daily'},
            {"species": "Panfish", "rule": "25 daily in total, no size limit"},
        ],
        "season_notes": [
            "WVIC storage reservoir: drawn down to minimum pool by late March, then refilled with snowmelt — expect low water and mudflats in early spring",
            "Fishable ice typically forms mid-December; winter creel shows strong pike, perch, and walleye effort",
        ],
        "access_points": [
            {"name": "Rainbow Dam Recreation Area (WVIC)", "directions": "At the dam on the southeast corner — landing, restrooms, shore fishing; the USGS gauge is here", "lat": 45.8305, "lng": -89.5524},
            {"name": "County D Landing", "directions": "Off CTH D on the southeast shore, just east of the D/E intersection", "lat": 45.8355, "lng": -89.5476},
            {"name": "Stormy Camp landing", "directions": "Northwest shore at the end of Stormy Landing Rd (primitive; location approximate)", "lat": 45.8680, "lng": -89.5900},
        ],
        "dnr_url": "https://apps.dnr.wi.gov/lakes/lakepages/LakeDetail.aspx?wbic=1595300",
    },
}

# Upcoming local events — manually updated as events are announced
# To add an event: append a dict with date, name, description, location, url
# To remove: delete the dict. Events with past dates are auto-filtered out.
LOCAL_EVENTS = [
    {
        "date": "2026-10-15",
        "name": "Inland Trout Season Closes",
        "description": "Last day for inland trout on streams, springs, and spring ponds. The Prairie, Little Plover, Tomorrow, and Rib tributaries all close until the early catch-and-release period in January.",
        "location": "Statewide",
        "category": "season",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/seasons",
    },
    {
        "date": "2027-01-02",
        "name": "Early Catch-and-Release Trout Opens",
        "description": "Winter catch-and-release trout season opens on inland streams (artificials only). Runs until the regular season opener in April.",
        "location": "Statewide",
        "category": "season",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/seasons",
    },
    {
        "date": "2027-01-16",
        "name": "Free Fishing Weekend (Winter)",
        "description": "Jan. 16\u201317. No license or stamps required for residents or nonresidents \u2014 a great weekend to try ice fishing. All bag/size limits still apply.",
        "location": "Statewide",
        "category": "event",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/anglereducation/freeFishingWeekend",
    },
    {
        "date": "2027-03-07",
        "name": "General Inland Game Fish Season Closes",
        "description": "Walleye, northern pike, and most inland game fish seasons close on inland waters until the first Saturday in May.",
        "location": "Statewide",
        "category": "season",
        "url": "https://dnr.wisconsin.gov/topic/Fishing/seasons",
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
    except (URLError, HTTPError, HTTPException, json.JSONDecodeError, TimeoutError, OSError) as e:
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
    except (URLError, HTTPError, HTTPException, TimeoutError, OSError) as e:
        log.error(f"Failed to fetch {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# USGS: Current instantaneous values
# ---------------------------------------------------------------------------

def fetch_usgs_current(gauge_id: str, period: str = "P1D") -> dict:
    """
    Fetch the most recent instantaneous values for a gauge.
    Uses the legacy WaterServices IV endpoint (still active, migrating to OGC API).

    Some gauges publish on a lag (Wolf at Shawano's computed flow can trail
    by days) — when the 24h window comes back empty, retry over a week and
    take the latest available reading; its timestamp shows the true age.

    Returns: {gage_height_ft, streamflow_cfs, water_temp_f, timestamp}
    """
    site = gauge_id
    params = f"{PARAM_GAGE_HEIGHT},{PARAM_STREAMFLOW},{PARAM_WATER_TEMP},{PARAM_PRECIP}"
    # period=P1D so precip can be summed over the past 24h
    url = (
        f"https://waterservices.usgs.gov/nwis/iv/"
        f"?format=json&sites={site}&parameterCd={params}&period={period}&siteStatus=all"
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

            # For all other params, take the latest reading.
            # NB: compare against None, not truthiness — a reading of exactly 0
            # (dry-bed flow, low-water stage) is valid data, not "missing".
            latest = values[-1]
            val = float(latest["value"]) if latest["value"] != "" else None
            if val is not None and val < 0:
                val = None

            if var_code == PARAM_GAGE_HEIGHT:
                result["gage_height_ft"] = round(val, 2) if val is not None else None
            elif var_code == PARAM_STREAMFLOW:
                result["streamflow_cfs"] = round(val, 1) if val is not None else None
            elif var_code == PARAM_WATER_TEMP:
                result["water_temp_f"] = round(val * 9 / 5 + 32, 1) if val is not None else None
                result["water_temp_c"] = round(val, 1) if val is not None else None

            ts_str = latest.get("dateTime")
            if ts_str and (result["timestamp"] is None or ts_str > result["timestamp"]):
                result["timestamp"] = ts_str
    except (KeyError, IndexError, TypeError, ValueError) as e:
        # ValueError: USGS emits non-numeric values ("Ice", "***") in winter.
        log.warning(f"Error parsing USGS data for {gauge_id}: {e}")

    # Lagged reporter: nothing in the last 24h — widen to a week. (Only
    # height/flow trigger this; the precip sum never rides the fallback
    # because its gauge reports continuously.)
    if (period == "P1D"
            and result.get("gage_height_ft") is None
            and result.get("streamflow_cfs") is None):
        return fetch_usgs_current(gauge_id, period="P7D")

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

    # Downsample 15-min data to 2-hour buckets: everything that consumes
    # history (200px sparklines, the map replay's 2h steps, the ±4h trend
    # window) is indistinguishable at this cadence, and it halves the
    # payload's largest component.
    by_hour: dict[str, dict] = {}
    try:
        for ts in data["value"]["timeSeries"]:
            var_code = ts["variable"]["variableCode"][0]["value"]
            for val_entry in ts["values"][0]["value"]:
                dt_str = val_entry["dateTime"]
                hour_key = f"{dt_str[:11]}{int(dt_str[11:13]) // 2 * 2:02d}"
                raw = val_entry["value"]
                val = float(raw) if raw != "" else None
                if val is not None and val < 0:
                    val = None

                if hour_key not in by_hour:
                    by_hour[hour_key] = {"timestamp": dt_str}

                if var_code == PARAM_GAGE_HEIGHT:
                    by_hour[hour_key]["gage_height_ft"] = round(val, 2) if val is not None else None
                elif var_code == PARAM_STREAMFLOW:
                    by_hour[hour_key]["streamflow_cfs"] = round(val, 1) if val is not None else None
    except (KeyError, IndexError, TypeError, ValueError) as e:
        # ValueError: USGS emits non-numeric values ("Ice", "***") in winter.
        log.warning(f"Error parsing USGS history for {gauge_id}: {e}")

    return sorted(by_hour.values(), key=lambda x: x["timestamp"])


# ---------------------------------------------------------------------------
# USGS: "Today vs. normal" flow comparison (daily statistics service)
# ---------------------------------------------------------------------------

# Percentile buckets follow the USGS WaterWatch convention.
def _flow_class(flow: float, p10, p25, p75, p90) -> str:
    if p90 is not None and flow > p90:
        return "much_above"
    if p75 is not None and flow > p75:
        return "above"
    if p10 is not None and flow < p10:
        return "much_below"
    if p25 is not None and flow < p25:
        return "below"
    return "normal"


def fetch_usgs_normal_flow(gauge_id: str, current_flow) -> dict | None:
    """
    Compare current streamflow to the long-term normal for today's calendar day,
    using the USGS daily statistics service (period-of-record percentiles per
    month/day). Comparison is flow-based (00060) because gage-height stats are
    unreliable across datum revisions.

    Returns {median_cfs, class, pct_of_median, years, count} or None.
    """
    if current_flow is None:
        return None

    url = (
        f"https://waterservices.usgs.gov/nwis/stat/"
        f"?sites={gauge_id}&statReportType=daily&statTypeCd=all"
        f"&parameterCd={PARAM_STREAMFLOW}&format=rdb"
    )
    text = fetch_text(url)
    if not text:
        return None

    today = datetime.now()
    header = None
    target = None
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        cols = line.split("\t")
        if header is None:
            header = cols
            continue
        # The line right after the header is an RDB format spec ("5s", "12n"…) — skip it.
        if re.match(r"^\d+[sn]$", cols[0]):
            continue
        idx = {name: i for i, name in enumerate(header)}
        try:
            if (int(cols[idx["month_nu"]]) == today.month
                    and int(cols[idx["day_nu"]]) == today.day):
                target = (cols, idx)
                break
        except (KeyError, ValueError, IndexError):
            continue

    if not target:
        return None

    cols, idx = target

    def col(name):
        try:
            raw = cols[idx[name]].strip()
            return float(raw) if raw not in ("", None) else None
        except (KeyError, ValueError, IndexError):
            return None

    p10, p25, p50, p75, p90 = (col("p10_va"), col("p25_va"),
                               col("p50_va"), col("p75_va"), col("p90_va"))
    if p50 is None:
        return None

    begin_yr = cols[idx["begin_yr"]] if "begin_yr" in idx else None
    end_yr = cols[idx["end_yr"]] if "end_yr" in idx else None
    count = col("count_nu")

    return {
        "median_cfs": round(p50),
        "class": _flow_class(current_flow, p10, p25, p75, p90),
        "pct_of_median": round(current_flow / p50 * 100) if p50 else None,
        "years": f"{begin_yr}–{end_yr}" if begin_yr and end_yr else None,
        "count": int(count) if count else None,
    }


# ---------------------------------------------------------------------------
# NWS: Flood alerts for Marathon County
# ---------------------------------------------------------------------------

def fetch_nws_alerts() -> list[dict]:
    """
    Fetch active outdoor-relevant alerts from the NWS API for every county
    with a monitored gauge (Langlade, Lincoln, Marathon, Portage, Wood).
    Includes flood, severe weather, fire weather, winter, and wind events —
    anything an outdoor or floodplain audience would want to know about.
    Returns: [{event, category, headline, severity, description, onset, expires, url}, ...]
    """
    url = f"https://api.weather.gov/alerts/active?zone={','.join(NWS_ZONES)}"
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

            # County zones this alert covers (drives map shading) — only
            # the counties we monitor, from the alert's UGC geocodes.
            geocode = props.get("geocode") or {}
            ugc = geocode.get("UGC") or []
            same = geocode.get("SAME") or []
            # Flood warnings are issued for county zones (WIC…), but heat,
            # winter, and severe alerts are issued for *forecast* zones
            # (WIZ…) that don't match our county list — their SAME/FIPS
            # codes are the reliable cross-walk. Use both.
            zones = sorted(
                {z for z in ugc if z in NWS_ZONES}
                | {NWS_ZONE_BY_FIPS[s] for s in same if s in NWS_ZONE_BY_FIPS}
            )

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
                "zones": zones,
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


def fetch_nws_stage_history(nws_lid: str, days: int = 7) -> list[dict]:
    """
    Observed stage history from NWPS (~30 days of 15-min data), shaped
    like the USGS history entries and downsampled to hourly. Used for
    gauges whose USGS real-time record is dead but whose NWS sensor is
    live (Wolf at Shawano).
    Returns: [{timestamp, gage_height_ft}, ...]
    """
    if not nws_lid:
        return []
    url = f"https://api.water.noaa.gov/nwps/v1/gauges/{nws_lid}/stageflow/observed"
    data = fetch_json(url)
    points = (data or {}).get("data") or []
    if not points:
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    by_hour: dict[str, dict] = {}
    for p in points:
        t = p.get("validTime")
        v = p.get("primary")
        if not t or v is None or v <= -999:
            continue
        if t < cutoff:
            continue
        # 2-hour buckets, matching fetch_usgs_history's cadence
        hour_key = f"{t[:11]}{int(t[11:13]) // 2 * 2:02d}"
        if hour_key not in by_hour:
            by_hour[hour_key] = {
                "timestamp": t,
                "gage_height_ft": round(float(v), 2),
            }
    return sorted(by_hour.values(), key=lambda x: x["timestamp"])


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
# NOAA National Water Model: flow forecasts via the NWPS /reaches API
# ---------------------------------------------------------------------------

def _nwm_points(obj) -> list:
    """Tolerantly extract [{validTime, flow}, ...] from an NWM payload —
    the series may sit at .data, .series.data, .shortRange.series.data,
    or .mediumRange.mean.data depending on the query."""
    if not isinstance(obj, dict):
        return []
    if isinstance(obj.get("data"), list):
        return obj["data"]
    for key in ("series", "mean", "shortRange", "mediumRange"):
        if key in obj:
            pts = _nwm_points(obj[key])
            if pts:
                return pts
    return []


def _nwm_reference_time(obj) -> str | None:
    if not isinstance(obj, dict):
        return None
    if obj.get("referenceTime"):
        return obj["referenceTime"]
    for key in ("series", "mean", "shortRange", "mediumRange"):
        if key in obj:
            r = _nwm_reference_time(obj[key])
            if r:
                return r
    return None


def _parse_iso(t: str):
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# Circuit breaker: when the NWM endpoint is down (it 504s/hangs under
# load), don't burn 15s × 22 calls of cron time — after two gauges fail
# completely, skip the rest of this run. Resets on any success.
_NWM_CONSECUTIVE_FAILURES = 0
# Each failure now costs one 8s timeout instead of two 15s ones, so the
# breaker can be more patient — more gauges get a fresh forecast on a
# partly-degraded cycle, and the carry-forward covers the rest.
_NWM_BREAKER_LIMIT = 4


def _nwm_summary(points: list[dict], current_flow) -> dict:
    """
    Card summary from forecast points: % change at the farthest point
    within 24h, measured against the current observed flow — or, for
    gauges with no live flow (Wolf at Shawano, discontinued sites),
    against the model's own next point. Thresholds match the
    observed-trend math.

    Anchored on *now* rather than the series start, so a forecast carried
    forward from an earlier run stays accurate as it ages.
    """
    now = datetime.now(timezone.utc)
    future = []
    for p in points:
        dt = _parse_iso(p.get("t"))
        if dt and dt > now and p.get("cfs") is not None:
            future.append((dt, float(p["cfs"])))
    if not future:
        return {}

    if current_flow is not None and current_flow > 0:
        baseline, baseline_kind = current_flow, "observed"
    elif future[0][1] > 0:
        baseline, baseline_kind = future[0][1], "model"
    else:
        return {}

    best = None
    for dt, f in future:
        if dt - now <= timedelta(hours=24):
            best = (dt, f)
    if not best:
        return {}

    pct = (best[1] - baseline) / baseline * 100
    return {
        "next24h_pct": round(pct),
        "horizon_h": max(1, round((best[0] - now).total_seconds() / 3600)),
        "class": "rising" if pct > 15 else "falling" if pct < -15 else "steady",
        "baseline": baseline_kind,
    }


def carry_forward_nwm(prev_forecast: dict | None, current_flow,
                      max_age_h: int = 12) -> dict | None:
    """
    Reuse the previous run's forecast when NOAA is unreachable. The NWPS
    reaches endpoint is intermittently down for whole scrape cycles, which
    would otherwise blank the forecast for every gauge; a model run a few
    hours old still carries real signal. The summary is recomputed against
    the current flow and the current clock, and future points are trimmed
    to what's still ahead.
    """
    if not prev_forecast:
        return None

    issued = _parse_iso(prev_forecast.get("issued"))
    now = datetime.now(timezone.utc)
    if issued and now - issued > timedelta(hours=max_age_h):
        return None

    points = [
        p for p in (prev_forecast.get("points") or [])
        if (_parse_iso(p.get("t")) or now) > now
    ]
    summary = _nwm_summary(points, current_flow)
    if not summary:
        return None

    carried = dict(prev_forecast)
    carried["points"] = points
    carried.update(summary)
    carried["carried_forward"] = True
    if issued:
        carried["age_h"] = max(1, round((now - issued).total_seconds() / 3600))
    return carried


def fetch_nwm_forecast(reach_id: str | None, current_flow) -> dict | None:
    """
    National Water Model flow forecast for an NHD reach, via NWPS.
    short_range = 18 hourly points (refreshed hourly); medium_range =
    ~8.5-day ensemble mean (refreshed every 6h). Values are ft³/s;
    -9999 sentinels mark non-forecast reaches. The endpoint 504s under
    load, so timeouts are short and any failure degrades to None.

    Returns {points, issued, peak_cfs, peak_time, next24h_pct,
    horizon_h, class} or None.
    """
    global _NWM_CONSECUTIVE_FAILURES
    if not reach_id:
        return None
    if _NWM_CONSECUTIVE_FAILURES >= _NWM_BREAKER_LIMIT:
        return None

    # NOAA answers in well under a second when healthy and hangs when not,
    # so a short timeout costs nothing real and keeps a bad cycle cheap.
    # Skip medium_range when short_range already failed — same host, so
    # it's almost certainly down too, and the carry-forward covers us.
    base = f"https://api.water.noaa.gov/nwps/v1/reaches/{reach_id}/streamflow?series="
    short = fetch_json(base + "short_range", timeout=8)
    medium = fetch_json(base + "medium_range", timeout=8) if short is not None else None

    if short is None and medium is None:
        _NWM_CONSECUTIVE_FAILURES += 1
        if _NWM_CONSECUTIVE_FAILURES == _NWM_BREAKER_LIMIT:
            log.warning("NWM API unreachable — skipping remaining forecast fetches this run")
        return None
    _NWM_CONSECUTIVE_FAILURES = 0

    def parse(payload):
        out = []
        for p in _nwm_points(payload or {}):
            t, f = p.get("validTime"), p.get("flow")
            if t is None or f is None:
                continue
            try:
                f = float(f)
            except (TypeError, ValueError):
                continue
            if f < 0:  # -9999 sentinel
                continue
            out.append((t, f))
        return out

    s_pts = parse(short)
    m_pts = parse(medium)
    if not s_pts and not m_pts:
        return None

    # Full hourly short-range, then every 3rd medium-range point beyond it,
    # capped at +72h — enough for the card summary and the sparkline tail
    # without bloating the payload.
    last_short = s_pts[-1][0] if s_pts else ""
    merged = list(s_pts)
    kept = 0
    for t, f in m_pts:
        if t <= last_short:
            continue
        if kept % 3 == 0:
            merged.append((t, f))
        kept += 1
    if not merged:
        return None

    t0 = _parse_iso(merged[0][0])
    if t0:
        merged = [
            (t, f) for t, f in merged
            if (_parse_iso(t) or t0) - t0 <= timedelta(hours=72)
        ]

    peak_t, peak_f = max(merged, key=lambda x: x[1])
    result = {
        "points": [{"t": t, "cfs": round(f, 1)} for t, f in merged],
        "issued": _nwm_reference_time(short) or _nwm_reference_time(medium),
        "peak_cfs": round(peak_f, 1),
        "peak_time": peak_t,
    }
    result.update(_nwm_summary(result["points"], current_flow))
    return result


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
            "lat": res.get("lat"),
            "lon": res.get("lon"),
            "feet_below_max": feet_below_max,
            "has_data": feet_below_max is not None,
            "source_url": WVIC_DATA_URL,
            "last_updated": now if feet_below_max is not None else None,
        })

    return results


# ---------------------------------------------------------------------------
# WVIC: Daily water temperatures (Flow-Temperature Summary)
# ---------------------------------------------------------------------------

WVIC_TEMP_URL = "https://wvic.com/tridentxml/FlowTempSummary/FlowTempSummary.html"

# Data-row cell layout (11 cells, first empty):
# [_, day, Rhinelander flow, temp, Tomahawk flow, Grandmother flow, temp,
#  Rothschild flow, temp, Wisconsin Rapids flow, temp]
WVIC_TEMP_COLUMNS = {8: "05398000", 10: "05400760"}  # temp cell → USGS gauge

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def fetch_wvic_water_temp() -> dict:
    """
    Daily water temperatures from WVIC's Flow-Temperature Summary page —
    the only water-temp source in the basin (USGS operates no active temp
    gauges here). The page is a static month-to-date HTML table; the last
    populated row is the most recent daily reading.

    Returns {usgs_gauge_id: {"temp_f": float, "date": "YYYY-MM-DD"}}.
    Provisional data — attribute WVIC wherever it surfaces.
    """
    html = fetch_text(WVIC_TEMP_URL)
    if not html:
        return {}

    # The header text is split across nested tags in the raw source —
    # strip markup before searching for e.g. "July - 2026".
    text = re.sub(r"<[^>]+>|&nbsp;?", " ", html)
    m = re.search(r"(January|February|March|April|May|June|July|August|"
                  r"September|October|November|December)\s*-\s*(\d{4})", text)
    if not m:
        log.warning("WVIC temp page: month header not found")
        return {}
    month, year = _MONTHS[m.group(1)], int(m.group(2))

    latest: dict = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>|&nbsp;?", " ", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if len(cells) < 11:
            continue
        try:
            day = int(cells[1])
        except ValueError:
            continue
        for idx, gid in WVIC_TEMP_COLUMNS.items():
            try:
                temp = float(cells[idx].replace(",", ""))
            except ValueError:
                continue
            if 32.0 <= temp <= 95.0:  # physical sanity for °F river water
                latest[gid] = {
                    "temp_f": temp,
                    "date": f"{year}-{month:02d}-{day:02d}",
                }
    return latest


# ---------------------------------------------------------------------------
# U.S. Drought Monitor: county drought status (weekly)
# ---------------------------------------------------------------------------

USDM_URL = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"

# Worst-first, so the summary can name the most severe class present.
DROUGHT_CLASSES = [
    ("d4", "D4", "exceptional drought"),
    ("d3", "D3", "extreme drought"),
    ("d2", "D2", "severe drought"),
    ("d1", "D1", "moderate drought"),
    ("d0", "D0", "abnormally dry"),
]

COUNTY_NAMES = {
    "055067": "Langlade", "055069": "Lincoln", "055073": "Marathon",
    "055085": "Oneida", "055097": "Portage", "055115": "Shawano",
    "055119": "Taylor", "055141": "Wood",
}


def fetch_drought() -> dict | None:
    """
    Drought status for the coverage area from the U.S. Drought Monitor.
    Published weekly (map dated Tuesday, released Thursday), so this is
    context rather than live data — it matters most in the low-water
    months when readers are asking why the rivers are down.

    Returns {map_date, worst_class, worst_label, counties:[{name, class,
    pct}], any_drought} or None. Attribution required: the USDM is
    produced by NDMC, USDA, and NOAA.
    """
    today = datetime.now()
    start = (today - timedelta(days=21)).strftime("%m/%d/%Y")
    end = today.strftime("%m/%d/%Y")

    counties = []
    map_date = None
    for same_code, name in COUNTY_NAMES.items():
        # Keys are SAME codes ("055073"); the USDM wants plain 5-digit FIPS.
        fips = same_code.lstrip("0")
        url = f"{USDM_URL}?aoi={fips}&startdate={start}&enddate={end}&statisticsType=1"
        rows = fetch_json(url, timeout=20)
        if not rows or not isinstance(rows, list):
            continue
        # Rows come newest-first; take the most recent map.
        row = rows[0]
        map_date = map_date or (row.get("mapDate") or "")[:10]
        worst = None
        pct = 0.0
        for key, label, _ in DROUGHT_CLASSES:
            try:
                value = float(row.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            # Below 1% of county area is noise, not a condition worth
            # telling readers about.
            if value >= 1.0:
                worst, pct = label, value
                break
        if worst:
            counties.append({"name": name, "class": worst, "pct": round(pct)})

    if not counties:
        # Every county fully "none" — no drought worth reporting.
        return {"map_date": map_date, "any_drought": False} if map_date else None

    order = [label for _, label, _ in DROUGHT_CLASSES]
    counties.sort(key=lambda c: (order.index(c["class"]), -c["pct"]))

    # The headline class must cover meaningful ground — at least 10% of
    # some county. Without this, a 2% sliver of D3 in one corner of Oneida
    # headlines "extreme drought" while the actual regional story is seven
    # counties wall-to-wall in D1 (bit us 2026-08-22).
    SIGNIFICANT_PCT = 10
    worst_class = next(
        (label for _, label, _ in DROUGHT_CLASSES
         if any(c["class"] == label and c["pct"] >= SIGNIFICANT_PCT for c in counties)),
        counties[0]["class"],  # nothing significant anywhere — fall back to the literal worst
    )
    worst_label = next(text for _, label, text in DROUGHT_CLASSES if label == worst_class)
    headline_rank = order.index(worst_class)

    # A sliver *worse* than the headline still deserves a footnote (shown
    # in the chip tooltip), just not the headline itself.
    sliver = next((c for c in counties if order.index(c["class"]) < headline_rank), None)

    return {
        "map_date": map_date,
        "any_drought": True,
        "worst_class": worst_class,
        "worst_label": worst_label,
        # Counties at (or worse than) the headline class — the UI names
        # these, so it can't imply a milder county is in a worse category.
        "worst_counties": [
            c["name"] for c in counties if order.index(c["class"]) <= headline_rank
        ],
        "sliver_note": (
            f"{sliver['class']} ({next(t for _, l, t in DROUGHT_CLASSES if l == sliver['class'])}) "
            f"touches {sliver['pct']}% of {sliver['name']} County"
            if sliver else None
        ),
        "counties": counties,
        "source_url": "https://droughtmonitor.unl.edu/",
    }


# ---------------------------------------------------------------------------
# Upstream rain: what's headed for each basin in the next 24 hours
# ---------------------------------------------------------------------------

# One representative headwater point per basin, and the gauges each one
# speaks for. Rain here is what shows up at those gauges tomorrow.
RAIN_BASINS = [
    {
        "key": "upper-wisconsin", "label": "Upper Wisconsin headwaters",
        "lat": 45.83, "lon": -89.55,
        "gauges": ["05391000", "05395000", "05394500"],
    },
    {
        "key": "wausau", "label": "Wausau-area basins",
        "lat": 45.05, "lon": -89.70,
        "gauges": ["05398000", "05398100", "05396000", "05396500", "05397500", "05400760"],
    },
    {
        "key": "eau-pleine", "label": "Big Eau Pleine basin",
        "lat": 44.88, "lon": -90.08,
        "gauges": ["05399500", "05363600"],
    },
    {
        "key": "wolf", "label": "Wolf River basin",
        "lat": 45.27, "lon": -88.73,
        "gauges": ["04074950", "04077400", "04077630", "04078500"],
    },
    {
        "key": "central-sands", "label": "Central Sands streams",
        "lat": 44.50, "lon": -89.40,
        "gauges": ["05400625", "04080798"],
    },
]

MM_PER_INCH = 25.4


def fetch_upstream_rain() -> dict:
    """
    Next-24h rainfall forecast for each basin's headwaters (Open-Meteo,
    one multi-point call). Answers the question the gauge readings can't:
    *why* the river is about to rise.

    Returns {gauge_id: {basin, label, inches, pop_pct}}.
    """
    lats = ",".join(str(b["lat"]) for b in RAIN_BASINS)
    lons = ",".join(str(b["lon"]) for b in RAIN_BASINS)
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}"
        f"&hourly=precipitation,precipitation_probability&forecast_days=2&timezone=UTC"
    )
    data = fetch_json(url, timeout=25)
    if not data:
        return {}
    locations = data if isinstance(data, list) else [data]
    if len(locations) != len(RAIN_BASINS):
        log.warning("Upstream rain: unexpected location count — skipping")
        return {}

    now = datetime.now(timezone.utc)
    out = {}
    for basin, loc in zip(RAIN_BASINS, locations):
        hourly = loc.get("hourly") or {}
        times = hourly.get("time") or []
        precip = hourly.get("precipitation") or []
        pops = hourly.get("precipitation_probability") or []

        total_mm = 0.0
        peak_pop = 0
        for i, t in enumerate(times):
            dt = _parse_iso(t if t.endswith("Z") else f"{t}:00Z" if len(t) == 13 else t + "Z")
            if not dt or dt < now or dt > now + timedelta(hours=24):
                continue
            try:
                total_mm += float(precip[i] or 0)
            except (IndexError, TypeError, ValueError):
                pass
            try:
                peak_pop = max(peak_pop, int(pops[i] or 0))
            except (IndexError, TypeError, ValueError):
                pass

        inches = round(total_mm / MM_PER_INCH, 2)
        for gid in basin["gauges"]:
            out[gid] = {
                "basin": basin["key"],
                "label": basin["label"],
                "inches": inches,
                "pop_pct": peak_pop,
            }
    return out


# ---------------------------------------------------------------------------
# Lake & pool levels (NWPS elevation gauges)
# ---------------------------------------------------------------------------

# Pool-elevation gauges. NB: their flood categories reference a different
# datum than the observed pool reading, which makes floodCategory read
# nonsense (Lake DuBay has reported a bogus "major") — we only ever show
# the elevation.
# Deliberately excludes EPLW3 (Big Eau Pleine pool): WVIC already reports
# that reservoir as "feet below maximum", and showing the same water twice
# with two different numbers just confuses readers.
LAKE_GAUGES = [
    {"lid": "DUBW3", "name": "Lake DuBay",
     "description": "Wisconsin River impoundment below Mosinee", "lat": 44.6650, "lon": -89.6508},
    {"lid": "WUUW3", "name": "Wisconsin River below Wausau Dam",
     "description": "Tailwater elevation in downtown Wausau", "lat": 44.9603, "lon": -89.6344},
]


def fetch_lake_levels() -> list[dict]:
    """
    Pool/tailwater elevations from NWPS. These read in feet above sea
    level (NGVD29), not gage height, so they are presented as elevations
    and never compared to the rivers' flood stages.
    """
    results = []
    for lake in LAKE_GAUGES:
        data = fetch_json(f"https://api.water.noaa.gov/nwps/v1/gauges/{lake['lid']}", timeout=20)
        observed = ((data or {}).get("status") or {}).get("observed") or {}
        value = observed.get("primary")
        unit = (observed.get("primaryUnit") or "").lower()
        if value is None or value <= -999 or not unit.startswith("ft"):
            continue
        results.append({
            "lid": lake["lid"],
            "name": lake["name"],
            "description": lake["description"],
            "lat": lake["lat"],
            "lon": lake["lon"],
            "elevation_ft": round(float(value), 2),
            "valid_time": observed.get("validTime"),
            "url": f"https://water.noaa.gov/gauges/{lake['lid'].lower()}",
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
    per species, ordered by best fit. Among equally good options the pick
    rotates on a per-gauge seed so neighboring cards with the same species
    mix don't all show the same three lures.
    """
    fishing = gauge_record.get("fishing") or {}
    species_list = fishing.get("species") or []
    if not species_list:
        return []

    if current_temp_f is None:
        current_temp_f = SEASONAL_WATER_TEMP_F.get(month, 50)

    # Deterministic per-gauge seed. Hash the id string — raw USGS ids in one
    # basin share digit patterns (all end in 0, several equal mod 3), so
    # arithmetic on the number itself doesn't separate neighboring gauges.
    gauge_id = str(gauge_record.get("id") or "")
    seed = int(hashlib.md5(gauge_id.encode()).hexdigest()[:8], 16)

    picks = []
    for species in species_list:
        scored = []
        for entry in LURE_DATABASE.get(species, []):
            in_season = month in entry["months"]
            t_low, t_high = entry["temp_range"]
            temp_ok = t_low <= current_temp_f <= t_high
            score = (2 if in_season else 0) + (2 if temp_ok else 0)
            if score > 0:
                scored.append((score, entry))
        if not scored:
            continue
        best = max(s for s, _ in scored)
        ties = [e for s, e in scored if s == best]
        pick = ties[seed % len(ties)]
        picks.append({"species": species, "lure": pick["lure"], "why": pick["why"], "score": best})

    picks.sort(key=lambda x: -x["score"])
    return [{"species": p["species"], "lure": p["lure"], "why": p["why"]} for p in picks[:3]]


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

        if current_cfs is None or len(history) < 8:
            continue

        # Compare current to ~24h ago: average the readings 20–28 hours
        # before the latest entry. Timestamp-based so it survives cadence
        # changes in the history sampling (currently 2-hour buckets).
        try:
            last_t = datetime.fromisoformat(history[-1]["timestamp"])
        except (KeyError, ValueError):
            continue
        old_flows = []
        for h in history:
            flow = h.get("streamflow_cfs")
            if flow is None:
                continue
            try:
                t = datetime.fromisoformat(h["timestamp"])
            except (KeyError, ValueError):
                continue
            age_h = (last_t - t).total_seconds() / 3600
            if 20 <= age_h <= 28:
                old_flows.append(flow)
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

    # Build summary sentences. With 17 gauges a full name list turns into a
    # wall of text \u2014 cap at three names and count the rest.
    def name_list(parts):
        if len(parts) <= 3:
            return ", ".join(parts)
        return ", ".join(parts[:3]) + f", and {len(parts) - 3} more"

    if flood_alerts:
        summaries.append("\u26a0\ufe0f " + "; ".join(flood_alerts) + ".")

    if rising:
        parts = [f"{n} (+{p}%)" for n, p in rising]
        summaries.append(f"Flows rising on {name_list(parts)} \u2014 expect reduced clarity.")

    if falling:
        parts = [f"{n} (-{p}%)" for n, p in falling]
        summaries.append(f"Flows dropping on {name_list(parts)} \u2014 clarity improving.")

    if stable and not rising and not falling:
        summaries.append("All gauges showing stable flows \u2014 consistent conditions.")
    elif len(stable) > 3:
        summaries.append(f"Flows steady on the other {len(stable)} gauges.")
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

    # Rating word — buckets match the widget UI (FishingConditions.jsx):
    # 7–8 renders as "Good" there, 9+ as "Excellent". Keep the article in sync.
    rating_word = ""
    if rating:
        rating_word = "poor" if rating <= 3 else "fair" if rating <= 6 else "good" if rating <= 8 else "excellent"

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

PUBLISHED_DATA_URL = (
    "https://rowanflynnpilot.github.io/wpr-river-conditions/data/river-data.json"
)


def fetch_published_gauges() -> dict:
    """
    The previous run's gauge records, used to carry forward values from
    upstreams that are intermittently unreachable.

    Primary source is the published payload — in CI that *is* the last
    successful run, since src/data/river-data.json is gitignored and never
    checked out. The local file fills any gaps so repeated local runs
    behave the same way (a no-op in CI, where it doesn't exist).

    Returns {gauge_id: gauge_record}.
    """
    out = {}
    data = fetch_json(PUBLISHED_DATA_URL, timeout=20)
    if data:
        out = {g["id"]: g for g in data.get("gauges", []) if g.get("id")}

    local_path = Path(__file__).parent.parent / "src" / "data" / "river-data.json"
    if local_path.exists():
        try:
            local = json.loads(local_path.read_text(encoding="utf-8"))
            for g in local.get("gauges", []):
                gid = g.get("id")
                if not gid:
                    continue
                if gid not in out:
                    out[gid] = g
                elif not out[gid].get("nwm_forecast") and g.get("nwm_forecast"):
                    # Published record exists but lost its forecast — keep
                    # the local one so a good run isn't discarded.
                    out[gid] = {**out[gid], "nwm_forecast": g["nwm_forecast"]}
        except (json.JSONDecodeError, OSError):
            pass

    if not out:
        log.info("  No previous payload available (first run)")
    return out


def main():
    log.info("Starting WPR River Conditions data fetch...")
    now = datetime.now(timezone.utc).isoformat()

    log.info("Loading last published payload (fallback source)...")
    published = fetch_published_gauges()

    log.info("Fetching upstream rain forecast...")
    upstream_rain = fetch_upstream_rain()
    if upstream_rain:
        wettest = max(upstream_rain.values(), key=lambda r: r["inches"])
        log.info(f"  Max basin: {wettest['label']} {wettest['inches']}in / 24h")

    # Daily WVIC water temps (one fetch covers Rothschild + Wisconsin Rapids)
    log.info("Fetching WVIC water temperatures...")
    wvic_temps = fetch_wvic_water_temp()
    if wvic_temps:
        log.info("  " + ", ".join(
            f"{gid}: {v['temp_f']:.0f}F ({v['date']})" for gid, v in wvic_temps.items()))

    # Fetch gauge data
    gauges_data = []
    for gauge in GAUGES:
        log.info(f"Fetching USGS data for {gauge['name']} ({gauge['id']})...")
        current = fetch_usgs_current(gauge["id"])

        # WVIC's daily reading fills the water-temp gap where USGS has no
        # sensor — set before lure suggestions so they use the real temp.
        wt = wvic_temps.get(gauge["id"])
        if wt and current.get("water_temp_f") is None:
            current["water_temp_f"] = wt["temp_f"]
            current["water_temp_source"] = "wvic"
            current["water_temp_date"] = wt["date"]
        history = fetch_usgs_history(gauge["id"], days=7)
        normal_flow = fetch_usgs_normal_flow(gauge["id"], current.get("streamflow_cfs"))
        if normal_flow:
            log.info(f"  Flow vs normal: {normal_flow['pct_of_median']}% of median ({normal_flow['class']})")

        # Fetch NWS flood category + forecast crest if available
        nws_data = {}
        nws_forecast = None
        if gauge.get("nws_lid"):
            log.info(f"  Fetching NWS NWPS data for {gauge['nws_lid']}...")
            nws_data = fetch_nws_flood_category(gauge["nws_lid"])
            nws_forecast = fetch_nws_forecast(gauge["nws_lid"])
            if nws_forecast:
                log.info(f"    Forecast: peak {nws_forecast['peak_stage']} {nws_forecast['units']} at {nws_forecast['peak_time']}")

        # NWS-sourced stage for gauges whose USGS real-time record is dead
        # (Wolf at Shawano): reading + hourly history from NWPS.
        if gauge.get("stage_from_nws"):
            nws_stage = nws_data.get("nws_observed_stage")
            nws_unit = (nws_data.get("nws_observed_unit") or "").lower()
            if (current.get("gage_height_ft") is None
                    and nws_stage is not None and nws_stage > -999
                    and nws_unit.startswith("ft")):
                current["gage_height_ft"] = round(float(nws_stage), 2)
                current["stage_source"] = "nws"
                if not current.get("timestamp"):
                    current["timestamp"] = nws_data.get("nws_valid_time")
            if not history:
                history = fetch_nws_stage_history(gauge["nws_lid"])

        # National Water Model flow forecast — the everyday "will it rise?"
        # signal (the NWS crest forecast above only appears in high water).
        nwm_forecast = None
        if gauge.get("nwm_reach"):
            flow_now = current.get("streamflow_cfs")
            nwm_forecast = fetch_nwm_forecast(gauge["nwm_reach"], flow_now)
            if nwm_forecast is None:
                # NOAA unreachable this cycle — reuse the last published
                # model run rather than blanking the forecast entirely.
                nwm_forecast = carry_forward_nwm(
                    (published.get(gauge["id"]) or {}).get("nwm_forecast"), flow_now
                )
                if nwm_forecast:
                    log.info(
                        f"  NWM: carried forward ({nwm_forecast.get('age_h', '?')}h old), "
                        f"{nwm_forecast.get('next24h_pct', 0):+d}%"
                    )
            elif nwm_forecast.get("next24h_pct") is not None:
                log.info(
                    f"  NWM: {nwm_forecast['next24h_pct']:+d}% over next "
                    f"{nwm_forecast['horizon_h']}h"
                )

        # Determine flood status using NWS thresholds.
        # Some gauges (Wolf at Shawano) report flow only through USGS —
        # fall back to the NWS-observed stage so thresholds still work.
        flood_status = "normal"
        stages = gauge.get("flood_stages")
        gage_ht = current.get("gage_height_ft")
        if gage_ht is None:
            nws_stage = nws_data.get("nws_observed_stage")
            nws_unit = (nws_data.get("nws_observed_unit") or "").lower()
            if nws_stage is not None and nws_stage > -999 and nws_unit.startswith("ft"):
                gage_ht = nws_stage

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
            "discontinued": gauge.get("discontinued", False),
            "nws_flood_category": nws_data.get("nws_flood_category"),
            "nws_forecast": nws_forecast,
            "nwm_forecast": nwm_forecast,
            "current": current,
            "history": history,
            "normal_flow": normal_flow,
            "upstream_rain": upstream_rain.get(gauge["id"]),
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
    log.info("Fetching NWS alerts for all gauge counties...")
    alerts = fetch_nws_alerts()

    # Fetch WVIC reservoirs
    log.info("Fetching WVIC reservoir data...")
    reservoirs = fetch_wvic_reservoirs()

    log.info("Fetching lake & pool elevations...")
    lakes = fetch_lake_levels()
    log.info(f"  {len(lakes)}/{len(LAKE_GAUGES)} reporting")

    log.info("Fetching drought monitor status...")
    drought = fetch_drought()
    if drought and drought.get("any_drought"):
        log.info(f"  {drought['worst_class']} ({drought['worst_label']}) in "
                 f"{len(drought['counties'])} county(ies)")

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

    # Surface the Rothschild water temp on the fishing panel too.
    if fishing_conditions is not None and wvic_temps.get("05398000"):
        wt = wvic_temps["05398000"]
        fishing_conditions["water_temp_f"] = wt["temp_f"]
        fishing_conditions["water_temp_station"] = "Wisconsin River at Rothschild"
        fishing_conditions["water_temp_date"] = wt["date"]

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
        "region": "Central Wisconsin",
        "gauges": gauges_data,
        "alerts": alerts,
        "reservoirs": reservoirs,
        "lakes": lakes,
        "drought": drought,
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

    # Summary — "reporting" matches the frontend's hasData (height OR flow)
    active_gauges = sum(
        1 for g in gauges_data
        if g["current"].get("gage_height_ft") is not None
        or g["current"].get("streamflow_cfs") is not None
    )
    log.info(
        f"Done: {active_gauges}/{len(gauges_data)} gauges reporting, "
        f"{len(alerts)} active alerts"
    )

    # Sanity gate: an (effectively) empty payload means an upstream outage,
    # not calm rivers — flood_status would default to "normal" and the site
    # would deploy an "All Clear" with no data behind it. Fail the run so CI
    # keeps the previous good deploy live.
    MIN_REPORTING_GAUGES = 5
    if active_gauges < MIN_REPORTING_GAUGES:
        log.error(
            f"Only {active_gauges} gauges reporting (< {MIN_REPORTING_GAUGES}) — "
            "refusing to publish a near-empty payload."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
