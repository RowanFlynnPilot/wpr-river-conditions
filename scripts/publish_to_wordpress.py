#!/usr/bin/env python3
"""
WPR River & Lake Conditions — WordPress publisher.

Reads the data the scraper already writes (src/data/river-data.json and
daily-summary.json) and publishes a crawlable "Central Wisconsin River Levels &
Fishing Report" article to wausaupilotandreview.com via the WordPress REST API.

Why this exists: the React widget is embedded via an <iframe>, and iframe
content does NOT count toward the host page's SEO. This script puts the same
information on the WPR domain as real, server-rendered HTML so it can rank for
queries like "Wisconsin River flooding Wausau" and "central Wisconsin fishing
report". The interactive widget is embedded below the text for readers.

Design notes:
  * Upserts a SINGLE evergreen post identified by slug, so one stable URL
    accumulates search authority and is refreshed in place (no daily spam posts).
  * Only updates when conditions actually change, via a content signature
    embedded as an HTML comment — avoids needless writes every 30 min.
  * No third-party deps (stdlib urllib only), matching fetch_data.py.
  * Authenticates with a WordPress Application Password (core feature since WP
    5.6 — no plugin needed). Create one under Users -> Profile -> Application
    Passwords, then set the env vars below.

Environment variables (set as GitHub Actions secrets):
  WP_URL            e.g. https://wausaupilotandreview.com   (required to publish)
  WP_USER           WordPress username                       (required to publish)
  WP_APP_PASSWORD   Application Password (spaces are ignored)(required to publish)
  WP_POST_SLUG      optional, default 'central-wisconsin-river-fishing-report'
  WP_POST_STATUS    optional, default 'publish'  (use 'draft' for a dry first run)
  WP_CATEGORY_ID    optional, numeric category ID to file the post under

Usage:
  python scripts/publish_to_wordpress.py --dry-run   # build + preview, no network
  python scripts/publish_to_wordpress.py             # publish if creds present
  python scripts/publish_to_wordpress.py --force     # publish even if unchanged
"""

import argparse
import base64
import hashlib
import html
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wp-publish")

ROOT = Path(__file__).parent.parent
DATA_PATH = ROOT / "src" / "data" / "river-data.json"
SUMMARY_PATH = ROOT / "src" / "data" / "daily-summary.json"
PREVIEW_PATH = ROOT / "src" / "data" / "wp-report.html"

WIDGET_URL = "https://rowanflynnpilot.github.io/wpr-river-conditions/"
DEFAULT_SLUG = "central-wisconsin-river-fishing-report"
POST_TITLE = "Central Wisconsin River Levels & Fishing Report — Wisconsin River, Wolf River & Area Trout Streams"

STATUS_LABEL = {
    "normal": "Normal",
    "action": "Action Stage",
    "minor": "Minor Flooding",
    "moderate": "Moderate Flooding",
    "major": "Major Flooding",
}
STATUS_ORDER = ["major", "moderate", "minor", "action", "normal"]
SIG_RE = re.compile(r"<!--\s*wpr-sig:([0-9a-f]+)\s*-->")


# ---------------------------------------------------------------------------
# Data loading & small helpers
# ---------------------------------------------------------------------------

def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        log.warning("Could not read %s: %s", path, e)
        return None


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def rating_word(rating) -> str:
    if rating is None:
        return ""
    if rating <= 3:
        return "poor"
    if rating <= 5:
        return "fair"
    if rating <= 7:
        return "good"
    return "excellent"


def extract_summary(summary_json):
    """Pull the headline and body text out of the daily-summary HTML."""
    headline, body = "", ""
    if not summary_json:
        return headline, body
    html_str = summary_json.get("html", "")
    h = re.search(r'__headline">(.*?)</h3>', html_str, re.S)
    b = re.search(r'__body">(.*?)</p>', html_str, re.S)
    if h:
        headline = re.sub(r"<[^>]*>", "", h.group(1)).strip()
    if b:
        body = re.sub(r"<[^>]*>", "", b.group(1)).strip()
    return headline, body


def fmt_ct(iso_str) -> str:
    """Format an ISO timestamp as Central-time, human readable."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        # Convert to America/Chicago without zoneinfo dependency assumptions:
        try:
            from zoneinfo import ZoneInfo

            dt = dt.astimezone(ZoneInfo("America/Chicago"))
            tz = "CT"
        except Exception:
            tz = "UTC"
        return dt.strftime(f"%b %-d, %Y at %-I:%M %p {tz}") if os.name != "nt" else \
            dt.strftime(f"%b %d, %Y at %I:%M %p {tz}")
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Article rendering
# ---------------------------------------------------------------------------

def compute_signature(data) -> str:
    """Hash only the meaningful fields, so the post updates when conditions
    change but NOT merely because the timestamp ticked over."""
    gauges = data.get("gauges", [])
    parts = []
    for g in sorted(gauges, key=lambda x: x.get("id", "")):
        ht = g.get("current", {}).get("gage_height_ft")
        flow = g.get("current", {}).get("streamflow_cfs")
        ht_r = round(ht, 1) if isinstance(ht, (int, float)) else None
        flow_r = round(flow / 50.0) * 50 if isinstance(flow, (int, float)) else None
        parts.append(f"{g.get('id')}:{g.get('flood_status')}:{ht_r}:{flow_r}")
    fc = data.get("fishing_conditions") or {}
    parts.append(f"rating={fc.get('day_rating')}")
    parts.append(f"pressure={fc.get('pressure_trend')}")
    parts.append(f"alerts={len(data.get('alerts') or [])}")
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def render_article(data, summary_json) -> tuple[str, str, str]:
    """Return (title, excerpt, content_html) for the WordPress post."""
    gauges = data.get("gauges", [])
    reporting = [
        g for g in gauges
        if g.get("current", {}).get("gage_height_ft") is not None
        or g.get("current", {}).get("streamflow_cfs") is not None
    ]

    worst = next((s for s in STATUS_ORDER if any(g.get("flood_status") == s for g in gauges)), "normal")
    worst_label = STATUS_LABEL.get(worst, "Normal")
    flooding = [g for g in gauges if g.get("flood_status") in ("minor", "moderate", "major")]
    action = [g for g in gauges if g.get("flood_status") == "action"]

    if flooding:
        status_sentence = ", ".join(g.get("short_name") or g["name"] for g in flooding) + " at flood stage."
    elif action:
        status_sentence = ", ".join(g.get("short_name") or g["name"] for g in action) + " above action stage."
    else:
        status_sentence = "River levels are normal across central Wisconsin."

    headline, body = extract_summary(summary_json)
    sig = compute_signature(data)
    updated = fmt_ct(data.get("generated_at"))

    # --- Gauge table ---
    rows = []
    for g in reporting:
        cur = g.get("current", {})
        ht = cur.get("gage_height_ft")
        flow = cur.get("streamflow_cfs")
        rows.append(
            "<tr>"
            f"<td>{esc(g['name'])}</td>"
            f"<td>{f'{ht} ft' if ht is not None else '&mdash;'}</td>"
            f"<td>{f'{round(flow):,} cfs' if isinstance(flow, (int, float)) else '&mdash;'}</td>"
            f"<td>{esc(STATUS_LABEL.get(g.get('flood_status'), 'Normal'))}</td>"
            "</tr>"
        )
    gauge_table = (
        "<figure class=\"wp-block-table wpr-report__gauges\"><table>"
        "<thead><tr><th>Gauge</th><th>Gauge height</th><th>Streamflow</th><th>Status</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></figure>"
    )

    # --- Fishing forecast bullets ---
    fc = data.get("fishing_conditions") or {}
    fish_items = []
    rw = rating_word(fc.get("day_rating"))
    if rw:
        fish_items.append(f"<li><strong>Today&rsquo;s bite:</strong> {esc(rw)}"
                          + (f" ({esc(fc.get('day_rating'))}/10)" if fc.get("day_rating") is not None else "")
                          + "</li>")
    bt = fc.get("best_time") or {}
    if bt.get("start") and bt.get("end"):
        fish_items.append(f"<li><strong>Best window:</strong> {esc(bt['start'])}&ndash;{esc(bt['end'])}</li>")
    if fc.get("pressure_trend"):
        fish_items.append(f"<li><strong>Barometric pressure:</strong> {esc(fc['pressure_trend'])}</li>")
    if fc.get("sunrise") and fc.get("sunset"):
        fish_items.append(f"<li><strong>Daylight:</strong> {esc(fc['sunrise'])} to {esc(fc['sunset'])}</li>")
    if fc.get("wind_speed_mph") and fc.get("wind_direction"):
        fish_items.append(f"<li><strong>Wind:</strong> {esc(fc['wind_speed_mph'])} mph {esc(fc['wind_direction'])}</li>")
    fishing_block = f"<ul>{''.join(fish_items)}</ul>" if fish_items else ""

    # --- Assemble content (a WordPress HTML fragment — no <html>/<head>) ---
    lead = body or status_sentence
    parts = [
        "<!-- This post is auto-generated by scripts/publish_to_wordpress.py. Manual edits will be overwritten. -->",
        f"<!-- wpr-sig:{sig} -->",
        f"<p><strong>{esc(worst_label)}.</strong> {esc(lead)}</p>",
        "<h2>Current river levels &mdash; Wausau &amp; central Wisconsin</h2>",
        f"<p>{esc(status_sentence)}</p>",
        gauge_table,
    ]
    if headline or fishing_block:
        parts.append("<h2>Fishing forecast</h2>")
        if headline:
            parts.append(f"<p>{esc(headline)}.</p>")
        if fishing_block:
            parts.append(fishing_block)
    parts.extend([
        "<h2>See live, interactive conditions</h2>",
        "<p>Levels, 7-day trends, flood thresholds, reservoir data and per-gauge access maps update every 30 minutes in the live dashboard below.</p>",
        f'<iframe src="{WIDGET_URL}" width="100%" height="900" style="border:0;max-width:900px;" '
        f'title="Wausau area river and lake conditions" loading="lazy"></iframe>',
        '<p class="wpr-report__safety"><em>Safety note:</em> All data is provisional and subject to revision. '
        "Always consult official National Weather Service sources for safety decisions. Never drive through flooded roads.</p>",
        '<p class="wpr-report__credit"><small>Data from USGS Water Services, the National Weather Service, '
        "WVIC, Open-Meteo and Solunar.org."
        + (f" Last updated {esc(updated)}." if updated else "")
        + "</small></p>",
    ])
    content = "\n".join(parts)

    excerpt = f"{worst_label}. " + (headline or status_sentence)
    if len(excerpt) > 155:
        excerpt = excerpt[:152].rstrip() + "…"

    return POST_TITLE, excerpt, content


# ---------------------------------------------------------------------------
# WordPress REST client (stdlib)
# ---------------------------------------------------------------------------

class WPClient:
    def __init__(self, base_url, user, app_password):
        self.base = base_url.rstrip("/") + "/wp-json/wp/v2"
        token = base64.b64encode(
            f"{user}:{app_password.replace(' ', '')}".encode("utf-8")
        ).decode("ascii")
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "WPR-River-Conditions-Publisher/1.0",
        }

    def _request(self, method, path, payload=None):
        url = f"{self.base}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(url, data=data, headers=self.headers, method=method)
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None

    def find_post(self, slug):
        statuses = "publish,future,draft,pending,private"
        path = f"/posts?slug={slug}&status={statuses}&context=edit&per_page=1"
        try:
            results = self._request("GET", path)
        except HTTPError as e:
            # context=edit needs auth; if that ever fails, retry as a public lookup.
            if e.code in (400, 401, 403):
                results = self._request("GET", f"/posts?slug={slug}&per_page=1")
            else:
                raise
        return results[0] if results else None

    def create_post(self, payload):
        return self._request("POST", "/posts", payload)

    def update_post(self, post_id, payload):
        return self._request("POST", f"/posts/{post_id}", payload)


def existing_signature(post) -> str | None:
    if not post:
        return None
    content = post.get("content", {})
    raw = content.get("raw") or content.get("rendered") or ""
    m = SIG_RE.search(raw)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Publish the river/fishing report to WordPress.")
    parser.add_argument("--dry-run", action="store_true", help="Build and preview only; no network calls.")
    parser.add_argument("--force", action="store_true", help="Publish even if conditions are unchanged.")
    args = parser.parse_args()

    data = load_json(DATA_PATH)
    if not data:
        log.error("No river data at %s — run scripts/fetch_data.py first.", DATA_PATH)
        sys.exit(1)
    summary_json = load_json(SUMMARY_PATH)

    title, excerpt, content = render_article(data, summary_json)
    sig = compute_signature(data)

    # Always write a local preview artifact for inspection.
    PREVIEW_PATH.write_text(content, encoding="utf-8")
    log.info("Wrote preview (%s bytes) -> %s", f"{len(content):,}", PREVIEW_PATH)

    if args.dry_run:
        log.info("DRY RUN — would publish:")
        log.info("  Title:   %s", title)
        log.info("  Slug:    %s", os.environ.get("WP_POST_SLUG", DEFAULT_SLUG))
        log.info("  Excerpt: %s", excerpt)
        log.info("  Sig:     %s", sig)
        return

    wp_url = os.environ.get("WP_URL", "").strip()
    wp_user = os.environ.get("WP_USER", "").strip()
    wp_pass = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (wp_url and wp_user and wp_pass):
        log.warning(
            "WP_URL / WP_USER / WP_APP_PASSWORD not all set — skipping publish "
            "(this is expected for local/forked builds without secrets)."
        )
        return

    slug = os.environ.get("WP_POST_SLUG", DEFAULT_SLUG)
    status = os.environ.get("WP_POST_STATUS", "publish")
    category_id = os.environ.get("WP_CATEGORY_ID", "").strip()

    client = WPClient(wp_url, wp_user, wp_pass)
    try:
        existing = client.find_post(slug)
    except (HTTPError, URLError) as e:
        log.error("Failed to query WordPress: %s", e)
        sys.exit(1)

    if existing and not args.force and existing_signature(existing) == sig:
        log.info("Conditions unchanged (sig %s) — post %s left as-is.", sig, existing.get("id"))
        return

    payload = {"title": title, "content": content, "excerpt": excerpt}
    if category_id.isdigit():
        payload["categories"] = [int(category_id)]

    try:
        if existing:
            result = client.update_post(existing["id"], payload)
            log.info("Updated post %s: %s", result.get("id"), result.get("link"))
        else:
            payload.update({"slug": slug, "status": status})
            result = client.create_post(payload)
            log.info("Created post %s: %s", result.get("id"), result.get("link"))
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        log.error("WordPress API error %s: %s", e.code, body)
        sys.exit(1)
    except URLError as e:
        log.error("Could not reach WordPress: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
