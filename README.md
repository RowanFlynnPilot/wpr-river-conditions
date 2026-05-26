# WPR River & Lake Conditions

A real-time river, flood, and fishing conditions dashboard for central Wisconsin, built and maintained by [Wausau Pilot & Review](https://wausaupilotandreview.com).

**Live widget:** **https://rowanflynnpilot.github.io/wpr-river-conditions/**

The widget is embedded as an iframe on the WP&R website and updates every 30 minutes from official USGS, NWS, NOAA, USNO, and WVIC data sources.

---

## What it does

Combines half a dozen public data feeds into a single, branded, mobile-friendly page covering:

- **Real-time river levels** at 12 USGS stream gauges across the central Wisconsin corridor (Merrill → Wausau → Wisconsin Rapids, plus tributaries and destination trout streams)
- **NWS flood thresholds** (action / minor / moderate / major) with auto-computed status badges and a "Current Status" hero headline
- **NWS flood forecast crests** when active, showing predicted peak stage and timing
- **Active NWS weather alerts** for Marathon County — flood, severe weather, winter storms, fire weather, wind, heat
- **5 WVIC reservoirs** with current "feet below maximum" levels
- **Interactive maps** — Marathon County overview with color-coded gauge pins, plus per-gauge boat-launch maps
- **Fishing conditions** — barometric pressure, wind, UV, sunrise/sunset, moon phase, solunar feeding windows, day rating
- **Lure picks** per gauge based on current water temp and month
- **Auto-generated daily fishing summary** in AP editorial style
- **5-day weather forecast**, recent observed precipitation, and a "Best day this week" picker
- **"Share Your Catch"** community form so anglers can submit photos and reports

Each gauge card includes a 7-day sparkline, current readings (gage height, streamflow, water temperature when available), water clarity estimate, recreation status (kayaking, tubing, paddling) when applicable, and links to the underlying USGS and NWS pages.

---

## Embed it

The widget is designed to be dropped into any WordPress post or HTML page as an iframe:

```html
<iframe
  src="https://rowanflynnpilot.github.io/wpr-river-conditions/"
  width="100%"
  height="900"
  frameborder="0"
  title="Central Wisconsin River & Lake Conditions"
></iframe>
```

The widget posts its own height to the parent window via `postMessage` so the iframe can auto-resize.

---

## How it works

```
                                  every 30 min (cron)
  ┌─────────────────────────────────────────────────────┐
  │                                                     ▼
┌─┴──────────────────┐    ┌─────────────────────┐    ┌──────────────┐
│  GitHub Actions    │───▶│  scripts/           │───▶│  src/data/   │
│  (cron + push)     │    │  fetch_data.py      │    │  river-data  │
└────────────────────┘    │                     │    │  .json       │
                          │  Fetches from:      │    └──────┬───────┘
                          │  • USGS Water       │           │
                          │  • NWS NWPS         │           ▼
                          │  • NWS Alerts       │    ┌──────────────┐
                          │  • Open-Meteo       │    │  Vite build  │
                          │  • USNO             │    │  → dist/     │
                          │  • WVIC (scrape)    │    └──────┬───────┘
                          └─────────────────────┘           │
                                                            ▼
                                                    ┌──────────────┐
                                                    │ GitHub Pages │
                                                    └──────┬───────┘
                                                           │
                                              embedded iframe
                                                           │
                                                           ▼
                                                ┌────────────────────┐
                                                │ wausaupilotand     │
                                                │ review.com         │
                                                └────────────────────┘
```

The frontend is a small React + Vite SPA. There is no backend server — every 30 minutes a GitHub Action runs the Python scraper, regenerates `river-data.json`, builds the React app, and publishes the static bundle to GitHub Pages. The widget then fetches that JSON file on load.

The Python scraper is a single file (~1,800 lines) with no dependencies beyond the Python standard library. The React app's only third-party runtime dependency is [Leaflet](https://leafletjs.com/) for the maps.

---

## Data sources

| Source | Used for | Auth |
|---|---|---|
| [USGS Water Services](https://waterservices.usgs.gov/) | Stream gauge readings (height, flow, temp, precip) | None |
| [NWS NWPS](https://water.noaa.gov/) | Flood thresholds, observed flood category, forecast crests | None |
| [NWS Alerts API](https://api.weather.gov/) | Active weather alerts for Marathon County | None |
| [WVIC](https://wvic.com/) | Reservoir levels (Rainbow, Willow, Spirit, Rice, Eau Pleine) | None (HTML scrape) |
| [Open-Meteo](https://open-meteo.com/) | Weather forecast, pressure, wind, UV | None |
| [U.S. Naval Observatory](https://aa.usno.navy.mil/) | Sunrise/sunset, moonrise/set/transit, moon phase | None |
| [Web3Forms](https://web3forms.com/) | Share Your Catch form submissions | Public access key |
| [Cloudflare Web Analytics](https://www.cloudflare.com/web-analytics/) | Pageview/session analytics | Public token |

All upstream data is provisional and subject to revision. The widget displays a disclaimer urging users to consult official sources for safety decisions.

---

## Local development

Requires **Node 20+** and **Python 3.10+**.

```bash
# Install dependencies
npm install

# Pull fresh data (writes to src/data/river-data.json)
python scripts/fetch_data.py

# Start dev server (http://localhost:5173/wpr-river-conditions/)
npm run dev

# Production build → dist/
npm run build
```

The Python scraper has no third-party dependencies — pure standard library. Anything more exotic would mean adding a `requirements.txt` and slowing the GitHub Action by ~30 seconds, so we've intentionally avoided it.

---

## Deployment

Deployment is fully automated:

- **Pushes to `main`** trigger `Fetch Data & Deploy` (`.github/workflows/deploy.yml`) which runs the scraper, builds the app, and publishes to GitHub Pages.
- **A cron schedule** runs the same workflow every 30 minutes (10:00–04:30 UTC daily) to refresh data even without code pushes.

No manual deploy step.

---

## Project structure

```
wpr-river-conditions/
├── .github/workflows/deploy.yml   # Cron + on-push deploy
├── docs/
│   └── sponsor-rate-card.md       # Sponsor pitch document
├── public/
│   ├── .nojekyll                  # Skip Jekyll on GH Pages
│   └── data/
│       ├── river-data.json        # Generated each cron run
│       └── sponsor.json           # Sponsor config (drives sponsor strip)
├── scripts/
│   └── fetch_data.py              # The whole scraper
├── src/
│   ├── App.jsx                    # Top-level layout
│   ├── index.css                  # All styles
│   ├── main.jsx                   # React entry
│   ├── assets/                    # Logo
│   ├── components/                # 17 focused components
│   ├── data/                      # Local copy of generated JSON (gitignored)
│   └── utils/
│       └── analytics.js           # Provider-agnostic event tracker
├── CLAUDE.md                      # AI assistant instructions
├── README.md                      # This file
├── index.html                     # Vite entry
├── package.json
└── vite.config.js                 # base: '/wpr-river-conditions/'
```

For more granular documentation — the data schema, component responsibilities, sponsor workflow, analytics events — see [`CLAUDE.md`](CLAUDE.md).

---

## Sponsorship

The widget supports several sponsorship slot types (presenting sponsor, section sponsor, rotator, tip sponsor) wired through [`public/data/sponsor.json`](public/data/sponsor.json). When no active sponsor is configured, the strip displays a "Reach out" CTA that opens a pre-filled mailto.

See [`docs/sponsor-rate-card.md`](docs/sponsor-rate-card.md) for the full pitch document: tiers, slot specs, suggested pricing, and the audience-snapshot template that gets populated after each month of Cloudflare analytics data.

For sponsorship inquiries, contact **Rowan Flynn** at [rowan.flynn@wausaupilotandreview.com](mailto:rowan.flynn@wausaupilotandreview.com).

---

## For other newsrooms

If you run a local news outlet in another region and want to adapt this for your own area, the entire codebase is here. The bulk of the customization lives in two places:

1. **`GAUGES` list** in [`scripts/fetch_data.py`](scripts/fetch_data.py) — add the USGS site numbers and NWS LIDs for gauges in your coverage area. USGS site numbers are 8-digit strings; NWS LIDs are 5-letter codes ending in your state's NWS letter.
2. **`FISHING_REFERENCE` dict** in the same file — add species, tips, regulations, and access points per gauge.

Branding (WPR logo, teal accent color, "Wausau Pilot & Review" text) is centralized in `src/assets/`, `src/index.css` (`:root` CSS variables), and `src/App.jsx` (chrome bar). A find-and-replace plus one logo swap covers the bulk of it.

The architecture (Python scraper → JSON → static React → GitHub Pages, all free, no backend, no API keys) is genuinely the cheapest viable way to ship something like this — total ongoing cost is $0 plus whatever your domain costs.

---

## Disclaimer

Data shown on this widget is provisional and may be revised by the originating agencies. Do not use this widget as the sole basis for safety decisions. Always consult official NWS, USGS, and local emergency-management sources during flood events. Do not drive through flooded roads.

---

*Built with care for the Central Wisconsin community. Last reviewed: May 2026.*
