import React, { useState, useEffect, useRef, useMemo } from 'react';
import GaugeCard from './components/GaugeCard';
import AlertBanner from './components/AlertBanner';
import ReservoirCard from './components/ReservoirCard';
import FishingConditions from './components/FishingConditions';
import FishingReference from './components/FishingReference';
import WeatherForecast from './components/WeatherForecast';
import CommunityBar from './components/CommunityBar';
import ConditionsSummary from './components/ConditionsSummary';
import EventsCalendar from './components/EventsCalendar';
import SponsorStrip from './components/SponsorStrip';
import HeroStatus from './components/HeroStatus';
import OverviewMap from './components/OverviewMap';
import FloodAlertSignup from './components/FloodAlertSignup';
import SkeletonPage from './components/SkeletonPage';
import GaugeFilter, { FILTER_PREDICATES } from './components/GaugeFilter';
import { trackEvent } from './utils/analytics';

import logoUrl from './assets/logo-32.png';

const DATA_URL = import.meta.env.DEV
  ? new URL('./data/river-data.json', import.meta.url).href
  : `${import.meta.env.BASE_URL}data/river-data.json`;

const SPONSOR_URL = import.meta.env.DEV
  ? new URL('../public/data/sponsor.json', import.meta.url).href
  : `${import.meta.env.BASE_URL}data/sponsor.json`;

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

export default function App() {
  const [data, setData] = useState(null);
  const [sponsor, setSponsor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const gaugeRefs = useRef({});

  useEffect(() => {
    Promise.all([
      fetch(DATA_URL).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
      fetch(SPONSOR_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ])
      .then(([d, s]) => {
        setData(d);
        setSponsor(s);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load river data:', err);
        setError(err.message);
        setLoading(false);
      });
  }, []);

  // Hooks must run on every render — compute derived data even when loading.
  const hasData = (g) =>
    g.current?.gage_height_ft != null || g.current?.streamflow_cfs != null;
  const statusOrder = { major: 0, moderate: 1, minor: 2, action: 3, normal: 4 };

  const sortedGauges = useMemo(() => {
    if (!data) return [];
    return [...data.gauges]
      .filter(hasData)
      .sort(
        (a, b) =>
          (statusOrder[a.flood_status] ?? 4) - (statusOrder[b.flood_status] ?? 4)
      );
  }, [data]);

  const filteredGauges = useMemo(
    () => sortedGauges.filter(FILTER_PREDICATES[filter] || FILTER_PREDICATES.all),
    [sortedGauges, filter]
  );

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

  const activeCount = sortedGauges.length;
  const wrapperStyle = sponsorAccentStyle(sponsor);

  const handleGaugePinClick = (gaugeId) => {
    const el = gaugeRefs.current[gaugeId];
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const handleFilterChange = (key) => {
    setFilter(key);
    trackEvent('gauge_filter', { filter: key });
  };

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

      {/* Sponsor Strip — sponsor.json drives display or "Reach out" CTA. */}
      <SponsorStrip sponsor={sponsor} />

      {/* Hero status (worst flood status across all gauges) */}
      <HeroStatus gauges={data.gauges} />

      {/* NWS alerts (above the fold when active) */}
      <AlertBanner alerts={data.alerts} />

      {/* Overview map with one pin per gauge, color-coded by status */}
      <OverviewMap gauges={data.gauges} onGaugeClick={handleGaugePinClick} />

      {/* Flood-alert email signup (Web3Forms) */}
      <FloodAlertSignup />

      {/* 5-day weather forecast */}
      <WeatherForecast forecast={data.weather_forecast} />

      {/* Conditions narrative & seasonal activity */}
      <ConditionsSummary
        summary={data.conditions_summary}
        seasonal={data.seasonal_activity}
      />

      {/* Stream Gauges */}
      <div className="section-header">
        <h2 className="section-header__title">Stream Gauges</h2>
        <span className="section-header__subtitle">
          {activeCount} of {data.gauges.length} reporting · Marathon County
        </span>
      </div>

      <GaugeFilter gauges={sortedGauges} active={filter} onChange={handleFilterChange} />

      <div className="gauges-grid">
        {filteredGauges.map((gauge) => (
          <div
            key={gauge.id}
            ref={(el) => { if (el) gaugeRefs.current[gauge.id] = el; }}
          >
            <GaugeCard gauge={gauge} />
          </div>
        ))}
      </div>

      {/* Fishing Conditions */}
      {data.fishing_conditions && (
        <>
          <div className="section-header" style={{ marginTop: 'var(--space-lg)' }}>
            <h2 className="section-header__title">Fishing Conditions</h2>
            <span className="section-header__subtitle">
              Wausau area · updated every 30 min
            </span>
          </div>
          <FishingConditions conditions={data.fishing_conditions} />
        </>
      )}

      {/* Upcoming Events */}
      <EventsCalendar events={data.upcoming_events} />

      {/* Reservoirs */}
      {data.reservoirs && data.reservoirs.length > 0 && (
        <>
          <div className="section-header" style={{ marginTop: 'var(--space-lg)' }}>
            <h2 className="section-header__title">Reservoirs</h2>
            <span className="section-header__subtitle">
              {data.reservoirs.filter((r) => r.has_data).length} of{' '}
              {data.reservoirs.length} reporting · WVIC System
            </span>
          </div>

          <div className="reservoirs-grid">
            {data.reservoirs.filter((r) => r.has_data).map((reservoir) => (
              <ReservoirCard key={reservoir.slug} reservoir={reservoir} />
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
          <a href="https://wvic.com/" target="_blank" rel="noopener noreferrer">
            WVIC
          </a>
          {' · '}
          <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
            Open-Meteo
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
