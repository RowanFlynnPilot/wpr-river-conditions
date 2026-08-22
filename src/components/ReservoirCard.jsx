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
  // Visual position within a 15 ft drawdown band (0 = at maximum).
  // WVIC only reports "feet below maximum" — we don't know each
  // reservoir's true operating range, so don't present this as a
  // real capacity percentage.
  const maxDrop = 15;
  const drop = Math.min(maxDrop, Math.abs(feetBelowMax));
  const fillPct = Math.max(0, ((maxDrop - drop) / maxDrop) * 100);

  return (
    <div
      className="reservoir-bar"
      title={`WVIC reports level as feet below maximum. Bar shows position within a ${maxDrop} ft drawdown band.`}
    >
      <div className="reservoir-bar__track">
        <div className="reservoir-bar__fill" style={{ width: `${fillPct}%` }} />
      </div>
      <div className="reservoir-bar__labels">
        <span className="reservoir-bar__label-left">
          {Math.abs(feetBelowMax).toFixed(1)} ft below max
        </span>
        <span className="reservoir-bar__label-right">full pool = 0 ft</span>
      </div>
    </div>
  );
}

// Pool/tailwater elevation from an NWPS gauge. These read in feet above
// sea level, not gage height, so they're never compared to flood stages.
export function LakeCard({ lake }) {
  return (
    <div className="reservoir-card">
      <div className="reservoir-card__name">{lake.name}</div>
      {lake.description && (
        <div className="reservoir-card__description">{lake.description}</div>
      )}
      <div className="reservoir-card__reading">
        <span className="reservoir-card__reading-value">
          {lake.elevation_ft.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        </span>
        <span className="reservoir-card__reading-unit">ft elevation</span>
      </div>
      <div className="reservoir-card__timestamp">
        <span>{formatTimestamp(lake.valid_time)}</span>
        <a
          className="reservoir-card__source-link"
          href={lake.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          NWS
        </a>
      </div>
    </div>
  );
}

export default function ReservoirCard({ reservoir }) {
  const { name, description, feet_below_max, has_data, source_url, last_updated } = reservoir;

  return (
    <div className="reservoir-card">
      <div className="reservoir-card__name">{name}</div>
      {description && (
        <div className="reservoir-card__description">{description}</div>
      )}

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
