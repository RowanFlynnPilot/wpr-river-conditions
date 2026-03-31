import React, { useState } from 'react';

export default function FishingReference({ gauges }) {
  const [expanded, setExpanded] = useState(false);

  // Only show gauges that have fishing data
  const fishingGauges = gauges?.filter((g) => g.fishing) || [];
  if (fishingGauges.length === 0) return null;

  return (
    <div className="fishing-ref">
      <div
        className="section-header fishing-ref__header"
        style={{ marginTop: 'var(--space-lg)', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <h2 className="section-header__title">Fishing Guide</h2>
        <span className="section-header__subtitle">
          {fishingGauges.length} waterways
          <span className={`fishing-ref__chevron ${expanded ? 'fishing-ref__chevron--open' : ''}`}>
            &#9662;
          </span>
        </span>
      </div>

      {expanded && (
        <div className="fishing-ref-grid">
          {fishingGauges.map((gauge) => {
            const f = gauge.fishing;
            return (
              <div key={gauge.id} className="fishing-ref-card">
                <div className="fishing-ref-card__name">{gauge.short_name}</div>

                {/* Species */}
                <div className="fishing-ref-card__species">
                  {f.species.map((s) => (
                    <span key={s} className="fishing-ref-card__pill">{s}</span>
                  ))}
                </div>

                {/* Trout classification */}
                {f.trout_class && (
                  <div className="fishing-ref-card__detail">
                    <span className="fishing-ref-card__detail-label">Trout Class</span>
                    {f.trout_class}
                  </div>
                )}

                {/* Regulations */}
                <div className="fishing-ref-card__detail">
                  <span className="fishing-ref-card__detail-label">Regulations</span>
                  {Array.isArray(f.regulations) ? (
                    <ul className="fishing-ref-card__list">
                      {f.regulations.map((r, i) => (
                        <li key={i}>
                          <strong>{r.species}:</strong> {r.rule}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    f.regulations
                  )}
                </div>

                {/* Season notes */}
                <div className="fishing-ref-card__detail">
                  <span className="fishing-ref-card__detail-label">Season</span>
                  {Array.isArray(f.season_notes) ? (
                    <ul className="fishing-ref-card__list">
                      {f.season_notes.map((note, i) => (
                        <li key={i}>{note}</li>
                      ))}
                    </ul>
                  ) : (
                    f.season_notes
                  )}
                </div>

                {/* Access points */}
                {f.access_points && f.access_points.length > 0 && (
                  <div className="fishing-ref-card__access">
                    <span className="fishing-ref-card__detail-label">Access</span>
                    {f.access_points.map((ap, i) => {
                      const query = ap.lat && ap.lng
                        ? `${ap.lat},${ap.lng}`
                        : `${ap.name}, Wisconsin`;
                      const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}`;
                      return (
                        <div key={i} className="fishing-ref-card__access-item">
                          <strong>{ap.name}</strong> &mdash; {ap.directions}
                          <a
                            className="fishing-ref-card__directions"
                            href={mapsUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Directions &rarr;
                          </a>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* DNR link */}
                <div className="fishing-ref-card__footer">
                  <a
                    className="fishing-ref-card__link"
                    href={f.dnr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    WI DNR &rarr;
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
