import React from 'react';

/**
 * Renders a simple sparkline SVG from an array of {date, value} points.
 * Includes a filled area beneath the line and a dot at the most recent point.
 */
export default function Sparkline({ data, valueKey, width = 200, height = 40 }) {
  if (!data || data.length < 2) return null;

  const values = data
    .map((d) => d[valueKey])
    .filter((v) => v != null && v >= 0);

  if (values.length < 2) return null;

  const padding = 4;
  const w = width - padding * 2;
  const h = height - padding * 2;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values.map((v, i) => ({
    x: padding + (i / (values.length - 1)) * w,
    y: padding + h - ((v - min) / range) * h,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');

  const areaPath =
    linePath +
    ` L${points[points.length - 1].x},${padding + h}` +
    ` L${points[0].x},${padding + h} Z`;

  const lastPoint = points[points.length - 1];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <path className="gauge-card__sparkline-area" d={areaPath} />
      <path className="gauge-card__sparkline-line" d={linePath} />
      <circle
        className="gauge-card__sparkline-dot"
        cx={lastPoint.x}
        cy={lastPoint.y}
        r={3}
      />
    </svg>
  );
}
