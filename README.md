# River conditions archive

Long-term history for the WPR river conditions widget. The widget's own
payload only carries seven days; this branch keeps everything. It is written
by `scripts/archive_history.py` on the `main` branch after each data fetch.
Do not edit by hand: the next run rewrites any file it touches.

| Path | One row per | Columns |
|------|-------------|---------|
| `readings/YYYY-MM.csv` | gauge per 2-hour bucket (UTC) | `bucket, gauge_id, timestamp, gage_height_ft, streamflow_cfs` |
| `forecasts/YYYY-MM.csv` | gauge per National Water Model run | `issued, gauge_id, archived_at, observed_cfs, horizon_h, forecast_pct, forecast_cfs, baseline` |
| `reservoirs/YYYY.csv` | reservoir per day | `date, slug, feet_below_max` |
| `manifest.json` | — | which files exist, plus the column lists |

Notes:

- All times are UTC. `bucket` is the start of the 2-hour window; `timestamp`
  is the actual reading kept for it (the latest in the window).
- `gauge_id` is the USGS site number. Empty cells mean the gauge does not
  report that value.
- Wolf River at Shawano (`04077400`) readings come from the NWS sensor, not USGS.
- In `forecasts`, `forecast_cfs` is the model's flow `horizon_h` hours after
  `archived_at`, and `observed_cfs` is the gauge reading at `archived_at`.
  Compare `forecast_cfs` with the `readings` row for that later time to see
  how the forecast did.
- Data is provisional, as published by USGS, NWS and WVIC at the time.

Files are readable directly, for example:
`https://raw.githubusercontent.com/RowanFlynnPilot/wpr-river-conditions/data/manifest.json`
