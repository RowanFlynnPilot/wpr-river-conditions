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

export default function HeroStatus({ gauges }) {
  if (!gauges || gauges.length === 0) return null;

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
      <div className="hero-status__headline">{conf.label}</div>
      <div className="hero-status__detail">{detail}</div>
    </div>
  );
}
