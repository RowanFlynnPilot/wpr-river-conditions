import React from 'react';
import { computeTrend, trendText, TREND_ARROWS } from '../utils/trend';

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

// Compact answer-first summary: one row per reporting gauge, visible
// within the first screen of the 900px WordPress embed.
export default function GlanceTable({ gauges, onSelect }) {
  if (!gauges || gauges.length === 0) return null;

  const handleKey = (id) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect?.(id);
    }
  };

  return (
    <div className="glance">
      <div className="glance__head">
        <span className="glance__title">At a glance</span>
        <span className="glance__hint">Select a river for details</span>
      </div>
      <table className="glance__table">
        <thead>
          <tr>
            <th scope="col">River</th>
            <th scope="col">Now</th>
            <th scope="col">24h trend</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {gauges.map((g) => {
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
                      {trendText(trend)}
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
          })}
        </tbody>
      </table>
    </div>
  );
}
