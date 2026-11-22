import React from 'react';

const STATUS_CONFIG = {
  major: {
    label: 'Major Flooding',
    detail: 'Take action — life-threatening flooding likely. Do not drive through flooded roads.',
    mod: 'major',
  },
  moderate: {
    label: 'Moderate Flooding',
    detail: 'Significant flooding of roads and low-lying property.',
    mod: 'moderate',
  },
  minor: {
    label: 'Minor Flooding',
    detail: 'Minor flooding of low-lying areas. Use caution near rivers and streams.',
    mod: 'minor',
  },
  action: {
    label: 'Action Stage',
    detail: 'Rivers approaching flood stage. Monitoring recommended.',
    mod: 'action',
  },
  normal: {
    label: 'All Clear',
    detail: 'River levels normal across central Wisconsin.',
    mod: 'normal',
  },
};

const SEVERITY_ORDER = ['major', 'moderate', 'minor', 'action', 'normal'];

function worstStatus(gauges) {
  for (const s of SEVERITY_ORDER) {
    if (gauges.some((g) => g.flood_status === s)) return s;
  }
  return 'normal';
}

// Past this age the readings can't support a status claim either way: an
// "All Clear" over day-old data would stay green straight through a flood.
const UNKNOWN_AFTER_MS = 6 * 60 * 60 * 1000;

function formatAge(ms) {
  const hours = Math.round(ms / 3600000);
  if (hours < 48) return `${hours} hours`;
  return `${Math.round(hours / 24)} days`;
}

export default function HeroStatus({ gauges, generatedAt }) {
  if (!gauges || gauges.length === 0) return null;

  const ageMs = generatedAt ? Date.now() - new Date(generatedAt).getTime() : 0;
  if (ageMs > UNKNOWN_AFTER_MS) {
    return (
      <div className="hero-status hero-status--unknown" role="status">
        <div className="hero-status__label">Current Status · Central Wisconsin</div>
        <h1 className="hero-status__headline">Status unavailable</h1>
        <div className="hero-status__detail">
          Our river data is {formatAge(ageMs)} old, so we can’t confirm current conditions.
          Check the{' '}
          <a href="https://water.noaa.gov/wfo/grb" target="_blank" rel="noopener noreferrer">
            National Weather Service
          </a>{' '}
          for flood warnings.
        </div>
      </div>
    );
  }

  const worst = worstStatus(gauges);
  const conf = STATUS_CONFIG[worst];
  const flooding = gauges.filter((g) =>
    ['minor', 'moderate', 'major'].includes(g.flood_status)
  );
  const action = gauges.filter((g) => g.flood_status === 'action');

  let detail = conf.detail;
  if (flooding.length > 0) {
    detail = `${flooding.map((g) => g.short_name).join(', ')} at flood stage.`;
  } else if (action.length > 0) {
    detail = `${action.map((g) => g.short_name).join(', ')} above action stage — monitoring.`;
  }

  return (
    <div className={`hero-status hero-status--${conf.mod}`} role="status">
      <div className="hero-status__label">Current Status · Central Wisconsin</div>
      {/* The page h1: the SEO prerender's heading is wiped when React
          mounts, so this is the only top-level heading readers get. */}
      <h1 className="hero-status__headline">{conf.label}</h1>
      <div className="hero-status__detail">{detail}</div>
    </div>
  );
}
