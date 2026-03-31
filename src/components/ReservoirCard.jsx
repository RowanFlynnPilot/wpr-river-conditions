import React from 'react';

function formatTimestamp(isoStr) {
  if (!isoStr) return 'No data';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch {
    return isoStr;
  }
}

function LevelBar({ feetBelowMax }) {
  // Scale: 0 (full) to -15 (very low). Closer to 0 = more full.
  const maxDrop = 15;
  const drop = Math.min(maxDrop, Math.abs(feetBelowMax));
  const fillPct = Math.max(0, ((maxDrop - drop) / maxDrop) * 100);

  return (
    <div className="reservoir-bar">
      <div className="reservoir-bar__track">
        <div className="reservoir-bar__fill" style={{ width: `${fillPct}%` }} />
      </div>
      <div className="reservoir-bar__labels">
        <span className="reservoir-bar__label-left">
          {Math.abs(feetBelowMax).toFixed(1)} ft below max
        </span>
        <span className="reservoir-bar__label-right">
          {Math.round(fillPct)}% capacity
        </span>
      </div>
    </div>
  );
}

export default function ReservoirCard({ reservoir }) {
  const { name, feet_below_max, has_data, source_url, last_updated } = reservoir;

  return (
    <div className="reservoir-card">
      <div className="reservoir-card__name">{name}</div>

      {has_data && feet_below_max != null ? (
        <>
          <div className="reservoir-card__reading">
            <span className="reservoir-card__reading-value">
              {Math.abs(feet_below_max).toFixed(1)}
            </span>
            <span className="reservoir-card__reading-unit">ft below max</span>
          </div>

          <LevelBar feetBelowMax={feet_below_max} />

          <div className="reservoir-card__timestamp">
            <span>{formatTimestamp(last_updated)}</span>
            <a
              className="reservoir-card__source-link"
              href={source_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              WVIC
            </a>
          </div>
        </>
      ) : (
        <div className="reservoir-card__no-data">
          <div className="reservoir-card__no-data-text">Data unavailable</div>
          <div className="reservoir-card__timestamp">
            <span>Not reported by WVIC</span>
            <a
              className="reservoir-card__source-link"
              href={source_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              WVIC &rarr;
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
