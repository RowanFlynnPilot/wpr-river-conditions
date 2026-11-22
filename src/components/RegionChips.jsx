import React from 'react';

// Region-wide context that isn't tied to one gauge: how much rain is
// headed for the basins, and where the Drought Monitor has the coverage
// area, and how much water is sitting in the snowpack. Each renders only
// when it has something to say.
export default function RegionChips({ gauges, drought, snowpack }) {
  // Wettest basin in the next 24h — the one that explains tomorrow.
  let wettest = null;
  for (const g of gauges || []) {
    const r = g.upstream_rain;
    if (r && r.inches > 0 && (!wettest || r.inches > wettest.inches)) wettest = r;
  }

  const showRain = wettest && wettest.inches >= 0.1;
  const showDrought = drought?.any_drought && drought.counties?.length;
  // Half an inch of water is the point where the snowpack starts to matter
  // to the rivers; below that the panel further down is enough.
  const showSnow = snowpack?.show && snowpack.max_swe_in >= 0.5;
  const snowActive = snowpack?.class === 'melting' || snowpack?.class === 'rapid';
  if (!showRain && !showDrought && !showSnow) return null;

  // Name only the counties at (or worse than) the headline class, then
  // count the rest — so a D0 county is never implied to be in D1.
  const atWorst = drought?.worst_counties || [];
  const others = showDrought ? drought.counties.length - atWorst.length : 0;
  const droughtNames =
    atWorst.slice(0, 3).join(', ') +
    (atWorst.length > 3 ? ` +${atWorst.length - 3}` : '') +
    (others > 0 ? `, ${others} more count${others > 1 ? 'ies' : 'y'} drier than normal` : '');

  return (
    <div className="region-chips">
      {showRain && (
        <span
          className={`region-chip region-chip--rain${wettest.inches >= 0.75 ? ' region-chip--rain-heavy' : ''}`}
          title={`Heaviest 24-hour rainfall forecast across the monitored headwaters (${wettest.label})`}
        >
          <span aria-hidden="true">🌧️</span>
          <strong>{wettest.inches.toFixed(2)} in</strong> rain forecast upstream ·{' '}
          {wettest.label}
        </span>
      )}
      {showSnow && (
        <a
          className={`region-chip region-chip--snow${snowActive ? ' region-chip--snow-melting' : ''}`}
          href="#snowpack"
          title={`${snowpack.headline}. ${snowpack.detail}`}
        >
          <span aria-hidden="true">❄️</span>
          <strong>{snowpack.max_swe_in.toFixed(1)} in</strong> of water in the snowpack
          {snowActive ? ', melting' : ''} · {snowpack.max_basin}
        </a>
      )}
      {showDrought && (
        <a
          className="region-chip region-chip--drought"
          href={drought.source_url || 'https://droughtmonitor.unl.edu/'}
          target="_blank"
          rel="noopener noreferrer"
          title={`U.S. Drought Monitor, map dated ${drought.map_date}.${
            drought.sliver_note ? ` ${drought.sliver_note}.` : ''
          } Produced by NDMC, USDA and NOAA.`}
        >
          <span aria-hidden="true">🌾</span>
          <strong>{drought.worst_class}</strong> {drought.worst_label} · {droughtNames}
        </a>
      )}
      {showDrought && drought.sliver_note && (
        <span className="region-chips__note">{drought.sliver_note}</span>
      )}
    </div>
  );
}
