import React from 'react';

const FILTERS = [
  { key: 'all',      label: 'All' },
  { key: 'flooding', label: 'Flooding' },
  { key: 'fishing',  label: 'Fishing' },
  { key: 'paddling', label: 'Paddling' },
];

// Predicates that decide whether a gauge belongs in each filter.
export const FILTER_PREDICATES = {
  all:      () => true,
  flooding: (g) => ['action', 'minor', 'moderate', 'major'].includes(g.flood_status),
  fishing:  (g) => !!g.fishing,
  paddling: (g) => !!g.recreation,
};

export default function GaugeFilter({ gauges, active, onChange }) {
  const counts = FILTERS.reduce((acc, f) => {
    acc[f.key] = gauges.filter(FILTER_PREDICATES[f.key]).length;
    return acc;
  }, {});

  return (
    <div className="gauge-filter" role="tablist" aria-label="Filter gauges">
      {FILTERS.map((f) => {
        const isActive = active === f.key;
        const isEmpty = counts[f.key] === 0 && f.key !== 'all';
        if (isEmpty) return null;
        return (
          <button
            key={f.key}
            role="tab"
            aria-selected={isActive}
            className={`gauge-filter__chip ${isActive ? 'gauge-filter__chip--active' : ''}`}
            onClick={() => onChange(f.key)}
          >
            {f.label}
            <span className="gauge-filter__count">{counts[f.key]}</span>
          </button>
        );
      })}
    </div>
  );
}
