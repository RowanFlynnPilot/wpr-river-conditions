// Computes a ~24-hour trend from a gauge's hourly history array.
// Prefers streamflow (relative % change); falls back to gage height
// (absolute ft delta) for stage-only gauges like Mosinee.

const HOUR_MS = 3600 * 1000;

export const TREND_ARROWS = { rising: '↗', falling: '↘', steady: '→' };

export function computeTrend(history) {
  if (!history || history.length < 6) return null;

  const hasFlow = history.some((h) => h.streamflow_cfs != null);
  const key = hasFlow ? 'streamflow_cfs' : 'gage_height_ft';
  const points = history.filter((h) => h[key] != null && h.timestamp);
  if (points.length < 6) return null;

  const last = points[points.length - 1];
  const lastT = new Date(last.timestamp).getTime();
  if (Number.isNaN(lastT)) return null;

  // Average the readings 20–28h before the latest one. A window (rather
  // than a single point) smooths hydro-peaking cycles on dam-regulated
  // reaches, and matches the scraper's "24h ago" math so the card and the
  // conditions narrative can't disagree.
  const target = lastT - 24 * HOUR_MS;
  const windowVals = [];
  for (const p of points) {
    const t = new Date(p.timestamp).getTime();
    if (Math.abs(t - target) <= 4 * HOUR_MS && p !== last) {
      windowVals.push(p[key]);
    }
  }
  if (windowVals.length === 0) return null;

  const now = last[key];
  const then = windowVals.reduce((a, b) => a + b, 0) / windowVals.length;

  if (key === 'streamflow_cfs') {
    if (then <= 0) return null;
    const pct = ((now - then) / then) * 100;
    // ±15% matches compute_conditions_summary in the scraper.
    const dir = pct > 15 ? 'rising' : pct < -15 ? 'falling' : 'steady';
    return { dir, key, pct: Math.round(pct) };
  }

  const delta = now - then;
  const dir = delta > 0.15 ? 'rising' : delta < -0.15 ? 'falling' : 'steady';
  return { dir, key, delta: Math.round(delta * 10) / 10 };
}

// Short human string: "+12% / 24h", "+0.3 ft / 24h", or "steady".
export function trendText(t) {
  if (!t) return null;
  if (t.dir === 'steady') return 'steady';
  if (t.key === 'streamflow_cfs') {
    return `${t.pct > 0 ? '+' : ''}${t.pct}% / 24h`;
  }
  return `${t.delta > 0 ? '+' : ''}${t.delta} ft / 24h`;
}
