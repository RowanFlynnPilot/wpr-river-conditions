import React from 'react';

/**
 * Renders a simple sparkline SVG from an array of {date, value} points.
 * Includes a filled area beneath the line, a dot at the most recent
 * observation, and optionally:
 *  - a dashed reference line (e.g. the NWS action stage) when it falls
 *    within the plotted range
 *  - a dotted forecast tail (National Water Model) continuing from the
 *    last observed point
 */
export default function Sparkline({
  data,
  valueKey,
  width = 200,
  height = 40,
  refValue = null,
  forecast = [],
}) {
  if (!data || data.length < 2) return null;

  const values = data
    .map((d) => d[valueKey])
    .filter((v) => v != null);

  if (values.length < 2) return null;

  const fcst = (forecast || []).filter((v) => v != null);
  const combined = [...values, ...fcst];

  const padding = 4;
  const w = width - padding * 2;
  const h = height - padding * 2;

  const min = Math.min(...combined);
  const max = Math.max(...combined);
  const range = max - min || 1;

  const points = combined.map((v, i) => ({
    x: padding + (i / (combined.length - 1)) * w,
    y: padding + h - ((v - min) / range) * h,
  }));

  const obsPoints = points.slice(0, values.length);
  const lastObs = obsPoints[obsPoints.length - 1];

  const linePath = obsPoints
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`)
    .join(' ');

  const areaPath =
    linePath +
    ` L${lastObs.x},${padding + h}` +
    ` L${obsPoints[0].x},${padding + h} Z`;

  // Forecast tail starts at the last observation so the line is continuous.
  let fcstPath = null;
  if (fcst.length > 0) {
    const tail = [lastObs, ...points.slice(values.length)];
    fcstPath = tail.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  }

  // Reference line only when it lands inside the plotted range.
  let refY = null;
  if (refValue != null && refValue >= min && refValue <= max) {
    refY = padding + h - ((refValue - min) / range) * h;
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <path className="gauge-card__sparkline-area" d={areaPath} />
      <path className="gauge-card__sparkline-line" d={linePath} />
      {fcstPath && (
        <path className="gauge-card__sparkline-fcst" d={fcstPath} />
      )}
      {refY != null && (
        <line
          className="gauge-card__sparkline-ref"
          x1={padding}
          x2={width - padding}
          y1={refY}
          y2={refY}
        />
      )}
      <circle
        className="gauge-card__sparkline-dot"
        cx={lastObs.x}
        cy={lastObs.y}
        r={3}
      />
    </svg>
  );
}
