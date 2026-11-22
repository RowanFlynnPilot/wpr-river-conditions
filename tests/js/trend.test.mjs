// Run with `npm test` (Node's built-in test runner, no dependencies).
import test from 'node:test';
import assert from 'node:assert/strict';

import { computeTrend, formatFlowChange, trendText } from '../../src/utils/trend.js';
import { dataAgeMs, isStatusUnknown, STATUS_UNKNOWN_AFTER_MS } from '../../src/utils/freshness.js';

const HOUR = 3600 * 1000;

// 13 two-hour readings ending now: `dayAgo` for the older half, `now` after.
function history(key, dayAgo, now) {
  const end = Date.UTC(2026, 10, 22, 18);
  return Array.from({ length: 13 }, (_, i) => ({
    timestamp: new Date(end - (12 - i) * 2 * HOUR).toISOString(),
    [key]: i < 3 ? dayAgo : now,
  }));
}

test('formatFlowChange matches the scraper wording', () => {
  // Same table as Narrative.test_flow_change_wording in tests/test_fetch_data.py.
  const cases = { 16: '+16%', 99: '+99%', 100: '2×', 140: '2.4×', 871: '9.7×', 1150: '13×', '-70': '-70%' };
  for (const [pct, text] of Object.entries(cases)) {
    assert.equal(formatFlowChange(Number(pct)), text);
  }
});

test('trendText switches to a multiple once flow doubles', () => {
  assert.equal(trendText({ dir: 'rising', key: 'streamflow_cfs', pct: 871 }), '9.7× in 24h');
  assert.equal(trendText({ dir: 'rising', key: 'streamflow_cfs', pct: 40 }), '+40% / 24h');
  assert.equal(trendText({ dir: 'falling', key: 'streamflow_cfs', pct: -70 }), '-70% / 24h');
  assert.equal(trendText({ dir: 'rising', key: 'gage_height_ft', delta: 0.3 }), '+0.3 ft / 24h');
  assert.equal(trendText({ dir: 'steady' }), 'steady');
});

test('computeTrend uses the ±15% flow threshold shared with the scraper', () => {
  assert.equal(computeTrend(history('streamflow_cfs', 100, 116)).dir, 'rising');
  assert.equal(computeTrend(history('streamflow_cfs', 100, 114)).dir, 'steady');
  assert.equal(computeTrend(history('streamflow_cfs', 100, 84)).dir, 'falling');
  assert.equal(computeTrend(history('streamflow_cfs', 72, 936)).pct, 1200);
});

test('computeTrend falls back to stage for gauges without flow', () => {
  const t = computeTrend(history('gage_height_ft', 12.0, 12.4));
  assert.deepEqual(t, { dir: 'rising', key: 'gage_height_ft', delta: 0.4 });
});

test('computeTrend needs enough history', () => {
  assert.equal(computeTrend([]), null);
  assert.equal(computeTrend(history('streamflow_cfs', 100, 120).slice(0, 4)), null);
});

test('status is unknown once data is more than six hours old', () => {
  const at = (ms) => new Date(Date.now() - ms).toISOString();
  assert.equal(isStatusUnknown(at(STATUS_UNKNOWN_AFTER_MS - 60_000)), false);
  assert.equal(isStatusUnknown(at(STATUS_UNKNOWN_AFTER_MS + 60_000)), true);
  assert.equal(isStatusUnknown(undefined), false);
  assert.equal(dataAgeMs('not a date'), 0);
});
