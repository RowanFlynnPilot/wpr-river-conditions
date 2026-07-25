import React from 'react';
import { computeTrend, TREND_ARROWS } from '../utils/trend';

const STATUS_CONFIG = {
  normal:   { label: 'Normal',      css: 'normal' },
  action:   { label: 'Action',      css: 'action' },
  minor:    { label: 'Minor Flood', css: 'minor' },
  moderate: { label: 'Moderate',    css: 'moderate' },
  major:    { label: 'Major Flood', css: 'major' },
};

function primaryReading(cur) {
  if (cur.gage_height_ft != null) return `${cur.gage_height_ft.toFixed(2)} ft`;
  if (cur.streamflow_cfs != null) {
    return `${Math.round(cur.streamflow_cfs).toLocaleString('en-US')} cfs`;
  }
  return '—';
}

// Compact trend for the table — the column header already says "24h",
// so the cell just carries direction + magnitude.
function shortTrend(t) {
  if (!t) return null;
  if (t.dir === 'steady') return 'steady';
  if (t.key === 'streamflow_cfs') return `${t.pct > 0 ? '+' : ''}${t.pct}%`;
  return `${t.delta > 0 ? '+' : ''}${t.delta} ft`;
}

// Compact answer-first summary: one row per reporting gauge, visible
// within the first screen of the 900px WordPress embed. Past 8 gauges
// the roster splits into two side-by-side tables at wider widths so the
// whole region still fits in one screen.
export default function GlanceTable({ gauges, onSelect }) {
  if (!gauges || gauges.length === 0) return null;

  const handleKey = (id) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect?.(id);
    }
  };

  const renderRows = (chunk) =>
    chunk.map((g) => {
      const cur = g.current || {};
      const trend = computeTrend(g.history);
      const conf = STATUS_CONFIG[g.flood_status] || STATUS_CONFIG.normal;
      const flow =
        cur.gage_height_ft != null && cur.streamflow_cfs != null
          ? `${Math.round(cur.streamflow_cfs).toLocaleString('en-US')} cfs`
          : null;
      return (
        <tr
          key={g.id}
          className="glance__row"
          onClick={() => onSelect?.(g.id)}
          onKeyDown={handleKey(g.id)}
          tabIndex={0}
          aria-label={`${g.short_name}: ${primaryReading(cur)}, ${conf.label}. Jump to details.`}
        >
          <td className="glance__name">{g.short_name}</td>
          <td className="glance__now">
            {primaryReading(cur)}
            {flow && <span className="glance__sub">{flow}</span>}
          </td>
          <td className={`glance__trend glance__trend--${trend ? trend.dir : 'na'}`}>
            {trend ? (
              <>
                <span aria-hidden="true">{TREND_ARROWS[trend.dir]}</span>{' '}
                {shortTrend(trend)}
              </>
            ) : (
              '—'
            )}
          </td>
          <td>
            <span className={`glance__chip glance__chip--${conf.css}`}>{conf.label}</span>
          </td>
        </tr>
      );
    });

  // Severity sort is preserved: the left/top table carries the worst gauges.
  const chunks =
    gauges.length > 8
      ? [gauges.slice(0, Math.ceil(gauges.length / 2)), gauges.slice(Math.ceil(gauges.length / 2))]
      : [gauges];

  return (
    <div className="glance">
      <div className="glance__head">
        <span className="glance__title">At a glance</span>
        <span className="glance__hint">Select a river for details</span>
      </div>
      <div className={`glance__cols ${chunks.length > 1 ? 'glance__cols--split' : ''}`}>
        {chunks.map((chunk, i) => (
          <table key={i} className="glance__table">
            <thead>
              <tr>
                <th scope="col">River</th>
                <th scope="col">Now</th>
                <th scope="col">24h</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>{renderRows(chunk)}</tbody>
          </table>
        ))}
      </div>
    </div>
  );
}
