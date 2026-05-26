import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Status colors must match --status-* in index.css.
const STATUS_COLORS = {
  normal:   { color: '#16a34a', label: 'Normal' },
  action:   { color: '#ca8a04', label: 'Action' },
  minor:    { color: '#ea580c', label: 'Minor Flood' },
  moderate: { color: '#dc2626', label: 'Moderate Flood' },
  major:    { color: '#991b1b', label: 'Major Flood' },
};

// Marathon County roughly centers here; auto-fit overrides this anyway.
const FALLBACK_CENTER = [44.89, -89.69];

function makePin(color) {
  return L.divIcon({
    className: 'overview-map__pin',
    html: `<svg width="22" height="28" viewBox="0 0 22 28" xmlns="http://www.w3.org/2000/svg">
      <path d="M11 0C4.9 0 0 4.9 0 11c0 8.25 11 17 11 17s11-8.75 11-17C22 4.9 17.1 0 11 0z"
        fill="${color}" stroke="white" stroke-width="2"/>
      <circle cx="11" cy="11" r="4" fill="white"/>
    </svg>`,
    iconSize: [22, 28],
    iconAnchor: [11, 28],
    popupAnchor: [0, -24],
  });
}

export default function OverviewMap({ gauges, onGaugeClick }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const validGauges = gauges.filter((g) => g.lat && g.lon);
    if (validGauges.length === 0) return;

    const map = L.map(containerRef.current, {
      scrollWheelZoom: false,
      zoomControl: true,
    }).setView(FALLBACK_CENTER, 9);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);

    const markers = [];
    validGauges.forEach((g) => {
      const conf = STATUS_COLORS[g.flood_status] || STATUS_COLORS.normal;
      const m = L.marker([g.lat, g.lon], { icon: makePin(conf.color) })
        .addTo(map)
        .bindPopup(
          `<div class="map-pin-label">${g.short_name}</div>
           <div class="map-pin-status" style="color:${conf.color}">${conf.label}</div>`
        );
      m.on('click', () => onGaugeClick?.(g.id));
      markers.push(m);
    });

    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds(), { padding: [24, 24], maxZoom: 11 });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="overview-map-wrap">
      <div ref={containerRef} className="overview-map" />
      <div className="overview-map-legend">
        {Object.entries(STATUS_COLORS).map(([key, { color, label }]) => (
          <span key={key} className="overview-map-legend__item">
            <span
              className="overview-map-legend__swatch"
              style={{ background: color }}
            />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
