import React from 'react';

const TREND_CONFIG = {
  falling: { arrow: '\u2198', color: 'var(--status-normal)', label: 'Falling' },
  steady:  { arrow: '\u2192', color: 'var(--status-action)', label: 'Steady' },
  rising:  { arrow: '\u2197', color: 'var(--wpr-ink-muted)', label: 'Rising' },
};

// Compass arrow rotation for wind direction
const COMPASS_ROTATIONS = {
  N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315,
};

// Moon phase emoji mapping
const MOON_EMOJIS = {
  'New Moon': '\uD83C\uDF11',
  'Waxing Crescent': '\uD83C\uDF12',
  'First Quarter': '\uD83C\uDF13',
  'Waxing Gibbous': '\uD83C\uDF14',
  'Full Moon': '\uD83C\uDF15',
  'Waning Gibbous': '\uD83C\uDF16',
  'Last Quarter': '\uD83C\uDF17',
  'Waning Crescent': '\uD83C\uDF18',
};

function getMoonEmoji(phase) {
  if (!phase) return '\uD83C\uDF15';
  for (const [key, emoji] of Object.entries(MOON_EMOJIS)) {
    if (phase.toLowerCase().includes(key.toLowerCase())) return emoji;
  }
  return '\uD83C\uDF15';
}

function formatPeriod(period) {
  if (!period?.start || !period?.end) return null;
  const fmt = (t) => {
    const [h, m] = t.split(':').map(Number);
    const hr = h > 24 ? h - 24 : h;
    const hour12 = hr % 12 || 12;
    const ampm = hr < 12 ? 'AM' : 'PM';
    return `${hour12}:${String(m).padStart(2, '0')} ${ampm}`;
  };
  return `${fmt(period.start)}\u2013${fmt(period.end)}`;
}

function getRatingLabel(rating) {
  if (rating <= 2) return 'Poor';
  if (rating <= 4) return 'Below Avg';
  if (rating <= 6) return 'Average';
  if (rating <= 8) return 'Good';
  return 'Excellent';
}

function RatingBar({ rating, max = 10 }) {
  const pct = (rating / max) * 100;
  return (
    <div className="fishing-panel__rating-bar">
      <div className="fishing-panel__rating-track">
        <div className="fishing-panel__rating-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="fishing-panel__rating-label">{getRatingLabel(rating)}</span>
    </div>
  );
}

function CompassArrow({ direction }) {
  const deg = COMPASS_ROTATIONS[direction] ?? 0;
  return (
    <span
      className="fishing-panel__compass"
      style={{ transform: `rotate(${deg}deg)` }}
      title={`Wind from ${direction}`}
    >
      {'\u2191'}
    </span>
  );
}

export default function FishingConditions({ conditions }) {
  if (!conditions) return null;

  const trend = TREND_CONFIG[conditions.pressure_trend] || TREND_CONFIG.steady;

  return (
    <div className="fishing-panel">
      <div className="fishing-panel__grid">
        {/* Weather */}
        <div className="fishing-panel__group">
          <div className="fishing-panel__item">
            <div className="fishing-panel__label">Barometric Pressure</div>
            <div className="fishing-panel__value">
              {conditions.pressure_hpa != null ? (
                <>
                  {conditions.pressure_hpa}
                  <span className="fishing-panel__unit">hPa</span>
                  <span className="fishing-panel__trend" style={{ color: trend.color }}>
                    {trend.arrow} {trend.label}
                  </span>
                </>
              ) : '\u2014'}
            </div>
          </div>
          <div className="fishing-panel__item">
            <div className="fishing-panel__label">Wind</div>
            <div className="fishing-panel__wind-row">
              {conditions.wind_speed_mph != null ? (
                <>
                  {conditions.wind_direction && (
                    <CompassArrow direction={conditions.wind_direction} />
                  )}
                  <div className="fishing-panel__value">
                    {conditions.wind_speed_mph}
                    <span className="fishing-panel__unit">mph {conditions.wind_direction}</span>
                  </div>
                </>
              ) : <div className="fishing-panel__value">{'\u2014'}</div>}
            </div>
          </div>
        </div>

        {/* Sun / Moon */}
        <div className="fishing-panel__group fishing-panel__group--center">
          <div className="fishing-panel__item">
            <div className="fishing-panel__label">Sunrise / Sunset</div>
            <div className="fishing-panel__sun-times">
              {conditions.sunrise && conditions.sunset ? (
                <>
                  <span className="fishing-panel__sun-entry">
                    <span className="fishing-panel__sun-emoji">{'\uD83C\uDF05'}</span>
                    {conditions.sunrise}
                  </span>
                  <span className="fishing-panel__sun-divider">&mdash;</span>
                  <span className="fishing-panel__sun-entry">
                    <span className="fishing-panel__sun-emoji">{'\uD83C\uDF07'}</span>
                    {conditions.sunset}
                  </span>
                </>
              ) : '\u2014'}
            </div>
          </div>
          <div className="fishing-panel__item">
            <div className="fishing-panel__label">Moon Phase</div>
            <div className="fishing-panel__moon">
              <span className="fishing-panel__moon-emoji">{getMoonEmoji(conditions.moon_phase)}</span>
              <span className="fishing-panel__moon-name">{conditions.moon_phase || '\u2014'}</span>
            </div>
          </div>
        </div>

        {/* Solunar */}
        <div className="fishing-panel__group">
          <div className="fishing-panel__item">
            <div className="fishing-panel__label">Fishing Rating</div>
            <div className="fishing-panel__value">
              {conditions.day_rating != null ? (
                <>
                  {conditions.day_rating}
                  <span className="fishing-panel__unit">/ 10</span>
                </>
              ) : '\u2014'}
            </div>
            {conditions.day_rating != null && (
              <RatingBar rating={conditions.day_rating} />
            )}
          </div>
          <div className="fishing-panel__item">
            <div className="fishing-panel__label">Feeding Windows</div>
            <div className="fishing-panel__windows">
              {conditions.major_periods?.length > 0 && (
                <div className="fishing-panel__window-group">
                  <span className="fishing-panel__window-badge fishing-panel__window-badge--major">Major</span>
                  <div className="fishing-panel__window-times">
                    {conditions.major_periods.map((p, i) => (
                      <span key={i} className="fishing-panel__window-time">{formatPeriod(p)}</span>
                    ))}
                  </div>
                </div>
              )}
              {conditions.minor_periods?.length > 0 && (
                <div className="fishing-panel__window-group">
                  <span className="fishing-panel__window-badge">Minor</span>
                  <div className="fishing-panel__window-times">
                    {conditions.minor_periods.map((p, i) => (
                      <span key={i} className="fishing-panel__window-time">{formatPeriod(p)}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
