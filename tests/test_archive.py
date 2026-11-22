"""Tests for scripts/archive_history.py (stdlib unittest)."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import archive_history as a  # noqa: E402


def payload(history=None, forecast=None, reservoirs=None, flow=100.0,
            generated_at="2026-11-22T18:00:00+00:00"):
    return {
        "generated_at": generated_at,
        "gauges": [{
            "id": "05398000",
            "current": {"streamflow_cfs": flow},
            "history": history or [],
            "nwm_forecast": forecast,
        }],
        "reservoirs": reservoirs or [],
    }


def point(ts, height=1.0, flow=100.0):
    return {"timestamp": ts, "gage_height_ft": height, "streamflow_cfs": flow}


def rows(root, relative):
    with (Path(root) / relative).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class Archive(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_running_twice_changes_nothing(self):
        data = payload(history=[point("2026-11-22T16:00:00+00:00"), point("2026-11-22T14:00:00+00:00")])
        self.assertEqual(a.archive(data, self.root)["readings"], 2)
        before = (self.root / "readings/2026-11.csv").read_bytes()
        self.assertEqual(a.archive(data, self.root)["readings"], 0)
        self.assertEqual((self.root / "readings/2026-11.csv").read_bytes(), before)

    def test_a_later_reading_in_the_same_bucket_replaces_the_earlier_one(self):
        a.archive(payload(history=[point("2026-11-22T16:05:00+00:00", flow=100.0)]), self.root)
        a.archive(payload(history=[point("2026-11-22T17:55:00+00:00", flow=140.0)]), self.root)
        archived = rows(self.root, "readings/2026-11.csv")
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["bucket"], "2026-11-22T16:00Z")
        self.assertEqual(archived[0]["timestamp"], "2026-11-22T17:55Z")
        self.assertEqual(archived[0]["streamflow_cfs"], "140")

    def test_local_time_offsets_are_normalised_to_utc(self):
        a.archive(payload(history=[point("2026-11-22T10:00:00.000-06:00")]), self.root)
        self.assertEqual(rows(self.root, "readings/2026-11.csv")[0]["timestamp"], "2026-11-22T16:00Z")

    def test_readings_are_split_by_utc_month(self):
        a.archive(payload(history=[point("2026-11-30T23:00:00+00:00"), point("2026-12-01T01:00:00+00:00")]),
                  self.root)
        self.assertEqual(len(rows(self.root, "readings/2026-11.csv")), 1)
        self.assertEqual(len(rows(self.root, "readings/2026-12.csv")), 1)

    def test_empty_and_unparseable_points_are_skipped(self):
        data = payload(history=[
            point("2026-11-22T16:00:00+00:00", height=None, flow=None),
            point("not a time"),
            point("2026-11-22T16:00:00"),            # no timezone: can't place it
            point("2026-11-22T14:00:00+00:00", height=3.5, flow=None),
        ])
        self.assertEqual(a.archive(data, self.root)["readings"], 1)
        only = rows(self.root, "readings/2026-11.csv")[0]
        self.assertEqual((only["gage_height_ft"], only["streamflow_cfs"]), ("3.5", ""))

    def test_rows_stay_sorted_so_diffs_are_small(self):
        a.archive(payload(history=[point("2026-11-22T16:00:00+00:00")]), self.root)
        a.archive(payload(history=[point("2026-11-20T16:00:00+00:00")]), self.root)
        buckets = [r["bucket"] for r in rows(self.root, "readings/2026-11.csv")]
        self.assertEqual(buckets, sorted(buckets))

    def test_forecast_is_recorded_once_per_model_run(self):
        forecast = {"issued": "2026-11-22T15:00:00Z", "next24h_pct": -40, "horizon_h": 16,
                    "baseline": "observed"}
        a.archive(payload(forecast=forecast, flow=200.0), self.root)
        # A later scrape of the same model run must not overwrite the first.
        a.archive(payload(forecast=forecast, flow=150.0, generated_at="2026-11-22T18:30:00+00:00"), self.root)
        archived = rows(self.root, "forecasts/2026-11.csv")
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["observed_cfs"], "200")
        self.assertEqual(archived[0]["forecast_cfs"], "120")
        self.assertEqual(archived[0]["archived_at"], "2026-11-22T18:00Z")

    def test_carried_forward_forecasts_are_not_archived(self):
        forecast = {"issued": "2026-11-22T09:00:00Z", "next24h_pct": 10, "horizon_h": 8,
                    "baseline": "observed", "carried_forward": True}
        self.assertEqual(a.archive(payload(forecast=forecast), self.root)["forecasts"], 0)

    def test_model_baseline_forecast_has_no_absolute_flow(self):
        forecast = {"issued": "2026-11-22T15:00:00Z", "next24h_pct": 9, "horizon_h": 15, "baseline": "model"}
        a.archive(payload(forecast=forecast, flow=None), self.root)
        self.assertEqual(rows(self.root, "forecasts/2026-11.csv")[0]["forecast_cfs"], "")

    def test_reservoirs_keep_one_row_per_day(self):
        def res(level):
            return [{"slug": "rainbow", "has_data": True, "feet_below_max": level,
                     "last_updated": "2026-11-22T18:00:00+00:00"},
                    {"slug": "lake-wausau", "has_data": False, "feet_below_max": None, "last_updated": None}]
        a.archive(payload(reservoirs=res(-5.61)), self.root)
        a.archive(payload(reservoirs=res(-5.58)), self.root)
        archived = rows(self.root, "reservoirs/2026.csv")
        self.assertEqual(archived, [{"date": "2026-11-22", "slug": "rainbow", "feet_below_max": "-5.58"}])

    def test_manifest_lists_what_exists(self):
        a.archive(payload(history=[point("2026-11-22T16:00:00+00:00")]), self.root)
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["readings"], ["2026-11"])
        self.assertEqual(manifest["forecasts"], [])
        self.assertEqual(manifest["fields"]["readings"], a.READING_FIELDS)

    def test_number_formatting(self):
        self.assertEqual([a._num(v) for v in (936.0, 13.79, 0, None, 6.6)], ["936", "13.79", "0", "", "6.6"])


if __name__ == "__main__":
    unittest.main()
