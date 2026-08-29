import React, { lazy, Suspense, useState, useEffect, useRef, useMemo, useCallback } from 'react';
import GaugeCard from './components/GaugeCard';
import AlertBanner from './components/AlertBanner';
import ReservoirCard, { LakeCard } from './components/ReservoirCard';
import RegionChips from './components/RegionChips';
import FishingConditions from './components/FishingConditions';
import FishingReference from './components/FishingReference';
import WeatherForecast from './components/WeatherForecast';
import CommunityBar from './components/CommunityBar';
import ConditionsSummary from './components/ConditionsSummary';
import EventsCalendar from './components/EventsCalendar';
import SponsorStrip from './components/SponsorStrip';
import HeroStatus from './components/HeroStatus';
import FloodAlertSignup from './components/FloodAlertSignup';
import SkeletonPage from './components/SkeletonPage';
import GaugeFilter, { FILTER_PREDICATES } from './components/GaugeFilter';
import GlanceTable from './components/GlanceTable';
import SectionNav from './components/SectionNav';
import LazyMount from './components/LazyMount';
import { trackEvent } from './utils/analytics';

import logoUrl from './assets/logo-32.png';

// Leaflet ships in its own on-demand chunk; the overview map mounts only
// when scrolled near (see LazyMount below), keeping the initial load light.
const OverviewMap = lazy(() => import('./components/OverviewMap'));

// In dev, Vite serves the repo's source tree directly — a plain path avoids
// the `new URL(..., import.meta.url)` form, which also emitted a duplicate
// 312 KB copy of the JSON into the production build as a hashed asset.
const DATA_URL = import.meta.env.DEV
  ? '/src/data/river-data.json'
  : `${import.meta.env.BASE_URL}data/river-data.json`;

// public/ files are served at the site root in dev, same as in the build.
const SPONSOR_URL = `${import.meta.env.BASE_URL}data/sponsor.json`;

const REFRESH_MS = 30 * 60 * 1000;      // matches the data cron cadence
const VISIBLE_REFRESH_MS = 10 * 60 * 1000; // refetch on tab return if older
const STALE_MS = 2 * 60 * 60 * 1000;    // warn when data is >2h old
const FILTER_STORAGE_KEY = 'wpr-gauge-filter';

function formatUpdatedAt(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`;

    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

// Build a CSS-var override style if the active sponsor specifies an accent color.
function sponsorAccentStyle(sponsor) {
  if (!sponsor?.enabled || !sponsor?.accent_color) return undefined;
  const c = sponsor.accent_color;
  return {
    '--accent': c,
    '--accent-dark': `color-mix(in srgb, ${c}, black 18%)`,
    '--accent-light': `color-mix(in srgb, ${c}, white 88%)`,
  };
}

function initialFilter() {
  try {
    const saved = window.localStorage.getItem(FILTER_STORAGE_KEY);
    return saved && FILTER_PREDICATES[saved] ? saved : 'all';
  } catch {
    return 'all';
  }
}

export default function App() {
  const [data, setData] = useState(null);
  const [sponsor, setSponsor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState(initialFilter);
  const [selectedGaugeId, setSelectedGaugeId] = useState(null);
  const [, setClockTick] = useState(0); // re-renders relative timestamps
  const gaugeRefs = useRef({});
  const lastFetchRef = useRef(0);
  const fetchSeqRef = useRef(0);

  const fetchData = useCallback((isRefresh = false) => {
    // The interval refresh and the tab-return refresh can overlap; tag each
    // fetch so a slow older response can't overwrite a newer one.
    const seq = ++fetchSeqRef.current;
    // Cache-bust refreshes so GitHub Pages' edge cache can't pin old data.
    const dataUrl = isRefresh ? `${DATA_URL}?t=${Date.now()}` : DATA_URL;
    const jobs = [
      fetch(dataUrl).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
    ];
    if (!isRefresh) {
      jobs.push(fetch(SPONSOR_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    }
    return Promise.all(jobs)
      .then(([d, s]) => {
        if (seq !== fetchSeqRef.current) return; // superseded by a newer fetch
        lastFetchRef.current = Date.now();
        setData(d);
        if (!isRefresh) setSponsor(s);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load river data:', err);
        // Keep showing the previous data on a failed refresh.
        if (!isRefresh) {
          setError(err.message);
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    fetchData(false);
  }, [fetchData]);

  // Keep an embedded/left-open widget current: periodic refresh, a refetch
  // when the tab becomes visible again, and a minute tick so "12m ago"
  // relative labels don't freeze.
  useEffect(() => {
    const interval = setInterval(() => fetchData(true), REFRESH_MS);
    const tick = setInterval(() => setClockTick((t) => t + 1), 60 * 1000);
    const onVisible = () => {
      if (
        document.visibilityState === 'visible' &&
        Date.now() - lastFetchRef.current > VISIBLE_REFRESH_MS
      ) {
        fetchData(true);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      clearInterval(tick);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [fetchData]);

  // Hooks must run on every render — compute derived data even when loading.
  const hasData = (g) =>
    g.current?.gage_height_ft != null || g.current?.streamflow_cfs != null;
  const statusOrder = { major: 0, moderate: 1, minor: 2, action: 3, normal: 4 };

  // Worst status first; gauges with no current reading sort last but still
  // render (their cards explain why — discontinued/offline — and can carry
  // a model-only forecast).
  const sortedGauges = useMemo(() => {
    if (!data) return [];
    return [...data.gauges].sort((a, b) => {
      const dataRank = (hasData(a) ? 0 : 1) - (hasData(b) ? 0 : 1);
      if (dataRank !== 0) return dataRank;
      return (statusOrder[a.flood_status] ?? 4) - (statusOrder[b.flood_status] ?? 4);
    });
  }, [data]);

  const reportingGauges = useMemo(() => sortedGauges.filter(hasData), [sortedGauges]);

  const filteredGauges = useMemo(
    () => sortedGauges.filter(FILTER_PREDICATES[filter] || FILTER_PREDICATES.all),
    [sortedGauges, filter]
  );

  // A persisted filter can be empty against today's data (e.g. "Flooding"
  // saved during a flood event) — fall back to All rather than a blank grid.
  useEffect(() => {
    if (!loading && filter !== 'all' && sortedGauges.length > 0 && filteredGauges.length === 0) {
      setFilter('all');
    }
  }, [loading, filter, sortedGauges, filteredGauges]);

  // Mirror filteredGauges in a ref so scrollToGauge stays referentially
  // stable — it's a dep of the overview map's pins effect, and a new
  // identity per filter click rebuilt every marker, tooltip, and ring.
  const filteredGaugesRef = useRef(filteredGauges);
  filteredGaugesRef.current = filteredGauges;

  const scrollToGauge = useCallback((gaugeId) => {
    // Selection is shared with the overview map (halo + pan).
    setSelectedGaugeId(gaugeId);
    const doScroll = () =>
      gaugeRefs.current[gaugeId]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const visible = filteredGaugesRef.current.some((g) => g.id === gaugeId);
    if (!visible) {
      setFilter('all');
      setTimeout(doScroll, 120); // let the full grid render first
    } else {
      doScroll();
    }
  }, []);

  // Deep links: #gauge-05398000 scrolls to that card (articles can link
  // straight to a river).
  useEffect(() => {
    if (loading || !data) return;
    const m = window.location.hash.match(/^#gauge-(\w+)$/);
    if (m) setTimeout(() => scrollToGauge(m[1]), 150);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  if (loading) {
    return (
      <div className="widget-container">
        <SkeletonPage />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="widget-container">
        <div className="error-state">
          Unable to load river data. Please try again later.
        </div>
      </div>
    );
  }

  const activeCount = reportingGauges.length;
  const wrapperStyle = sponsorAccentStyle(sponsor);
  const reservoirsReporting = (data.reservoirs || []).filter((r) => r.has_data);
  const isStale = data.generated_at && Date.now() - new Date(data.generated_at).getTime() > STALE_MS;

  const handleFilterChange = (key) => {
    setFilter(key);
    try {
      window.localStorage.setItem(FILTER_STORAGE_KEY, key);
    } catch {
      // private mode — persistence is best-effort
    }
    trackEvent('gauge_filter', { filter: key });
  };

  const navSections = [
    { id: 'gauges', label: 'Rivers' },
    data.fishing_conditions ? { id: 'fishing', label: 'Fishing' } : null,
    data.weather_forecast?.length ? { id: 'weather', label: 'Weather' } : null,
    { id: 'map', label: 'Map' },
    reservoirsReporting.length > 0 ? { id: 'reservoirs', label: 'Reservoirs' } : null,
  ].filter(Boolean);

  return (
    <div className="widget-container" style={wrapperStyle}>
      {/* Chrome Bar */}
      <div className="chrome-bar">
        <a
          className="chrome-bar__brand"
          href="https://wausaupilotandreview.com"
          target="_blank"
          rel="noopener noreferrer"
        >
          <img className="chrome-bar__logo-img" src={logoUrl} alt="Wausau Pilot & Review" />
          <span className="chrome-bar__logo">Wausau Pilot & Review</span>
          <span className="chrome-bar__divider" />
          <span className="chrome-bar__section-name">River Conditions</span>
        </a>
        <span className="chrome-bar__updated">
          {formatUpdatedAt(data.generated_at)}
        </span>
      </div>

      {/* Data-freshness warning — shown only if the feed pipeline stalls */}
      {isStale && (
        <div className="stale-banner" role="status">
          Data feed delayed — readings were last updated{' '}
          {formatUpdatedAt(data.generated_at)}. Showing the most recent available.
        </div>
      )}

      {/* Sponsor Strip — sponsor.json drives display or "Reach out" CTA. */}
      <SponsorStrip sponsor={sponsor} />

      {/* Hero status (worst flood status across all gauges) */}
      <HeroStatus gauges={data.gauges} />

      {/* NWS alerts (above the fold when active) */}
      <AlertBanner alerts={data.alerts} />

      {/* Sticky in-widget navigation (the WP embed is a 900px window) */}
      <SectionNav sections={navSections} />

      {/* Region-wide context: rain headed for the basins, drought status */}
      <RegionChips gauges={data.gauges} drought={data.drought} />

      {/* Answer-first summary: every reporting gauge in one screen */}
      <GlanceTable gauges={reportingGauges} onSelect={scrollToGauge} />

      {/* Stream Gauges */}
      <div className="section-header" id="gauges">
        <h2 className="section-header__title">Stream Gauges</h2>
        <span className="section-header__subtitle">
          {activeCount} of {data.gauges.length} reporting · Central Wisconsin
        </span>
      </div>

      <GaugeFilter gauges={sortedGauges} active={filter} onChange={handleFilterChange} />

      <div className="gauges-grid">
        {filteredGauges.map((gauge) => (
          <div
            key={gauge.id}
            id={`gauge-${gauge.id}`}
            className="gauge-card-anchor"
            ref={(el) => { if (el) gaugeRefs.current[gauge.id] = el; }}
          >
            <GaugeCard gauge={gauge} />
          </div>
        ))}
      </div>

      {/* Fishing Conditions */}
      {data.fishing_conditions && (
        <>
          <div className="section-header" id="fishing" style={{ marginTop: 'var(--space-lg)' }}>
            <h2 className="section-header__title">Fishing Conditions</h2>
            <span className="section-header__subtitle">
              Wausau area · updated every 30 min
            </span>
          </div>
          <FishingConditions conditions={data.fishing_conditions} />
        </>
      )}

      {/* 5-day weather forecast */}
      {data.weather_forecast?.length > 0 && (
        <div id="weather">
          <WeatherForecast forecast={data.weather_forecast} />
        </div>
      )}

      {/* Conditions narrative & seasonal activity */}
      <ConditionsSummary
        summary={data.conditions_summary}
        seasonal={data.seasonal_activity}
      />

      {/* Overview map — orientation, below the readings it locates */}
      <div id="map">
        <LazyMount minHeight={340}>
          <Suspense
            fallback={
              <div className="overview-map-wrap">
                <div className="overview-map" aria-hidden="true" />
              </div>
            }
          >
            <OverviewMap
              gauges={data.gauges}
              reservoirs={data.reservoirs || []}
              alerts={data.alerts || []}
              selectedId={selectedGaugeId}
              onGaugeClick={scrollToGauge}
            />
          </Suspense>
        </LazyMount>
      </div>

      {/* Flood-alert email signup (Web3Forms) */}
      <FloodAlertSignup />

      {/* Upcoming Events */}
      <EventsCalendar events={data.upcoming_events} />

      {/* Reservoirs & lakes */}
      {(reservoirsReporting.length > 0 || (data.lakes || []).length > 0) && (
        <>
          <div className="section-header" id="reservoirs" style={{ marginTop: 'var(--space-lg)' }}>
            <h2 className="section-header__title">Reservoirs &amp; Lakes</h2>
            <span className="section-header__subtitle">
              {reservoirsReporting.length} WVIC reservoirs
              {(data.lakes || []).length > 0 && ` · ${data.lakes.length} lake levels (NWS)`}
            </span>
          </div>

          <div className="reservoirs-grid">
            {reservoirsReporting.map((reservoir) => (
              <ReservoirCard key={reservoir.slug} reservoir={reservoir} />
            ))}
            {(data.lakes || []).map((lake) => (
              <LakeCard key={lake.lid} lake={lake} />
            ))}
          </div>
        </>
      )}

      {/* Fishing Guide */}
      <FishingReference gauges={data.gauges} />

      {/* Community */}
      <CommunityBar links={data.community_links} />

      {/* Footer */}
      <footer className="widget-footer">
        <div className="widget-footer__sources">
          Data from{' '}
          <a href="https://waterservices.usgs.gov/" target="_blank" rel="noopener noreferrer">
            USGS Water Services
          </a>
          {' · '}
          <a href="https://api.weather.gov/" target="_blank" rel="noopener noreferrer">
            National Weather Service
          </a>
          {' · '}
          <a href="https://water.noaa.gov/about/nwm" target="_blank" rel="noopener noreferrer">
            NOAA National Water Model
          </a>
          {' · '}
          <a href="https://wvic.com/" target="_blank" rel="noopener noreferrer">
            WVIC
          </a>
          {' · '}
          <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
            Open-Meteo
          </a>
          {' · '}
          <a href="https://droughtmonitor.unl.edu/" target="_blank" rel="noopener noreferrer">
            U.S. Drought Monitor (NDMC/USDA/NOAA)
          </a>
          {' · '}
          <a href="https://solunar.org/" target="_blank" rel="noopener noreferrer">
            Solunar
          </a>
          {' · '}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">
            OpenStreetMap
          </a>
        </div>
        <div className="widget-footer__disclaimer">
          Data is provisional and subject to revision. Always consult official sources
          for safety decisions. Do not drive through flooded areas.
        </div>
      </footer>
    </div>
  );
}
