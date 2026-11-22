"""Tests for scripts/fetch_data.py.

Standard library only (unittest), matching the scraper: run with
`python -m unittest discover -s tests`. Fixtures in tests/fixtures are
trimmed recordings of real API responses from 2026-11-22.
"""

import json
import logging
import sys
import unittest
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import fetch_data as f  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
logging.disable(logging.CRITICAL)

BIG_EAU_PLEINE = "05399500"   # has a rain gauge
RED_RIVER = "04077630"        # has the only USGS water-temp sensor
RECORDED_AT = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def reset_batch():
    f._usgs_batch.update({"iv": {}, "stat": {}, "normals": {}, "source": None})


class NowCentral(unittest.TestCase):
    def at(self, *utc):
        fixed = datetime(*utc, tzinfo=timezone.utc)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed.astimezone(tz) if tz else fixed

        with mock.patch.object(f, "datetime", Clock):
            return f.now_central()

    def test_daylight_time_starts_second_sunday_of_march(self):
        self.assertEqual(self.at(2026, 3, 8, 7, 59).tzname(), "CST")
        self.assertEqual(self.at(2026, 3, 8, 8, 0).tzname(), "CDT")

    def test_daylight_time_ends_first_sunday_of_november(self):
        self.assertEqual(self.at(2026, 11, 1, 6, 59).tzname(), "CDT")
        self.assertEqual(self.at(2026, 11, 1, 7, 0).tzname(), "CST")

    def test_evening_in_wisconsin_is_still_today(self):
        # 23:30 UTC is 6:30 PM Central — the UTC runner must not roll the date.
        self.assertEqual(self.at(2026, 8, 29, 23, 30).date(), date(2026, 8, 29))
        self.assertEqual(self.at(2026, 8, 30, 3, 0).date(), date(2026, 8, 29))


class Retries(unittest.TestCase):
    USGS = "https://api.waterdata.usgs.gov/x"

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)  # mock HTTPErrors hold no socket
        f._retry_budget["left"] = 12
        self.sleep = mock.patch.object(f.time, "sleep").start()
        self.addCleanup(mock.patch.stopall)

    def urlopen(self, *outcomes):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": 1}'
        effects = [response if o == "ok" else HTTPError("u", o, "x", {}, None) for o in outcomes]
        return mock.patch.object(f, "urlopen", side_effect=effects).start()

    def test_recovers_after_transient_errors(self):
        opened = self.urlopen(503, 503, "ok")
        self.assertEqual(f.fetch_json(self.USGS), {"ok": 1})
        self.assertEqual(opened.call_count, 3)

    def test_gives_up_after_two_retries(self):
        opened = self.urlopen(503, 503, 503)
        self.assertIsNone(f.fetch_json(self.USGS))
        self.assertEqual(opened.call_count, 3)

    def test_does_not_retry_a_client_error(self):
        opened = self.urlopen(404, "ok")
        self.assertIsNone(f.fetch_json(self.USGS))
        self.assertEqual(opened.call_count, 1)

    def test_does_not_retry_other_hosts(self):
        opened = self.urlopen(503, "ok")
        self.assertIsNone(f.fetch_json("https://api.water.noaa.gov/x"))
        self.assertEqual(opened.call_count, 1)

    def test_stops_retrying_when_the_run_budget_is_spent(self):
        f._retry_budget["left"] = 0
        opened = self.urlopen(503, "ok")
        self.assertIsNone(f.fetch_json(self.USGS))
        self.assertEqual(opened.call_count, 1)


class UsgsModernApi(unittest.TestCase):
    def setUp(self):
        self.by_site = f._ogc_to_time_series(load("usgs_ogc_continuous.json")["features"])

    def current(self, site):
        return f._parse_usgs_current(self.by_site[site], site,
                                     precip_since=RECORDED_AT - timedelta(hours=24))

    def test_groups_features_by_site_and_parameter(self):
        self.assertEqual(set(self.by_site), {BIG_EAU_PLEINE, RED_RIVER})
        codes = {ts["variable"]["variableCode"][0]["value"] for ts in self.by_site[BIG_EAU_PLEINE]}
        self.assertEqual(codes, {"00060", "00065", "00045"})

    def test_readings_are_in_time_order(self):
        for series in self.by_site[RED_RIVER]:
            times = [v["dateTime"] for v in series["values"][0]["value"]]
            self.assertEqual(times, sorted(times))

    def test_current_reading(self):
        cur = self.current(BIG_EAU_PLEINE)
        self.assertEqual(cur["gage_height_ft"], 3.02)
        self.assertEqual(cur["streamflow_cfs"], 74.6)
        self.assertTrue(cur["timestamp"].startswith("2026-11-22T"))

    def test_water_temperature_is_converted_to_fahrenheit(self):
        cur = self.current(RED_RIVER)
        self.assertAlmostEqual(cur["water_temp_f"], cur["water_temp_c"] * 9 / 5 + 32, places=1)
        self.assertTrue(32 <= cur["water_temp_f"] <= 60)

    def test_matches_the_legacy_service_for_the_same_window(self):
        legacy = {}
        for ts in load("usgs_legacy_iv.json")["value"]["timeSeries"]:
            legacy.setdefault(ts["sourceInfo"]["siteCode"][0]["value"], []).append(ts)
        for site in (BIG_EAU_PLEINE, RED_RIVER):
            new = self.current(site)
            old = f._parse_usgs_current(legacy[site], site)
            for key in ("gage_height_ft", "streamflow_cfs", "water_temp_f"):
                self.assertEqual(new.get(key), old.get(key), f"{site} {key}")

    def test_discontinued_series_are_dropped(self):
        feature = {"properties": {
            "monitoring_location_id": "USGS-05363600", "parameter_code": "00060",
            "time": "2026-11-22T17:00:00+00:00", "value": "40",
            "qualifier": ["BACKWATER", "DISCONTINUED"], "time_series_id": "a"}}
        self.assertEqual(f._ogc_to_time_series([feature]), {})

    def test_newest_series_wins_when_a_sensor_was_replaced(self):
        def feat(series, when, value):
            return {"properties": {
                "monitoring_location_id": "USGS-1", "parameter_code": "00065",
                "time": when, "value": value, "qualifier": None, "time_series_id": series}}
        by_site = f._ogc_to_time_series([
            feat("old", "2026-11-20T00:00:00+00:00", "1.0"),
            feat("new", "2026-11-22T00:00:00+00:00", "2.0"),
        ])
        self.assertEqual(f._parse_usgs_current(by_site["1"], "1")["gage_height_ft"], 2.0)

    def test_paging_follows_next_links_and_fails_whole_on_a_bad_page(self):
        page1 = {"features": [1], "links": [{"rel": "next", "href": "https://next"}]}
        page2 = {"features": [2], "links": []}
        with mock.patch.object(f, "fetch_json", side_effect=[page1, page2]):
            self.assertEqual(f._fetch_ogc_items("continuous", {}), [1, 2])
        with mock.patch.object(f, "fetch_json", side_effect=[page1, None]):
            self.assertIsNone(f._fetch_ogc_items("continuous", {}))

    def test_api_key_header_only_when_configured(self):
        with mock.patch.dict(f.os.environ, {"USGS_API_KEY": " abc "}):
            self.assertEqual(f._usgs_api_headers(), {"X-Api-Key": "abc"})
        with mock.patch.dict(f.os.environ, {}, clear=True):
            self.assertEqual(f._usgs_api_headers(), {})


class UsgsParsing(unittest.TestCase):
    @staticmethod
    def series(code, *readings):
        return {"variable": {"variableCode": [{"value": code}]},
                "values": [{"value": [
                    {"value": v, "dateTime": t, "qualifiers": q} for v, t, q in readings]}]}

    def test_zero_is_a_reading_not_missing(self):
        cur = f._parse_usgs_current([self.series("00060", ("0", "2026-07-01T10:00:00+00:00", []))], "x")
        self.assertEqual(cur["streamflow_cfs"], 0.0)

    def test_negative_sentinel_is_missing(self):
        cur = f._parse_usgs_current([self.series("00060", ("-999999", "2026-07-01T10:00:00+00:00", []))], "x")
        self.assertIsNone(cur["streamflow_cfs"])

    def test_ice_qualifier_flags_the_gauge_and_keeps_other_readings(self):
        when = "2027-01-10T16:00:00+00:00"
        cur = f._parse_usgs_current([
            self.series("00060", ("-999999", when, ["ICE"])),
            self.series("00065", ("4.21", when, [])),
        ], "x")
        self.assertTrue(cur["ice_affected"])
        self.assertIsNone(cur["streamflow_cfs"])
        self.assertEqual(cur["gage_height_ft"], 4.21)

    def test_non_numeric_placeholder_does_not_lose_the_gauge(self):
        when = "2027-01-10T16:00:00+00:00"
        cur = f._parse_usgs_current([
            self.series("00060", ("Ice", when, [])),
            self.series("00065", ("4.21", when, [])),
        ], "x")
        self.assertTrue(cur["ice_affected"])
        self.assertEqual(cur["gage_height_ft"], 4.21)

    def test_precipitation_total_only_counts_the_last_24_hours(self):
        rain = self.series(
            "00045",
            ("1.00", "2026-11-20T12:00:00+00:00", []),   # two days ago
            ("0.25", "2026-11-22T06:00:00+00:00", []),
            ("0.50", "2026-11-22T12:00:00+00:00", []),
        )
        since = datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)
        self.assertEqual(f._parse_usgs_current([rain], "x", precip_since=since)["precip_24h_in"], 0.75)
        self.assertEqual(f._parse_usgs_current([rain], "x")["precip_24h_in"], 1.75)

    def test_history_is_bucketed_to_two_hours_and_sorted(self):
        reset_batch()
        f._usgs_batch["iv"][BIG_EAU_PLEINE] = f._ogc_to_time_series(
            load("usgs_ogc_continuous.json")["features"])[BIG_EAU_PLEINE]
        history = f.fetch_usgs_history(BIG_EAU_PLEINE)
        reset_batch()
        self.assertTrue(10 <= len(history) <= 13)   # 24h of readings
        self.assertEqual(history, sorted(history, key=lambda h: h["timestamp"]))
        self.assertTrue(all("gage_height_ft" in h and "streamflow_cfs" in h for h in history))


class NormalFlow(unittest.TestCase):
    TODAY = datetime(2026, 11, 22, 12, 0)

    def setUp(self):
        reset_batch()
        self.addCleanup(reset_batch)
        mock.patch.object(f, "now_central", return_value=self.TODAY).start()
        self.addCleanup(mock.patch.stopall)

    def test_modern_statistics_api(self):
        with mock.patch.object(f, "fetch_json", return_value=load("usgs_normals.json")):
            self.assertTrue(f._prefetch_usgs_normals([BIG_EAU_PLEINE, RED_RIVER]))
        normal = f.fetch_usgs_normal_flow(BIG_EAU_PLEINE, 74.6)
        self.assertEqual(normal["class"], "normal")
        self.assertEqual(normal["median_cfs"], 41)
        self.assertEqual((normal["typical_low_cfs"], normal["typical_high_cfs"]), (23, 85))

    def test_legacy_statistics_service_agrees(self):
        with mock.patch.object(f, "fetch_json", return_value=load("usgs_normals.json")):
            f._prefetch_usgs_normals([BIG_EAU_PLEINE, RED_RIVER])
        modern = {g: f.fetch_usgs_normal_flow(g, 100.0) for g in (BIG_EAU_PLEINE, RED_RIVER)}
        reset_batch()
        f._usgs_batch["stat"].update(
            f._split_stat_rdb((FIXTURES / "usgs_legacy_stat.rdb").read_text(encoding="utf-8")))
        for gauge, new in modern.items():
            old = f.fetch_usgs_normal_flow(gauge, 100.0)
            self.assertEqual(new["class"], old["class"])
            self.assertAlmostEqual(new["median_cfs"], old["median_cfs"], delta=old["median_cfs"] * 0.02)

    def test_site_without_statistics_makes_no_extra_request(self):
        with mock.patch.object(f, "fetch_json", return_value={"features": [], "next": None}):
            f._prefetch_usgs_normals(["99999999"])
        with mock.patch.object(f, "fetch_text") as fetch_text:
            self.assertIsNone(f.fetch_usgs_normal_flow("99999999", 50.0))
            fetch_text.assert_not_called()

    def test_no_flow_reading_means_no_comparison(self):
        self.assertIsNone(f.fetch_usgs_normal_flow(BIG_EAU_PLEINE, None))

    def test_flow_classes_follow_the_percentile_bands(self):
        bands = dict(p10=10, p25=25, p75=75, p90=90)
        self.assertEqual(f._flow_class(5, **bands), "much_below")
        self.assertEqual(f._flow_class(20, **bands), "below")
        self.assertEqual(f._flow_class(50, **bands), "normal")
        self.assertEqual(f._flow_class(80, **bands), "above")
        self.assertEqual(f._flow_class(95, **bands), "much_above")


class Prefetch(unittest.TestCase):
    def setUp(self):
        reset_batch()
        self.addCleanup(reset_batch)

    def test_falls_back_to_legacy_when_the_modern_api_fails(self):
        with mock.patch.object(f, "_fetch_ogc_items", return_value=None), \
             mock.patch.object(f, "_prefetch_usgs_normals", return_value=True), \
             mock.patch.object(f, "fetch_json", return_value=load("usgs_legacy_iv.json")):
            f.prefetch_usgs([BIG_EAU_PLEINE, RED_RIVER, "05396500"])
        self.assertEqual(f._usgs_batch["source"], "legacy")
        self.assertTrue(f._usgs_batch["iv"][BIG_EAU_PLEINE])
        # A gauge the service has nothing for is recorded as empty, not missing.
        self.assertEqual(f._usgs_batch["iv"]["05396500"], [])

    def test_uses_the_modern_api_when_it_answers(self):
        features = load("usgs_ogc_continuous.json")["features"]
        with mock.patch.object(f, "_fetch_ogc_items", return_value=features), \
             mock.patch.object(f, "_prefetch_usgs_normals", return_value=True):
            f.prefetch_usgs([BIG_EAU_PLEINE, RED_RIVER])
        self.assertEqual(f._usgs_batch["source"], "ogc")
        self.assertEqual(f.fetch_usgs_current(BIG_EAU_PLEINE)["gage_height_ft"], 3.02)


class Wvic(unittest.TestCase):
    def test_reservoir_levels(self):
        with mock.patch.object(f, "fetch_json", return_value=load("wvic_reservoirs.json")):
            reservoirs = {r["slug"]: r for r in f.fetch_wvic_reservoirs()}
        self.assertEqual(reservoirs["rainbow"]["feet_below_max"], -5.61)
        self.assertTrue(all(reservoirs[s]["has_data"] for s in
                            ("rainbow", "willow", "rice", "spirit", "eau-pleine")))
        self.assertFalse(reservoirs["lake-wausau"]["has_data"])

    def test_water_temperature(self):
        with mock.patch.object(f, "fetch_json", return_value=load("wvic_flow_temp.json")):
            temps = f.fetch_wvic_water_temp()
        self.assertEqual(temps["05398000"], {"temp_f": 43.0, "date": "2026-11-22"})
        self.assertIn("05400760", temps)

    def test_placeholder_for_the_coming_day_is_skipped(self):
        series = {"header": {"missVal": "-999.999"}, "events": [
            {"date": "2026-11-22", "value": "5.61", "flag": "0"},
            {"date": "2026-11-23", "value": "-999.999", "flag": "8"}]}
        self.assertEqual(f._fews_latest(series), (5.61, "2026-11-22"))

    def test_service_failure_leaves_reservoirs_without_data(self):
        with mock.patch.object(f, "fetch_json", return_value=None):
            self.assertFalse(any(r["has_data"] for r in f.fetch_wvic_reservoirs()))


class Seasons(unittest.TestCase):
    def test_inland_trout(self):
        self.assertEqual(f.species_season("Brook Trout", date(2026, 10, 15)), "open")
        self.assertEqual(f.species_season("Brook Trout", date(2026, 10, 16)), "closed")
        self.assertEqual(f.species_season("Brown Trout", date(2027, 1, 1)), "closed")
        self.assertEqual(f.species_season("Brown Trout", date(2027, 1, 2)), "early_trout")
        self.assertEqual(f.species_season("Brown Trout", date(2027, 4, 30)), "early_trout")
        self.assertEqual(f.species_season("Brown Trout", date(2027, 5, 1)), "open")

    def test_spring_game_fish_closure(self):
        self.assertEqual(f.species_season("Walleye", date(2027, 3, 7)), "open")
        self.assertEqual(f.species_season("Walleye", date(2027, 3, 8)), "closed")
        self.assertEqual(f.species_season("Walleye", date(2027, 4, 30)), "closed")
        self.assertEqual(f.species_season("Walleye", date(2027, 5, 1)), "open")

    def test_musky(self):
        self.assertEqual(f.species_season("Musky", date(2026, 12, 31)), "open")
        self.assertEqual(f.species_season("Musky", date(2027, 1, 1)), "closed")
        self.assertEqual(f.species_season("Musky", date(2027, 5, 28)), "closed")
        self.assertEqual(f.species_season("Musky", date(2027, 5, 29)), "open")

    def test_panfish_are_always_open(self):
        self.assertEqual(f.species_season("Panfish", date(2027, 3, 20)), "open")


class Lures(unittest.TestCase):
    def picks(self, species, temp, day):
        return f.compute_lure_suggestions({"id": "05394500", "fishing": {"species": species}}, temp, day)

    def test_no_trout_lures_after_the_season_closes(self):
        self.assertEqual(self.picks(["Brook Trout", "Brown Trout"], 43.0, date(2026, 11, 22)), [])

    def test_early_trout_season_is_flagged_and_excludes_live_bait(self):
        picks = self.picks(["Brook Trout", "Brown Trout", "Rainbow Trout"], 44.0, date(2027, 4, 10))
        self.assertTrue(picks)
        self.assertTrue(all(p["note"] == f.EARLY_TROUT_NOTE for p in picks))
        self.assertFalse(any("worm" in p["lure"].lower() for p in picks))

    def test_a_lure_is_only_offered_in_its_months(self):
        for day in (date(2026, 1, 15), date(2026, 7, 15), date(2026, 11, 15)):
            for pick in self.picks(list(f.LURE_DATABASE), 55.0, day):
                entry = next(e for e in f.LURE_DATABASE[pick["species"]] if e["lure"] == pick["lure"])
                self.assertIn(day.month, entry["months"], f"{pick['lure']} on {day}")

    def test_at_most_three_picks_and_no_internal_score(self):
        picks = self.picks(list(f.LURE_DATABASE), 70.0, date(2026, 7, 10))
        self.assertEqual(len(picks), 3)
        self.assertTrue(all("score" not in p for p in picks))


class Recreation(unittest.TestCase):
    ROTHSCHILD = "05398000"

    def test_cold_water_replaces_the_rating_and_drops_tubing(self):
        self.assertEqual(f.compute_recreation_status(self.ROTHSCHILD, 2570, 43.0, 11), {"kayaking": "cold"})

    def test_warm_water_rates_by_flow(self):
        self.assertEqual(f.compute_recreation_status(self.ROTHSCHILD, 4000, 72.0, 7),
                         {"kayaking": "ideal", "tubing": "ideal"})

    def test_dangerous_flow_outranks_cold(self):
        self.assertEqual(f.compute_recreation_status(self.ROTHSCHILD, 18000, 40.0, 11),
                         {"kayaking": "dangerous"})

    def test_month_stands_in_when_there_is_no_temperature(self):
        self.assertEqual(f.compute_recreation_status("05397500", 105, None, 11), {"kayaking": "cold"})
        self.assertEqual(f.compute_recreation_status("05397500", 105, None, 7), {"kayaking": "low"})

    def test_unrated_gauge(self):
        self.assertIsNone(f.compute_recreation_status("05394500", 150, 60.0, 7))


class Narrative(unittest.TestCase):
    def test_flow_change_wording(self):
        cases = {16: "+16%", 99: "+99%", 100: "2×", 140: "2.4×", 871: "9.7×", 1150: "13×", -70: "-70%"}
        for pct, text in cases.items():
            self.assertEqual(f._fmt_flow_change(pct), text)

    @staticmethod
    def gauge(name, now, day_ago):
        start = datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc)
        history = [{"timestamp": (start + timedelta(hours=2 * i)).isoformat(),
                    "streamflow_cfs": day_ago if i < 6 else now} for i in range(13)]
        return {"short_name": name, "flood_status": "normal",
                "current": {"streamflow_cfs": now}, "history": history}

    def test_summary_names_risers_with_the_shared_wording(self):
        summary = f.compute_conditions_summary([
            self.gauge("Big Rib River", 936, 72),
            self.gauge("Red River", 115, 114),
        ])
        self.assertIn("Big Rib River (13×)", summary[0])
        self.assertIn("Stable on Red River", summary[1])

    def test_all_steady(self):
        summary = f.compute_conditions_summary([self.gauge("Red River", 115, 114)])
        self.assertEqual(summary, ["All gauges showing stable flows — consistent conditions."])


if __name__ == "__main__":
    unittest.main()
