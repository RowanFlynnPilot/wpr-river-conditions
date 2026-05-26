import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { trackEvent } from '../utils/analytics';

const GAUGE_ICON = L.divIcon({
  className: 'gauge-map__pin',
  html: `<svg width="22" height="28" viewBox="0 0 22 28" xmlns="http://www.w3.org/2000/svg">
    <path d="M11 0C4.9 0 0 4.9 0 11c0 8.25 11 17 11 17s11-8.75 11-17C22 4.9 17.1 0 11 0z"
      fill="#0d7377" stroke="white" stroke-width="2"/>
    <circle cx="11" cy="11" r="4" fill="white"/>
  </svg>`,
  iconSize: [22, 28],
  iconAnchor: [11, 28],
  popupAnchor: [0, -24],
});

const ACCESS_ICON = L.divIcon({
  className: 'gauge-map__access-pin',
  html: `<svg width="18" height="22" viewBox="0 0 18 22" xmlns="http://www.w3.org/2000/svg">
    <path d="M9 0C4 0 0 4 0 9c0 6.75 9 13 9 13s9-6.25 9-13C18 4 14 0 9 0z"
      fill="#ca8a04" stroke="white" stroke-width="2"/>
    <circle cx="9" cy="9" r="3" fill="white"/>
  </svg>`,
  iconSize: [18, 22],
  iconAnchor: [9, 22],
  popupAnchor: [0, -20],
});

function GaugeMapInner({ gauge }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const points = [];
    if (gauge.lat && gauge.lon) points.push([gauge.lat, gauge.lon]);
    (gauge.fishing?.access_points || []).forEach((p) => {
      if (p.lat && p.lng) points.push([p.lat, p.lng]);
    });

    if (points.length === 0) return;

    const map = L.map(containerRef.current, {
      scrollWheelZoom: false,
      zoomControl: false,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);

    if (gauge.lat && gauge.lon) {
      L.marker([gauge.lat, gauge.lon], { icon: GAUGE_ICON })
        .addTo(map)
        .bindPopup(`<div class="map-pin-label">${gauge.short_name}</div>`);
    }

    (gauge.fishing?.access_points || []).forEach((p) => {
      if (!p.lat || !p.lng) return;
      L.marker([p.lat, p.lng], { icon: ACCESS_ICON })
        .addTo(map)
        .bindPopup(
          `<div class="map-pin-label">${p.name}</div>
           <div class="map-pin-status">${p.directions || ''}</div>`
        );
    });

    if (points.length === 1) {
      map.setView(points[0], 13);
    } else {
      map.fitBounds(points, { padding: [16, 16], maxZoom: 13 });
    }

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [gauge]);

  return <div ref={containerRef} className="gauge-map" />;
}

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
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) trackEvent('gauge_map_open', { gauge: gauge.id });
        }}
      >
        {label}
      </button>
      {open && <GaugeMapInner gauge={gauge} />}
    </div>
  );
}
