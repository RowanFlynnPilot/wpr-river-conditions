# Sponsor a Wausau Pilot & Review widget

> **Status:** Draft. Audience numbers are placeholders to be populated after ~30 days of Cloudflare Web Analytics data. Pricing is suggested starting points — adjust to your local market and existing WPR ad rates.

## The Wausau Pilot & Review River & Lake Conditions widget

Real-time river levels, flood status, fishing forecasts, and reservoir data for central Wisconsin. Updates every 30 minutes from official USGS, NWS, WVIC, and NOAA sources.

**Live widget:** https://rowanflynnpilot.github.io/wpr-river-conditions/
**Embedded on:** wausaupilotandreview.com

### Why sponsors choose this widget

- **Civic-service adjacency.** Anglers, paddlers, homeowners near floodplains, and weekend boaters all check this when planning their day. Your brand sits next to data that affects real decisions.
- **High repeat visits.** Unlike a one-time article, conditions data is checked daily during fishing/boating season and during flood events.
- **Hyper-local intent.** Visitors are in Marathon County or planning a trip here. No ad-tech waste.
- **Editorial trust.** Surrounded by data from the USGS, National Weather Service, and the Wisconsin Valley Improvement Company — your sponsorship inherits that credibility.

---

## Audience snapshot

> *Numbers below are placeholders. Replace with real Cloudflare Web Analytics metrics after ~30 days of data collection.*

| Metric | Last 30 days | Notes |
|---|---:|---|
| Page views | **[ ___ ]** | Includes views on the wausaupilotandreview.com embed |
| Unique visitors | **[ ___ ]** | |
| Avg. session duration | **[ ___ ]** | |
| Mobile / desktop split | **[ __ ]% / [ __ ]%** | |
| Top referring pages | **[ list ]** | Most likely the WPR homepage + the river conditions article |
| Geographic concentration | **[ __ ]% Wisconsin** | Marathon + adjacent counties |

### Seasonality
Traffic spikes around three predictable events:
- **Spring snowmelt / flood season** (March–May) — public-safety lookups
- **Fishing opener weekend** (first Saturday in May) — record traffic
- **Active flood warnings** (any time) — 3–10× normal volume

---

## Sponsorship packages

### 🥇 Presenting Sponsor — *one slot*
The most prominent placement. The top strip on every view, every device.

- **Placement:** Strip directly under the WPR chrome bar, top of widget
- **Format:** Logo (optional) + "Brought to you by [Your Business] — [your tagline]" + clickable link
- **Color takeover (optional):** Sponsor brand color replaces the widget's teal accent
- **Exclusivity:** No other sponsor in this slot; rotates monthly or quarterly
- **Reporting:** Monthly impressions + click-through report
- **Suggested rate:** **$[ ___ ] / month** (3-month minimum recommended)

### 🥈 Section Sponsor — *up to 4 slots*
Sponsor a specific section that matches your business category.

| Section | Best-fit advertisers |
|---|---|
| **Fishing Conditions** | Bait shops, guide services, marine dealers, sporting goods |
| **Weather Forecast** | HVAC, roofing, propane, lawn care |
| **Reservoirs** | Marinas, boat storage, lake real estate, fishing resorts |
| **Upcoming Events** | Outfitters, lodges, tourism bureaus, breweries |

- **Format:** Small "Powered by [Logo]" footer on the chosen section
- **Suggested rate:** **$[ ___ ] / month per section**

### 🥉 Featured Local Business rotator — *up to 5 slots*
A real card in the widget that rotates between sponsors on each page load.

- **Format:** Logo + 1-line description + clickable link
- **Best fit:** Any local business wanting consistent visibility without dominating
- **Suggested rate:** **$[ ___ ] / month** (5 slots, rotates evenly)

### 🎣 Tip Sponsor — *one slot per gauge*
Attribute the "Right now, try [lure]" tip on each gauge card to a tackle shop or guide.

- **Format:** "Tip from [Your Shop]" byline under the auto-generated lure suggestion
- **Best fit:** Bait & tackle shops, fishing guides
- **Suggested rate:** **$[ ___ ] / month per gauge** or **$[ ___ ] / month for all gauges**

---

## Slot specifications

| Slot | Image dimensions | File format | Max file size | Link rules |
|---|---|---|---:|---|
| Presenting sponsor logo | 60×18 px (or proportional, 2× for retina) | PNG or SVG (transparent bg) | 30 KB | `rel="noopener noreferrer sponsored"` |
| Color takeover accent | Hex color (e.g. `#0d7377`) | — | — | — |
| Section sponsor logo | 24×24 px (square) | PNG or SVG | 15 KB | Same |
| Featured rotator card | 320×120 px | PNG or JPG | 50 KB | Same |
| Tip sponsor byline | Text only (max 30 chars) | — | — | Same |

All outbound links carry UTM parameters (`utm_source=wpr-river&utm_medium=widget&utm_campaign=[sponsor-slug]`) so sponsors can attribute traffic in their own analytics.

---

## How impressions and clicks are tracked

The widget uses **Cloudflare Web Analytics**, a privacy-first analytics platform with no cookies and no consent banner required. Custom events fire on every sponsor interaction:

- `sponsor_click` — sponsor link clicked
- `sponsor_cta_click` — "Reach out" CTA clicked (proves the slot is engaging)
- `gauge_map_open` — gauge access-point map expanded
- (more events added as features grow)

Sponsors receive a monthly screenshot of their slot's performance. Read-only Cloudflare dashboard links are available on request.

---

## Onboarding workflow

1. Sponsor signs IO and provides creative (logo, tagline, link)
2. WPR edits `public/data/sponsor.json` (presenting) or the relevant config file (section/rotator)
3. Push to `main` — GitHub Actions auto-deploys in ~2 minutes
4. Confirmation screenshot sent to sponsor
5. Monthly performance reports sent on the 1st of each month

---

## Contact

**Rowan Flynn** — rowan.flynn@wausaupilotandreview.com

---

*Last updated: [DATE]. This document is a living draft. Pricing, slot specs, and audience numbers should be reviewed quarterly.*
