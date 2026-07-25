import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { computeTrend, trendText, TREND_ARROWS } from '../utils/trend';
import { trackEvent } from '../utils/analytics';

// Status colors must match --status-* in index.css.
const STATUS_COLORS = {
  normal:   { color: '#16a34a', label: 'Normal' },
  action:   { color: '#ca8a04', label: 'Action' },
  minor:    { color: '#ea580c', label: 'Minor Flood' },
  moderate: { color: '#dc2626', label: 'Moderate Flood' },
  major:    { color: '#991b1b', label: 'Major Flood' },
};

// Draw order: the common case (normal) renders first so rarer, worse
// statuses stay on top where pins crowd around Wausau.
const STATUS_DRAW_ORDER = { normal: 0, action: 1, minor: 2, moderate: 3, major: 4 };

// Overlays read different-in-kind from the status dots: slate diamonds for
// reservoirs, small teal triangles for boat launches.
const RESERVOIR_COLOR = '#5B7A99';

const FALLBACK_CENTER = [44.89, -89.69];

// Pin radii track zoom: compact at regional view, clickable at street
// level. Non-normal gauges stay a step bigger throughout.
function radiusFor(statusKey, zoom) {
  const grow = zoom >= 11 ? 2 : zoom >= 10 ? 1 : 0;
  return (statusKey === 'normal' ? 6 : 7.5) + grow;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function gaugeTipHtml(gauge) {
  const cur = gauge.current || {};
  const parts = [];
  if (cur.gage_height_ft != null) parts.push(`${cur.gage_height_ft.toFixed(2)} ft`);
  if (cur.streamflow_cfs != null) {
    parts.push(`${Math.round(cur.streamflow_cfs).toLocaleString('en-US')} cfs`);
  }
  const trend = computeTrend(gauge.history);
  const trendStr = trend ? ` · ${TREND_ARROWS[trend.dir]} ${trendText(trend)}` : '';
  return (
    `<span class="map-tip__name">${escapeHtml(gauge.short_name)}</span>` +
    `<span class="map-tip__sub">${escapeHtml(parts.join(' · ') || 'No current data')}${escapeHtml(trendStr)}</span>`
  );
}

export default function OverviewMap({ gauges, reservoirs = [], selectedId = null, onGaugeClick }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const gaugeLayerRef = useRef(null);
  const reservoirLayerRef = useRef(null);
  const launchLayerRef = useRef(null);
  const haloRef = useRef(null);

  const [shownStatuses, setShownStatuses] = useState({
    normal: true, action: true, minor: true, moderate: true, major: true,
  });
  const [showReservoirs, setShowReservoirs] = useState(true);
  const [showLaunches, setShowLaunches] = useState(false);

  const validGauges = useMemo(
    () => gauges.filter((g) => g.lat && g.lon),
    [gauges]
  );

  const statusCounts = useMemo(() => {
    const counts = {};
    for (const g of validGauges) {
      const key = STATUS_COLORS[g.flood_status] ? g.flood_status : 'normal';
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [validGauges]);

  const launchCount = useMemo(
    () =>
      gauges.reduce(
        (n, g) => n + (g.fishing?.access_points || []).filter((p) => p.lat && p.lng).length,
        0
      ),
    [gauges]
  );

  // --- Map init (once) ---
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined;

    const map = L.map(containerRef.current, {
      center: FALLBACK_CENTER,
      zoom: 9,
      minZoom: 7,
      // Scroll-zoom stays off until the reader clicks in, so the widget
      // never hijacks the page scroll inside the 900px embed.
      scrollWheelZoom: false,
      zoomControl: true,
    });
    map.on('focus click', () => map.scrollWheelZoom.enable());
    map.on('blur', () => map.scrollWheelZoom.disable());

    // Base tiles carry no labels; place labels render in their own pane
    // ABOVE the data, so "Wausau" stays readable over the pins.
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      maxZoom: 19,
    }).addTo(map);
    map.createPane('labels');
    map.getPane('labels').style.zIndex = 650;
    map.getPane('labels').style.pointerEvents = 'none';
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      pane: 'labels',
    }).addTo(map);

    // County outlines sit beneath the marker SVG (overlayPane is z 400).
    map.createPane('boundary');
    map.getPane('boundary').style.zIndex = 350;

    gaugeLayerRef.current = L.layerGroup().addTo(map);
    reservoirLayerRef.current = L.layerGroup().addTo(map);
    launchLayerRef.current = L.layerGroup().addTo(map);

    // Rescale gauge pins in place on zoom (not a React re-render).
    map.on('zoomend', () => {
      const zoom = map.getZoom();
      gaugeLayerRef.current?.eachLayer((m) => {
        if (m.options.statusKey) m.setRadius(radiusFor(m.options.statusKey, zoom));
      });
    });

    // Dashed five-county outline — orientation, quietly omitted on failure.
    const ac = new AbortController();
    fetch(`${import.meta.env.BASE_URL}data/counties.geojson`, { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => {
        if (!geo || !mapRef.current) return;
        const boundary = L.geoJSON(geo, {
          pane: 'boundary',
          interactive: false,
          style: { color: '#66756f', weight: 1.2, dashArray: '5 4', fill: false },
        }).addTo(mapRef.current);
        // Keep panning in the neighborhood (padded so the northern
        // reservoirs stay reachable).
        mapRef.current.setMaxBounds(boundary.getBounds().pad(0.6));
      })
      .catch(() => {});

    mapRef.current = map;
    // Debug handle for automated verification.
    containerRef.current._leafletMap = map;

    return () => {
      ac.abort();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Camera frames the gauges once at mount.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || validGauges.length === 0) return;
    const bounds = L.latLngBounds(validGauges.map((g) => [g.lat, g.lon]));
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.12), { maxZoom: 10 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Gauge pins ---
  useEffect(() => {
    const map = mapRef.current;
    const group = gaugeLayerRef.current;
    if (!map || !group) return;
    group.clearLayers();

    const ordered = [...validGauges].sort(
      (a, b) =>
        (STATUS_DRAW_ORDER[a.flood_status] ?? 0) - (STATUS_DRAW_ORDER[b.flood_status] ?? 0)
    );

    for (const g of ordered) {
      const key = STATUS_COLORS[g.flood_status] ? g.flood_status : 'normal';
      if (!shownStatuses[key]) continue;
      const conf = STATUS_COLORS[key];
      // White stroke separates overlapping dots on the light basemap.
      const marker = L.circleMarker([g.lat, g.lon], {
        radius: radiusFor(key, map.getZoom()),
        color: '#ffffff',
        weight: 1.5,
        fillColor: conf.color,
        fillOpacity: 0.92,
        statusKey: key,
      });
      marker.bindTooltip(gaugeTipHtml(g), {
        className: 'map-tip',
        direction: 'top',
        offset: [0, -6],
      });
      marker.on('click', () => onGaugeClick?.(g.id));
      marker.addTo(group);
    }
  }, [validGauges, shownStatuses, onGaugeClick]);

  // --- Reservoir diamonds (toggleable overlay) ---
  useEffect(() => {
    const group = reservoirLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!showReservoirs) return;

    for (const r of reservoirs) {
      if (r.lat == null || r.lon == null) continue;
      const marker = L.marker([r.lat, r.lon], {
        icon: L.divIcon({
          className: 'rsv-pin',
          html: `<span class="rsv-pin__diamond" style="background:${RESERVOIR_COLOR}"></span>`,
          iconSize: [15, 15],
        }),
        keyboard: false,
      });
      const sub = r.feet_below_max != null
        ? `${Math.abs(r.feet_below_max).toFixed(1)} ft below max`
        : 'Not currently reported';
      marker.bindTooltip(
        `<span class="map-tip__name">${escapeHtml(r.name)}</span>` +
          `<span class="map-tip__sub">${escapeHtml(sub)}</span>`,
        { className: 'map-tip', direction: 'top', offset: [0, -8] }
      );
      marker.on('click', () => {
        document.getElementById('reservoirs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      marker.addTo(group);
    }
  }, [reservoirs, showReservoirs]);

  // --- Boat-launch triangles (toggleable overlay, off by default) ---
  useEffect(() => {
    const group = launchLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!showLaunches) return;

    for (const g of gauges) {
      for (const p of g.fishing?.access_points || []) {
        if (!p.lat || !p.lng) continue;
        const marker = L.marker([p.lat, p.lng], {
          icon: L.divIcon({
            className: 'launch-pin',
            html: '<span class="launch-pin__tri" aria-hidden="true">▲</span>',
            iconSize: [14, 14],
          }),
          keyboard: false,
        });
        marker.bindTooltip(
          `<span class="map-tip__name">${escapeHtml(p.name)}</span>` +
            `<span class="map-tip__sub">${escapeHtml(p.directions || g.short_name)}</span>`,
          { className: 'map-tip', direction: 'top', offset: [0, -8] }
        );
        marker.addTo(group);
      }
    }
  }, [gauges, showLaunches]);

  // --- Selection halo: the glance table / cards drive the map too ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (haloRef.current) {
      haloRef.current.remove();
      haloRef.current = null;
    }
    if (!selectedId) return;
    const g = validGauges.find((x) => x.id === selectedId);
    if (!g) return;
    const key = STATUS_COLORS[g.flood_status] ? g.flood_status : 'normal';
    haloRef.current = L.circleMarker([g.lat, g.lon], {
      radius: 13,
      color: STATUS_COLORS[key].color,
      weight: 3,
      fill: false,
      interactive: false,
    }).addTo(map);
    map.panTo([g.lat, g.lon]);
  }, [selectedId, validGauges]);

  const toggleStatus = (key) => (e) => {
    setShownStatuses((s) => ({ ...s, [key]: e.target.checked }));
    trackEvent('map_layer_toggle', { layer: key, on: e.target.checked });
  };

  // Legend rows only for statuses present today; the row order follows
  // severity so "Action · 2" surfaces right after Normal during events.
  const legendStatuses = Object.entries(STATUS_COLORS).filter(([key]) => statusCounts[key]);

  return (
    <div className="overview-map-wrap">
      <div
        ref={containerRef}
        className="overview-map"
        role="region"
        aria-label="Map of central Wisconsin river gauges, reservoirs, and boat launches"
      />
      <div className="overview-map-legend">
        {legendStatuses.map(([key, { color, label }]) => (
          <label key={key} className="overview-map-legend__toggle">
            <input
              type="checkbox"
              checked={shownStatuses[key]}
              onChange={toggleStatus(key)}
            />
            <span className="overview-map-legend__swatch" style={{ background: color }} />
            {label} · {statusCounts[key]}
          </label>
        ))}
        {reservoirs.some((r) => r.lat != null) && (
          <label className="overview-map-legend__toggle overview-map-legend__toggle--sep">
            <input
              type="checkbox"
              checked={showReservoirs}
              onChange={(e) => {
                setShowReservoirs(e.target.checked);
                trackEvent('map_layer_toggle', { layer: 'reservoirs', on: e.target.checked });
              }}
            />
            <span
              className="overview-map-legend__diamond"
              style={{ background: RESERVOIR_COLOR }}
            />
            Reservoirs
          </label>
        )}
        {launchCount > 0 && (
          <label className="overview-map-legend__toggle">
            <input
              type="checkbox"
              checked={showLaunches}
              onChange={(e) => {
                setShowLaunches(e.target.checked);
                trackEvent('map_layer_toggle', { layer: 'launches', on: e.target.checked });
              }}
            />
            <span className="overview-map-legend__launch" aria-hidden="true">▲</span>
            Boat launches · {launchCount}
          </label>
        )}
      </div>
    </div>
  );
}
