import React, { lazy, Suspense, useState } from 'react';
import { trackEvent } from '../utils/analytics';

// The Leaflet-backed map lives in GaugeMapInner and is loaded on demand,
// so Leaflet stays out of the initial bundle (maps only exist post-click).
const GaugeMapInner = lazy(() => import('./GaugeMapInner'));

export default function GaugeMap({ gauge }) {
  const [open, setOpen] = useState(false);
  const accessCount = gauge.fishing?.access_points?.length || 0;
  const hasGaugeCoord = gauge.lat && gauge.lon;
  if (!hasGaugeCoord && accessCount === 0) return null;

  const label = accessCount > 0
    ? `${open ? 'Hide' : 'Show'} launches · ${accessCount}`
    : `${open ? 'Hide' : 'Show'} map`;

  return (
    <div>
      <button
        type="button"
        className="gauge-map-toggle"
        aria-expanded={open}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) trackEvent('gauge_map_open', { gauge: gauge.id });
        }}
      >
        {label}
      </button>
      {open && (
        <Suspense fallback={<div className="gauge-map" aria-hidden="true" />}>
          <GaugeMapInner gauge={gauge} />
        </Suspense>
      )}
    </div>
  );
}
