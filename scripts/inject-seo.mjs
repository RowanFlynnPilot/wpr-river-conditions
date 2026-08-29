// Post-build SEO injection.
//
// Vite ships an empty <div id="root"></div>, so crawlers that don't run JS see
// no content and the page can't rank for the queries it actually answers
// ("Wisconsin River flooding Wausau", "Rib River level", fishing reports, etc.).
//
// This script runs as `postbuild` (after `vite build`) and rewrites dist/index.html:
//   1. Bakes a real, keyword-rich content snapshot INTO #root. React's
//      createRoot().render() clears #root on mount, so users still get the full
//      interactive widget — the snapshot is purely for crawlers / no-JS / faster
//      indexing, and is visually hidden so it never flashes on screen.
//   2. Rewrites the `data-seo="dynamic"` meta/OG/Twitter tags with the current
//      flood status and readings.
//   3. Injects JSON-LD structured data (Organization + Dataset + the daily
//      fishing report as a NewsArticle).
//   4. Writes dist/sitemap.xml with today's lastmod.
//
// It degrades gracefully: if the data files are missing it leaves the build
// untouched rather than failing.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const SITE_URL = 'https://rowanflynnpilot.github.io/wpr-river-conditions/';
const PUBLISHER = 'Wausau Pilot & Review';

const DIST_HTML = join(ROOT, 'dist', 'index.html');
const DATA_JSON = join(ROOT, 'src', 'data', 'river-data.json');
const SUMMARY_JSON = join(ROOT, 'src', 'data', 'daily-summary.json');

const STATUS_LABEL = {
  normal: 'Normal',
  action: 'Action Stage',
  minor: 'Minor Flooding',
  moderate: 'Moderate Flooding',
  major: 'Major Flooding',
};
const STATUS_ORDER = ['major', 'moderate', 'minor', 'action', 'normal'];

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, '&quot;');
}
function stripTags(s) {
  return String(s).replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
}

function bail(msg) {
  console.warn(`[inject-seo] ${msg} — skipping SEO injection.`);
  process.exit(0);
}

if (!existsSync(DIST_HTML)) bail(`${DIST_HTML} not found`);
if (!existsSync(DATA_JSON)) bail(`${DATA_JSON} not found`);

let data;
try {
  data = JSON.parse(readFileSync(DATA_JSON, 'utf8'));
} catch (e) {
  bail(`could not parse river-data.json (${e.message})`);
}

const gauges = Array.isArray(data.gauges) ? data.gauges : [];
const reporting = gauges.filter(
  (g) => g.current?.gage_height_ft != null || g.current?.streamflow_cfs != null
);

// --- Worst flood status across all gauges (mirrors HeroStatus.jsx) ---
const worst =
  STATUS_ORDER.find((s) => gauges.some((g) => g.flood_status === s)) || 'normal';
const worstLabel = STATUS_LABEL[worst] || 'Normal';
const flooding = gauges.filter((g) =>
  ['minor', 'moderate', 'major'].includes(g.flood_status)
);
const action = gauges.filter((g) => g.flood_status === 'action');

let statusSentence;
if (flooding.length) {
  statusSentence = `${flooding.map((g) => g.short_name || g.name).join(', ')} at flood stage in central Wisconsin.`;
} else if (action.length) {
  statusSentence = `${action.map((g) => g.short_name || g.name).join(', ')} above action stage in central Wisconsin.`;
} else {
  statusSentence = 'River levels are normal across central Wisconsin.';
}

// --- Primary gauge (Rothschild) readings for the description ---
const primary = gauges.find((g) => g.id === '05398000');
let primaryReading = '';
if (primary?.current) {
  const ht = primary.current.gage_height_ft;
  const flow = primary.current.streamflow_cfs;
  const bits = [];
  if (ht != null) bits.push(`${ht} ft`);
  if (flow != null) bits.push(`${Math.round(flow).toLocaleString('en-US')} cfs`);
  if (bits.length) primaryReading = ` Wisconsin River at Rothschild: ${bits.join(' / ')}.`;
}

// --- Last-updated, human readable (Central time) ---
let updatedStr = '';
if (data.generated_at) {
  try {
    updatedStr = new Date(data.generated_at).toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    updatedStr = '';
  }
}

// --- Daily fishing summary (headline + body) ---
let summaryHeadline = '';
let summaryBody = '';
if (existsSync(SUMMARY_JSON)) {
  try {
    const summary = JSON.parse(readFileSync(SUMMARY_JSON, 'utf8'));
    const html = summary.html || '';
    const hMatch = html.match(/__headline">([\s\S]*?)<\/h3>/);
    const bMatch = html.match(/__body">([\s\S]*?)<\/p>/);
    if (hMatch) summaryHeadline = stripTags(hMatch[1]);
    if (bMatch) summaryBody = stripTags(bMatch[1]);
  } catch {
    /* summary is optional */
  }
}

// --- Dynamic strings -------------------------------------------------------
const dynamicDescription = `${statusSentence}${primaryReading} Live USGS gauge data, NWS flood thresholds, and the daily fishing forecast for central Wisconsin — updated every 30 minutes.`;
const dynamicTitle =
  worst === 'normal'
    ? `River & Lake Conditions — ${PUBLISHER}`
    : `${worstLabel} — Wausau Area River Conditions | ${PUBLISHER}`;

// --- Prerendered content snapshot (visually hidden; cleared by React) ------
const gaugeRows = reporting
  .map((g) => {
    const ht = g.current?.gage_height_ft;
    const flow = g.current?.streamflow_cfs;
    return `<tr>
      <td>${escapeHtml(g.name)}</td>
      <td>${ht != null ? `${ht} ft` : '—'}</td>
      <td>${flow != null ? `${Math.round(flow).toLocaleString('en-US')} cfs` : '—'}</td>
      <td>${escapeHtml(STATUS_LABEL[g.flood_status] || 'Normal')}</td>
    </tr>`;
  })
  .join('\n');

const prerender = `
  <div id="seo-snapshot" aria-hidden="true" style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;">
    <h1>Wausau Area River, Lake &amp; Fishing Conditions — Central Wisconsin</h1>
    <p><strong>Current flood status:</strong> ${escapeHtml(worstLabel)}. ${escapeHtml(statusSentence)}${updatedStr ? ` Updated ${escapeHtml(updatedStr)}.` : ''}</p>
    ${summaryHeadline ? `<h2>${escapeHtml(summaryHeadline)}</h2>` : ''}
    ${summaryBody ? `<p>${escapeHtml(summaryBody)}</p>` : ''}
    <h2>Stream gauge readings</h2>
    <table>
      <thead><tr><th>Gauge</th><th>Gauge height</th><th>Streamflow</th><th>Status</th></tr></thead>
      <tbody>
${gaugeRows}
      </tbody>
    </table>
    <p>Data from USGS Water Services, the National Weather Service, WVIC and Open-Meteo. Provisional and subject to revision — always consult official sources for safety decisions.</p>
  </div>`;

// --- JSON-LD ---------------------------------------------------------------
const graph = [
  {
    '@type': 'Organization',
    '@id': `${SITE_URL}#org`,
    name: PUBLISHER,
    url: 'https://wausaupilotandreview.com',
  },
  {
    '@type': 'Dataset',
    name: 'Central Wisconsin River & Stream Gauge Conditions',
    description:
      'Real-time gauge height and streamflow for the Wisconsin River and tributary streams in central Wisconsin (Wausau, Marathon County, and surrounding counties), with NWS flood-stage thresholds.',
    url: SITE_URL,
    isAccessibleForFree: true,
    creator: { '@id': `${SITE_URL}#org` },
    spatialCoverage:
      'Central Wisconsin — Marathon, Shawano, Oneida, Taylor, Lincoln, Langlade, Portage, and Wood counties',
    ...(data.generated_at ? { dateModified: data.generated_at } : {}),
    keywords: [
      'Wisconsin River level',
      'Wolf River water level',
      'Wausau flood status',
      'Marathon County river conditions',
      'Shawano fishing report',
      'Rainbow Flowage',
      'central Wisconsin fishing report',
      'central Wisconsin trout streams',
    ],
  },
];

if (summaryHeadline) {
  graph.push({
    '@type': 'NewsArticle',
    headline: summaryHeadline,
    articleBody: summaryBody || undefined,
    ...(data.generated_at
      ? { datePublished: data.generated_at, dateModified: data.generated_at }
      : {}),
    publisher: { '@id': `${SITE_URL}#org` },
    mainEntityOfPage: SITE_URL,
    about: 'Central Wisconsin fishing and river conditions',
  });
}

const jsonLd = {
  '@context': 'https://schema.org',
  '@graph': graph,
};
// Escape "<" so content can never form a premature </script> inside the tag.
const jsonLdScript = `<script type="application/ld+json">${JSON.stringify(jsonLd).replace(/</g, '\\u003c')}</script>`;

// --- Rewrite dist/index.html ----------------------------------------------
let html = readFileSync(DIST_HTML, 'utf8');

// Rewrite the dynamic meta tags by name/property.
// Replacer functions throughout: replacement *strings* treat $&, $', $`
// as patterns, which would corrupt output if a headline ever contains "$".
function setMetaContent(attr, value, escaped) {
  const re = new RegExp(`(<meta ${attr}[^>]*\\bdata-seo="dynamic"[^>]*\\bcontent=")[^"]*(")`);
  if (re.test(html)) {
    html = html.replace(re, (_, p1, p2) => p1 + escaped + p2);
  } else {
    console.warn(`[inject-seo] dynamic meta not found for ${attr}=${value}`);
  }
}
const descAttr = escapeAttr(dynamicDescription);
const titleAttr = escapeAttr(dynamicTitle);
setMetaContent('name="description"', dynamicDescription, descAttr);
setMetaContent('property="og:title"', dynamicTitle, titleAttr);
setMetaContent('property="og:description"', dynamicDescription, descAttr);
setMetaContent('name="twitter:title"', dynamicTitle, titleAttr);
setMetaContent('name="twitter:description"', dynamicDescription, descAttr);

// The <title> element is what search results show — og:/twitter: alone
// only reach social shares, so the live flood status belongs here too.
html = html.replace(/<title>[^<]*<\/title>/, () => `<title>${escapeHtml(dynamicTitle)}</title>`);

// Inject JSON-LD and the prerendered snapshot at their anchors.
html = html.replace('<!-- SEO:JSONLD -->', () => jsonLdScript);
html = html.replace('<!-- SEO:PRERENDER -->', () => prerender);

writeFileSync(DIST_HTML, html, 'utf8');

// --- sitemap.xml -----------------------------------------------------------
const lastmod = new Date().toISOString().slice(0, 10);
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${SITE_URL}</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
`;
writeFileSync(join(ROOT, 'dist', 'sitemap.xml'), sitemap, 'utf8');

console.log(
  `[inject-seo] Injected snapshot (${reporting.length} gauges, status: ${worst}), JSON-LD, meta, and sitemap.xml.`
);
