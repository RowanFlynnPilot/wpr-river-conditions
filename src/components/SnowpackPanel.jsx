import React from 'react';

// Snow water equivalent per basin (NOAA's daily snow analysis) and what the
// week's forecast does to it. The scraper writes the headline and the melt
// estimate; this only lays them out. Shown in snow season, or whenever
// there is snow on the ground.

const CLASS_LABEL = {
  rapid: 'Rapid melt possible',
  melting: 'Melting',
  building: 'Building',
  holding: 'Holding',
  none: 'No snow',
};

// Bars share one scale. Six inches of water is a heavy late-winter pack
// here, so a normal winter fills most of the track without clipping.
const MIN_SCALE_IN = 6;

function formatAnalysisDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function weekday(dateStr) {
  // Noon avoids the date slipping a day in any US time zone.
  const d = new Date(`${dateStr}T12:00:00`);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-US', { weekday: 'short' });
}

function inches(value) {
  return Number(value).toFixed(1);
}

function BasinRow({ basin, scale }) {
  const pct = Math.min(100, (basin.swe_in / scale) * 100);
  const bare = basin.swe_in < 0.1;
  return (
    <li className="snowpack__basin">
      <div className="snowpack__basin-head">
        <span className="snowpack__basin-name">{basin.label}</span>
        {basin.class && basin.class !== 'none' && (
          <span className={`snowpack__tag snowpack__tag--${basin.class}`}>{CLASS_LABEL[basin.class]}</span>
        )}
      </div>
      <div className="snowpack__track" aria-hidden="true">
        <div className="snowpack__fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="snowpack__basin-reading">
        {bare ? (
          'Bare ground'
        ) : (
          <>
            <strong>{inches(basin.swe_in)} in</strong> of water
            {basin.depth_in != null && ` · ${basin.depth_in} in deep`}
            {basin.melt_in >= 0.3 && ` · about ${inches(basin.melt_in)} in could melt this week`}
          </>
        )}
      </div>
    </li>
  );
}

function WeekStrip({ week, basinLabel }) {
  if (!week?.length) return null;
  return (
    <div className="snowpack__week">
      <div className="snowpack__week-title">Next seven days · {basinLabel}</div>
      <ol className="snowpack__days">
        {week.map((d) => {
          const thaw = (d.high_f + d.low_f) / 2 > 32;
          return (
            <li key={d.date} className={`snowpack__day${thaw ? ' snowpack__day--thaw' : ''}`}>
              <span className="snowpack__day-name">{weekday(d.date)}</span>
              <span className="snowpack__day-temps">
                {d.high_f}°<span className="snowpack__day-low"> / {d.low_f}°</span>
              </span>
              <span className="snowpack__day-precip">
                {d.snow_in >= 0.1 ? `${inches(d.snow_in)}″ snow` : d.rain_in >= 0.05 ? `${d.rain_in.toFixed(2)}″ rain` : ' '}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="snowpack__week-key">
        <span className="snowpack__key-swatch" aria-hidden="true" /> Days averaging above freezing
      </div>
    </div>
  );
}

export default function SnowpackPanel({ snowpack }) {
  if (!snowpack?.show || !snowpack.basins?.length) return null;

  const scale = Math.max(MIN_SCALE_IN, snowpack.max_swe_in || 0);
  const analysed = formatAnalysisDate(snowpack.valid);

  return (
    <>
      <div className="section-header" id="snowpack" style={{ marginTop: 'var(--space-lg)' }}>
        <h2 className="section-header__title">Snowpack &amp; Spring Melt</h2>
        <span className="section-header__subtitle">
          NOAA snow analysis{analysed && ` · ${analysed}`}
        </span>
      </div>

      <div className={`snowpack snowpack--${snowpack.class || 'none'}`}>
        <p className="snowpack__headline">{snowpack.headline}</p>
        <p className="snowpack__detail">{snowpack.detail}</p>

        {/* Five empty bars say nothing "No snowpack yet" hasn't already. */}
        {snowpack.max_swe_in >= 0.1 && (
          <ul className="snowpack__basins">
            {snowpack.basins.map((b) => (
              <BasinRow key={b.key} basin={b} scale={scale} />
            ))}
          </ul>
        )}

        <WeekStrip week={snowpack.week} basinLabel={snowpack.max_basin} />

        <p className="snowpack__note">
          “Inches of water” is the snow water equivalent: the depth of water left if the snow
          melted in place. Melt figures are a rough estimate from forecast temperatures, not a flood
          forecast. Frozen ground, rain and how fast it warms all change what reaches the rivers.{' '}
          <a href={snowpack.outlook_url} target="_blank" rel="noopener noreferrer">
            NWS river forecast and long-range outlook for Rothschild
          </a>{' '}
          ·{' '}
          <a href={snowpack.source_url} target="_blank" rel="noopener noreferrer">
            NOAA national snow analysis
          </a>
        </p>
      </div>
    </>
  );
}
