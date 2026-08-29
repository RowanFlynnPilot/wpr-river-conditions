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

// Neutral water color for river channels whose owning gauge is normal;
// segments switch to the status color when their gauge runs action+.
const RIVER_COLOR = '#4a90a4';

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

  // National Water Model outlook, when the payload carries one.
  const nwm = gauge.nwm_forecast;
  let fcstLine = '';
  if (nwm?.next24h_pct != null) {
    const arrow = TREND_ARROWS[nwm.class] || '→';
    const text = nwm.class === 'steady'
      ? 'holding steady'
      : `${nwm.next24h_pct > 0 ? '+' : ''}${nwm.next24h_pct}% next ${nwm.horizon_h || 24}h`;
    fcstLine = `<span class="map-tip__sub map-tip__fcst">Forecast: ${arrow} ${escapeHtml(text)}</span>`;
  }

  return (
    `<span class="map-tip__name">${escapeHtml(gauge.short_name)}</span>` +
    `<span class="map-tip__sub">${escapeHtml(parts.join(' · ') || 'No current data')}${escapeHtml(trendStr)}</span>` +
    fcstLine
  );
}

// Flood status from a historical stage reading — same thresholds the
// scraper applies to the live reading (used by the replay scrubber).
function statusFromHeight(ht, stages) {
  if (!stages || ht == null) return 'normal';
  if (ht >= stages.major) return 'major';
  if (ht >= stages.moderate) return 'moderate';
  if (ht >= stages.minor) return 'minor';
  if (ht >= stages.action) return 'action';
  return 'normal';
}

function fmtReplayTime(ms) {
  return new Date(ms).toLocaleString('en-US', {
    weekday: 'short',
    hour: 'numeric',
  });
}

export default function OverviewMap({
  gauges,
  reservoirs = [],
  alerts = [],
  selectedId = null,
  onGaugeClick,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const gaugeLayerRef = useRef(null);
  const reservoirLayerRef = useRef(null);
  const launchLayerRef = useRef(null);
  const riverLayerRef = useRef(null);
  const boundaryRef = useRef(null);
  const haloRef = useRef(null);
  const radarLayerRef = useRef(null);
  const markersByIdRef = useRef({});

  const [shownStatuses, setShownStatuses] = useState({
    normal: true, action: true, minor: true, moderate: true, major: true,
  });
  const [showReservoirs, setShowReservoirs] = useState(true);
  const [showLaunches, setShowLaunches] = useState(false);
  const [showRadar, setShowRadar] = useState(false);
  const [countiesGeo, setCountiesGeo] = useState(null);
  const [riversGeo, setRiversGeo] = useState(null);
  // Replay scrubber: null = live; otherwise an index into the timeline.
  const [replayIdx, setReplayIdx] = useState(null);
  // Mirrored for the map's zoomend handler, which is bound once at creation.
  const replayingRef = useRef(false);
  const [playing, setPlaying] = useState(false);

  const validGauges = useMemo(
    () => gauges.filter((g) => g.lat && g.lon),
    [gauges]
  );

  const gaugesById = useMemo(
    () => Object.fromEntries(gauges.map((g) => [g.id, g])),
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
      // Quarter-step zoom. fitBounds FLOORS to the nearest snap, so with
      // Leaflet's default integer snapping our coverage area (which wants
      // z7.75 in this container) drops all the way to z7 — showing half
      // the upper Midwest. Quarter steps keep the camera on the counties.
      zoomSnap: 0.25,
      zoomDelta: 0.5,
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

    // Stacking: radar (330) < boundary (350) < rivers (360) < markers (400).
    map.createPane('radar');
    map.getPane('radar').style.zIndex = 330;
    map.getPane('radar').style.pointerEvents = 'none';
    map.createPane('boundary');
    map.getPane('boundary').style.zIndex = 350;
    map.createPane('rivers');
    map.getPane('rivers').style.zIndex = 360;

    riverLayerRef.current = L.layerGroup().addTo(map);
    gaugeLayerRef.current = L.layerGroup().addTo(map);
    reservoirLayerRef.current = L.layerGroup().addTo(map);
    launchLayerRef.current = L.layerGroup().addTo(map);

    // Rescale gauge pins (and their pulse rings) in place on zoom. Skipped
    // during replay: pins there carry historical, flow-scaled radii, and
    // resizing from live statusKey would silently break that encoding.
    map.on('zoomend', () => {
      if (replayingRef.current) return;
      const zoom = map.getZoom();
      gaugeLayerRef.current?.eachLayer((m) => {
        if (m.options.statusKey) m.setRadius(radiusFor(m.options.statusKey, zoom));
        if (m.options.pulseFor) m.setRadius(radiusFor(m.options.pulseFor, zoom) + 5);
      });
    });

    // Static geometry, fetched once: county outlines (also the alert-shading
    // polygons) and the flow-oriented river network. Both are orientation/
    // ambience — quietly omitted on failure.
    const ac = new AbortController();
    fetch(`${import.meta.env.BASE_URL}data/counties.geojson`, { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => geo && setCountiesGeo(geo))
      .catch(() => {});
    fetch(`${import.meta.env.BASE_URL}data/rivers.geojson`, { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((geo) => geo && setRiversGeo(geo))
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

  // Camera frames the gauges once at mount, as tightly as the container
  // allows. Pixel padding (not a bounds pad) so the framing doesn't loosen
  // as the roster grows.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || validGauges.length === 0) return;
    const bounds = L.latLngBounds(validGauges.map((g) => [g.lat, g.lon]));
    // animate:false — this is the opening framing, so there's nothing to
    // animate from, and a zoom animation depends on animation frames that
    // never run while the document is hidden. The widget lazy-mounts inside
    // a backgrounded iframe often enough that an animated fit can strand
    // the map at its constructor zoom.
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [18, 18], maxZoom: 11, animate: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- County outlines + alert shading ---
  // Counties with an active alert fill with the alert's color (flood wins
  // over other categories), so a warning reads geographically at a glance.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !countiesGeo) return;
    if (boundaryRef.current) {
      boundaryRef.current.remove();
      boundaryRef.current = null;
    }

    const zoneCategory = {};
    for (const a of alerts || []) {
      for (const z of a.zones || []) {
        if (a.category === 'flood' || !zoneCategory[z]) zoneCategory[z] = a.category;
      }
    }

    const boundary = L.geoJSON(countiesGeo, {
      pane: 'boundary',
      interactive: false,
      style: (feature) => {
        const cat = zoneCategory[feature.properties?.zone];
        const base = { color: '#66756f', weight: 1.2, dashArray: '5 4', fill: false };
        if (!cat) return base;
        const alertColor = cat === 'flood' ? '#dc2626' : '#ca8a04';
        return {
          ...base,
          color: alertColor,
          weight: 1.6,
          fill: true,
          fillColor: alertColor,
          fillOpacity: 0.09,
        };
      },
    }).addTo(map);
    boundaryRef.current = boundary;
    // Keep panning near the coverage area (a little slack so the northern
    // reservoirs and the map's own edges stay reachable).
    map.setMaxBounds(boundary.getBounds().pad(0.25));
  }, [countiesGeo, alerts]);

  // --- The living river layer ---
  // Each segment: a soft base channel plus an animated dash overlay whose
  // direction follows the geometry (built upstream→downstream) and whose
  // speed follows the owning gauge's flow vs. normal. Color switches from
  // water-blue to the status color when the owner runs action stage or up.
  useEffect(() => {
    const map = mapRef.current;
    const group = riverLayerRef.current;
    if (!map || !group || !riversGeo) return;
    group.clearLayers();

    for (const f of riversGeo.features || []) {
      const coords = f.geometry?.coordinates || [];
      if (coords.length < 2) continue;
      const latlngs = coords.map(([lon, lat]) => [lat, lon]);
      const stem = !!f.properties?.stem;
      const owner = gaugesById[f.properties?.gauge];
      const status = owner && STATUS_COLORS[owner.flood_status] && owner.flood_status !== 'normal'
        ? owner.flood_status
        : null;
      const flowColor = status ? STATUS_COLORS[status].color : RIVER_COLOR;

      L.polyline(latlngs, {
        pane: 'rivers',
        interactive: false,
        color: RIVER_COLOR,
        weight: stem ? 5 : 3,
        opacity: 0.26,
        lineCap: 'round',
      }).addTo(group);

      const cls = owner?.normal_flow?.class;
      const speed =
        cls === 'much_above' || cls === 'above' ? 'riverflow--fast'
        : cls === 'much_below' || cls === 'below' ? 'riverflow--slow'
        : '';
      L.polyline(latlngs, {
        pane: 'rivers',
        interactive: false,
        color: flowColor,
        weight: stem ? 2.4 : 1.7,
        opacity: 0.85,
        lineCap: 'round',
        className: `riverflow ${speed}`.trim(),
      }).addTo(group);
    }
  }, [riversGeo, gaugesById]);

  // --- Gauge pins ---
  useEffect(() => {
    const map = mapRef.current;
    const group = gaugeLayerRef.current;
    if (!map || !group) return;
    group.clearLayers();
    markersByIdRef.current = {};

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

      // Gauges at action stage or above get a pulsing attention ring.
      let ring = null;
      if (key !== 'normal') {
        ring = L.circleMarker([g.lat, g.lon], {
          radius: radiusFor(key, map.getZoom()) + 5,
          color: conf.color,
          weight: 2,
          fill: false,
          interactive: false,
          className: 'gauge-pulse',
          pulseFor: key,
        }).addTo(group);
      }

      marker.addTo(group);
      markersByIdRef.current[g.id] = { marker, ring, key };
    }
  }, [validGauges, shownStatuses, onGaugeClick]);

  // --- Replay scrubber: 7 days of history on the pins ---
  // Timeline at 2h steps spanning every gauge's history.
  const timeline = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const g of gauges) {
      for (const h of g.history || []) {
        const t = Date.parse(h.timestamp);
        if (!Number.isNaN(t)) {
          if (t < min) min = t;
          if (t > max) max = t;
        }
      }
    }
    if (!Number.isFinite(min) || max - min < 12 * 3600e3) return [];
    const steps = [];
    for (let t = min; t <= max; t += 2 * 3600e3) steps.push(t);
    return steps;
  }, [gauges]);

  const replaySeries = useMemo(() => {
    const out = {};
    for (const g of gauges) {
      const pts = (g.history || [])
        .map((h) => ({ t: Date.parse(h.timestamp), ht: h.gage_height_ft, cfs: h.streamflow_cfs }))
        .filter((p) => !Number.isNaN(p.t));
      const flows = pts.map((p) => p.cfs).filter((v) => v != null);
      out[g.id] = {
        pts,
        lo: flows.length ? Math.min(...flows) : null,
        hi: flows.length ? Math.max(...flows) : null,
      };
    }
    return out;
  }, [gauges]);

  // A 30-min data refresh rebuilds the timeline, which can come back shorter
  // while the user is scrubbing near the end — clamp so timeline[replayIdx]
  // can't dereference past it ("Invalid Date" label, all pins gray).
  useEffect(() => {
    setReplayIdx((i) => {
      if (i == null) return i;
      if (timeline.length === 0) return null;
      return Math.min(i, timeline.length - 1);
    });
  }, [timeline.length]);

  // Restyle pins in place for the selected replay step (or restore live).
  useEffect(() => {
    replayingRef.current = replayIdx != null;
    const map = mapRef.current;
    if (!map) return;
    const zoom = map.getZoom();
    for (const g of validGauges) {
      const entry = markersByIdRef.current[g.id];
      if (!entry) continue;

      if (replayIdx == null) {
        const conf = STATUS_COLORS[entry.key];
        entry.marker.setStyle({ fillColor: conf.color, fillOpacity: 0.92 });
        entry.marker.setRadius(radiusFor(entry.key, zoom));
        if (entry.ring) entry.ring.setStyle({ opacity: 1 });
        continue;
      }

      // Pulse rings describe *now* — hide them while time-traveling.
      if (entry.ring) entry.ring.setStyle({ opacity: 0 });

      const t = timeline[replayIdx];
      const s = replaySeries[g.id];
      let best = null;
      let bestD = Infinity;
      for (const p of s?.pts || []) {
        const d = Math.abs(p.t - t);
        if (d < bestD) {
          bestD = d;
          best = p;
        }
      }
      if (!best || bestD > 90 * 60 * 1000) {
        entry.marker.setStyle({ fillColor: '#9ca3af', fillOpacity: 0.55 });
        entry.marker.setRadius(4);
        continue;
      }

      const st = statusFromHeight(best.ht, g.flood_stages);
      let r = radiusFor(st, zoom);
      // Size tracks that gauge's own flow range for the week, so small
      // trout streams move visibly too.
      if (best.cfs != null && s.hi != null && s.hi > s.lo) {
        const pct = (best.cfs - s.lo) / (s.hi - s.lo);
        r = 4.5 + 5 * pct + (st !== 'normal' ? 1.5 : 0);
      }
      entry.marker.setStyle({ fillColor: STATUS_COLORS[st].color, fillOpacity: 0.92 });
      entry.marker.setRadius(r);
    }
  }, [replayIdx, timeline, replaySeries, validGauges, shownStatuses]);

  // Advance the playhead while playing.
  useEffect(() => {
    if (!playing) return undefined;
    const iv = setInterval(() => {
      setReplayIdx((i) => {
        const next = i == null ? 0 : i + 1;
        if (next >= timeline.length) {
          setPlaying(false);
          return timeline.length - 1;
        }
        return next;
      });
    }, 300);
    return () => clearInterval(iv);
  }, [playing, timeline.length]);

  // --- Radar overlay (RainViewer latest frame) ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return undefined;
    if (radarLayerRef.current) {
      radarLayerRef.current.remove();
      radarLayerRef.current = null;
    }
    if (!showRadar) return undefined;
    const ac = new AbortController();
    fetch('https://api.rainviewer.com/public/weather-maps.json', { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        const frames = d?.radar?.past || [];
        const last = frames[frames.length - 1];
        if (!last || !d.host || !mapRef.current || radarLayerRef.current) return;
        radarLayerRef.current = L.tileLayer(
          `${d.host}${last.path}/256/{z}/{x}/{y}/4/1_1.png`,
          {
            pane: 'radar',
            opacity: 0.6,
            attribution: '<a href="https://www.rainviewer.com/">RainViewer</a>',
          }
        ).addTo(mapRef.current);
      })
      .catch(() => {});
    return () => ac.abort();
  }, [showRadar]);

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
      {timeline.length > 8 && (
        <div className="map-replay">
          <button
            type="button"
            className="map-replay__btn"
            aria-label={playing ? 'Pause replay' : 'Replay the past 7 days'}
            onClick={() => {
              if (playing) {
                setPlaying(false);
                return;
              }
              if (replayIdx == null || replayIdx >= timeline.length - 1) setReplayIdx(0);
              setPlaying(true);
              trackEvent('map_replay', { action: 'play' });
            }}
          >
            {playing ? '❚❚' : '▶'}
          </button>
          <input
            type="range"
            className="map-replay__slider"
            min="0"
            max={timeline.length - 1}
            value={replayIdx == null ? timeline.length - 1 : replayIdx}
            aria-label="Scrub through the past 7 days"
            onChange={(e) => {
              setPlaying(false);
              setReplayIdx(Number(e.target.value));
            }}
          />
          <span className="map-replay__label" aria-live="polite">
            {replayIdx == null ? 'Live' : fmtReplayTime(timeline[replayIdx])}
          </span>
          {replayIdx != null && (
            <button
              type="button"
              className="map-replay__live"
              onClick={() => {
                setPlaying(false);
                setReplayIdx(null);
              }}
            >
              Back to live
            </button>
          )}
        </div>
      )}
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
        <label className="overview-map-legend__toggle" title="Latest radar frame from RainViewer">
          <input
            type="checkbox"
            checked={showRadar}
            onChange={(e) => {
              setShowRadar(e.target.checked);
              trackEvent('map_layer_toggle', { layer: 'radar', on: e.target.checked });
            }}
          />
          <span className="overview-map-legend__radar" aria-hidden="true">◍</span>
          Radar
        </label>
      </div>
    </div>
  );
}
